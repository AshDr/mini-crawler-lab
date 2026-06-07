from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    TextIO,
    Union,
)
from urllib.parse import urlparse

from mini_crawler_lab import (
    FetchStrategy,
    HTMLParser,
    ProfileStore,
    SQLiteUrlFrontier,
    URLNormalizer,
)


DEFAULT_CONFIG_PATH = Path("configs/sites.yaml")
DEFAULT_SEEDS_PATH = Path("seed_urls.txt")
DEFAULT_REPORT_PATH = Path("data/metrics.json")
DEFAULT_FRONTIER_PATH = Path("data/frontier.sqlite")
DEFAULT_USER_AGENT = "MiniCrawlerLab/0.1"


class ProgressDisplay:
    """Render compact crawl progress on an interactive terminal."""

    def __init__(
        self,
        total: int,
        stream: TextIO = sys.stderr,
        width: int = 24,
        enabled: bool = True,
    ) -> None:
        """Configure the target stream and progress bar dimensions."""
        self.total = total
        self.stream = stream
        self.width = width
        self.enabled = enabled and stream.isatty()
        self._rendered = False

    def update(self, metrics: Mapping[str, Any], url: str) -> None:
        """Refresh the terminal line with the latest crawl counters."""
        if not self.enabled:
            return

        attempted = int(metrics["pages_attempted"])
        succeeded = int(metrics["pages_succeeded"])
        failed = int(metrics["pages_failed"])
        fetch_modes = metrics["fetch_modes"]
        completed_width = min(
            self.width,
            int(self.width * attempted / self.total),
        )
        bar = "#" * completed_width + "-" * (self.width - completed_width)
        percentage = min(100, int(100 * attempted / self.total))
        average_ms = (
            float(metrics["elapsed_ms_total"]) / attempted if attempted else 0.0
        )
        current_url = self._shorten_url(url)
        line = (
            f"\rCrawling [{bar}] {percentage:3d}% {attempted}/{self.total} "
            f"ok={succeeded} failed={failed} "
            f"http={fetch_modes['http']} render={fetch_modes['render']} "
            f"queued={metrics['urls_enqueued']} avg={average_ms:.0f}ms "
            f"{current_url}"
        )
        self.stream.write(line)
        self.stream.flush()
        self._rendered = True

    def finish(self, metrics: Mapping[str, Any]) -> None:
        """End the in-place progress line after the crawl completes."""
        if not self.enabled or not self._rendered:
            return
        self.stream.write("\n")
        self.stream.flush()

    @staticmethod
    def _shorten_url(url: str, limit: int = 48) -> str:
        """Keep the changing URL compact enough for a terminal line."""
        sanitized = "".join(
            character if character.isprintable() else " "
            for character in url
        )
        if len(sanitized) <= limit:
            return sanitized
        return f"...{sanitized[-(limit - 3):]}"


