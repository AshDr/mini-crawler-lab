from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Dict, Iterable, Mapping, Optional, Set

import httpx


@dataclass(frozen=True)
class FetchResult:
    """Result returned by an HTTP fetch attempt."""

    url: str
    final_url: Optional[str]
    status_code: Optional[int]
    headers: Dict[str, str]
    text: Optional[str]
    elapsed_ms: float
    error_type: Optional[str]


@dataclass(frozen=True)
class RenderResult:
    """Result returned by a browser-rendered fetch attempt."""

    url: str
    final_url: Optional[str]
    status_code: Optional[int]
    headers: Dict[str, str]
    html: Optional[str]
    elapsed_ms: float
    error_type: Optional[str]
    request_count: int = 0
    blocked_count: int = 0

    @property
    def text(self) -> Optional[str]:
        """Backward-compatible alias for rendered HTML."""
        return self.html


class HttpFetcher:
    """Small synchronous HTTP client wrapper used by the crawler."""

    def __init__(
        self,
        timeout: float = 10.0,
        headers: Optional[Mapping[str, str]] = None,
        follow_redirects: bool = True,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        """Configure request defaults and an optional test transport."""
        self.timeout = timeout
        self.headers = dict(headers or {})
        self.follow_redirects = follow_redirects
        self.transport = transport

    def fetch(
        self,
        url: str,
        headers: Optional[Mapping[str, str]] = None,
    ) -> FetchResult:
        """Fetch a URL and convert success or failure into a FetchResult."""
        started_at = perf_counter()
        request_headers = dict(headers or {})

        try:
            with httpx.Client(
                timeout=self.timeout,
                headers=self.headers,
                follow_redirects=self.follow_redirects,
                transport=self.transport,
            ) as client:
                response = client.get(url, headers=request_headers)

            return FetchResult(
                url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                headers=dict(response.headers),
                text=response.text,
                elapsed_ms=self._elapsed_ms(started_at),
                error_type=None,
            )
        except Exception as exc:
            return FetchResult(
                url=url,
                final_url=None,
                status_code=None,
                headers={},
                text=None,
                elapsed_ms=self._elapsed_ms(started_at),
                error_type=self._error_type(exc),
            )

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        """Return elapsed wall-clock time in milliseconds."""
        return (perf_counter() - started_at) * 1000

    @staticmethod
    def _error_type(exc: Exception) -> str:
        """Map httpx exceptions to stable crawler error labels."""
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, (httpx.InvalidURL, httpx.UnsupportedProtocol)):
            return "invalid_url"
        if isinstance(exc, httpx.TooManyRedirects):
            return "too_many_redirects"
        if isinstance(exc, httpx.RequestError):
            return "request_error"
        return "unknown_error"


