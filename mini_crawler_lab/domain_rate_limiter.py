from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict
from urllib.parse import urlparse


@dataclass
class _DomainState:
    """Mutable scheduling state for a single domain."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_available_at: float = 0.0


class DomainRateLimiter:
    """Async per-domain rate limiter for crawler requests."""

    def __init__(self, max_rps: float) -> None:
        """Set the maximum request rate allowed for each domain."""
        if max_rps <= 0:
            raise ValueError("max_rps must be greater than 0")
        self.max_rps = max_rps
        self._interval = 1.0 / max_rps
        self._states: Dict[str, _DomainState] = {}

    async def acquire(self, domain: str) -> None:
        """Wait until the next request slot is available for a domain."""
        key = self._domain_key(domain)
        state = self._states.setdefault(key, _DomainState())
        loop = asyncio.get_running_loop()

        async with state.lock:
            now = loop.time()
            wait_for = max(0.0, state.next_available_at - now)
            state.next_available_at = max(now, state.next_available_at) + self._interval

        if wait_for > 0:
            await asyncio.sleep(wait_for)

    @staticmethod
    def _domain_key(domain: str) -> str:
        """Normalize a host or URL into a stable lowercase domain key."""
        parsed = urlparse(domain if "://" in domain else f"https://{domain}")
        return (parsed.hostname or parsed.netloc or parsed.path).lower()


async def demo() -> None:
    """Run a tiny manual demonstration of rate limiting behavior."""
    limiter = DomainRateLimiter(max_rps=2)

    for domain in ["example.com", "example.com", "docs.example.com"]:
        await limiter.acquire(domain)
        print(f"request allowed for {domain}")
