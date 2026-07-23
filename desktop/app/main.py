"""Point d'entrée de l'application desktop Lumio (pywebview).

En développement (LUMIO_DEV=1) : charge le serveur Vite (npm run dev) pour
le rechargement à chaud. En production : charge les fichiers statiques
buildés (frontend/dist/index.html), inclus dans le paquet PyInstaller.

À lancer avec `python -m desktop.app.main` depuis la racine du dépôt
(jamais `python desktop/app/main.py` directement : les imports relatifs
de ce module exigent qu'il soit exécuté comme partie du package `desktop.app`).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import webview

from .api import Api

_DEV_URL = "http://localhost:5173"


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):  # exécuté depuis un .exe PyInstaller
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def _frontend_dist_path() -> Path:
    return _bundle_root() / "frontend" / "dist" / "index.html"


def _icon_path() -> str | None:
    icon = _bundle_root() / "frontend" / "lumio_icon.ico"
    return str(icon) if icon.exists() else None


def main() -> None:
    api = Api()
    is_dev = os.environ.get("LUMIO_DEV") == "1"
    target = _DEV_URL if is_dev else str(_frontend_dist_path())

    window = webview.create_window(
        "Lumio",
        target,
        js_api=api,
        width=1180,
        height=760,
        min_size=(900, 600),
        background_color="#14131c",
    )
    api.set_window(window)
    webview.start(debug=is_dev, icon=_icon_path())


if __name__ == "__main__":
    main()
