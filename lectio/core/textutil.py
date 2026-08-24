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


# Deux passages sont « les mêmes » au-delà de ce seuil de ressemblance. Assez
# haut pour ne pas confondre deux phrases distinctes du même cours, assez
# souple pour absorber une coupure de ligne ou une ponctuation qui change.
_DEDUPE_MIN_SIMILARITY = 0.90
# En dessous, un passage est trop court pour qu'une ressemblance signifie
# quoi que ce soit (« 1/5 », « Fig. 2 »).
_DEDUPE_MIN_SEGMENT_CHARS = 12

# Volontairement SANS « : » : en français il introduit le plus souvent la
# suite de la même idée (« Étape 2 : dissociation »), et découper dessus
# fragmenterait le sens au lieu de séparer deux passages distincts.
_SEGMENT_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|\n+")


def _segments(text: str) -> list[str]:
    """Découpe une page en passages comparables (lignes et phrases)."""
    return [part.strip() for part in _SEGMENT_SPLIT_RE.split(text) if part.strip()]


def _already_seen(segment: str, previous: list[str]) -> bool:
    """Ce passage figurait-il déjà, où que ce soit, sur la page précédente ?"""
    normalized = " ".join(segment.split()).lower()
    for earlier in previous:
        other = " ".join(earlier.split()).lower()
        if normalized == other:
            return True
        if len(normalized) < _DEDUPE_MIN_SEGMENT_CHARS:
            continue  # trop court : seule l'égalité stricte compte
        if difflib.SequenceMatcher(None, normalized, other).ratio() >= _DEDUPE_MIN_SIMILARITY:
            return True
    return False


def dedupe_cumulative_source(previous_source: str, current_source: str) -> str:
    """Retire du texte de CETTE page les passages déjà présents sur la précédente.

    Cas visé : une diapositive qui se dévoile étape par étape (animation
    PowerPoint exportée en PDF). Chaque page réaffiche tout ce qui précède,
    plus un élément. Sans ce filtrage, on demande au modèle d'« expliquer le
    contenu de cette page », qui grossit à chaque étape — un modèle fidèle à
    la consigne récapitule donc de plus en plus.

    La comparaison se fait passage par passage et NON par préfixe : une
    version antérieure exigeait que la page précédente soit un préfixe exact,
    ce qui échouait dès qu'un numéro de page, un pied de page, ou un simple
    changement d'ordre de lecture s'intercalait — c'est-à-dire sur la plupart
    des supports réels.

    Ne touche JAMAIS aux images rendues (la diapositive complète doit rester
    visible à l'écran) : uniquement le texte envoyé au modèle pour savoir
    quoi raconter.
    """
    previous = _segments(previous_source)
    current = _segments(current_source)
    if not previous or not current:
        return current_source

    kept = [segment for segment in current if not _already_seen(segment, previous)]
    if not kept:
        return current_source  # rien de neuf : on garde tout, par sécurité
    if len(kept) == len(current):
        return current_source  # aucun recoupement : page sans lien, texte intact
    return "\n".join(kept)
