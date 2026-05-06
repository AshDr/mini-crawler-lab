from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Optional, Tuple, Union
from urllib.parse import urlparse

from mini_crawler_lab import (
    CrawlEvent,
    DomainRateLimiter,
    EventLogger,
    HTMLParser,
    HttpFetcher,
    JsonlItemWriter,
    RobotTxtChecker,
    RobotsTxt,
    RobotsTxtFetchError,
    RobotsTxtNotFoundError,
    SQLiteUrlFrontier,
    SeenUrlStore,
    URLNormalizer,
)


URLFrontier = SQLiteUrlFrontier
RateLimiter = DomainRateLimiter

DEFAULT_USER_AGENT = "MiniCrawlerLab/0.1"


def crawl_static_site(
    seed_url: str,
    max_pages: int,
    output_dir: Optional[Union[Path, str]] = None,
    *,
    fetcher: Optional[HttpFetcher] = None,
    parser: Optional[HTMLParser] = None,
    frontier: Optional[URLFrontier] = None,
    rate_limiter: Optional[RateLimiter] = None,
    event_logger: Optional[EventLogger] = None,
    robots_checker: Optional[RobotTxtChecker] = None,
    normalizer: Optional[URLNormalizer] = None,
    item_writer: Optional[JsonlItemWriter] = None,
    same_host_only: bool = True,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Dict[str, Any]:
    """Synchronously crawl a small static site and return a run report."""
    if max_pages < 1:
        raise ValueError("max_pages must be greater than 0")

    return asyncio.run(
        _crawl_static_site(
            seed_url=seed_url,
            max_pages=max_pages,
            output_dir=output_dir,
            fetcher=fetcher,
            parser=parser,
            frontier=frontier,
            rate_limiter=rate_limiter,
            event_logger=event_logger,
            robots_checker=robots_checker,
            normalizer=normalizer,
            item_writer=item_writer,
            same_host_only=same_host_only,
            user_agent=user_agent,
        )
    )

# 处理单个host的结果
async def _crawl_static_site(
    seed_url: str,
    max_pages: int,
    output_dir: Optional[Union[Path, str]],
    *,
    fetcher: Optional[HttpFetcher],
    parser: Optional[HTMLParser],
    frontier: Optional[URLFrontier],
    rate_limiter: Optional[RateLimiter],
    event_logger: Optional[EventLogger],
    robots_checker: Optional[RobotTxtChecker],
    normalizer: Optional[URLNormalizer],
    item_writer: Optional[JsonlItemWriter],
    same_host_only: bool,
    user_agent: str,
) -> Dict[str, Any]:
    """Run the crawler loop with injectable collaborators for testing."""
    started_at = perf_counter()
    started_at_utc = _utc_now()
    output_path = Path(output_dir) if output_dir is not None else _default_output_dir()
    raw_html_dir = output_path / "raw_html"
    robots_dir = output_path / "robots"
    report_path = output_path / "daily_report.json"
    log_path = output_path / "events.jsonl"
    item_path = output_path / "items.jsonl"
    frontier_path = output_path / "frontier.sqlite"
    output_path.mkdir(parents=True, exist_ok=True)

    normalizer = normalizer or URLNormalizer(keep_trailing_slash=False)
    fetcher = fetcher or HttpFetcher(headers={"user-agent": user_agent})
    parser = parser or HTMLParser()
    frontier = frontier or URLFrontier(frontier_path, max_retry=0)
    rate_limiter = rate_limiter or RateLimiter(max_rps=1.0)
    event_logger = event_logger or EventLogger(log_path)
    robots_checker = robots_checker or RobotTxtChecker(
        headers={"user-agent": user_agent},
        storage_dir=robots_dir,
    )
    item_writer = item_writer or JsonlItemWriter(item_path)
    seen = SeenUrlStore(normalizer)
    robots_cache: Dict[str, Optional[RobotsTxt]] = {}

    normalized_seed = normalizer.normalize(seed_url)
    if not _is_http_url(normalized_seed):
        raise ValueError("seed_url must be an absolute http or https URL")

    seed_host = _host(normalized_seed)
    stats: Dict[str, Any] = {
        "seed_url": normalized_seed,
        "max_pages": max_pages,
        "pages_fetched": 0,
        "pages_saved": 0,
        "items_saved": 0,
        "links_extracted": 0,
        "links_enqueued": 0,
        "duplicates_skipped": 0,
        "non_http_skipped": 0,
        "offsite_skipped": 0,
        "robots_allowed": 0,
        "robots_blocked": 0,
        "robots_errors": 0,
        "fetch_errors": 0,
        "http_errors": 0,
    }

    seen.add(normalized_seed)
    frontier.add_url(normalized_seed)

    try:
        while stats["pages_fetched"] < max_pages:
            current_url = frontier.get_next()
            if current_url is None:
                break

            domain = _host(current_url)
            if not domain:
                frontier.mark_failed(current_url, "invalid_url")
                stats["non_http_skipped"] += 1
                continue

            is_allowed, robots_error = await _can_fetch(
                current_url,
                _origin(current_url),
                user_agent,
                robots_cache,
                robots_checker,
                rate_limiter,
            )
            if robots_error:
                stats["robots_errors"] += 1

            if not is_allowed:
                frontier.mark_failed(current_url, "robots_disallowed")
                stats["robots_blocked"] += 1
                event_logger.log(
                    CrawlEvent(
                        url=current_url,
                        domain=domain,
                        fetch_mode="robots",
                        status_code=None,
                        error_type="robots_disallowed",
                        elapsed_ms=0.0,
                        content_length=None,
                    )
                )
                continue

            stats["robots_allowed"] += 1
            await rate_limiter.acquire(domain)
            result = fetcher.fetch(current_url, headers={"user-agent": user_agent})
            content_length = len(result.text.encode("utf-8")) if result.text is not None else None
            event_logger.log(
                CrawlEvent(
                    url=current_url,
                    domain=domain,
                    fetch_mode="http",
                    status_code=result.status_code,
                    error_type=result.error_type,
                    elapsed_ms=result.elapsed_ms,
                    content_length=content_length,
                )
            )
            stats["pages_fetched"] += 1

            if result.error_type is not None:
                frontier.mark_failed(current_url, result.error_type)
                stats["fetch_errors"] += 1
                continue

            if result.status_code is None or not 200 <= result.status_code < 400:
                frontier.mark_failed(current_url, f"http_{result.status_code}")
                stats["http_errors"] += 1
                continue

            html = result.text or ""
            base_url = result.final_url or current_url
            parsed = parser.parse(html, base_url)
            html_path = _save_html(raw_html_dir, current_url, html)
            item_writer.append(
                {
                    "url": current_url,
                    "final_url": result.final_url,
                    "status_code": result.status_code,
                    "title": parsed.title,
                    "text_length": parsed.text_length,
                    "link_count": len(parsed.links),
                    "html_path": str(html_path),
                }
            )
            stats["pages_saved"] += 1
            stats["items_saved"] += 1
            stats["links_extracted"] += len(parsed.links)

            for link in parsed.links:
                normalized_link = normalizer.normalize(link, base_url)
                if not _is_http_url(normalized_link):
                    stats["non_http_skipped"] += 1
                    continue
                if same_host_only and _host(normalized_link) != seed_host:
                    stats["offsite_skipped"] += 1
                    continue
                if not seen.add(normalized_link):
                    stats["duplicates_skipped"] += 1
                    continue
                if frontier.add_url(normalized_link):
                    stats["links_enqueued"] += 1
                else:
                    stats["duplicates_skipped"] += 1
            # 当前页面的所有链接都处理完了，标记为 done
            frontier.mark_done(current_url)
    finally:
        frontier.close()

    finished_at_utc = _utc_now()
    report = {
        **stats,
        "same_host_only": same_host_only,
        "started_at": started_at_utc,
        "finished_at": finished_at_utc,
        "duration_seconds": round(perf_counter() - started_at, 6),
        "log_summary": EventLogger.summarize(log_path),
        "paths": {
            "output_dir": str(output_path),
            "raw_html_dir": str(raw_html_dir),
            "items": str(item_path),
            "events": str(log_path),
            "frontier": str(frontier_path),
            "report": str(report_path),
        },
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report


async def _can_fetch(
    url: str,
    origin: str,
    user_agent: str,
    robots_cache: Dict[str, Optional[RobotsTxt]],
    robots_checker: RobotTxtChecker,
    rate_limiter: RateLimiter,
) -> Tuple[bool, bool]:
    """Check robots.txt permission and report whether a robots fetch failed."""
    if origin not in robots_cache:
        await rate_limiter.acquire(origin)
        try:
            robots_cache[origin] = robots_checker.fetch(origin, store=True)
        except RobotsTxtNotFoundError:
            robots_cache[origin] = None
        except RobotsTxtFetchError:
            return False, True

    robots_txt = robots_cache[origin]
    return (True if robots_txt is None else robots_txt.can_fetch(user_agent, url)), False


def _save_html(raw_html_dir: Path, url: str, html: str) -> Path:
    """Save raw HTML under a deterministic URL hash filename."""
    raw_html_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    path = raw_html_dir / f"{digest}.html"
    path.write_text(html, encoding="utf-8")
    return path


def _host(url: str) -> str:
    """Return the lowercase network location for a URL."""
    return (urlparse(url).netloc or "").lower()


def _origin(url: str) -> str:
    """Return the lowercase scheme and network location for a URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def _is_http_url(url: str) -> bool:
    """Return whether a URL is absolute HTTP or HTTPS."""
    return urlparse(url).scheme in {"http", "https"} and bool(_host(url))


def _utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _default_output_dir() -> Path:
    """Return the timestamped default crawl output directory."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("data") / "crawls" / stamp


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Crawl a small static site.")
    parser.add_argument("seed_url")
    parser.add_argument("max_pages", type=int)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-rps", type=float, default=1.0)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument(
        "--allow-offsite",
        action="store_true",
        help="enqueue links outside the seed URL host",
    )
    return parser


def main() -> None:
    """Parse CLI arguments, run the crawl, and print the JSON report."""
    args = _build_arg_parser().parse_args()
    report = crawl_static_site(
        args.seed_url,
        args.max_pages,
        output_dir=args.output_dir,
        rate_limiter=RateLimiter(max_rps=args.max_rps),
        same_host_only=not args.allow_offsite,
        user_agent=args.user_agent,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
