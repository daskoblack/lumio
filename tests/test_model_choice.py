"""Choix explicite du modèle d'IA, au lieu du seul ordre par défaut.

Le modèle choisi passe EN TÊTE, mais les autres restent derrière en secours :
le retirer complètement rendrait une génération dépendante d'un seul quota
quotidien — exactement ce que la chaîne de repli avait résolu.
"""

import pytest

from lectio.core.config import Config, LLMCandidate
from lectio.providers.llm.factory import build_llm

_TOUTES_LES_CLES = ("GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY")


@pytest.fixture
def cles(monkeypatch):
    for variable in _TOUTES_LES_CLES:
        monkeypatch.setenv(variable, "test-key")


def _ordre(config: Config) -> list[str]:
    return build_llm(config).available_labels


def test_sans_choix_l_ordre_par_defaut_est_conserve(cles):
    config = Config()
    assert _ordre(config)[0] == "groq/openai/gpt-oss-120b"


@pytest.mark.parametrize("choisi", [
    "mistral/mistral-small-latest",
    "gemini/gemini-2.5-flash-lite",
    "cerebras/gpt-oss-120b",
    "groq/openai/gpt-oss-20b",
])
def test_le_modele_choisi_passe_en_tete(cles, choisi):
    config = Config()
    config.providers.llm.preferred = choisi
    assert _ordre(config)[0] == choisi


def test_les_autres_restent_disponibles_en_secours(cles):
    """Sinon un quota épuisé stopperait net la génération."""
    config = Config()
    config.providers.llm.preferred = "mistral/mistral-small-latest"
    ordre = _ordre(config)
    assert len(ordre) == 5
    assert "groq/openai/gpt-oss-120b" in ordre[1:]


def test_un_choix_inconnu_ne_casse_rien(cles):
    """Un modèle retiré du catalogue (cas vécu avec Groq) ne doit pas empêcher
    l'application de fonctionner."""
    config = Config()
    config.providers.llm.preferred = "fournisseur/modele-inexistant"
    assert _ordre(config)[0] == "groq/openai/gpt-oss-120b"


def test_revenir_a_automatique(cles):
    config = Config()
    config.providers.llm.preferred = "mistral/mistral-small-latest"
    assert _ordre(config)[0] == "mistral/mistral-small-latest"
    config.providers.llm.preferred = ""
    assert _ordre(config)[0] == "groq/openai/gpt-oss-120b"


def test_un_modele_sans_cle_n_est_pas_propose(monkeypatch):
    """On ne propose jamais un modèle qu'on ne peut pas appeler."""
    for variable in _TOUTES_LES_CLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")

    config = Config()
    config.providers.llm.preferred = "groq/openai/gpt-oss-120b"  # clé absente
    assert _ordre(config) == ["mistral/mistral-small-latest"]


def test_chaque_modele_du_catalogue_a_un_intitule_lisible():
    """Le sélecteur montre ces intitulés : un identifiant technique y serait
    incompréhensible."""
    for candidate in Config().providers.llm.candidates():
        assert candidate.label, f"{candidate.identifier} n'a pas d'intitulé"
        assert candidate.model not in candidate.label


def test_l_identifiant_est_stable():
    candidate = LLMCandidate(name="groq", model="openai/gpt-oss-120b")
    assert candidate.identifier == "groq/openai/gpt-oss-120b"
