from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, Iterable, Mapping, Optional, Set

from .fetch_result import RenderResult


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
            # Start Playwright lazily and reuse the browser across fetches.
            browser = self._ensure_browser()
            # Use a fresh context for every fetch to isolate cookies and storage.
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
