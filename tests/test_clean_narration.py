"""Nettoyage des scories de formatage que la voix lirait à haute voix.

Risque accru depuis l'ajout de modèles de repli plus légers : ils préfixent
plus volontiers leur réponse (« Voici la narration : ») ou la formatent en
Markdown.
"""

import pytest

from lectio.core.textutil import clean_narration


def test_prefixe_meta_retire():
    texte = "Voici la narration :\nLes fractions représentent une partie d'un tout."
    assert clean_narration(texte) == "Les fractions représentent une partie d'un tout."


def test_prefixe_meta_sans_deux_points_conserve():
    """Sans « : », c'est probablement une vraie phrase : on n'y touche pas."""
    texte = "Voici les fractions\nElles représentent une partie d'un tout."
    assert clean_narration(texte) == texte


def test_vraie_phrase_terminee_par_deux_points_conservee():
    """Une phrase longue et non méta doit survivre, même finie par « : »."""
    texte = (
        "Retenez bien les trois éléments suivants qui structurent tout le raisonnement :\n"
        "le numérateur, le dénominateur, et la barre de fraction."
    )
    assert clean_narration(texte) == texte


def test_blocs_de_code_retires():
    assert clean_narration("```\nBonjour à tous.\n```") == "Bonjour à tous."
    assert clean_narration("```text\nBonjour à tous.\n```") == "Bonjour à tous."


def test_gras_et_italique_markdown_retires_mais_mots_gardes():
    assert clean_narration("Le **numérateur** est en haut.") == "Le numérateur est en haut."
    assert clean_narration("Le *dénominateur* est en bas.") == "Le dénominateur est en bas."
    assert clean_narration("Point __important__ ici.") == "Point important ici."


def test_narration_propre_inchangee():
    texte = "Bonjour, aujourd'hui nous allons parler des fractions. C'est simple."
    assert clean_narration(texte) == texte


def test_asterisque_isole_non_touche():
    """Un astérisque seul n'est pas du gras : ne pas manger le texte autour."""
    texte = "La note 4 * 3 vaut douze."
    assert clean_narration(texte) == texte


@pytest.mark.parametrize("entree", ["", "   ", "\n\n"])
def test_texte_vide_reste_vide_sans_erreur(entree):
    assert clean_narration(entree) == ""
