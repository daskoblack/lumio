"""Distinction entre « attends un peu » et « quota épuisé ».

Un 429 par MINUTE se règle en patientant quelques secondes. Un 429 par JOUR
(quota quotidien épuisé) ne se règle pas en attendant : patienter bloquerait
la génération pendant des heures. Le second cas doit faire basculer la
`LLMChain` vers le fournisseur/modèle suivant, pas attendre.
"""

from __future__ import annotations

import re

from ...core.exceptions import LLMError

# Au-delà de ce délai, attendre n'a plus de sens pendant une génération :
# on considère le fournisseur comme épuisé et on passe au suivant.
_MAX_SENSIBLE_WAIT_S = 90.0

_RETRY_AFTER_RE = re.compile(r"try again in (\d+(?:\.\d+)?)(?:m(\d+(?:\.\d+)?))?s", re.IGNORECASE)
_DAILY_MARKERS = (
    "per day",
    "tpd",
    "rpd",
    "daily",
    "quota exceeded",
    "exceeded your current quota",
    "resource_exhausted",  # Gemini
    "insufficient_quota",
    "out of credit",
    "billing",
)


class QuotaExhaustedError(LLMError):
    """Le fournisseur ne répondra pas utilement avant longtemps (quota du jour,
    crédit épuisé, clé invalide) : inutile d'attendre, il faut changer de
    fournisseur."""


def retry_delay_s(message: str) -> float | None:
    """Délai suggéré par l'API (« Please try again in 8.08s »), si présent."""
    match = _RETRY_AFTER_RE.search(message)
    if not match:
        return None
    first, second = match.group(1), match.group(2)
    # Format « 2m21.6s » : le premier groupe est alors les minutes.
    if second is not None:
        return float(first) * 60 + float(second)
    return float(first)


def is_quota_exhausted(message: str) -> bool:
    """Vrai si l'erreur signale un plafond qui ne se libérera pas rapidement."""
    lowered = message.lower()
    if any(marker in lowered for marker in _DAILY_MARKERS):
        return True
    delay = retry_delay_s(message)
    return delay is not None and delay > _MAX_SENSIBLE_WAIT_S


def is_auth_error(message: str) -> bool:
    """Clé absente/invalide : le fournisseur est inutilisable, on passe au suivant."""
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in ("401", "403", "invalid api key", "invalid_api_key", "unauthorized")
    )
