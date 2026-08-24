"""Réglages locaux de l'app desktop (clés API, voix par défaut).

Stockés dans le dossier de données utilisateur (indépendant du dossier de
travail des jobs), modifiables à tout moment depuis l'écran Réglages.

Plusieurs clés d'IA peuvent coexister : la première renseignée sert de
fournisseur principal, les autres de repli automatique quand un quota
quotidien tombe en pleine génération (voir providers/llm/chain.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from lectio.core.config import LLM_ENV_KEYS

from . import paths

# Un réglage par fournisseur d'IA, plus la voix.
API_KEY_FIELDS = {name: f"{name}_api_key" for name in LLM_ENV_KEYS}

_DEFAULTS: dict[str, str] = {
    **{field: "" for field in API_KEY_FIELDS.values()},
    "voice_id": "fr-FR-DeniseNeural",
    # Modèle d'IA choisi par l'utilisateur (« fournisseur/modèle »).
    # Vide = Lumio décide, comme avant l'introduction du choix.
    "llm_model": "",
}


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


def save_settings(updates: dict | None = None, **kwargs) -> dict:
    """Met à jour les réglages fournis (les autres restent inchangés)."""
    current = load_settings()
    for key, value in {**(updates or {}), **kwargs}.items():
        if value is not None and key in _DEFAULTS:
            current[key] = value
    _settings_path().write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def apply_to_environment(settings: dict) -> None:
    """Injecte les clés dans l'environnement du process.

    Le reste du code (Config.api_key_for) n'a pas besoin de savoir d'où elles
    viennent. Une clé vidée dans les réglages est retirée de l'environnement,
    sinon l'ancienne valeur continuerait de s'appliquer jusqu'au redémarrage.
    """
    for provider_name, field in API_KEY_FIELDS.items():
        env_var = LLM_ENV_KEYS[provider_name]
        value = settings.get(field) or ""
        if value:
            os.environ[env_var] = value
        else:
            os.environ.pop(env_var, None)
