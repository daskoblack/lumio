"""Réglages locaux de l'app desktop (clé API, voix par défaut).

Stockés dans le dossier de données utilisateur (indépendant du dossier de
travail des jobs), modifiables à tout moment depuis l'écran Réglages.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import paths

_DEFAULTS = {"groq_api_key": "", "voice_id": "fr-FR-DeniseNeural"}


def _settings_dir() -> Path:
    return paths.app_data_dir("Lumio")


def _settings_path() -> Path:
    return _settings_dir() / "settings.json"


def load_settings() -> dict:
    path = _settings_path()
    if not path.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {}
    return {**_DEFAULTS, **data}


def save_settings(groq_api_key: str | None = None, voice_id: str | None = None) -> dict:
    current = load_settings()
    if groq_api_key is not None:
        current["groq_api_key"] = groq_api_key
    if voice_id is not None:
        current["voice_id"] = voice_id
    _settings_path().write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def apply_to_environment(settings: dict) -> None:
    """Injecte la clé dans l'environnement du process : le reste du code
    (Config.groq_api_key) n'a pas besoin de savoir d'où elle vient."""
    if settings.get("groq_api_key"):
        os.environ["GROQ_API_KEY"] = settings["groq_api_key"]
