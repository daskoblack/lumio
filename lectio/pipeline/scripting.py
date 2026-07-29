"""Génération des scripts 'professeur', PAR SLIDE, avec durée personnalisable.

Approche hybride :
- Chaque slide (page) a son propre audio -> synchro image/son garantie par
  construction (pas de découpage artificiel du temps).
- Mais le texte est généré SÉQUENTIELLEMENT au sein d'une section, avec le
  contexte de ce qui vient d'être dit (page précédente) et un aperçu de ce
  qui arrive (page suivante). Le professeur peut ainsi enchaîner et même
  annoncer la suite ("Nous allons maintenant voir...") sans jamais répéter
  l'intro sur la slide suivante : effet de continuité, sans perdre la
  fiabilité de la synchro par page.

Principe de durée (inchangé) :
- Si l'utilisateur a fixé `target_duration_s` sur la SECTION, ce budget est
  réparti entre ses slides (au prorata de l'estimation initiale), et chaque
  slide vise son propre budget de mots.
- Vérification du nombre de mots APRÈS génération (gratuit, sans TTS). Hors
  tolérance -> UNE seule passe de correction du texte (boucle bornée).
- Sans cible : génération libre, aucune contrainte.
"""

from __future__ import annotations

from ..core.models import Script, Section, SectionKind, Slide
from ..core.textutil import clean_narration, is_pronounceable
from ..core.timing import count_words, deviation
from ..providers.llm.base import LLMProvider

_FALLBACK_MAX_CHARS = 600  # de quoi une narration de secours plausible, pas plus

_SYSTEM = """Tu es un professeur qui donne un cours à l'oral, face caméra, page \
par page d'un support. Tu produis une NARRATION ORIGINALE, naturelle et \
pédagogique — PAS une lecture du support. Le cours doit sonner comme UN SEUL \
flux continu même s'il est écrit page par page : n'introduis pas deux fois le \
même sujet, enchaîne naturellement, et annonce parfois ce qui arrive ensuite \
avant un changement de page ("Nous allons maintenant voir...") plutôt que de \
répéter l'annonce sur la page suivante. Français clair, phrases dites à voix \
haute. Ne mets aucune didascalie, aucun titre, aucune balise : uniquement le \
texte que le professeur prononce."""

_KIND_HINTS = {
    SectionKind.INTRO: "Accroche l'auditeur et annonce ce qui va être vu.",
    SectionKind.CONCEPT: "Explique le concept clairement, avec une intuition avant la définition.",
    SectionKind.EXAMPLE: "Déroule un exemple concret pas à pas.",
    SectionKind.EXERCISE: "Guide la réflexion sur l'exercice sans donner trop vite la réponse.",
    SectionKind.SUMMARY: "Récapitule les points essentiels de façon synthétique.",
    SectionKind.OTHER: "",
}

_PREVIEW_CHARS = 250  # aperçu de la page suivante : juste de quoi teaser, pas tout dévoiler


def _budget_instruction(target_words: int, tolerance: float) -> str:
    low = round(target_words * (1 - tolerance))
    high = round(target_words * (1 + tolerance))
    return (
        f"Contrainte de durée pour CETTE page : vise environ {target_words} mots "
        f"(entre {low} et {high}). Pour tenir ce budget, ADAPTE la quantité de "
        f"contenu (nombre d'exemples, niveau de détail), sans jamais accélérer "
        f"ou compresser artificiellement le style."
    )


def _build_user_prompt(
    section: Section,
    slide: Slide,
    position: int,
    total: int,
    previous_text: str | None,
    next_slide: Slide | None,
    target_words: int | None,
    tolerance: float,
) -> str:
    hint = _KIND_HINTS.get(section.kind, "")
    budget = _budget_instruction(target_words, tolerance) if target_words else (
        "Rédige une narration complète et naturelle, de la longueur qui convient "
        "au contenu (pas de contrainte de durée)."
    )

    context_lines = [
        f"Partie du cours : {section.title}",
        f"Type : {section.kind.value}. {hint}",
        f"Résumé de la partie : {section.summary}",
        f"Page {position}/{total} de cette partie.",
    ]

    if previous_text is None:
        context_lines.append(
            "C'est la PREMIÈRE page de cette partie : introduis normalement le sujet."
        )
    else:
        context_lines.append(
            "Tu viens juste de dire (ne le répète pas, enchaîne directement dessus) :\n"
            f"« {previous_text} »"
        )

    if next_slide is not None:
        preview = next_slide.source_text()[:_PREVIEW_CHARS]
        context_lines.append(
            "Aperçu de ce qui arrive juste après (pour préparer une transition "
            f"naturelle en fin de texte, SANS le détailler ni le résumer) :\n« {preview}… »"
        )
    else:
        context_lines.append(
            "C'est la DERNIÈRE page de cette partie : conclus-la normalement."
        )

    return (
        "\n".join(context_lines)
        + f"\n\nContenu source de CETTE page à expliquer :\n{slide.source_text()}\n\n"
        + f"{budget}\n\nRédige uniquement la narration parlée de cette page."
    )


