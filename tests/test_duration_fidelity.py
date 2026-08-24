"""La durée demandée par l'utilisateur (en SECONDES) doit être tenue quel que
soit le débit réel de la voix.

Défaut corrigé : le budget de mots était calculé avec un débit SUPPOSÉ
(2,3 mots/s de la config) tandis que le contrôle audio recalculait sa cible
avec le débit CALIBRÉ. Le contrôle était donc circulaire -- il mesurait
toujours ~0% d'écart, y compris quand la vidéo faisait 13% de moins que
promis (voix edge-tts réelle mesurée à 2,64 mots/s).
"""

from pathlib import Path

import pytest

from lectio.core.config import Config
from lectio.core.models import ContentBlock, Course, CourseStatus, Section, SectionKind, Slide
from lectio.jobs.orchestrator import Orchestrator
from lectio.providers.llm.base import LLMProvider
from lectio.providers.tts.base import TTSProvider, TTSResult
from lectio.providers.video.base import VideoEngine


class _ObedientLLM(LLMProvider):
    """Écrit exactement le nombre de mots demandé dans le prompt.

    Isole la question de la DURÉE : si le pipeline demande le bon nombre de
    mots, la durée sera bonne. Tout écart restant vient donc du calcul de
    budget, pas de la désobéissance du modèle.
    """

    async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
        import re
        m = re.search(r"vise environ (\d+) mots", user)
        if not m:  # prompt de correction
            m = re.search(r"cible de (\d+) mots", user)
        n = int(m.group(1)) if m else 100
        return " ".join(["mot"] * n)


class _VoiceAtRate(TTSProvider):
    """Voix qui parle à un débit RÉEL fixé, différent du défaut de config."""

    def __init__(self, real_rate_wps: float) -> None:
        self.real_rate = real_rate_wps
        self.calls = 0

    async def synthesize(self, text, voice, out_path):
        self.calls += 1
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"x")
        words = len(text.split())
        return TTSResult(audio_path=out_path, duration_s=words / self.real_rate,
                          word_count=words)


class _NoopVideo(VideoEngine):
    async def assemble(self, timeline, out_path):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"x")
        return out_path


def _course_with_target(tmp_path, target_seconds: float, n_pages: int = 4):
    config = Config.load()
    config.paths.workspace = str(tmp_path / "ws")
    slides = [
        Slide(index=i, source_page=i + 1, title=f"P{i+1}",
              content_blocks=[ContentBlock(kind="text", text="Contenu de la page. " * 20)],
              estimated_narration_words=100)
        for i in range(n_pages)
    ]
    section = Section(
        index=0, kind=SectionKind.CONCEPT, title="S", context="Contexte.",
        slide_ids=[s.id for s in slides], target_duration_s=target_seconds,
    )
    course = Course(title="C", source_pdf="x.pdf", status=CourseStatus.ANALYZED,
                     slides=slides, sections=[section])
    return config, course


async def _produce(tmp_path, target_seconds: float, real_rate: float) -> float:
    """Génère un cours et retourne la durée RÉELLE totale produite."""
    config, course = _course_with_target(tmp_path, target_seconds)
    tts = _VoiceAtRate(real_rate)
    orch = Orchestrator(config, llm=_ObedientLLM(), tts=tts, video=_NoopVideo())
    orch.store.save(course)
    await orch.run_scripting(course.id)
    course = await orch.run_synthesis(course.id)
    return sum(sl.actual_duration_s or 0.0
               for s in course.sections for sl in course.section_slides(s))


@pytest.mark.asyncio
@pytest.mark.parametrize("real_rate", [2.3, 2.638, 1.9, 3.0])
async def test_duree_demandee_est_tenue_quel_que_soit_le_debit(tmp_path, real_rate):
    """2,638 = débit réel mesuré d'edge-tts Denise ; 1,9 et 3,0 encadrent les
    voix plus lentes / plus rapides. Avant correctif, seul 2,3 tombait juste."""
    demande = 600.0  # 10 minutes
    produite = await _produce(tmp_path, demande, real_rate)
    ecart = abs(produite - demande) / demande
    assert ecart <= 0.10, (
        f"débit réel {real_rate} mots/s : {produite:.0f}s produits pour "
        f"{demande:.0f}s demandés ({ecart:.0%} d'écart)"
    )


@pytest.mark.asyncio
async def test_le_budget_de_mots_suit_le_debit_reel_de_la_voix(tmp_path):
    """Une voix rapide doit recevoir PLUS de mots pour remplir la même durée."""
    config, course = _course_with_target(tmp_path, 600.0)
    orch = Orchestrator(config, llm=_ObedientLLM(), tts=_VoiceAtRate(2.3), video=_NoopVideo())
    orch.store.save(course)

    voice = orch._voice_profile(course)
    voice.speech_rate_wps = 3.0          # voix rapide
    voice.calibration_samples = 50       # calibration déjà bien établie
    orch._voice_store.save(voice)

    plan_rapide = orch._build_narration_plan(course, orch._voice_rate(course))

    voice.speech_rate_wps = 1.9          # voix lente
    orch._voice_store.save(voice)
    plan_lent = orch._build_narration_plan(course, orch._voice_rate(course))

    mots_rapide = sum(c.target_words for c in plan_rapide)
    mots_lent = sum(c.target_words for c in plan_lent)
    assert mots_rapide > mots_lent, (
        f"voix rapide {mots_rapide} mots vs voix lente {mots_lent} mots : "
        "le budget doit suivre le débit réel"
    )


@pytest.mark.asyncio
async def test_la_promesse_en_secondes_est_portee_par_le_contexte(tmp_path):
    """`target_seconds` doit exister sur chaque page d'une section configurée,
    et leur somme reconstituer la durée demandée."""
    config, course = _course_with_target(tmp_path, 480.0)
    orch = Orchestrator(config, llm=_ObedientLLM(), tts=_VoiceAtRate(2.3), video=_NoopVideo())
    orch.store.save(course)

    plan = orch._build_narration_plan(course, orch._voice_rate(course))
    assert all(c.target_seconds is not None for c in plan)
    assert sum(c.target_seconds for c in plan) == pytest.approx(480.0)


@pytest.mark.asyncio
async def test_section_automatique_ne_porte_aucune_promesse(tmp_path):
    """Sans durée choisie, aucune seconde n'est promise : le comportement
    historique (plafond souple, pas de correction pour un manque) est conservé."""
    config, course = _course_with_target(tmp_path, 480.0)
    course.sections[0].target_duration_s = None
    orch = Orchestrator(config, llm=_ObedientLLM(), tts=_VoiceAtRate(2.3), video=_NoopVideo())
    orch.store.save(course)

    plan = orch._build_narration_plan(course, orch._voice_rate(course))
    assert all(c.target_seconds is None for c in plan)
    assert all(not c.precise for c in plan)
