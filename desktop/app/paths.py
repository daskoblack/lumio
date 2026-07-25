"""Résolution robuste de dossiers utilisateur Windows.

`Path.home()` s'appuie sur des variables d'environnement (USERPROFILE, ou à
défaut HOMEDRIVE+HOMEPATH) qui peuvent être mal configurées sur certaines
machines (profils Windows atypiques, comptes de domaine, images OEM) — le
chemin renvoyé peut alors ne pas exister et ne pas être créable, faisant
planter l'app au tout premier lancement (vécu en conditions réelles).

Ces fonctions ne font JAMAIS confiance à un chemin candidat sans essayer
activement de le créer, et retombent toujours sur le dossier temporaire du
système en tout dernier recours (qui, lui, existe systématiquement).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable


def _first_writable(candidates: list[Callable[[], Path]]) -> Path:
    for make_candidate in candidates:
        try:
            candidate = make_candidate()
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except (OSError, KeyError, RuntimeError):
            continue
    # Dernier filet de sécurité : le dossier temp système existe presque
    # toujours et n'échoue jamais pour les mêmes raisons qu'un profil cassé.
    fallback = Path(tempfile.gettempdir()) / "Lumio"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def app_data_dir(app_name: str) -> Path:
    """Dossier de réglages (%APPDATA%/{app_name}), avec repli robuste."""
    return _first_writable([
        lambda: Path(os.environ["APPDATA"]) / app_name,
        lambda: Path.home() / f".{app_name.lower()}",
    ])


def default_workspace_dir(app_name: str) -> Path:
    """Dossier de travail par défaut (vidéos générées), avec repli robuste."""
    return _first_writable([
        lambda: Path.home() / "Documents" / app_name,
        lambda: Path(os.environ["LOCALAPPDATA"]) / app_name,
    ])
