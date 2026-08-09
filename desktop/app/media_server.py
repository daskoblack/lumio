"""Petit serveur de fichiers local pour servir la vidéo générée au lecteur.

Pourquoi pas un simple `<video src="file:///...">` : ça fonctionne dans l'app
packagée (chargée elle-même depuis un fichier local), mais pas en
développement (`npm run dev`, servi depuis http://localhost:5173 — un
navigateur bloque par défaut l'accès file:// depuis une origine http://).
Un serveur HTTP local, lui, marche à l'identique dans les deux cas.

Lié à 127.0.0.1 uniquement : jamais exposé au réseau.
"""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path


def start(root_dir: Path) -> int:
    """Démarre le serveur (thread démon) et retourne le port choisi par l'OS."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(root_dir)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server.server_address[1]
