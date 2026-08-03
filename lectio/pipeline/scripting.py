"""Génération des scripts 'professeur', PAGE PAR PAGE, dans l'ordre du cours.

Approche :
- Chaque page a son propre audio -> synchro image/son garantie par
  construction (pas de découpage artificiel du temps).
- Le texte est généré SÉQUENTIELLEMENT sur TOUT le cours, jamais section par
  section en parallèle. Chaque page connaît donc réellement ce qui a déjà été
  dit — y compris au-delà d'une frontière de section, là où se produisaient
  les répétitions (chaque section ré-introduisait le sujet depuis zéro).
- Le contexte transmis est borné : texte complet de la page précédente (pour
  un enchaînement fluide) + résumés courts des pages d'avant (pour ne pas
  redire ce qui a déjà été traité) + aperçu de la page suivante (pour amener
  une transition).

Principe de durée (inchangé) :
- Si l'utilisateur a fixé `target_duration_s` sur la SECTION, ce budget est
  réparti entre ses pages, et chaque page vise son propre budget de mots.
- Vérification du nombre de mots APRÈS génération (gratuit, sans TTS). Hors
  tolérance -> UNE seule passe de correction du texte (boucle bornée).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.models import Script, Section, SectionKind, Slide
from ..core.textutil import clean_narration, is_pronounceable
from ..core.timing import count_words, deviation
from ..providers.llm.base import LLMProvider

_FALLBACK_MAX_CHARS = 600   # de quoi une narration de secours plausible, pas plus
_PREVIEW_CHARS = 250        # aperçu de la page suivante : de quoi amener, pas dévoiler
_SUMMARY_CHARS = 130        # longueur d'un rappel de page déjà traitée
_MAX_SUMMARIES = 6          # borne la taille du prompt sur un cours long


@dataclass
class NarrationContext:
    """Tout ce que le professeur doit savoir pour rédiger UNE page.

    Regroupé en un objet plutôt qu'une dizaine de paramètres : la liste
    s'allongeait à chaque besoin de contexte supplémentaire.
    """

    section: Section
    slide: Slide
    position: int                  # rang de la page dans le COURS entier (1-based)
    total: int                     # nombre total de pages du cours
    starts_new_section: bool = False
    previous_text: str | None = None
    previous_summaries: list[str] = field(default_factory=list)
    next_slide: Slide | None = None
    target_words: int | None = None
    # Rempli par la synthèse : avertissement non bloquant (voix remplacée…).
    warning: str | None = None


_SYSTEM = """Tu es un professeur qui donne un cours à l'oral, face caméra, page \
par page d'un support. Tu produis une NARRATION ORIGINALE, naturelle et \
pédagogique — PAS une lecture du support.

RÈGLE ABSOLUE : le cours est UN SEUL discours continu, du début à la fin. \
Tu ne réintroduis JAMAIS le cours, le sujet global ni ce qui a déjà été \
expliqué. Tu ne redis pas ce que tu viens de dire avec d'autres mots. Chaque \
page apporte quelque chose de NOUVEAU et enchaîne sur la précédente.