def load_seed_urls(
    path: Union[str, Path],
    normalizer: Optional[URLNormalizer] = None,
) -> List[str]:
    """Load, validate, normalize, and deduplicate seed URLs."""
    seed_path = Path(path)
    active_normalizer = normalizer or URLNormalizer(keep_trailing_slash=False)
    seeds: List[str] = []
    seen: Set[str] = set()

    for line_number, raw_line in enumerate(
        seed_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue

        normalized = active_normalizer.normalize(value)
        if not _is_http_url(normalized):
            raise ValueError(
                f"{seed_path}:{line_number} is not an absolute HTTP(S) URL",
            )
        if normalized in seen:
            continue

        seen.add(normalized)
        seeds.append(normalized)

    if not seeds:
        raise ValueError(f"{seed_path} does not contain any URLs")

    return seeds


def run_crawler(
    config_path: Union[str, Path] = DEFAULT_CONFIG_PATH,
    seeds_path: Union[str, Path] = DEFAULT_SEEDS_PATH,
    report_path: Union[str, Path] = DEFAULT_REPORT_PATH,
    frontier_path: Union[str, Path] = DEFAULT_FRONTIER_PATH,
    max_pages: int = 100,
    user_agent: str = DEFAULT_USER_AGENT,
    *,
    strategy: Optional[FetchStrategy] = None,
    parser: Optional[HTMLParser] = None,
    normalizer: Optional[URLNormalizer] = None,
    frontier: Optional[SQLiteUrlFrontier] = None,
    verified_at: Optional[str] = None,
    progress: Optional[Callable[[Mapping[str, Any], str], None]] = None,
) -> Dict[str, Any]:
    """Run the bounded crawler and persist learned profiles and metrics."""
    if max_pages < 1:
        raise ValueError("max_pages must be greater than 0")

    started_at = datetime.now(timezone.utc)
    started_clock = perf_counter()
    config_file = Path(config_path)
    report_file = Path(report_path)
    frontier_file = Path(frontier_path)
    active_normalizer = normalizer or URLNormalizer(keep_trailing_slash=False)
    active_parser = parser or HTMLParser()
    profile_store = ProfileStore.load_yaml(config_file)
    seeds = load_seed_urls(seeds_path, active_normalizer)
    allowed_domains = {_host(seed) for seed in seeds}

    report_file.parent.mkdir(parents=True, exist_ok=True)
    frontier_file.parent.mkdir(parents=True, exist_ok=True)

    owns_frontier = frontier is None
    active_frontier = frontier or SQLiteUrlFrontier(frontier_file, max_retry=0)
    owns_strategy = strategy is None
    active_strategy = strategy or FetchStrategy(profile_store=profile_store)
    metrics = _new_metrics(
        config_file=config_file,
        seeds_file=Path(seeds_path),
        report_file=report_file,
        frontier_file=frontier_file,
        max_pages=max_pages,
        seeds_loaded=len(seeds),
        started_at=started_at,
    )
    successful_domains: Set[str] = set()
    rendered_domains: Set[str] = set()

    try:
        for seed in seeds:
            if active_frontier.add_url(seed):
                metrics["urls_enqueued"] += 1

        while metrics["pages_attempted"] < max_pages:
            url = active_frontier.get_next()
            if url is None:
                break

            result = active_strategy.fetch(
                url,
                headers={"user-agent": user_agent},
            )
            metrics["pages_attempted"] += 1
            metrics["fetch_modes"][result.fetch_mode] += 1
            metrics["elapsed_ms_total"] += result.elapsed_ms
            _increment(metrics["status_codes"], result.status_code)

            failure = _fetch_failure(result.error_type, result.status_code)
            if failure is not None:
                active_frontier.mark_failed(url, failure)
                metrics["pages_failed"] += 1
                _increment(metrics["errors"], failure)
                if progress is not None:
                    progress(metrics, url)
                continue

            active_frontier.mark_done(url)
            metrics["pages_succeeded"] += 1
            domain = _host(result.final_url or url)
            successful_domains.add(domain)
            if result.fetch_mode == "render":
                rendered_domains.add(domain)

            parsed = active_parser.parse(result.text or "", result.final_url or url)
            metrics["links_extracted"] += len(parsed.links)
            _enqueue_links(
                parsed.links,
                base_url=result.final_url or url,
                allowed_domains=allowed_domains,
                normalizer=active_normalizer,
                frontier=active_frontier,
                metrics=metrics,
            )
            if progress is not None:
                progress(metrics, url)

        metrics["profiles_updated"] = _update_profiles(
            profile_store,
            successful_domains,
            rendered_domains,
            verified_at or datetime.now(timezone.utc).date().isoformat(),
        )
        profile_store.save()
    finally:
        try:
            if owns_strategy:
                active_strategy.close()
        finally:
            if owns_frontier:
                active_frontier.close()

    finished_at = datetime.now(timezone.utc)
    metrics["finished_at"] = finished_at.isoformat()
    metrics["duration_ms"] = (perf_counter() - started_clock) * 1000
    metrics["average_fetch_ms"] = (
        metrics["elapsed_ms_total"] / metrics["pages_attempted"]
        if metrics["pages_attempted"]
        else 0.0
    )
    _write_json(report_file, metrics)
    return metrics


def _new_metrics(
    *,
    config_file: Path,
    seeds_file: Path,
    report_file: Path,
    frontier_file: Path,
    max_pages: int,
    seeds_loaded: int,
    started_at: datetime,
) -> Dict[str, Any]:
    """Create the stable metrics report shape."""
    return {
        "config_path": str(config_file),
        "seeds_path": str(seeds_file),
        "report_path": str(report_file),
        "frontier_path": str(frontier_file),
        "max_pages": max_pages,
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "duration_ms": 0.0,
        "seeds_loaded": seeds_loaded,
        "urls_enqueued": 0,
        "pages_attempted": 0,
        "pages_succeeded": 0,
        "pages_failed": 0,
        "fetch_modes": {"http": 0, "render": 0},
        "status_codes": {},
        "errors": {},
        "links_extracted": 0,
        "links_enqueued": 0,
        "duplicates_skipped": 0,
        "offsite_skipped": 0,
        "non_http_skipped": 0,
        "profiles_updated": 0,
        "elapsed_ms_total": 0.0,
        "average_fetch_ms": 0.0,
    }


def _enqueue_links(
    links: Iterable[str],
    *,
    base_url: str,
    allowed_domains: Set[str],
    normalizer: URLNormalizer,
    frontier: SQLiteUrlFrontier,
    metrics: Dict[str, Any],
) -> None:
    """Normalize and enqueue crawlable links while updating counters."""
    for link in links:
        normalized = normalizer.normalize(link, base_url)
        if not _is_http_url(normalized):
            metrics["non_http_skipped"] += 1
            continue
        if _host(normalized) not in allowed_domains:
            metrics["offsite_skipped"] += 1
            continue
        if frontier.add_url(normalized):
            metrics["urls_enqueued"] += 1
            metrics["links_enqueued"] += 1
        else:
            metrics["duplicates_skipped"] += 1


def _update_profiles(
    store: ProfileStore,
    successful_domains: Set[str],
    rendered_domains: Set[str],
    verified_at: str,
) -> int:
    """Persist verification time and learned render preference per domain."""
    for domain in sorted(successful_domains):
        changes: Dict[str, Any] = {"last_verified": verified_at}
        if domain in rendered_domains:
            changes["default_fetch_mode"] = "render"
        store.update(domain, save=False, **changes)
    return len(successful_domains)


def _fetch_failure(
    error_type: Optional[str],
    status_code: Optional[int],
) -> Optional[str]:
    """Return a stable failure label for unsuccessful fetch results."""
    if error_type is not None:
        return error_type
    if status_code is None:
        return "missing_status"
    if not 200 <= status_code < 400:
        return f"http_{status_code}"
    return None


def _increment(counters: Dict[str, int], value: Any) -> None:
    """Increment a JSON-safe string counter when a value is present."""
    if value is None:
        return
    key = str(value)
    counters[key] = counters.get(key, 0) + 1


def _is_http_url(url: str) -> bool:
    """Return whether a URL is absolute HTTP or HTTPS."""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _host(url: str) -> str:
    """Return a normalized URL hostname."""
    return (urlparse(url).hostname or "").lower()


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    """Atomically write a formatted JSON report."""
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the crawler."""
    parser = argparse.ArgumentParser(
        description="Run a bounded mini crawler with JavaScript fallback.",
        epilog=(
            "Example: uv run python run_crawler.py --max-pages 25 "
            "--report data/metrics.json"
        ),
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="site profile YAML path (default: %(default)s)",
    )
    parser.add_argument(
        "--seeds",
        default=str(DEFAULT_SEEDS_PATH),
        help="seed URL file path (default: %(default)s)",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT_PATH),
        help="metrics JSON output path (default: %(default)s)",
    )
    parser.add_argument(
        "--frontier",
        default=str(DEFAULT_FRONTIER_PATH),
        help="SQLite frontier path (default: %(default)s)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="maximum pages to fetch (default: %(default)s)",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="HTTP user agent (default: %(default)s)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="disable interactive progress output",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI and return a process exit code."""
    args = build_parser().parse_args(argv)
    progress_display = ProgressDisplay(
        total=args.max_pages,
        enabled=not args.quiet,
    )

    try:
        report = run_crawler(
            config_path=args.config,
            seeds_path=args.seeds,
            report_path=args.report,
            frontier_path=args.frontier,
            max_pages=args.max_pages,
            user_agent=args.user_agent,
            progress=progress_display.update if progress_display.enabled else None,
        )
    except (OSError, ValueError) as exc:
        progress_display.finish({})
        print(f"run_crawler: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        progress_display.finish({})
        print("run_crawler: interrupted", file=sys.stderr)
        return 130

    progress_display.finish(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
