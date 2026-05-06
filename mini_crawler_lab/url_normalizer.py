from __future__ import annotations

from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlunparse, urlparse


TRACKING_QUERY_KEYS = {"fbclid", "gclid"}


class URLNormalizer:
    """Canonicalize URLs before duplicate checks and frontier enqueueing."""

    def __init__(self, keep_trailing_slash: bool = True) -> None:
        """Configure whether non-root trailing slashes are preserved."""
        self.keep_trailing_slash = keep_trailing_slash

    def normalize(self, url: str, base_url: Optional[str] = None) -> str:
        """Resolve and normalize a URL while removing fragments."""
        absolute_url = urljoin(base_url or "", url)
        parsed = urlparse(absolute_url)

        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = self._normalize_path(parsed.path)
        query = self._normalize_query(parsed.query)

        return urlunparse((scheme, netloc, path, parsed.params, query, ""))

    def _normalize_path(self, path: str) -> str:
        """Apply trailing-slash policy to the parsed URL path."""
        if self.keep_trailing_slash or path == "/":
            return path
        return path.rstrip("/")

    @staticmethod
    def _normalize_query(query: str) -> str:
        """Remove tracking query parameters and sort the rest."""
        params = [
            (key, value)
            for key, value in parse_qsl(query, keep_blank_values=True)
            if not URLNormalizer._is_tracking_query_key(key)
        ]
        params.sort()
        return urlencode(params)

    @staticmethod
    def _is_tracking_query_key(key: str) -> bool:
        """Return whether a query parameter is used for tracking."""
        normalized_key = key.lower()
        return normalized_key.startswith("utm_") or normalized_key in TRACKING_QUERY_KEYS
