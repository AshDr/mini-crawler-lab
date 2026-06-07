import json
from pathlib import Path

import pytest

from mini_crawler_lab import FetchResult, ProfileStore
from run_crawler import load_seed_urls, main, run_crawler


class FakeFetchStrategy:
    """Return deterministic pages without making network requests."""

    def __init__(self, results):
        self.results = results
        self.calls = []
        self.closed = False

    def fetch(self, url, headers=None):
        self.calls.append((url, headers))
        return self.results[url]

    def close(self):
        self.closed = True


def make_result(url: str, html: str, fetch_mode: str) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        headers={"content-type": "text/html"},
        text=html,
        elapsed_ms=10.0,
        error_type=None,
        fetch_mode=fetch_mode,
    )


def test_run_crawler_completes_js_fallback_flow(tmp_path: Path) -> None:
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
    seeds_path = tmp_path / "seed_urls.txt"
    seeds_path.write_text(
        "# crawl target\nhttps://example.test/\nhttps://example.test/\n",
        encoding="utf-8",
    )
    report_path = tmp_path / "output" / "metrics.json"
    frontier_path = tmp_path / "output" / "frontier.sqlite"
    strategy = FakeFetchStrategy(
        {
            "https://example.test/": make_result(
                "https://example.test/",
                """
                <html><body>
                  <a href="/about?utm_source=test">About</a>
                  <a href="/">Home</a>
                  <a href="https://outside.test/">Outside</a>
                  <a href="mailto:team@example.test">Mail</a>
                </body></html>
                """,
                "render",
            ),
            "https://example.test/about": make_result(
                "https://example.test/about",
                "<html><body><p>About</p></body></html>",
                "http",
            ),
        }
    )

    report = run_crawler(
        config_path=config_path,
        seeds_path=seeds_path,
        report_path=report_path,
        frontier_path=frontier_path,
        max_pages=10,
        strategy=strategy,
        verified_at="2026-06-07",
    )

    assert [call[0] for call in strategy.calls] == [
        "https://example.test/",
        "https://example.test/about",
    ]
    assert not strategy.closed
    assert report["seeds_loaded"] == 1
    assert report["pages_attempted"] == 2
    assert report["pages_succeeded"] == 2
    assert report["fetch_modes"] == {"http": 1, "render": 1}
    assert report["links_extracted"] == 4
    assert report["links_enqueued"] == 1
    assert report["duplicates_skipped"] == 1
    assert report["offsite_skipped"] == 1
    assert report["non_http_skipped"] == 1
    assert report["profiles_updated"] == 1
    assert json.loads(report_path.read_text(encoding="utf-8")) == report

    profiles = ProfileStore.load_yaml(config_path)
    profile = profiles.require("example.test")
    assert profile.default_fetch_mode == "render"
    assert profile.last_verified == "2026-06-07"


def test_load_seed_urls_rejects_file_without_urls(tmp_path: Path) -> None:
    seeds_path = tmp_path / "seed_urls.txt"
    seeds_path.write_text("# no targets yet\n\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not contain any URLs"):
        load_seed_urls(seeds_path)


def test_main_emits_json_report(monkeypatch, capsys, tmp_path: Path) -> None:
    expected = {"pages_attempted": 3, "pages_succeeded": 2}

    def fake_run_crawler(**kwargs):
        assert kwargs["max_pages"] == 3
        return expected

    monkeypatch.setattr("run_crawler.run_crawler", fake_run_crawler)

    exit_code = main(
        [
            "--config",
            str(tmp_path / "sites.yaml"),
            "--seeds",
            str(tmp_path / "seeds.txt"),
            "--report",
            str(tmp_path / "metrics.json"),
            "--frontier",
            str(tmp_path / "frontier.sqlite"),
            "--max-pages",
            "3",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == expected
