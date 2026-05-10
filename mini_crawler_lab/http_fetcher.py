from __future__ import annotations

from time import perf_counter
from typing import Mapping, Optional

import httpx

from .fetch_result import FetchResult


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
