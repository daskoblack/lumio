"""Suivi de la consommation quotidienne d'IA, pour que l'utilisateur sache
où il en est de sa réserve gratuite.

Les fournisseurs gratuits plafonnent le nombre de jetons par JOUR. Sans
indication, on découvre la limite en pleine génération : les pages restantes
basculent alors en mode dégradé, après avoir déjà attendu de longues minutes.
Ce module compte ce qui a réellement été envoyé/reçu afin d'avertir AVANT.

Le comptage en jetons est approximatif (environ quatre caractères par jeton) :
il sert à situer un ordre de grandeur — « il te reste à peu près de quoi faire
un cours » — jamais à afficher un décompte exact.

Règle absolue : aucune erreur de suivi ne doit jamais interrompre une
génération. Toutes les opérations d'écriture sont silencieusement tolérantes.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

# Plafond quotidien constaté sur les offres gratuites (Groq notamment).
# Ordre de grandeur volontairement prudent : mieux vaut prévenir trop tôt.
DAILY_FREE_TOKENS = 100_000

# Un jeton vaut environ quatre caractères en français comme en anglais.
_CHARS_PER_TOKEN = 4

# Au-delà, l'historique n'apporte plus rien et le fichier grossirait pour rien.
_HISTORY_DAYS = 7

# Coût moyen par page, MESURÉ sur le pipeline réel (cours de 40 pages) :
# une durée choisie déclenche des corrections supplémentaires, donc davantage
# d'appels. Sert uniquement à prévenir avant de lancer une longue génération.
TOKENS_PER_PAGE_AUTO = 1_320
TOKENS_PER_PAGE_PRECISE = 2_120


def estimate_course_tokens(pages: int, has_target_duration: bool) -> int:
    """Consommation attendue pour un cours, d'après son nombre de pages."""
    par_page = TOKENS_PER_PAGE_PRECISE if has_target_duration else TOKENS_PER_PAGE_AUTO
    return max(0, pages) * par_page


def estimate_tokens(*texts: str) -> int:
    """Estimation du nombre de jetons d'un ou plusieurs textes."""
    return sum(len(text) for text in texts if text) // _CHARS_PER_TOKEN


class UsageTracker:
    """Compteur de jetons par jour et par fournisseur, persisté en JSON."""

    def __init__(self, path: Path, daily_limit: int = DAILY_FREE_TOKENS) -> None:
        self._path = Path(path)
        self.daily_limit = daily_limit

    # --- Lecture ---------------------------------------------------------
    def _load(self) -> dict[str, dict[str, int]]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - fichier absent, illisible ou corrompu
            return {}

    def today_by_provider(self) -> dict[str, int]:
        """Jetons consommés aujourd'hui, par fournisseur."""
        return self._load().get(date.today().isoformat(), {})

    def today_total(self) -> int:
        return sum(self.today_by_provider().values())

    def remaining_for(self, provider: str) -> int:
        """Réserve estimée restante pour un fournisseur donné."""
        used = self.today_by_provider().get(provider, 0)
        return max(0, self.daily_limit - used)

    # --- Écriture --------------------------------------------------------
    def record(self, provider: str, tokens: int) -> None:
        """Ajoute une consommation. N'échoue jamais : le suivi est secondaire
        par rapport à la génération en cours."""
        if tokens <= 0:
            return
        try:
            data = self._load()
            today = date.today().isoformat()
            jour = data.setdefault(today, {})
            jour[provider] = jour.get(provider, 0) + tokens
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._prune(data), indent=2), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001 - jamais interrompre une génération
            pass

    @staticmethod
    def _prune(data: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
        limite = (date.today() - timedelta(days=_HISTORY_DAYS)).isoformat()
        return {jour: valeurs for jour, valeurs in data.items() if jour >= limite}
