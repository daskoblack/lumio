"""Filet de sécurité contre les plantages muets au démarrage.

L'application est packagée sans console (`console=False` dans lumio.spec) :
toute exception non rattrapée fait donc disparaître le processus SANS le
moindre message. Pour un utilisateur non technique, l'application « ne
s'ouvre pas », sans aucune piste ni recours.

Ce module garantit deux choses dans ce cas :
1. un message lisible s'affiche, dans une boîte de dialogue native Windows —
   volontairement via ctypes, sans dépendre de pywebview ni de Qt, puisque
   c'est peut-être justement leur chargement qui a échoué ;
2. le détail technique est écrit dans un fichier journal, à un emplacement
   indiqué à l'utilisateur pour qu'il puisse le transmettre.
"""

from __future__ import annotations

import ctypes
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable

_DIALOG_TITLE = "Lumio n'a pas pu démarrer"
_MB_ICON_ERROR = 0x10
_LOG_NAME = "lumio-erreur.log"


def log_path() -> Path:
    """Emplacement du journal d'erreur, avec repli sur le dossier temporaire.

    `app_data_dir` peut elle-même échouer (profil Windows cassé — le cas qui
    a motivé paths.py) : ce module doit rester utilisable même alors.
    """
    try:
        from . import paths

        return paths.app_data_dir("Lumio") / _LOG_NAME
    except Exception:  # noqa: BLE001 - le journal ne doit jamais planter à son tour
        return Path(tempfile.gettempdir()) / _LOG_NAME


def write_report(exc: BaseException) -> Path | None:
    """Écrit l'erreur complète dans le journal. Retourne son chemin, ou None."""
    destination = log_path()
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Ajout en fin de fichier : on garde l'historique des incidents
        # précédents, utile quand le problème est intermittent.
        with destination.open("a", encoding="utf-8") as fichier:
            fichier.write(f"\n===== {horodatage} =====\n{detail}")
        return destination
    except Exception:  # noqa: BLE001 - disque plein, droits manquants...
        return None


def show_dialog(message: str) -> None:
    """Boîte de dialogue native. Sans effet hors Windows (CLI, tests, CI)."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.MessageBoxW(None, message, _DIALOG_TITLE, _MB_ICON_ERROR)
    except Exception:  # noqa: BLE001 - jamais bloquer sur l'affichage lui-même
        pass


def _build_message(exc: BaseException, report: Path | None) -> str:
    message = (
        "Lumio a rencontré un problème et n'a pas pu s'ouvrir.\n\n"
        f"Détail : {type(exc).__name__} — {exc}\n\n"
    )
    if report is not None:
        message += f"Un rapport a été enregistré ici :\n{report}"
    else:
        message += "Le rapport d'erreur n'a pas pu être enregistré."
    return message


def report_fatal(exc: BaseException, notify: Callable[[str], None] = show_dialog) -> None:
    """Journalise l'erreur et prévient l'utilisateur."""
    notify(_build_message(exc, write_report(exc)))


def guard(entry: Callable[[], None], notify: Callable[[str], None] = show_dialog) -> None:
    """Exécute le point d'entrée de l'application sous filet de sécurité.

    Seules les `Exception` sont interceptées : une fermeture normale
    (SystemExit) ou un Ctrl+C (KeyboardInterrupt) doivent continuer à
    remonter sans afficher de message d'erreur.
    """
    try:
        entry()
    except Exception as exc:  # noqa: BLE001 - c'est précisément le but ici
        report_fatal(exc, notify)
        raise SystemExit(1) from exc
