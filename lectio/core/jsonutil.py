"""Extraction robuste de JSON depuis une réponse LLM (tolère les ``` et le bruit)."""

from __future__ import annotations

import json
import re
from typing import Any

from .exceptions import LLMError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_json(text: str) -> Any:
    """Parse le JSON d'une réponse LLM, en retirant d'éventuels blocs de code."""
    text = text.strip()

    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Dernier recours : isoler le premier objet {...} de la chaîne.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise LLMError(f"JSON invalide dans la réponse LLM : {exc}") from exc
        raise LLMError("Aucun JSON exploitable dans la réponse LLM.")