class RenderFetcher:
    """Synchronous Playwright fetcher that reuses one browser instance."""

    def __init__(
        self,
        timeout_ms: float = 10000,
        headers: Optional[Mapping[str, str]] = None,
        browser_name: str = "chromium",
        headless: bool = True,
        wait_until: str = "networkidle",
        block_resource_types: Optional[Iterable[str]] = None,
        browser: Optional[Any] = None,
        playwright: Optional[Any] = None,
    ) -> None:
        """Configure browser defaults and optional injected test doubles."""
        self.timeout_ms = timeout_ms
        self.headers = dict(headers or {})
        self.browser_name = browser_name
        self.headless = headless
        self.wait_until = wait_until
        self.block_resource_types = self._normalize_resource_types(block_resource_types)
        self._browser = browser
        self._playwright = playwright

    def fetch(
        self,
        url: str,
        headers: Optional[Mapping[str, str]] = None,
        wait_for_selector: Optional[str] = None,
        block_resource_types: Optional[Iterable[str]] = None,
    ) -> RenderResult:
        """Render a URL in a fresh browser context and return the page HTML."""
        started_at = perf_counter()
        context = None
        request_stats = {"total": 0, "blocked": 0}

        try:
            # Get a PlayWright browser instance, starting Playwright if needed, and reuse it across fetches
            browser = self._ensure_browser()
            # Use a new browser context for each fetch to isolate cookies and other state
            context = browser.new_context(
                extra_http_headers=self._headers_for_request(headers),
            )
            active_block_types = (
                self.block_resource_types
                if block_resource_types is None
                else self._normalize_resource_types(block_resource_types)
            )
            self._install_request_route(context, active_block_types, request_stats)
            page = context.new_page()
            response = page.goto(
                url,
                wait_until=self.wait_until,
                timeout=self.timeout_ms,
            )

            if wait_for_selector:
                page.wait_for_selector(wait_for_selector, timeout=self.timeout_ms)

            return RenderResult(
                url=url,
                final_url=page.url,
                status_code=None if response is None else response.status,
                headers={} if response is None else dict(response.headers),
                html=page.content(),
                elapsed_ms=self._elapsed_ms(started_at),
                error_type=None,
                request_count=request_stats["total"],
                blocked_count=request_stats["blocked"],
            )
        except Exception as exc:
            return RenderResult(
                url=url,
                final_url=None,
                status_code=None,
                headers={},
                html=None,
                elapsed_ms=self._elapsed_ms(started_at),
                error_type=self._error_type(exc),
                request_count=request_stats["total"],
                blocked_count=request_stats["blocked"],
            )
        finally:
            self._close_context(context)

    def close(self) -> None:
        """Close the reused browser and stop Playwright if it was started."""
        browser = self._browser
        playwright = self._playwright
        self._browser = None
        self._playwright = None

        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()

    def _ensure_browser(self) -> Any:
        """Start Playwright lazily and reuse the browser across fetches."""
        if self._browser is not None:
            return self._browser

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        launcher = getattr(self._playwright, self.browser_name)
        self._browser = launcher.launch(headless=self.headless)
        return self._browser

    def _headers_for_request(
        self,
        headers: Optional[Mapping[str, str]],
    ) -> Dict[str, str]:
        """Merge default headers with per-request headers."""
        request_headers = dict(self.headers)
        request_headers.update(headers or {})
        return request_headers

    @classmethod
    def _normalize_resource_types(
        cls,
        resource_types: Optional[Iterable[str]],
    ) -> Set[str]:
        """Normalize Playwright resource type names for route matching."""
        return {resource_type.lower() for resource_type in resource_types or ()}

    @classmethod
    def _install_request_route(
        cls,
        context: Any,
        block_resource_types: Set[str],
        request_stats: Dict[str, int],
    ) -> None:
        """Count all routed requests and abort blocked resource types."""

        def handle_route(route: Any) -> None:
            request_stats["total"] += 1
            resource_type = cls._resource_type_for_route(route)

            if resource_type in block_resource_types:
                request_stats["blocked"] += 1
                route.abort()
                return

            route.continue_()

        context.route("**/*", handle_route)

    @staticmethod
    def _resource_type_for_route(route: Any) -> str:
        """Read Playwright's request.resource_type from a route object."""
        request = getattr(route, "request", None)
        resource_type = getattr(request, "resource_type", "")

        if callable(resource_type):
            resource_type = resource_type()

        return str(resource_type).lower()

    @staticmethod
    def _close_context(context: Optional[Any]) -> None:
        """Close a browser context without hiding the fetch result."""
        if context is None:
            return

        try:
            context.close()
        except Exception:
            pass

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        """Return elapsed wall-clock time in milliseconds."""
        return (perf_counter() - started_at) * 1000

    @staticmethod
    def _error_type(exc: Exception) -> str:
        """Map Playwright exceptions to stable crawler error labels."""
        exc_name = type(exc).__name__.lower()
        message = str(exc).lower()

        if isinstance(exc, ModuleNotFoundError) and exc.name == "playwright":
            return "playwright_not_installed"
        if "timeout" in exc_name or "timeout" in message:
            return "timeout"
        if "invalid url" in message or "unsupported url protocol" in message:
            return "invalid_url"
        if "closed" in message:
            return "browser_closed"
        if "playwright" in type(exc).__module__:
            return "browser_error"
        return "unknown_error"
