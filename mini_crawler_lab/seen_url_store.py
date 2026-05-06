from __future__ import annotations

from typing import Optional, Set

from .url_normalizer import URLNormalizer


class SeenUrlStore:
    """In-memory set of normalized URLs already observed by a crawl."""

    def __init__(self, normalizer: Optional[URLNormalizer] = None) -> None:
        """Create the store with an optional custom URL normalizer."""
        self.normalizer = normalizer or URLNormalizer()
        self._seen: Set[str] = set()

    def add(self, url: str, base_url: Optional[str] = None) -> bool:
        """Add a normalized URL and report whether it was unseen."""
        normalized_url = self.normalizer.normalize(url, base_url)
        if normalized_url in self._seen:
            return False

        self._seen.add(normalized_url)
        return True

    def has_seen(self, url: str, base_url: Optional[str] = None) -> bool:
        """Return whether the normalized URL has already been stored."""
        normalized_url = self.normalizer.normalize(url, base_url)
        return normalized_url in self._seen

    def __len__(self) -> int:
        """Return the number of unique normalized URLs stored."""
        return len(self._seen)
