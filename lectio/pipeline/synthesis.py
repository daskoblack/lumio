"""Synthèse vocale par PAGE + boucle de correction bornée (phase 3).

Chaque page a son propre audio (garantit la synchro image/son). Pour chaque
page :
1. TTS du script actuel -> mesure de la durée RÉELLE (ffprobe, autorité finale)
2. Calibration du VoiceProfile (débit) à partir de cette mesure
3. Si un budget de mots cible existe ET que l'écart réel/cible dépasse le
   seuil : régénère le texte (même contexte narratif) et resynthétise.

Pour une cible EXPLICITE (`ctx.precise`), la correction est BIDIRECTIONNELLE
et bornée à `_MAX_AUDIO_ATTEMPTS_PRECISE` tentatives. Elle vise `target_seconds`
-- la durée réellement promise à l'utilisateur -- et RETRADUIT ce budget en
mots avec le débit fraîchement mesuré avant chaque nouvelle tentative.

Piège corrigé ici : comparer l'audio à `target_words / débit_calibré` était
circulaire, puisque le débit calibré vient de cette même mesure. L'écart
constaté valait donc toujours ~0%, y compris quand la vidéo faisait 13% de
moins que la durée demandée (voix edge-tts mesurée à 2,64 mots/s contre 2,3
supposés). Le contrôle ne détectait rien.

Pour une cible AUTO, la correction reste UNIQUE et n'agit qu'en cas de
dépassement (aucune promesse explicite à tenir sur une section non configurée).

Sans cible, aucune contrainte : la durée réelle du premier TTS fait foi.
"""

from __future__ import annotations

from pathlib import Path

from ..providers.llm.base import LLMProvider
from ..providers.tts.base import TTSProvider, VoiceProfile
from . import scripting
from .scripting import NarrationContext

_MAX_AUDIO_ATTEMPTS_PRECISE = 3  # 1 synthèse + jusqu'à 2 corrections
_MAX_AUDIO_ATTEMPTS_AUTO = 2     # 1 synthèse + 1 correction max (inchangé)


async def synthesize_slide(
    llm: LLMProvider,
    tts: TTSProvider,
    ctx: NarrationContext,
    voice: VoiceProfile,
    out_dir: Path,
    deviation_threshold: float,
    max_passes: int,
) -> None:
    """Synthétise (et corrige au besoin) l'audio d'une page. Mute la page en place."""
    slide = ctx.slide
    assert slide.script is not None, "Le scripting doit précéder la synthèse."

    out_path = str(out_dir / f"slide_{slide.index:03d}.mp3")
    result = await tts.synthesize(slide.script.text, voice, out_path)
    ctx.warning = result.warning

    slide.script.audio_path = result.audio_path
    slide.script.audio_duration_s = result.duration_s
    slide.actual_duration_s = result.duration_s
    voice.recalibrate(result.word_count, result.duration_s)

    if slide.script.word_count_target is None:
        return  # mode auto sans estimation : pas de contrainte

    # LA cible est en SECONDES : c'est ce que l'utilisateur a demandé.
    # La comparer à un budget de mots redivisé par le débit observé rendait le
    # contrôle circulaire -- l'écart mesuré valait toujours ~0%, même quand la
    # vidéo faisait 13% de moins que promis.
    slide_target_s = ctx.target_seconds
    if slide_target_s is None or slide_target_s <= 0:
        # Cible AUTO : pas de durée promise, on borne seulement l'emballement
        # à partir du budget de mots estimé.
        slide_target_s = slide.script.word_count_target / voice.speech_rate_wps

    max_attempts = _MAX_AUDIO_ATTEMPTS_PRECISE if ctx.precise else _MAX_AUDIO_ATTEMPTS_AUTO
    attempts = 1

    while attempts < max_attempts:
        gap = (result.duration_s - slide_target_s) / slide_target_s
        if ctx.precise:
            if abs(gap) <= deviation_threshold:
                break
        else:
            # Cible AUTO : comportement historique -- jamais de correction
            # pour un manque, uniquement en cas de dépassement.
            if gap <= deviation_threshold:
                break

        # Le débit vient d'être recalibré sur cette page : on retraduit la
        # durée promise en budget de mots AVEC ce débit réel, pour que la
        # régénération vise vraiment les secondes demandées.
        if ctx.precise and ctx.target_seconds:
            ctx.target_words = scripting.words_for_seconds(
                ctx.target_seconds, voice.speech_rate_wps, ctx.min_words
            )

        slide.script = await scripting.generate_slide_script(llm, ctx, max_passes)
        result = await tts.synthesize(slide.script.text, voice, out_path)
        ctx.warning = result.warning or ctx.warning
        slide.script.audio_path = result.audio_path
        slide.script.audio_duration_s = result.duration_s
        slide.actual_duration_s = result.duration_s
        voice.recalibrate(result.word_count, result.duration_s)
        attempts += 1

    final_gap = (result.duration_s - slide_target_s) / slide_target_s
    residual = abs(final_gap) > deviation_threshold if ctx.precise else final_gap > deviation_threshold
    if residual:
        section = ctx.section
        direction = "Dépassement" if final_gap > 0 else "Manque"
        section.synthesis_note = (
            f"{section.synthesis_note + ' ' if section.synthesis_note else ''}"
            f"{direction} résiduel de {abs(final_gap):.0%} sur la page "
            f"{slide.source_page} (cible {slide_target_s:.0f}s, réel {result.duration_s:.0f}s)."
        )
