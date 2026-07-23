"""Point d'entrée de l'application desktop Lumio (pywebview).

En développement (LUMIO_DEV=1) : charge le serveur Vite (npm run dev) pour
le rechargement à chaud. En production : charge les fichiers statiques
buildés (frontend/dist/index.html), inclus dans le paquet PyInstaller.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import webview

from .api import Api

_DEV_URL = "http://localhost:5173"


def _frontend_dist_path() -> Path:
    if getattr(sys, "frozen", False):  # exécuté depuis un .exe PyInstaller
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parents[1]
    return base / "frontend" / "dist" / "index.html"


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
    webview.start(debug=is_dev)


if __name__ == "__main__":
    main()
