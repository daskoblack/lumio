"""Point d'entrée PyInstaller pour Lumio.

Ce script existe séparément de `app/main.py` car il ne doit PAS utiliser
d'imports relatifs : PyInstaller exécute le script d'entrée comme `__main__`,
exactement comme `python lumio_launcher.py` le ferait — les imports relatifs
de `app/main.py` (`from .api import Api`) ne fonctionnent que si ce module
est importé en tant que partie du package `desktop.app`, pas exécuté
directement. En passant par un import absolu ici, `app.main` est chargé
normalement comme un sous-module et ses imports relatifs internes résolvent
correctement.
"""

from desktop.app.crash import guard
from desktop.app.main import main

if __name__ == "__main__":
    # Sans console dans l'app packagée, une exception ici serait totalement
    # muette : `guard` garantit un message et un journal d'erreur.
    guard(main)
