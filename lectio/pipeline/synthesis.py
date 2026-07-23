"""Synthèse vocale par SLIDE + boucle de correction bornée (phase 3).

Chaque slide a son propre audio (garantit la synchro image/son). Pour chaque
slide :
1. TTS du script actuel -> mesure de la durée RÉELLE (ffprobe, autorité finale)
2. Calibration du VoiceProfile (débit) à partir de cette mesure
3. Si un budget de mots cible existe (dérivé du target_duration_s de la
   section) ET l'écart réel/cible dépasse le seuil : UNE seule régénération
   du texte de CETTE slide (contexte narratif inchangé : même page précédente/
   suivante), + un seul nouveau TTS. Résultat accepté quel que soit l'écart
   résiduel, avec une note d'écart sur la section.

Sans cible, aucune contrainte : la durée réelle du premier TTS fait foi.
"""

from __future__ import annotations

from pathlib import Path

from ..core.models import Section, Slide
from ..core.timing import deviation
from ..providers.llm.base import LLMProvider
from ..providers.tts.base import TTSProvider, VoiceProfile
from . import scripting


async def synthesize_slide(
    llm: LLMProvider,
    tts: TTSProvider,
    section: Section,
    slide: Slide,
    position: int,
    total: int,
    previous_text: str | None,
    next_slide: Slide | None,
    voice: VoiceProfile,
    out_dir: Path,
    tolerance: float,
    deviation_threshold: float,
    max_passes: int,
) -> None:
    """Synthétise (et corrige au besoin) l'audio d'une slide. Mute `slide` en place."""
    assert slide.script is not None, "Le scripting doit précéder la synthèse."

    out_path = str(out_dir / f"slide_{slide.index:03d}.mp3")
    result = await tts.synthesize(slide.script.text, voice, out_path)

    slide.script.audio_path = result.audio_path
    slide.script.audio_duration_s = result.duration_s
    slide.actual_duration_s = result.duration_s
    voice.recalibrate(result.word_count, result.duration_s)

    target_words = slide.script.word_count_target
    if target_words is None:
        return  # mode auto : pas de contrainte, la durée réelle fait foi telle quelle

    # Cible de durée équivalente pour CETTE slide (dérivée de son propre budget de mots).
    slide_target_s = target_words / voice.speech_rate_wps
    dev = deviation(result.duration_s, slide_target_s)

    if dev <= deviation_threshold:
        return

    # Correction UNIQUE : régénère le texte de cette slide avec le débit calibré.
    slide.script = await scripting.generate_slide_script(
        llm, section, slide, position, total, previous_text, next_slide,
        target_words, tolerance, max_passes,
    )

    result2 = await tts.synthesize(slide.script.text, voice, out_path)
    slide.script.audio_path = result2.audio_path
    slide.script.audio_duration_s = result2.duration_s
    slide.actual_duration_s = result2.duration_s
    voice.recalibrate(result2.word_count, result2.duration_s)

    dev2 = deviation(result2.duration_s, slide_target_s)
    if dev2 > deviation_threshold:
        section.synthesis_note = (
            f"{section.synthesis_note + ' ' if section.synthesis_note else ''}"
            f"Écart résiduel de {dev2:.0%} après correction sur la page {slide.source_page} "
            f"(cible {slide_target_s:.0f}s, réel {result2.duration_s:.0f}s)."
        )
