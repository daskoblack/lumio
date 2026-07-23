"""Espacement minimal entre appels réseau (évite les 429 de rate limit).

Un verrou asyncio sérialise les appels : même si plusieurs sections tournent
en concurrence (scripting/synthèse), les appels au fournisseur ne partent
jamais plus rapprochés que `min_interval_s`, quel que soit le nombre de
coroutines qui les demandent en même temps.
"""

from __future__ import annotations

import asyncio


class RateLimiter:
    def __init__(self, min_interval_s: float) -> None:
        self._min_interval = min_interval_s
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = asyncio.get_event_loop().time()
