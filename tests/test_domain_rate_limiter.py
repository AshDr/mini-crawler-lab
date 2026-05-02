import asyncio

import pytest

from mini_crawler_lab import DomainRateLimiter


def test_domain_rate_limiter_rejects_invalid_max_rps() -> None:
    with pytest.raises(ValueError):
        DomainRateLimiter(max_rps=0)


def test_domain_rate_limiter_waits_per_domain() -> None:
    async def run() -> tuple[float, float, float]:
        limiter = DomainRateLimiter(max_rps=20)
        loop = asyncio.get_running_loop()

        await limiter.acquire("example.com")
        first_same_domain = loop.time()

        await limiter.acquire("https://example.com/page")
        second_same_domain = loop.time()

        await limiter.acquire("other.example.com")
        other_domain = loop.time()

        return first_same_domain, second_same_domain, other_domain

    first_same_domain, second_same_domain, other_domain = asyncio.run(run())

    assert second_same_domain - first_same_domain >= 0.04
    assert other_domain - second_same_domain < 0.04
