import httpx

from mini_crawler_lab import FetchResult, HttpFetcher


def test_fetch_returns_success_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="hello",
            request=request,
        )

    fetcher = HttpFetcher(transport=httpx.MockTransport(handler))

    result = fetcher.fetch("https://example.com/page")

    assert isinstance(result, FetchResult)
    assert result.url == "https://example.com/page"
    assert result.final_url == "https://example.com/page"
    assert result.status_code == 200
    assert result.headers["content-type"] == "text/plain"
    assert result.text == "hello"
    assert result.elapsed_ms >= 0
    assert result.error_type is None


def test_fetch_follows_redirects_and_reports_final_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(302, headers={"location": "/new"}, request=request)
        return httpx.Response(200, text="new page", request=request)

    fetcher = HttpFetcher(transport=httpx.MockTransport(handler))

    result = fetcher.fetch("https://example.com/old")

    assert result.status_code == 200
    assert result.final_url == "https://example.com/new"
    assert result.text == "new page"
    assert result.error_type is None


def test_fetch_uses_default_and_request_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "mini-crawler"
        assert request.headers["x-trace-id"] == "request-123"
        return httpx.Response(200, text="ok", request=request)

    fetcher = HttpFetcher(
        headers={"user-agent": "mini-crawler"},
        transport=httpx.MockTransport(handler),
    )

    result = fetcher.fetch(
        "https://example.com/",
        headers={"x-trace-id": "request-123"},
    )

    assert result.status_code == 200
    assert result.error_type is None


def test_fetch_converts_timeout_to_error_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    fetcher = HttpFetcher(timeout=0.1, transport=httpx.MockTransport(handler))

    result = fetcher.fetch("https://example.com/slow")

    assert result.status_code is None
    assert result.headers == {}
    assert result.text is None
    assert result.final_url is None
    assert result.error_type == "timeout"
    assert result.elapsed_ms >= 0


def test_fetch_converts_request_error_to_error_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    fetcher = HttpFetcher(transport=httpx.MockTransport(handler))

    result = fetcher.fetch("https://example.com/unreachable")

    assert result.status_code is None
    assert result.error_type == "request_error"


def test_fetch_converts_invalid_url_to_error_type() -> None:
    fetcher = HttpFetcher()

    result = fetcher.fetch("not a valid url")

    assert result.status_code is None
    assert result.final_url is None
    assert result.error_type == "invalid_url"
