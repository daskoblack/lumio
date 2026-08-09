"""Tests du découpage : mapping pages->slides et calcul de durée estimée.

L'IA estime un nombre de mots PAR PAGE (`estimated_words_per_page`), pas un
total pour la section entière : c'est ce qui garantit que le budget par page
ne s'effondre plus quand une section regroupe beaucoup de pages (cause du
"délire" au-delà de 2-3 pages par section)."""

from lectio.core.models import ContentBlock, Slide
from lectio.core.timing import words_to_duration
from lectio.pipeline.sectioning import build_sections


def test_build_sections_maps_slides_and_durations():
    slides = [
        Slide(index=0, source_page=1, title="P1"),
        Slide(index=1, source_page=2, title="P2"),
    ]
    structure = {
        "sections": [
            {
                "title": "Intro",
                "kind": "intro",
                "context": "Présentation du cours et de ses objectifs.",
                "source_pages": [1],
                "estimated_words_per_page": 92,
            },
            {
                "title": "Concept",
                "kind": "concept",
                "context": "Le cœur du sujet : définitions et vocabulaire clé.",
                "source_pages": [2],
                "estimated_words_per_page": 230,
            },
        ]
    }
    sections = build_sections(structure, slides, speech_rate_wps=2.3)

    assert len(sections) == 2
    assert sections[0].kind.value == "intro"
    assert sections[0].slide_ids == [slides[0].id]
    assert sections[0].context == "Présentation du cours et de ses objectifs."
    # Une seule page dans chaque section : le total de la section == le budget par page.
    assert sections[1].estimated_duration_s == words_to_duration(230, 2.3)
    # Pas de durée cible tant que l'utilisateur n'en fixe pas.
    assert all(s.target_duration_s is None for s in sections)


def test_unknown_kind_falls_back_to_other():
    slides = [Slide(index=0, source_page=1, title="P1")]
    structure = {"sections": [{"title": "X", "kind": "bizarre", "source_pages": [1]}]}
    sections = build_sections(structure, slides, 2.3)
    assert sections[0].kind.value == "other"


def test_word_budget_distributed_proportionally_across_slides():
    short_text = "un deux trois"  # 3 mots
    long_text = " ".join(["mot"] * 27)  # 27 mots -> poids 9x le premier
    slides = [
        Slide(index=0, source_page=1, title="P1", content_blocks=[ContentBlock(kind="text", text=short_text)]),
        Slide(index=1, source_page=2, title="P2", content_blocks=[ContentBlock(kind="text", text=long_text)]),
    ]
    structure = {
        "sections": [
            {
                "title": "Concept", "kind": "concept", "source_pages": [1, 2],
                "estimated_words_per_page": 150,  # total section = 150 * 2 pages = 300
            }
        ]
    }
    build_sections(structure, slides, speech_rate_wps=2.3, min_words_per_page=1)

    # 3 mots vs 27 mots -> poids 1/10 et 9/10 du budget total de 300.
    assert slides[0].estimated_narration_words == 30
    assert slides[1].estimated_narration_words == 270
    # La somme des slides doit reconstituer exactement le budget de la section.
    assert slides[0].estimated_narration_words + slides[1].estimated_narration_words == 300


def test_le_budget_par_page_ne_diminue_pas_avec_le_nombre_de_pages():
    """Le coeur du correctif : avant, un total FIXE pour la section était divisé
    par N pages -> le budget par page s'effondrait dès 3 pages. Désormais
    l'estimation EST déjà par page : elle reste stable quel que soit N."""
    def _section_a_n_pages(n: int, words_per_page: int = 100):
        slides = [
            Slide(index=i, source_page=i + 1, title=f"P{i+1}",
                  content_blocks=[ContentBlock(kind="text", text="contenu " * 20)])
            for i in range(n)
        ]
        structure = {"sections": [{
            "title": "S", "kind": "concept", "source_pages": list(range(1, n + 1)),
            "estimated_words_per_page": words_per_page,
        }]}
        build_sections(structure, slides, speech_rate_wps=2.3, min_words_per_page=1)
        return slides

    for n in (1, 2, 3, 6, 10):
        slides = _section_a_n_pages(n)
        # Poids identiques (même longueur de texte) -> répartition égale ~100/page.
        assert all(89 <= s.estimated_narration_words <= 111 for s in slides), (
            f"section à {n} pages : budget par page hors plage attendue "
            f"{[s.estimated_narration_words for s in slides]}"
        )


def test_plancher_applique_meme_si_l_estimation_ia_est_trop_faible():
    """Une IA qui sous-estime (ou un modèle de repli qui ignore la consigne
    et renvoie 0) ne doit jamais produire un budget par page en dessous du
    plancher absolu."""
    slides = [
        Slide(index=i, source_page=i + 1, title=f"P{i+1}",
              content_blocks=[ContentBlock(kind="text", text="contenu " * 5)])
        for i in range(4)
    ]
    structure = {"sections": [{
        "title": "S", "kind": "concept", "source_pages": [1, 2, 3, 4],
        "estimated_words_per_page": 5,  # largement sous-estimé
    }]}
    build_sections(structure, slides, speech_rate_wps=2.3, min_words_per_page=70)
    assert all(s.estimated_narration_words >= 70 for s in slides)


def test_champ_absent_retombe_sur_le_plancher_sans_planter():
    slides = [Slide(index=0, source_page=1, title="P1")]
    structure = {"sections": [{"title": "S", "kind": "other", "source_pages": [1]}]}
    sections = build_sections(structure, slides, 2.3, min_words_per_page=70)
    assert sections[0].estimated_narration_words == 70
