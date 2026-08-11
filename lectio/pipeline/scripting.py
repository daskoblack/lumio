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

Principe de durée :
- Si l'utilisateur a fixé `target_duration_s` sur la SECTION, ce budget est
  réparti entre ses pages, et chaque page vise son propre budget de mots
  (`NarrationContext.precise = True`).
- Vérification du nombre de mots APRÈS génération (gratuit, sans TTS). Hors
  tolérance -> correction BIDIRECTIONNELLE et itérative, bornée à
  `max_generation_passes` tentatives (voir `_refine_to_target`). Le sens
  "allonger" est strictement borné au texte source de la page (jamais
  d'invention) -- contrairement à l'ancien comportement (retiré en v1.0.5)
  qui produisait des inventions hors sujet en demandant d'« ajouter un
  exemple » sans contrainte de source.
- Une cible AUTO (estimée, jamais choisie par l'utilisateur) garde le
  comportement historique : correction unique, uniquement en cas de
  dépassement.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from ..core.models import Script, Section, SectionKind, Slide
from ..core.textutil import clean_narration, has_suspicious_pattern, is_pronounceable
from ..core.timing import count_words
from ..providers.llm.base import LLMProvider

_FALLBACK_MAX_CHARS = 600   # de quoi une narration de secours plausible, pas plus
_PREVIEW_CHARS = 250        # aperçu de la page suivante : de quoi amener, pas dévoiler
_SUMMARY_CHARS = 130        # longueur d'un rappel de page déjà traitée
_MAX_SUMMARIES = 6          # borne la taille du prompt sur un cours long

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
    # Texte source à narrer pour cette page, si différent de
    # `slide.source_text()` (voir `dedupe_cumulative_source`). None = aucun
    # chevauchement détecté, on utilise le texte de la page tel quel.
    content_to_narrate: str | None = None
    target_words: int | None = None
    # Tolérance de dépassement avant correction. Plus large pour une cible AUTO
    # (simple plafond estimé) que pour une cible EXPLICITE (choisie par l'utilisateur).
    tolerance: float = 0.10
    # True uniquement pour une cible EXPLICITE (l'utilisateur a choisi une
    # durée sur cette section) : déclenche la correction BIDIRECTIONNELLE et
    # itérative (voir _refine_to_target). Une cible AUTO reste corrigée au
    # mieux, uniquement en cas de dépassement, en une seule passe -> aucune
    # promesse explicite à tenir, pas la peine d'y consacrer plus d'appels IA.
    precise: bool = False
    # Rempli par la synthèse : avertissement non bloquant (voix remplacée…).
    warning: str | None = None
    # Consigne ponctuelle de l'utilisateur pour la RÉGÉNÉRATION CIBLÉE d'une
    # section depuis l'écran de lecture ("plus court", "reformule l'exemple
    # avec des fruits"...). None en génération normale.
    user_instruction: str | None = None


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
    if ctx.section.context:
        # Rappelé à CHAQUE page (pas seulement la première) : c'est l'ancrage
        # fixe qui limite la dérive/répétition sur les sections longues, là où
        # le seul fil "page précédente -> page suivante" pouvait s'égarer.
        lines.append(
            "Contexte de cette partie, à respecter tout du long sans s'en "
            f"écarter :\n{ctx.section.context}"
        )

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

    if ctx.user_instruction:
        # Placée juste avant le contenu, en dernière position pour que ce soit
        # la consigne la plus "fraîche" pour le modèle. Prioritaire mais ne
        # doit pas casser le reste (cohérence de section, budget) : le modèle
        # doit l'appliquer EN PLUS, pas à la place, des règles ci-dessus.
        lines.append(
            "Consigne spécifique de l'utilisateur pour CETTE page, à respecter "
            f"en priorité sans perdre le fil du cours : {ctx.user_instruction}"
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
        + f"\n\nContenu de CETTE page à expliquer :\n{ctx.content_to_narrate or ctx.slide.source_text()}\n\n"
        + f"{budget}\n\nRédige uniquement la narration parlée de cette page."
    )


def _build_trim_prompt(previous: str, actual_words: int, target_words: int) -> str:
    """Demande de RACCOURCIR. Jamais d'invention possible dans ce sens : on
    ne fait que retirer, le risque de dérive hors sujet est nul."""
    return (
        f"La narration suivante fait {actual_words} mots, au-dessus de la "
        f"cible de {target_words} mots. Réécris-la plus courte : retire "
        f"des détails secondaires ou un exemple, sans rien ajouter de nouveau. "
        f"Garde le même sujet, le même ton, et les mêmes transitions "
        f"d'enchaînement avec ce qui précède/suit.\n\n"
        f"Narration à corriger :\n{previous}\n\n"
        f"Renvoie uniquement la narration raccourcie."
    )


def _build_extend_prompt(previous: str, actual_words: int, target_words: int, source: str) -> str:
    """Demande d'ALLONGER, en restant strictement dans la matière déjà
    fournie par la page (jamais un exemple ou un fait qui n'y figure pas).

    Distinct de l'ancien comportement (retiré en v1.0.5 après avoir produit
    des inventions hors sujet en usage réel, jusqu'à des ruptures de
    personnage) : ici, le développement est explicitement borné au texte
    source de la page, pas à l'imagination du modèle.
    """
    return (
        f"La narration suivante fait {actual_words} mots, en dessous de la "
        f"cible de {target_words} mots. Développe-la : explique plus en détail "
        f"un point déjà présent dans le texte source ci-dessous, ou reformule "
        f"une idée pour être plus complet. N'INVENTE RIEN : n'ajoute aucun "
        f"exemple, fait ou notion qui ne figure pas dans ce texte source. Si le "
        f"texte source ne contient vraiment rien de plus à en tirer, reformule "
        f"plus lentement plutôt que d'ajouter une idée nouvelle.\n\n"
        f"Texte source de cette page (seule matière disponible) :\n{source}\n\n"
        f"Narration à développer :\n{previous}\n\n"
        f"Renvoie uniquement la narration développée."
    )


def _is_valid_narration(text: str) -> bool:
    """Texte utilisable : prononçable ET sans rupture de personnage détectée."""
    return is_pronounceable(text) and not has_suspicious_pattern(text)


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
    max_passes: int,
) -> Script:
    """Génère (et corrige au besoin) la narration d'UNE page, avec son contexte."""
    user_prompt = _build_user_prompt(ctx, ctx.tolerance)
    text = clean_narration(await llm.complete(system=_SYSTEM, user=user_prompt, temperature=0.5))

    # Deux défauts rattrapés ici, où l'on peut encore redemander à l'IA :
    # - une réponse sans lettre ni chiffre (« ... », « --- ») ferait échouer
    #   la synthèse vocale plus loin, avec un message incompréhensible ;
    # - une rupture de personnage (gabarit non rempli, le modèle qui se
    #   présente comme une IA) est textuellement valide mais n'a rien à faire
    #   dans un cours : elle passerait inaperçue jusqu'à l'oreille de l'utilisateur.
    fallback_used = False
    if not _is_valid_narration(text):
        retry = clean_narration(
            await llm.complete(system=_SYSTEM, user=user_prompt, temperature=0.7)
        )
        if _is_valid_narration(retry):
            text = retry
        else:
            text = _fallback_narration(ctx)
            fallback_used = True

    actual = count_words(text)
    generation_pass = 1

    if not fallback_used and ctx.target_words is not None and max_passes >= 2:
        if ctx.precise:
            # Cible EXPLICITE : converge dans les deux sens, sur plusieurs
            # passes si besoin, jusqu'à la marge configurée.
            text, actual, generation_pass = await _refine_to_target(
                llm, ctx, text, actual, max_passes
            )
        else:
            # Cible AUTO : comportement historique, inchangé -- correction
            # UNIQUEMENT en cas de dépassement, une seule tentative. Un
            # manque reste fidèle au contenu et est accepté tel quel (aucune
            # promesse explicite de durée à tenir sur une section que
            # l'utilisateur n'a pas configurée).
            overshoot = (actual - ctx.target_words) / ctx.target_words
            if overshoot > ctx.tolerance:
                corrected = clean_narration(await llm.complete(
                    system=_SYSTEM,
                    user=_build_trim_prompt(text, actual, ctx.target_words),
                    temperature=0.5,
                ))
                if _is_valid_narration(corrected):
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


async def _refine_to_target(
    llm: LLMProvider, ctx: NarrationContext, text: str, actual: int, max_passes: int
) -> tuple[str, int, int]:
    """Boucle bornée : corrige dans les deux sens jusqu'à tenir la tolérance
    de `ctx`, ou jusqu'à épuiser `max_passes` tentatives.

    Le sens "allonger" est strictement borné au texte source de la page
    (voir `_build_extend_prompt`) : jamais d'invention, contrairement à
    l'ancien comportement retiré en v1.0.5.
    """
    assert ctx.target_words is not None
    source = ctx.content_to_narrate or ctx.slide.source_text()
    generation_pass = 1

    while generation_pass < max_passes:
        gap = (actual - ctx.target_words) / ctx.target_words
        if abs(gap) <= ctx.tolerance:
            break

        prompt = (
            _build_trim_prompt(text, actual, ctx.target_words) if gap > 0
            else _build_extend_prompt(text, actual, ctx.target_words, source)
        )
        corrected = clean_narration(await llm.complete(
            system=_SYSTEM, user=prompt, temperature=0.5,
        ))
        generation_pass += 1

        # Une correction invalide (imprononçable, hors personnage, ou une
        # extension qui a fini par inventer malgré la consigne) est écartée :
        # on garde le dernier texte fiable plutôt que de dégrader la qualité
        # pour gagner en précision.
        if not _is_valid_narration(corrected):
            break
        text, actual = corrected, count_words(corrected)

    return text, actual, generation_pass


def distribute_target_words(
    section: Section, slides: list[Slide], target_words: int, min_words_per_page: int = 70
) -> list[int]:
    """Répartit un budget de mots cible (dérivé de target_duration_s) entre les pages.

    Même logique proportionnelle que l'estimation initiale (poids = part de
    `estimated_narration_words` de chaque page), pour rester cohérent avec le
    découpage déjà présenté à l'utilisateur. Chaque page reçoit AU MOINS
    `min_words_per_page` : si l'utilisateur choisit une durée très courte pour
    une section à beaucoup de pages, mieux vaut dépasser légèrement sa
    consigne (l'écart résiduel est déjà signalé ailleurs) qu'imposer un
    budget trop petit pour être écrit correctement.
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
            shares.append(max(min_words_per_page, remaining))
        else:
            share = max(min_words_per_page, round(target_words * weight / total_weight))
            shares.append(share)
            remaining -= share
    return shares
