"""Le découpage en sections doit « voir » CHAQUE page du document.

Défaut corrigé : le texte était coupé à `max_document_chars`, ce qui faisait
disparaître les dernières pages de l'analyse. Sur un cours de 40 pages denses,
la moitié recevait sections, contexte pédagogique et durée sans que le modèle
n'ait jamais vu son contenu.
"""

import pytest

from lectio.pipeline.analysis import build_analysis_document
from lectio.providers.llm.base import LLMProvider


def _pages(n: int, chars_per_page: int = 1200) -> list[tuple[int, str]]:
    return [(i + 1, f"Sujet de la page {i + 1}. " + "contenu " * (chars_per_page // 8))
            for i in range(n)]


def test_document_court_est_envoye_entier():
    pages = _pages(5, chars_per_page=400)
    document, shortened = build_analysis_document(pages, max_chars=24_000)
    assert shortened is False
    for number, text in pages:
        assert text in document  # texte intégral, aucune perte


def test_toutes_les_pages_sont_presentes_meme_sur_un_long_document():
    """Le cœur du correctif : 40 pages denses tiennent dans le budget."""
    pages = _pages(40, chars_per_page=1200)
    document, shortened = build_analysis_document(pages, max_chars=24_000)
    assert shortened is True
    for number, _ in pages:
        assert f"=== PAGE {number} ===" in document, f"page {number} absente de l'analyse"


def test_le_sujet_de_chaque_page_reste_lisible():
    """Un extrait doit contenir le début de la page, là où se trouve son sujet."""
    pages = _pages(40, chars_per_page=1200)
    document, _ = build_analysis_document(pages, max_chars=24_000)
    for number, _ in pages:
        assert f"Sujet de la page {number}." in document


def test_le_budget_est_respecte():
    pages = _pages(40, chars_per_page=1200)
    document, _ = build_analysis_document(pages, max_chars=24_000)
    assert len(document) <= 24_000


@pytest.mark.parametrize("n_pages", [1, 12, 40, 120])
def test_aucune_page_perdue_quelle_que_soit_la_taille(n_pages):
    pages = _pages(n_pages, chars_per_page=1500)
    document, _ = build_analysis_document(pages, max_chars=24_000)
    for number, _ in pages:
        assert f"=== PAGE {number} ===" in document


def test_document_tres_long_garde_un_extrait_minimal_lisible():
    """Sur 500 pages, un partage strict donnerait ~40 caractères par page :
    inexploitable. On préfère dépasser un peu le budget que rendre l'analyse
    aveugle."""
    pages = _pages(500, chars_per_page=1500)
    document, shortened = build_analysis_document(pages, max_chars=24_000)
    assert shortened is True
    for number, _ in pages:
        assert f"Sujet de la page {number}." in document


def test_aucune_page_ne_produit_un_document_vide():
    document, shortened = build_analysis_document([], max_chars=24_000)
    assert document == ""
    assert shortened is False


@pytest.mark.asyncio
async def test_analyze_structure_transmet_bien_toutes_les_pages():
    """Vérifie le chemin complet, pas seulement le constructeur de document."""
    from lectio.pipeline.analysis import analyze_structure

    captured = {}

    class _Spy(LLMProvider):
        async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
            captured["user"] = user
            return '{"course_title": "C", "sections": []}'

    pages = _pages(40, chars_per_page=1200)
    _, shortened = await analyze_structure(_Spy(), pages, max_chars=24_000)
    assert shortened is True
    for number, _ in pages:
        assert f"=== PAGE {number} ===" in captured["user"]
