"""Contrôles sur le texte destiné à être prononcé.

Un texte sans aucune lettre ni chiffre (« ... », « --- », « " ") fait échouer
la synthèse vocale avec un message obscur (« No audio was received »), ou pire
produit un fichier audio vide qui casse la mesure de durée bien plus loin dans
le pipeline. On vérifie donc en amont, là où le diagnostic est encore clair.
"""

from __future__ import annotations

import difflib
import re


def is_pronounceable(text: str) -> bool:
    """Vrai si le texte contient au moins une lettre ou un chiffre.

    Critère volontairement strict : de la ponctuation seule n'est pas
    synthétisable, alors qu'un texte contenant ne serait-ce qu'un mot l'est.
    """
    return any(char.isalnum() for char in text)


# Un modèle bavard préfixe volontiers sa réponse (« Voici la narration : »).
# Prononcé à voix haute, ça sonne faux. On ne retire qu'une PREMIÈRE ligne
# courte, terminée par « : » et clairement méta — jamais une vraie phrase.
_META_KEYWORDS = ("narration", "voici", "texte", "script", "réponse", "reponse")
_MAX_META_LINE_CHARS = 90

_CODE_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*\n?|\n?\s*```\s*$")
_EMPHASIS_RE = re.compile(r"(\*{1,3}|_{2,3})(?=\S)(.+?)(?<=\S)\1", re.DOTALL)


# Motifs qui trahissent une rupture de personnage plutôt qu'une vraie
# narration de cours : un gabarit non rempli (« [Votre Nom] »), ou le modèle
# qui parle de lui-même comme une IA au lieu du professeur qu'il est censé
# incarner. Repéré en usage réel : un modèle de repli, poussé à combler un
# écart de mots, retombe parfois sur un patron générique de lettre-type.
# Volontairement restrictif : ne doit jamais rejeter une vraie phrase de cours.
_PLACEHOLDER_RE = re.compile(r"\[[^\[\]]{2,40}\]")
_AI_SELF_REFERENCE_RE = re.compile(
    r"je m.appelle|en tant qu.(assistant|ia\b|intelligence artificielle)|"
    r"je suis (un|une) (assistant|intelligence artificielle|mod[eè]le de langage)|"
    r"\bopenai\b|\bchatgpt\b|mod[eè]le de langage",
    re.IGNORECASE,
)


def has_suspicious_pattern(text: str) -> bool:
    """Vrai si le texte ressemble à une rupture de personnage (gabarit non
    rempli, ou le modèle qui se présente comme une IA) plutôt qu'à une
    narration de cours légitime."""
    return bool(_PLACEHOLDER_RE.search(text)) or bool(_AI_SELF_REFERENCE_RE.search(text))


def clean_narration(text: str) -> str:
    """Retire les scories de formatage que le TTS lirait à voix haute.

    Sans effet sur une narration déjà propre : chaque nettoyage est ciblé et
    ne s'applique que lorsqu'il est sans ambiguïté.
    """
    cleaned = _CODE_FENCE_RE.sub("", text).strip()
    # Gras/italique Markdown : on garde le mot, on jette les astérisques.
    cleaned = _EMPHASIS_RE.sub(r"\2", cleaned)

    lines = cleaned.split("\n", 1)
    if len(lines) == 2:
        first = lines[0].strip()
        lowered = first.lower()
        if (
            first.endswith(":")
            and len(first) <= _MAX_META_LINE_CHARS
            and any(keyword in lowered for keyword in _META_KEYWORDS)
        ):
            cleaned = lines[1].strip()

    return cleaned.strip()


# Seuils de détection du texte source cumulatif (frises/animations en
# construction progressive : chaque page PDF réaffiche tout ce qui a déjà été
# révélé + un élément de plus). En dessous, on ne touche à rien : mieux vaut
# rater un vrai doublon que couper du contenu légitime par erreur.
# Vérifié en conditions réelles : une première phase de frise peut être
# courte (« Phase 1 : origines. » ~20 caractères) ; un seuil trop haut la
# laissait passer sans déduplication. 15 reste sûr contre un simple en-tête
# partagé (« Chapitre 3 », 10 caractères, voir test dédié).
_DEDUPE_MIN_OVERLAP_CHARS = 15
_DEDUPE_MIN_SIMILARITY = 0.85


def dedupe_cumulative_source(previous_source: str, current_source: str) -> str:
    """Retire, du texte source de CETTE page, ce qui répète déjà la page
    précédente presque mot pour mot en début de texte.

    Cas visé : une frise en 5 phases exportée en 'build' PowerPoint, où la
    page 3 contient tout le texte de la page 2 (elle-même contenant celui de
    la page 1) suivi de la nouvelle phase. Sans ça, on demande au modèle
    d'« expliquer le contenu de cette page », qui grossit à chaque page —
    un modèle fidèle à la consigne récapitule donc de plus en plus.

    Ne touche JAMAIS aux images rendues (la frise complète doit rester
    visible à l'écran) : uniquement le texte envoyé au modèle pour savoir
    quoi raconter.
    """
    prev_norm = " ".join(previous_source.split())
    curr_norm = " ".join(current_source.split())
    if len(prev_norm) < _DEDUPE_MIN_OVERLAP_CHARS or not curr_norm or prev_norm == curr_norm:
        return current_source

    prefix_len = min(len(prev_norm), len(curr_norm))
    similarity = difflib.SequenceMatcher(None, prev_norm, curr_norm[:prefix_len]).ratio()
    if similarity < _DEDUPE_MIN_SIMILARITY:
        return current_source  # pas un vrai chevauchement, juste une coïncidence

    remainder = curr_norm[prefix_len:].strip()
    return remainder or current_source  # rien de nouveau -> on garde tout, par sécurité
