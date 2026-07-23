"""Test de l'espacement minimal entre appels (évite les 429 Groq)."""

import asyncio

import pytest

from lectio.core.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_spaces_out_calls():
    limiter = RateLimiter(min_interval_s=0.05)
    loop = asyncio.get_event_loop()

    start = loop.time()
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = loop.time() - start

    # 3 appels espacés d'au moins 0.05s -> au moins 0.10s entre le 1er et le 3e.
    assert elapsed >= 0.10


@pytest.mark.asyncio
async def test_rate_limiter_serializes_concurrent_callers():
    """Même appelés en concurrence (gather), les appels restent espacés."""
    limiter = RateLimiter(min_interval_s=0.05)
    loop = asyncio.get_event_loop()
    call_times: list[float] = []

    async def _call():
        await limiter.acquire()
        call_times.append(loop.time())

    await asyncio.gather(*(_call() for _ in range(4)))

    call_times.sort()
    gaps = [b - a for a, b in zip(call_times, call_times[1:])]
    assert all(gap >= 0.045 for gap in gaps)  # tolérance légère pour le scheduling
