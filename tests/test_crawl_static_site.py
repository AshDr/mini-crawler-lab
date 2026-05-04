import json
from pathlib import Path

import httpx
import pytest

from crawl_static_site import crawl_static_site
from mini_crawler_lab import DomainRateLimiter, HttpFetcher, RobotTxtChecker


def test_crawl_static_site_runs_full_static_site_flow(tmp_path: Path) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == "http://example.test/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: *\nDisallow: /blocked\n",
                request=request,
            )
        if str(request.url) == "http://example.test/":
            return httpx.Response(
                200,
                text="""
                <html>
                  <head><title>Home</title></head>
                  <body>
                    <a href="/about">About</a>
                    <a href="/about?utm_source=news">Duplicate About</a>
                    <a href="/blocked">Blocked</a>
                    <a href="https://other.test/">Offsite</a>
                    <a href="mailto:hello@example.test">Mail</a>
                  </body>
                </html>
                """,
                request=request,
            )
        if str(request.url) == "http://example.test/about":
            return httpx.Response(
                200,
                text="""
                <html>
                  <head><title>About</title></head>
                  <body><a href="/">Home</a></body>
                </html>
                """,
                request=request,
            )
        raise AssertionError(f"unexpected URL: {request.url}")

    transport = httpx.MockTransport(handler)
    output_dir = tmp_path / "crawl"

    report = crawl_static_site(
        "HTTP://Example.Test/",
        5,
        output_dir=output_dir,
        fetcher=HttpFetcher(transport=transport),
        robots_checker=RobotTxtChecker(
            transport=transport,
            storage_dir=output_dir / "robots",
        ),
        rate_limiter=DomainRateLimiter(max_rps=1000000),
    )

    assert requests.count("http://example.test/robots.txt") == 1
    assert "http://example.test/" in requests
    assert "http://example.test/about" in requests
    assert "http://example.test/blocked" not in requests

    assert report["seed_url"] == "http://example.test/"
    assert report["pages_fetched"] == 2
    assert report["pages_saved"] == 2
    assert report["items_saved"] == 2
    assert report["links_enqueued"] == 2
    assert report["duplicates_skipped"] == 2
    assert report["offsite_skipped"] == 1
    assert report["non_http_skipped"] == 1
    assert report["robots_allowed"] == 2
    assert report["robots_blocked"] == 1
    assert report["log_summary"]["total"] == 3
    assert report["log_summary"]["successful"] == 2

    items = [
        json.loads(line)
        for line in (output_dir / "items.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [item["title"] for item in items] == ["Home", "About"]
    assert all(Path(item["html_path"]).exists() for item in items)

    daily_report = json.loads((output_dir / "daily_report.json").read_text(encoding="utf-8"))
    assert daily_report["pages_saved"] == 2
    assert (output_dir / "robots" / "example.test_robots.json").exists()


def test_crawl_static_site_requires_absolute_http_seed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="seed_url"):
        crawl_static_site("/relative", 1, output_dir=tmp_path)
