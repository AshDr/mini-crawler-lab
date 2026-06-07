from __future__ import annotations

import re
from dataclasses import replace
from typing import Mapping, Optional

from .fetch_result import FetchResult, RenderResult
from .http_fetcher import HttpFetcher
from .render_decision import RenderDecision, RenderDecisionEngine
from .render_fetcher import RenderFetcher
from .site_profile import ProfileStore, SiteProfile


class FetchStrategy:
    """Select HTTP or browser rendering and return a unified fetch result."""

    def __init__(
        self,
        http_fetcher: Optional[HttpFetcher] = None,
        render_fetcher: Optional[RenderFetcher] = None,
        decision_engine: Optional[RenderDecisionEngine] = None,
        profile_store: Optional[ProfileStore] = None,
    ) -> None:
        """Configure injectable fetchers, decision engine, and profile store."""
        self.http_fetcher = http_fetcher or HttpFetcher()
        self.render_fetcher = render_fetcher or RenderFetcher()
        self.decision_engine = decision_engine or RenderDecisionEngine()
        self.profile_store = profile_store

    def fetch(
        self,
        url: str,
        profile: Optional[SiteProfile] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> FetchResult:
        """Fetch through HTTP first and render only when the strategy requires it."""
        active_profile = profile or self._profile_for_url(url)
        http_result = self.http_fetcher.fetch(url, headers=headers)
        normalized_http_result = self._normalize_http_result(http_result)
        decision = self.decision_engine.decide(http_result.text or "")

        if not self._should_render(url, active_profile, decision):
            return normalized_http_result

        render_result = self.render_fetcher.fetch(url, headers=headers)
        return self._normalize_render_result(render_result)

    def close(self) -> None:
        """Release browser resources owned by the render fetcher."""
        self.render_fetcher.close()

    def _profile_for_url(self, url: str) -> Optional[SiteProfile]:
        """Look up a URL's profile when a profile store is configured."""
        if self.profile_store is None:
            return None
        return self.profile_store.get(url)

    @classmethod
    def _should_render(
        cls,
        url: str,
        profile: Optional[SiteProfile],
        decision: RenderDecision,
    ) -> bool:
        """Combine profile policy, URL rules, and HTTP quality signals."""
        if profile is not None:
            if profile.render_policy == "never":
                return False
            if profile.render_policy == "always":
                return True
            if profile.default_fetch_mode == "render":
                return True
            if cls._matches_any_pattern(url, profile.js_required_patterns):
                return True

        return decision.decision == "need_render"

    @staticmethod
    def _matches_any_pattern(url: str, patterns: tuple[str, ...]) -> bool:
        """Return whether a URL matches any configured regular expression."""
        for pattern in patterns:
            try:
                if re.search(pattern, url):
                    return True
            except re.error:
                if pattern in url:
                    return True
        return False

    @staticmethod
    def _normalize_http_result(result: FetchResult) -> FetchResult:
        """Ensure an HTTP result records the mode actually used."""
        return replace(result, fetch_mode="http")

    @staticmethod
    def _normalize_render_result(result: RenderResult) -> FetchResult:
        """Convert a browser-specific result into the common result model."""
        return FetchResult(
            url=result.url,
            final_url=result.final_url,
            status_code=result.status_code,
            headers=result.headers,
            text=result.html,
            elapsed_ms=result.elapsed_ms,
            error_type=result.error_type,
            fetch_mode="render",
        )
