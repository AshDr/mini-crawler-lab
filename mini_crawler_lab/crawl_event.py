from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CrawlEvent:
    url: str
    domain: str
    fetch_mode: str
    status_code: Optional[int]
    error_type: Optional[str]
    elapsed_ms: float
    content_length: Optional[int]
    timestamp: str = field(default_factory=_utc_timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
