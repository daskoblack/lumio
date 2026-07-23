"""Génération des scripts 'professeur' avec durée personnalisable (cœur phase 2).

Principe :
- Si l'utilisateur a fixé `target_duration_s`, on en dérive un budget de mots
  (cible × débit) et on demande au LLM d'ADAPTER LA QUANTITÉ DE CONTENU pour
  le tenir (plus/moins d'exemples et de détails), pas de changer le débit.
- On vérifie le nombre de mots APRÈS génération (gratuit, sans TTS). Hors
  tolérance -> UNE seule passe de correction du texte (boucle bornée).
- Sans cible : génération libre, aucune contrainte.

Aucun round-trip TTS ici : l'ajustement se fait au niveau du texte.
"""

from __future__ import annotations

from ..core.models import Script, Section, SectionKind
from ..core.timing import count_words, deviation, duration_to_words
from ..providers.llm.base import LLMProvider

_SYSTEM = """Tu es un professeur qui explique un cours à l'oral, face caméra. \
Tu produis une NARRATION ORIGINALE, naturelle et pédagogique — PAS une lecture \
du support. Français clair, phrases dites à voix haute. Ne mets aucune didascalie, \
aucun titre, aucune balise : uniquement le texte que le professeur prononce."""

_KIND_HINTS = {
    SectionKind.INTRO: "Accroche l'auditeur et annonce ce qui va être vu.",
    SectionKind.CONCEPT: "Explique le concept clairement, avec une intuition avant la définition.",
    SectionKind.EXAMPLE: "Déroule un exemple concret pas à pas.",
    SectionKind.EXERCISE: "Guide la réflexion sur l'exercice sans donner trop vite la réponse.",
    SectionKind.SUMMARY: "Récapitule les points essentiels de façon synthétique.",
    SectionKind.OTHER: "",
}


def _budget_instruction(target_words: int, tolerance: float) -> str:
    low = round(target_words * (1 - tolerance))
    high = round(target_words * (1 + tolerance))
    return (
        f"Contrainte de durée : vise environ {target_words} mots "
        f"(entre {low} et {high}). Pour tenir ce budget, ADAPTE la quantité de "
        f"contenu (nombre d'exemples, niveau de détail), sans jamais accélérer "
        f"ou compresser artificiellement le style."
    )


def _build_user_prompt(
    section: Section, source_text: str, target_words: int | None, tolerance: float
) -> str:
    hint = _KIND_HINTS.get(section.kind, "")
    budget = _budget_instruction(target_words, tolerance) if target_words else (
        "Rédige une narration complète et naturelle, de la longueur qui convient "
        "au contenu (pas de contrainte de durée)."
    )
    return (
        f"Section : {section.title}\n"
        f"Type : {section.kind.value}. {hint}\n"
        f"Résumé : {section.summary}\n\n"
        f"Contenu source à expliquer :\n{source_text}\n\n"
        f"{budget}\n\n"
        f"Rédige uniquement la narration parlée."
    )


def _build_correction_prompt(
    section: Section, previous: str, actual_words: int, target_words: int, tolerance: float
) -> str:
    direction = "raccourcir" if actual_words > target_words else "allonger"
    lever = (
        "retire des détails ou un exemple"
        if actual_words > target_words
        else "ajoute un exemple ou développe une explication"
    )
    low = round(target_words * (1 - tolerance))
    high = round(target_words * (1 + tolerance))
    return (
        f"La narration suivante fait {actual_words} mots, mais la cible est "
        f"{target_words} mots (fourchette {low}-{high}). Réécris-la pour "
        f"{direction} : {lever}. Garde le même sujet et le même ton, ne change "
        f"pas le style de diction.\n\n"
        f"Narration à corriger :\n{previous}\n\n"
        f"Renvoie uniquement la narration corrigée."
    )


async def generate_script(
    llm: LLMProvider,
    section: Section,
    source_text: str,
    speech_rate_wps: float,
    tolerance: float,
    max_passes: int,
) -> Script:
    """Génère (et corrige au besoin) la narration d'une section."""
    target_words: int | None = None
    if section.target_duration_s is not None:
        target_words = duration_to_words(section.target_duration_s, speech_rate_wps)

    text = await llm.complete(
        system=_SYSTEM,
        user=_build_user_prompt(section, source_text, target_words, tolerance),
        temperature=0.5,
    )
    text = text.strip()
    actual = count_words(text)
    generation_pass = 1

    # Correction unique, uniquement si une cible est fixée et l'écart trop grand.
    if target_words is not None and max_passes >= 2:
        if deviation(actual, target_words) > tolerance:
            corrected = await llm.complete(
                system=_SYSTEM,
                user=_build_correction_prompt(
                    section, text, actual, target_words, tolerance
                ),
                temperature=0.5,
            )
            text = corrected.strip()
            actual = count_words(text)
            generation_pass = 2

    return Script(
        section_id=section.id,
        text=text,
        word_count_target=target_words,
        word_count_actual=actual,
        generation_pass=generation_pass,
    )
