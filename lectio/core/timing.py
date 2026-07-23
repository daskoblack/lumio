"""Logique pure de conversion durée <-> mots. Aucune I/O : testable isolément.

C'est le cœur du calcul de durée :
- durée cible (utilisateur)  -> budget de mots (contrainte de génération)
- nb de mots (généré)        -> durée estimée (avant TTS)
La durée RÉELLE (post-TTS) reste toujours l'autorité finale pour la timeline.
"""

from __future__ import annotations

import re


def duration_to_words(seconds: float, rate_wps: float) -> int:
    """Convertit une durée cible en budget de mots via le débit de la voix."""
    if rate_wps <= 0:
        raise ValueError("Le débit (mots/s) doit être strictement positif.")
    return max(1, round(seconds * rate_wps))


def words_to_duration(words: int, rate_wps: float) -> float:
    """Estime la durée orale d'un texte à partir de son nombre de mots."""
    if rate_wps <= 0:
        raise ValueError("Le débit (mots/s) doit être strictement positif.")
    return words / rate_wps


def deviation(actual: float, target: float) -> float:
    """Écart relatif |réel - cible| / cible. Sert à décider d'une correction."""
    if target <= 0:
        raise ValueError("La cible doit être strictement positive.")
    return abs(actual - target) / target


def count_words(text: str) -> int:
    """Comptage de mots simple (suffisant pour le budget en français)."""
    return len(text.split())


_DURATION_RE = re.compile(
    r"^\s*(?:(?P<m>\d+(?:\.\d+)?)\s*m)?\s*(?:(?P<s>\d+(?:\.\d+)?)\s*s)?\s*$",
    re.IGNORECASE,
)


def parse_duration(text: str) -> float:
    """Parse une durée utilisateur en secondes.

    Formats acceptés : "90" (secondes nues), "90s", "2m", "1m30s", "1.5m".
    """
    text = text.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):  # nombre nu = secondes
        return float(text)

    match = _DURATION_RE.match(text)
    if not match or (match.group("m") is None and match.group("s") is None):
        raise ValueError(f"Durée invalide : {text!r} (ex. '90', '90s', '2m', '1m30s').")

    total = 0.0
    if match.group("m"):
        total += float(match.group("m")) * 60
    if match.group("s"):
        total += float(match.group("s"))
    return total


def format_duration(seconds: float | None) -> str:
    """Formatage lisible d'une durée (ex. 95.4 -> '1m35s')."""
    if seconds is None:
        return "—"
    seconds = round(seconds)
    minutes, secs = divmod(seconds, 60)
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"
