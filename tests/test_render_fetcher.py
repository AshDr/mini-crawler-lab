from typing import Dict, List, Optional

from mini_crawler_lab import RenderFetcher, RenderResult


class FakeResponse:
    def __init__(self, status: int = 200, headers: Optional[Dict[str, str]] = None):
        self.status = status
        self.headers = dict(headers or {})


class FakePage:
    def __init__(
        self,
        final_url: str = "https://example.com/",
        html: str = "<html></html>",
        response: Optional[FakeResponse] = None,
        error: Optional[Exception] = None,
    ):
        self.url = "about:blank"
        self.final_url = final_url
        self.html = html
        self.response = response
        self.error = error
        self.goto_calls = []
        self.wait_calls = []

    def goto(self, url: str, wait_until: str, timeout: float):
        self.goto_calls.append(
            {
                "url": url,
                "wait_until": wait_until,
                "timeout": timeout,
            },
        )

        if self.error is not None:
            raise self.error

        self.url = self.final_url
        return self.response

    def wait_for_selector(self, selector: str, timeout: float) -> None:
        self.wait_calls.append({"selector": selector, "timeout": timeout})

    def content(self) -> str:
        return self.html


class FakeContext:
    def __init__(self, page: FakePage, extra_http_headers: Dict[str, str]):
        self.page = page
        self.extra_http_headers = extra_http_headers
        self.closed = False

    def new_page(self) -> FakePage:
        return self.page

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, pages: List[FakePage]):
        self.pages = pages
        self.contexts: List[FakeContext] = []
        self.close_count = 0

    def new_context(self, extra_http_headers: Dict[str, str]) -> FakeContext:
        context = FakeContext(self.pages[len(self.contexts)], extra_http_headers)
        self.contexts.append(context)
        return context

    def close(self) -> None:
        self.close_count += 1


class FakePlaywright:
    def __init__(self):
        self.stop_count = 0

    def stop(self) -> None:
        self.stop_count += 1


def test_render_fetcher_reuses_browser_and_creates_context_per_fetch() -> None:
    browser = FakeBrowser(
        [
            FakePage(
                final_url="https://example.com/one",
                html="<html>one</html>",
                response=FakeResponse(200, {"content-type": "text/html"}),
            ),
            FakePage(
                final_url="https://example.com/two",
                html="<html>two</html>",
                response=FakeResponse(201, {"x-page": "two"}),
            ),
        ],
    )
    fetcher = RenderFetcher(
        headers={"user-agent": "mini-crawler"},
        browser=browser,
    )

    result_one = fetcher.fetch(
        "https://example.com/one",
        headers={"x-trace-id": "request-1"},
    )
    result_two = fetcher.fetch("https://example.com/two")

    assert isinstance(result_one, RenderResult)
    assert result_one.final_url == "https://example.com/one"
    assert result_one.status_code == 200
    assert result_one.headers["content-type"] == "text/html"
    assert result_one.text == "<html>one</html>"
    assert result_one.error_type is None
    assert result_one.elapsed_ms >= 0
    assert result_two.final_url == "https://example.com/two"
    assert result_two.status_code == 201
    assert result_two.text == "<html>two</html>"
    assert len(browser.contexts) == 2
    assert browser.contexts[0] is not browser.contexts[1]
    assert browser.contexts[0].closed
    assert browser.contexts[1].closed
    assert browser.contexts[0].extra_http_headers == {
        "user-agent": "mini-crawler",
        "x-trace-id": "request-1",
    }


def test_render_fetcher_waits_for_selector() -> None:
    page = FakePage(response=FakeResponse())
    fetcher = RenderFetcher(timeout_ms=2500, browser=FakeBrowser([page]))

    result = fetcher.fetch("https://example.com/", wait_for_selector="#ready")

    assert result.error_type is None
    assert page.wait_calls == [{"selector": "#ready", "timeout": 2500}]


def test_render_fetcher_returns_error_type_and_closes_context() -> None:
    page = FakePage(error=TimeoutError("Timeout 2500ms exceeded"))
    browser = FakeBrowser([page])
    fetcher = RenderFetcher(timeout_ms=2500, browser=browser)

    result = fetcher.fetch("https://example.com/slow")

    assert result.status_code is None
    assert result.final_url is None
    assert result.headers == {}
    assert result.text is None
    assert result.error_type == "timeout"
    assert result.elapsed_ms >= 0
    assert browser.contexts[0].closed


def test_render_fetcher_reports_missing_playwright_dependency() -> None:
    result = RenderFetcher._error_type(ModuleNotFoundError(name="playwright"))

    assert result == "playwright_not_installed"


def test_render_fetcher_close_closes_browser_and_playwright_once() -> None:
    browser = FakeBrowser([])
    playwright = FakePlaywright()
    fetcher = RenderFetcher(browser=browser, playwright=playwright)

    fetcher.close()
    fetcher.close()

    assert browser.close_count == 1
    assert playwright.stop_count == 1
