from typing import Optional

from mini_crawler_lab import (
    FetchResult,
    FetchStrategy,
    ProfileStore,
    RenderResult,
    SiteProfile,
)


RICH_HTML = f"<html><body><p>{'useful static content ' * 20}</p></body></html>"
APP_SHELL_HTML = """
<html>
  <body>
    <div id="root"></div>
    <script src="/runtime.js"></script>
    <script src="/app.js"></script>
  </body>
</html>
"""


class FakeHttpFetcher:
    """Return a configured HTTP result and record fetch calls."""

    def __init__(self, result: FetchResult) -> None:
        self.result = result
        self.calls = []

    def fetch(self, url, headers=None):
        self.calls.append((url, headers))
        return self.result


class FakeRenderFetcher:
    """Return a configured render result and record fetch calls."""

    def __init__(self, result: RenderResult) -> None:
        self.result = result
        self.calls = []

    def fetch(self, url, headers=None):
        self.calls.append((url, headers))
        return self.result


def http_result(url: str, text: str) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        headers={"content-type": "text/html"},
        text=text,
        elapsed_ms=12.0,
        error_type=None,
    )


def render_result(
    url: str,
    html: Optional[str],
    error_type: Optional[str] = None,
) -> RenderResult:
    return RenderResult(
        url=url,
        final_url=url if error_type is None else None,
        status_code=200 if error_type is None else None,
        headers={"content-type": "text/html"} if error_type is None else {},
        html=html,
        elapsed_ms=34.0,
        error_type=error_type,
        request_count=4,
        blocked_count=1,
    )


def test_returns_http_result_when_static_html_has_enough_content() -> None:
    url = "https://example.com/article"
    http_fetcher = FakeHttpFetcher(http_result(url, RICH_HTML))
    render_fetcher = FakeRenderFetcher(render_result(url, "<p>unused</p>"))
    strategy = FetchStrategy(
        http_fetcher=http_fetcher,
        render_fetcher=render_fetcher,
    )

    result = strategy.fetch(url, headers={"x-trace-id": "123"})

    assert isinstance(result, FetchResult)
    assert result.text == RICH_HTML
    assert result.fetch_mode == "http"
    assert http_fetcher.calls == [(url, {"x-trace-id": "123"})]
    assert render_fetcher.calls == []


def test_renders_app_shell_and_normalizes_render_result() -> None:
    url = "https://example.com/app"
    rendered_html = "<html><body><h1>Rendered application</h1></body></html>"
    http_fetcher = FakeHttpFetcher(http_result(url, APP_SHELL_HTML))
    render_fetcher = FakeRenderFetcher(render_result(url, rendered_html))
    strategy = FetchStrategy(
        http_fetcher=http_fetcher,
        render_fetcher=render_fetcher,
    )

    result = strategy.fetch(url)

    assert isinstance(result, FetchResult)
    assert result.text == rendered_html
    assert result.elapsed_ms == 34.0
    assert result.fetch_mode == "render"
    assert http_fetcher.calls == [(url, None)]
    assert render_fetcher.calls == [(url, None)]


def test_profile_store_forces_render_for_matching_url_pattern() -> None:
    url = "https://example.com/products/42"
    profile_store = ProfileStore(
        [
            SiteProfile(
                domain="example.com",
                js_required_patterns=(r"/products/\d+",),
            ),
        ]
    )
    http_fetcher = FakeHttpFetcher(http_result(url, RICH_HTML))
    render_fetcher = FakeRenderFetcher(render_result(url, "<p>product</p>"))
    strategy = FetchStrategy(
        http_fetcher=http_fetcher,
        render_fetcher=render_fetcher,
        profile_store=profile_store,
    )

    result = strategy.fetch(url)

    assert result.fetch_mode == "render"
    assert len(http_fetcher.calls) == 1
    assert len(render_fetcher.calls) == 1


def test_render_policy_never_keeps_need_render_http_result() -> None:
    url = "https://example.com/app"
    profile = SiteProfile(domain="example.com", render_policy="never")
    http_fetcher = FakeHttpFetcher(http_result(url, APP_SHELL_HTML))
    render_fetcher = FakeRenderFetcher(render_result(url, "<p>unused</p>"))
    strategy = FetchStrategy(
        http_fetcher=http_fetcher,
        render_fetcher=render_fetcher,
    )

    result = strategy.fetch(url, profile=profile)

    assert result.fetch_mode == "http"
    assert result.text == APP_SHELL_HTML
    assert render_fetcher.calls == []


def test_render_failure_is_returned_as_unified_fetch_result() -> None:
    url = "https://example.com/app"
    http_fetcher = FakeHttpFetcher(http_result(url, APP_SHELL_HTML))
    render_fetcher = FakeRenderFetcher(
        render_result(url, html=None, error_type="timeout"),
    )
    strategy = FetchStrategy(
        http_fetcher=http_fetcher,
        render_fetcher=render_fetcher,
    )

    result = strategy.fetch(url)

    assert isinstance(result, FetchResult)
    assert result.fetch_mode == "render"
    assert result.text is None
    assert result.status_code is None
    assert result.error_type == "timeout"
