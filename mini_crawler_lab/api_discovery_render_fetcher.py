from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Iterable, List, Mapping, Optional, Set, Tuple

from .fetch_result import ApiDiscoveryRecord, ApiDiscoveryResult
from .render_fetcher import RenderFetcher


class ApiDiscoveryRenderFetcher(RenderFetcher):
    """Render pages with Playwright and summarize JSON API responses."""

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
        candidate_keywords: Optional[Iterable[str]] = None,
    ) -> None:
        """Configure browser defaults and candidate API keyword matching."""
        super().__init__(
            timeout_ms=timeout_ms,
            headers=headers,
            browser_name=browser_name,
            headless=headless,
            wait_until=wait_until,
            block_resource_types=block_resource_types,
            browser=browser,
            playwright=playwright,
        )
        self.candidate_keywords = self._normalize_keywords(candidate_keywords)

    def fetch(
        self,
        url: str,
        headers: Optional[Mapping[str, str]] = None,
        wait_for_selector: Optional[str] = None,
        block_resource_types: Optional[Iterable[str]] = None,
        candidate_keywords: Optional[Iterable[str]] = None,
    ) -> ApiDiscoveryResult:
        """Render a URL and collect JSON response metadata from response events."""
        started_at = perf_counter()
        context = None
        request_stats = {"total": 0, "blocked": 0}
        discovered_apis: List[ApiDiscoveryRecord] = []
        keywords = (
            self.candidate_keywords
            if candidate_keywords is None
            else self._normalize_keywords(candidate_keywords)
        )

        try:
            browser = self._ensure_browser()
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
            page.on(
                "response",
                lambda response: self._record_json_response(
                    response,
                    keywords,
                    discovered_apis,
                ),
            )
            response = page.goto(
                url,
                wait_until=self.wait_until,
                timeout=self.timeout_ms,
            )

            if wait_for_selector:
                page.wait_for_selector(wait_for_selector, timeout=self.timeout_ms)

            return ApiDiscoveryResult(
                url=url,
                final_url=page.url,
                status_code=None if response is None else response.status,
                discovered_apis=tuple(discovered_apis),
                elapsed_ms=self._elapsed_ms(started_at),
                error_type=None,
            )
        except Exception as exc:
            return ApiDiscoveryResult(
                url=url,
                final_url=None,
                status_code=None,
                discovered_apis=tuple(discovered_apis),
                elapsed_ms=self._elapsed_ms(started_at),
                error_type=self._error_type(exc),
            )
        finally:
            self._close_context(context)

    @classmethod
    def _record_json_response(
        cls,
        response: Any,
        keywords: Set[str],
        discovered_apis: List[ApiDiscoveryRecord],
    ) -> None:
        """Append response metadata when a Playwright response is JSON."""
        headers = dict(getattr(response, "headers", {}) or {})
        content_type = cls._header_value(headers, "content-type").lower()

        if "application/json" not in content_type:
            return

        try:
            json_text = response.text()
        except Exception:
            return

        discovered_apis.append(
            ApiDiscoveryRecord(
                url=str(getattr(response, "url", "")),
                status=int(getattr(response, "status", 0)),
                json_size=len(json_text.encode("utf-8")),
                top_level_keys=cls._top_level_keys(json_text),
                candidate_api=cls._has_candidate_keyword(json_text, keywords),
            ),
        )

    @staticmethod
    def _header_value(headers: Mapping[str, str], name: str) -> str:
        """Return a header value using case-insensitive lookup."""
        lowered_name = name.lower()

        for header_name, header_value in headers.items():
            if header_name.lower() == lowered_name:
                return str(header_value)

        return ""

    @staticmethod
    def _top_level_keys(json_text: str) -> Tuple[str, ...]:
        """Return object keys for top-level JSON objects."""
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError:
            return ()

        if not isinstance(parsed, dict):
            return ()

        return tuple(str(key) for key in parsed.keys())

    @staticmethod
    def _has_candidate_keyword(json_text: str, keywords: Set[str]) -> bool:
        """Return whether any keyword appears in the JSON text."""
        normalized_text = json_text.lower()
        return any(keyword in normalized_text for keyword in keywords)

    @staticmethod
    def _normalize_keywords(keywords: Optional[Iterable[str]]) -> Set[str]:
        """Normalize API candidate keywords for case-insensitive matching."""
        default_keywords = ("title", "price", "name")
        return {
            str(keyword).lower()
            for keyword in (keywords or default_keywords)
            if str(keyword)
        }