Français clair, phrases faites pour être dites à voix haute. Ne mets aucune \
didascalie, aucun titre, aucune balise, aucun préfixe : uniquement le texte \
que le professeur prononce."""

_KIND_HINTS = {
    SectionKind.INTRO: "Accroche l'auditeur et annonce ce qui va être vu.",
    SectionKind.CONCEPT: "Explique le concept clairement, avec une intuition avant la définition.",
    SectionKind.EXAMPLE: "Déroule un exemple concret pas à pas.",
    SectionKind.EXERCISE: "Guide la réflexion sur l'exercice sans donner trop vite la réponse.",
    SectionKind.SUMMARY: "Récapitule les points essentiels de façon synthétique.",
    SectionKind.OTHER: "",
}


def summarize_for_context(text: str) -> str:
    """Rappel court d'une page déjà narrée, pour éviter d'y revenir."""
    condensed = " ".join(text.split())
    return condensed[:_SUMMARY_CHARS] + ("…" if len(condensed) > _SUMMARY_CHARS else "")


def _budget_instruction(target_words: int, tolerance: float) -> str:
    low = round(target_words * (1 - tolerance))
    high = round(target_words * (1 + tolerance))
    return (
        f"Contrainte de durée pour CETTE page : vise environ {target_words} mots "
        f"(entre {low} et {high}). Pour tenir ce budget, ADAPTE la quantité de "
        f"contenu (nombre d'exemples, niveau de détail), sans jamais accélérer "
        f"ou compresser artificiellement le style."
    )


def _build_user_prompt(ctx: NarrationContext, tolerance: float) -> str:
    hint = _KIND_HINTS.get(ctx.section.kind, "")
    budget = _budget_instruction(ctx.target_words, tolerance) if ctx.target_words else (
        "Rédige une narration complète et naturelle, de la longueur qui convient "
        "au contenu (pas de contrainte de durée)."
    )

    lines = [
        f"Page {ctx.position} sur {ctx.total} du cours.",
        f"Partie en cours : « {ctx.section.title} » — {ctx.section.kind.value}. {hint}",
    ]
    if ctx.section.summary:
        lines.append(f"Ce que couvre cette partie : {ctx.section.summary}")

    # --- Ce qui a déjà été dit --------------------------------------------
    if ctx.position == 1:
        lines.append(
            "C'est la TOUTE PREMIÈRE page du cours : c'est le seul endroit où tu "
            "introduis le sujet."
        )
    else:
        if ctx.previous_summaries:
            deja = "\n".join(f"  - {s}" for s in ctx.previous_summaries)
            lines.append(
                "Pages déjà traitées avant (NE REVIENS PAS dessus, ne les résume pas) :\n"
                + deja
            )
        if ctx.previous_text:
            lines.append(
                "Tu viens exactement de dire ceci (enchaîne dessus sans le répéter "
                f"ni le reformuler) :\n« {ctx.previous_text} »"
            )
        if ctx.starts_new_section:
            lines.append(
                f"Cette page ouvre une nouvelle partie « {ctx.section.title} ». "
                "Amène-la par une courte transition (une phrase), SANS réintroduire "
                "le cours ni rappeler ce qui précède."
            )

    # --- Ce qui arrive après ----------------------------------------------
    if ctx.next_slide is not None:
        preview = ctx.next_slide.source_text()[:_PREVIEW_CHARS]
        lines.append(
            "Aperçu de la page suivante, uniquement pour préparer une transition "
            f"en fin de texte (ne la traite pas, ne la résume pas) :\n« {preview}… »"
        )
    else:
        lines.append("C'est la DERNIÈRE page du cours : conclus-le.")

    return (
        "\n".join(lines)
        + f"\n\nContenu de CETTE page à expliquer :\n{ctx.slide.source_text()}\n\n"
        + f"{budget}\n\nRédige uniquement la narration parlée de cette page."
    )


def _build_correction_prompt(
    previous: str, actual_words: int, target_words: int, tolerance: float
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
        f"{direction} : {lever}. Garde le même sujet, le même ton, et les mêmes "
        f"transitions d'enchaînement avec ce qui précède/suit.\n\n"
        f"Narration à corriger :\n{previous}\n\n"
        f"Renvoie uniquement la narration corrigée."
    )


def _fallback_narration(ctx: NarrationContext) -> str:
    """Narration de secours quand l'IA ne rend rien de prononçable.

    Bâtie sur le contenu réel de la page : mieux vaut une explication sobre
    qu'une vidéo qui échoue entièrement à cause d'une seule page.
    """
    for candidate in (
        ctx.slide.source_text().strip(),
        ctx.slide.title.strip(),
        ctx.section.title.strip(),
    ):
        if is_pronounceable(candidate):
            return candidate[:_FALLBACK_MAX_CHARS]
    return "Passons à la page suivante."


def emergency_script(ctx: NarrationContext) -> Script:
    """Narration de repli SANS aucun appel à l'IA.

    Utilisée quand le fournisseur d'IA est totalement indisponible sur cette
    page : la vidéo reste produite, avec cette page signalée comme dégradée,
    plutôt que de perdre tout le travail déjà fait.
    """
    text = _fallback_narration(ctx)
    return Script(
        slide_id=ctx.slide.id,
        text=text,
        word_count_target=ctx.target_words,
        word_count_actual=count_words(text),
        generation_pass=1,
        fallback_used=True,
    )


async def generate_slide_script(
    llm: LLMProvider,
    ctx: NarrationContext,
    tolerance: float,
    max_passes: int,
) -> Script:
    """Génère (et corrige au besoin) la narration d'UNE page, avec son contexte."""
    user_prompt = _build_user_prompt(ctx, tolerance)
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
            text = _fallback_narration(ctx)
            fallback_used = True

    actual = count_words(text)
    generation_pass = 1

    if ctx.target_words is not None and max_passes >= 2:
        if deviation(actual, ctx.target_words) > tolerance:
            corrected = clean_narration(await llm.complete(
                system=_SYSTEM,
                user=_build_correction_prompt(text, actual, ctx.target_words, tolerance),
                temperature=0.5,
            ))
            # Une correction qui rendrait le texte imprononçable est ignorée :
            # mieux vaut une durée imparfaite qu'un audio impossible.
            if is_pronounceable(corrected):
                text = corrected
                actual = count_words(text)
                generation_pass = 2

    return Script(
        slide_id=ctx.slide.id,
        text=text,
        word_count_target=ctx.target_words,
        word_count_actual=actual,
        generation_pass=generation_pass,
        fallback_used=fallback_used,
    )


def distribute_target_words(section: Section, slides: list[Slide], target_words: int) -> list[int]:
    """Répartit un budget de mots cible (dérivé de target_duration_s) entre les pages.

    Même logique proportionnelle que l'estimation initiale (poids = part de
    `estimated_narration_words` de chaque page), pour rester cohérent avec le
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
