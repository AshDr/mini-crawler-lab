from io import StringIO
from pathlib import Path

from mini_crawler_lab import FetchResult
from run_crawler import ProgressDisplay, build_parser, run_crawler


class TTYBuffer(StringIO):
    """In-memory stream that behaves like an interactive terminal."""

    def isatty(self):
        return True


class FakeFetchStrategy:
    """Return configured results and avoid external requests."""

    def __init__(self, results):
        self.results = results

    def fetch(self, url, headers=None):
        return self.results[url]


def make_result(url: str, html: str, fetch_mode: str = "http") -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        headers={"content-type": "text/html"},
        text=html,
        elapsed_ms=25.0,
        error_type=None,
        fetch_mode=fetch_mode,
    )


def test_progress_display_renders_terminal_crawl_status() -> None:
    stream = TTYBuffer()
    display = ProgressDisplay(total=10, stream=stream)
    metrics = {
        "pages_attempted": 5,
        "pages_succeeded": 4,
        "pages_failed": 1,
        "fetch_modes": {"http": 3, "render": 2},
        "urls_enqueued": 12,
        "elapsed_ms_total": 750.0,
    }

    display.update(metrics, "https://example.test/catalogue/a-book")
    display.finish(metrics)

    output = stream.getvalue()
    assert "\rCrawling [" in output
    assert "50%" in output
    assert "5/10" in output
    assert "ok=4" in output
    assert "failed=1" in output
    assert "http=3" in output
    assert "render=2" in output
    assert "queued=12" in output
    assert "avg=150ms" in output
    assert "a-book" in output
    assert output.endswith("\n")


def test_run_crawler_emits_progress_after_each_page(tmp_path: Path) -> None:
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        """
profiles:
  - domain: example.test
    default_fetch_mode: http
    max_rps: 10
    js_required_patterns:
    api_patterns:
    render_policy: auto
    last_verified: null
""",
        encoding="utf-8",
    )
    seeds_path = tmp_path / "seeds.txt"
    seeds_path.write_text("https://example.test/\n", encoding="utf-8")
    strategy = FakeFetchStrategy(
        {
            "https://example.test/": make_result(
                "https://example.test/",
                '<body><a href="/next">Next</a></body>',
            ),
            "https://example.test/next": make_result(
                "https://example.test/next",
                "<body>Done</body>",
                fetch_mode="render",
            ),
        }
    )
    events = []

    report = run_crawler(
        config_path=config_path,
        seeds_path=seeds_path,
        report_path=tmp_path / "metrics.json",
        frontier_path=tmp_path / "frontier.sqlite",
        max_pages=2,
        strategy=strategy,
        progress=lambda metrics, url: events.append(
            (metrics["pages_attempted"], url),
        ),
        verified_at="2026-06-07",
    )

    assert report["pages_attempted"] == 2
    assert events == [
        (1, "https://example.test/"),
        (2, "https://example.test/next"),
    ]


def test_cli_supports_quiet_progress_mode() -> None:
    args = build_parser().parse_args(["--quiet"])

    assert args.quiet
