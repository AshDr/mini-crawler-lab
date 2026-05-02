from __future__ import annotations

from typing import Optional, Set

from .url_normalizer import URLNormalizer


class SeenUrlStore:
    def __init__(self, normalizer: Optional[URLNormalizer] = None) -> None:
        self.normalizer = normalizer or URLNormalizer()
        self._seen: Set[str] = set()

    def add(self, url: str, base_url: Optional[str] = None) -> bool:
        normalized_url = self.normalizer.normalize(url, base_url)
        if normalized_url in self._seen:
            return False

        self._seen.add(normalized_url)
        return True

    def has_seen(self, url: str, base_url: Optional[str] = None) -> bool:
        normalized_url = self.normalizer.normalize(url, base_url)
        return normalized_url in self._seen

    def __len__(self) -> int:
        return len(self._seen)
