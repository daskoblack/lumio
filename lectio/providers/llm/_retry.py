"""Logique d'appel partagée par les fournisseurs LLM (espacement + retry borné).

Factorisée ici car identique pour tous les fournisseurs : seule la fonction
d'appel change. Évite de dupliquer la gestion des 429 dans chaque provider.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from ...core.exceptions import LLMError
from ...core.rate_limiter import RateLimiter
from .errors import QuotaExhaustedError, is_auth_error, is_quota_exhausted, retry_delay_s


async def call_with_retry(
    call: Callable[[], Awaitable[object]],
    rate_limiter: RateLimiter,
    provider_label: str,
) -> object:
    """Appelle `call()` en respectant l'espacement, avec UN retry sur 429 court.

    Lève QuotaExhaustedError (et non LLMError) si le plafond ne se libérera
    pas rapidement : la chaîne de repli peut alors changer de fournisseur au
    lieu d'attendre plusieurs minutes au milieu d'une génération.
    """
    await rate_limiter.acquire()
    try:
        return await call()
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if is_quota_exhausted(message) or is_auth_error(message):
            raise QuotaExhaustedError(f"{provider_label} indisponible : {message}") from exc

        delay = retry_delay_s(message)
        if "429" not in message or delay is None:
            raise LLMError(f"Appel {provider_label} échoué : {message}") from exc

        # 429 court (plafond par minute) : on patiente le délai indiqué, une fois.
        await asyncio.sleep(delay + 0.5)
        await rate_limiter.acquire()
        try:
            return await call()
        except Exception as exc2:  # noqa: BLE001
            message2 = str(exc2)
            if is_quota_exhausted(message2) or is_auth_error(message2):
                raise QuotaExhaustedError(
                    f"{provider_label} indisponible : {message2}"
                ) from exc2
            raise LLMError(f"Appel {provider_label} échoué (après retry) : {message2}") from exc2
