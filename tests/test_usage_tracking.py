"""Suivi de la réserve d'IA gratuite.

Les offres gratuites plafonnent le nombre de jetons par jour. Sans indication,
l'utilisateur découvre la limite en pleine génération : les pages restantes
basculent en mode dégradé après de longues minutes d'attente.
"""

import json
from datetime import date, timedelta

import pytest

from lectio.core.usage import (
    DAILY_FREE_TOKENS,
    UsageTracker,
    estimate_course_tokens,
    estimate_tokens,
)
from lectio.providers.llm.base import LLMProvider
from lectio.providers.llm.chain import LLMChain


@pytest.fixture
def tracker(tmp_path) -> UsageTracker:
    return UsageTracker(tmp_path / "usage.json")


# --- Comptage --------------------------------------------------------------

def test_consommation_cumulee_par_fournisseur(tracker):
    tracker.record("groq/llama", 1_000)
    tracker.record("groq/llama", 500)
    tracker.record("mistral/small", 300)

    assert tracker.today_by_provider() == {"groq/llama": 1_500, "mistral/small": 300}
    assert tracker.today_total() == 1_800


def test_reserve_restante_par_fournisseur(tracker):
    tracker.record("groq/llama", 30_000)
    assert tracker.remaining_for("groq/llama") == DAILY_FREE_TOKENS - 30_000
    assert tracker.remaining_for("mistral/small") == DAILY_FREE_TOKENS


def test_la_reserve_ne_devient_jamais_negative(tracker):
    tracker.record("groq/llama", DAILY_FREE_TOKENS * 3)
    assert tracker.remaining_for("groq/llama") == 0


def test_une_consommation_nulle_est_ignoree(tracker):
    tracker.record("groq/llama", 0)
    tracker.record("groq/llama", -5)
    assert tracker.today_total() == 0


def test_seule_la_journee_en_cours_est_comptee(tracker, tmp_path):
    hier = (date.today() - timedelta(days=1)).isoformat()
    (tmp_path / "usage.json").write_text(
        json.dumps({hier: {"groq/llama": 90_000}}), encoding="utf-8"
    )
    assert tracker.today_total() == 0  # la réserve repart à zéro chaque jour


def test_l_historique_ancien_est_purge(tracker, tmp_path):
    vieux = (date.today() - timedelta(days=30)).isoformat()
    (tmp_path / "usage.json").write_text(
        json.dumps({vieux: {"groq/llama": 1_000}}), encoding="utf-8"
    )
    tracker.record("groq/llama", 10)

    data = json.loads((tmp_path / "usage.json").read_text(encoding="utf-8"))
    assert vieux not in data


# --- Robustesse : le suivi ne doit JAMAIS casser une génération ------------

def test_un_fichier_corrompu_est_ignore(tracker, tmp_path):
    (tmp_path / "usage.json").write_text("{ ceci n'est pas du JSON", encoding="utf-8")
    assert tracker.today_total() == 0
    tracker.record("groq/llama", 100)  # ne doit pas lever


def test_un_chemin_inaccessible_ne_leve_pas(tmp_path):
    obstacle = tmp_path / "fichier"
    obstacle.write_text("x", encoding="utf-8")
    bloque = UsageTracker(obstacle / "sous" / "usage.json")
    bloque.record("groq/llama", 100)  # doit rester silencieux
    assert bloque.today_total() == 0


# --- Estimation ------------------------------------------------------------

def test_estimation_de_jetons_a_partir_du_texte():
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("a" * 200, "b" * 200) == 100


def test_une_duree_choisie_coute_plus_cher():
    """Une cible explicite déclenche des corrections, donc plus d'appels."""
    auto = estimate_course_tokens(40, has_target_duration=False)
    precis = estimate_course_tokens(40, has_target_duration=True)
    assert precis > auto


def test_estimation_proportionnelle_au_nombre_de_pages():
    assert estimate_course_tokens(40, False) == 2 * estimate_course_tokens(20, False)
    assert estimate_course_tokens(0, False) == 0


# --- Intégration avec la chaîne LLM ---------------------------------------

class _FakeLLM(LLMProvider):
    async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
        return "r" * 400


@pytest.mark.asyncio
async def test_la_chaine_enregistre_ce_qu_elle_consomme(tracker):
    chain = LLMChain([("groq/llama", _FakeLLM())], tracker)
    await chain.complete(system="s" * 400, user="u" * 400)

    # 400+400 envoyés + 400 reçus = 1200 caractères ≈ 300 jetons
    assert tracker.today_by_provider() == {"groq/llama": 300}


@pytest.mark.asyncio
async def test_la_chaine_fonctionne_sans_suivi():
    """Le suivi est facultatif : le CLI et les tests s'en passent."""
    chain = LLMChain([("groq/llama", _FakeLLM())])
    assert await chain.complete(system="s", user="u") == "r" * 400


@pytest.mark.asyncio
async def test_seul_le_fournisseur_reellement_utilise_est_compte(tracker):
    """Un fournisseur épuisé ne doit pas se voir imputer la consommation du
    suivant, sinon les compteurs deviennent trompeurs."""
    from lectio.providers.llm.errors import QuotaExhaustedError

    class _Epuise(LLMProvider):
        async def complete(self, system, user, **kwargs):
            raise QuotaExhaustedError("plus de quota")

    chain = LLMChain([("groq/llama", _Epuise()), ("mistral/small", _FakeLLM())], tracker)
    await chain.complete(system="s" * 400, user="u" * 400)

    consommation = tracker.today_by_provider()
    assert "groq/llama" not in consommation
    assert consommation["mistral/small"] == 300
