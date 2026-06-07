from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Optional, Tuple


ActualFetchMode = Literal["http", "render"]


@dataclass(frozen=True)
class FetchResult:
    """Unified result returned by an HTTP or rendered fetch attempt."""

    url: str
    final_url: Optional[str]
    status_code: Optional[int]
    headers: Dict[str, str]
    text: Optional[str]
    elapsed_ms: float
    error_type: Optional[str]
    fetch_mode: ActualFetchMode = "http"


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


@dataclass(frozen=True)
class ApiDiscoveryRecord:
    """Metadata captured from a JSON response during browser rendering."""

    url: str
    status: int
    json_size: int
    top_level_keys: Tuple[str, ...]
    candidate_api: bool


@dataclass(frozen=True)
class ApiDiscoveryResult:
    """Result returned by browser-rendered API discovery."""

    url: str
    final_url: Optional[str]
    status_code: Optional[int]
    discovered_apis: Tuple[ApiDiscoveryRecord, ...]
    elapsed_ms: float
    error_type: Optional[str]
