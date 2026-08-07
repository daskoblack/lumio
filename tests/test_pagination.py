"""Le découpage vient d'un LLM : il oublie parfois une page, la cite deux
fois, ou invente un numéro. Une page perdue disparaîtrait de la vidéo sans
le moindre signal — ces tests verrouillent la réparation."""

import pytest

from lectio.core.models import ContentBlock, Slide
from lectio.pipeline.sectioning import build_sections


def _slides(n: int) -> list[Slide]:
    return [
        Slide(
            index=i, source_page=i + 1, title=f"P{i + 1}",
            content_blocks=[ContentBlock(kind="text", text=f"contenu page {i + 1}")],
        )
        for i in range(n)
    ]


def _pages_couvertes(sections, slides) -> list[int]:
    par_id = {s.id: s.source_page for s in slides}
    pages = []
    for section in sections:
        pages.extend(par_id[sid] for sid in section.slide_ids)
    return pages


def _structure(*groupes) -> dict:
    return {
        "sections": [
            {"title": f"S{i}", "kind": "concept", "context": "",
             "source_pages": list(pages), "estimated_narration_words": 100}
            for i, pages in enumerate(groupes)
        ]
    }


def test_decoupage_correct_est_preserve():
    slides = _slides(5)
    sections = build_sections(_structure([1, 2], [3, 4, 5]), slides, 2.3)
    assert _pages_couvertes(sections, slides) == [1, 2, 3, 4, 5]


def test_page_oubliee_est_rattachee():
    """Page 3 absente du découpage : elle doit réapparaître, pas disparaître."""
    slides = _slides(5)
    sections = build_sections(_structure([1, 2], [4, 5]), slides, 2.3)
    assert _pages_couvertes(sections, slides) == [1, 2, 3, 4, 5]


def test_page_en_double_n_est_comptee_qu_une_fois():
    slides = _slides(4)
    sections = build_sections(_structure([1, 2], [2, 3, 4]), slides, 2.3)
    assert _pages_couvertes(sections, slides) == [1, 2, 3, 4]


def test_page_inexistante_est_ignoree():
    slides = _slides(3)
    sections = build_sections(_structure([1, 2], [3, 99]), slides, 2.3)
    assert _pages_couvertes(sections, slides) == [1, 2, 3]


def test_numero_non_entier_est_ignore_sans_planter():
    slides = _slides(3)
    structure = {"sections": [
        {"title": "S", "kind": "concept", "source_pages": [1, "deux", None, 3]},
    ]}
    sections = build_sections(structure, slides, 2.3)
    assert _pages_couvertes(sections, slides) == [1, 2, 3]


def test_aucune_page_citee_couvre_tout_le_document():
    slides = _slides(4)
    sections = build_sections(_structure([], []), slides, 2.3)
    assert _pages_couvertes(sections, slides) == [1, 2, 3, 4]


def test_structure_vide_produit_une_section_couvrant_tout():
    slides = _slides(3)
    sections = build_sections({"sections": []}, slides, 2.3)
    assert len(sections) == 1
    assert _pages_couvertes(sections, slides) == [1, 2, 3]


def test_pages_desordonnees_sont_remises_dans_l_ordre():
    slides = _slides(4)
    sections = build_sections(_structure([3, 1], [4, 2]), slides, 2.3)
    # Chaque section est ordonnée, et aucune page n'est perdue.
    assert sorted(_pages_couvertes(sections, slides)) == [1, 2, 3, 4]
    for section in sections:
        pages = [s.source_page for s in slides if s.id in section.slide_ids]
        assert pages == sorted(pages)


@pytest.mark.parametrize("nb_pages", [1, 2, 7, 20])
def test_aucune_page_perdue_quel_que_soit_le_document(nb_pages):
    """Propriété générale : autant de pages en sortie qu'en entrée, sans doublon."""
    slides = _slides(nb_pages)
    # Découpage volontairement bancal : trous, doublons, numéro absurde.
    structure = _structure([1], [1, 2, 999], list(range(4, nb_pages + 1)))
    sections = build_sections(structure, slides, 2.3)
    couvertes = _pages_couvertes(sections, slides)
    assert sorted(couvertes) == list(range(1, nb_pages + 1))
    assert len(couvertes) == len(set(couvertes))