def _build_correction_prompt(previous: str, actual_words: int, target_words: int, tolerance: float) -> str:
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
        f"{direction} : {lever}. Garde le même sujet, le même ton, et les mêmes "
        f"transitions d'enchaînement avec ce qui précède/suit.\n\n"
        f"Narration à corriger :\n{previous}\n\n"
        f"Renvoie uniquement la narration corrigée."
    )


def _fallback_narration(section: Section, slide: Slide) -> str:
    """Narration de secours quand l'IA ne rend rien de prononçable.

    Bâtie sur le contenu réel de la page : mieux vaut une explication sobre
    qu'une vidéo qui échoue entièrement à cause d'une seule page.
    """
    for candidate in (slide.source_text().strip(), slide.title.strip(), section.title.strip()):
        if is_pronounceable(candidate):
            return candidate[:_FALLBACK_MAX_CHARS]
    return "Passons à la page suivante."


async def generate_slide_script(
    llm: LLMProvider,
    section: Section,
    slide: Slide,
    position: int,
    total: int,
    previous_text: str | None,
    next_slide: Slide | None,
    target_words: int | None,
    tolerance: float,
    max_passes: int,
) -> Script:
    """Génère (et corrige au besoin) la narration d'UNE slide, avec contexte."""
    user_prompt = _build_user_prompt(
        section, slide, position, total, previous_text, next_slide, target_words, tolerance
    )
    text = clean_narration(await llm.complete(system=_SYSTEM, user=user_prompt, temperature=0.5))

    # Une réponse sans lettre ni chiffre (« ... », « --- ») ferait échouer la
    # synthèse vocale plus loin, avec un message incompréhensible : on la
    # rattrape ici, où l'on peut encore redemander à l'IA.
    fallback_used = False
    if not is_pronounceable(text):
        retry = clean_narration(
            await llm.complete(system=_SYSTEM, user=user_prompt, temperature=0.7)
        )
        if is_pronounceable(retry):
            text = retry
        else:
            text = _fallback_narration(section, slide)
            fallback_used = True

    actual = count_words(text)
    generation_pass = 1

    if target_words is not None and max_passes >= 2:
        if deviation(actual, target_words) > tolerance:
            corrected = clean_narration(await llm.complete(
                system=_SYSTEM,
                user=_build_correction_prompt(text, actual, target_words, tolerance),
                temperature=0.5,
            ))
            # Une correction qui rendrait le texte imprononçable est ignorée :
            # mieux vaut garder une durée imparfaite qu'un audio impossible.
            if is_pronounceable(corrected):
                text = corrected
                actual = count_words(text)
                generation_pass = 2

    return Script(
        slide_id=slide.id,
        text=text,
        word_count_target=target_words,
        word_count_actual=actual,
        generation_pass=generation_pass,
        fallback_used=fallback_used,
    )


def distribute_target_words(section: Section, slides: list[Slide], target_words: int) -> list[int]:
    """Répartit un budget de mots cible (dérivé de target_duration_s) entre les slides.

    Même logique proportionnelle que l'estimation initiale (poids = part de
    `estimated_narration_words` de chaque slide), pour rester cohérent avec le
    découpage déjà présenté à l'utilisateur.
    """
    if not slides:
        return []

    total_estimated = sum(s.estimated_narration_words for s in slides)
    weights = (
        [s.estimated_narration_words for s in slides]
        if total_estimated > 0
        else [1] * len(slides)
    )
    total_weight = sum(weights)

    shares: list[int] = []
    remaining = target_words
    for i, weight in enumerate(weights):
        if i == len(slides) - 1:
            shares.append(max(1, remaining))
        else:
            share = max(1, round(target_words * weight / total_weight))
            shares.append(share)
            remaining -= share
    return shares
