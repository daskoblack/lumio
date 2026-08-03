"""Schéma de données de Lectio (Pydantic v2).

Séparation stricte : ces modèles sont le SEUL contrat entre la logique
pédagogique (découpage/scripts) et la logique de rendu (slides/vidéo).
Aucun module de rendu ne lit `target_duration_s` ni `estimated_duration_s` :
seule `actual_duration_s` (mesurée post-TTS) construit la timeline.

La narration est générée PAR SLIDE (une page = un audio = une image affichée
pendant exactement sa durée réelle -> synchro garantie). La Section reste le
niveau de regroupement pédagogique (c'est là que l'utilisateur fixe une durée
cible), mais son script est la somme narrative de ses slides, générées en
séquence avec mémoire du contexte (page précédente/suivante) pour un
enchaînement fluide plutôt qu'un découpage haché page par page.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class CourseStatus(str, Enum):
    """États du job, persistés pour permettre l'arrêt/reprise entre étapes."""

    CREATED = "created"
    EXTRACTED = "extracted"
    ANALYZED = "analyzed"       # sections + estimations prêtes -> revue utilisateur
    SCRIPTED = "scripted"       # narrations générées (fin de la phase 2)
    SYNTHESIZED = "synthesized"  # audio produit (phase 3)
    RENDERED = "rendered"        # slides + montage (phase 4)
    DONE = "done"
    FAILED = "failed"


class SectionKind(str, Enum):
    """Nature pédagogique d'une section (guide le style de narration)."""

    INTRO = "intro"
    CONCEPT = "concept"
    EXAMPLE = "example"
    EXERCISE = "exercise"
    SUMMARY = "summary"
    OTHER = "other"


class ContentBlock(BaseModel):
    """Bloc de contenu source extrait d'une page."""

    kind: str  # "heading" | "text" | "image"
    text: str | None = None
    image_path: str | None = None


class Script(BaseModel):
    """Narration 'professeur' d'une slide (texte original, pas une lecture du PDF)."""

    slide_id: str
    text: str = ""
    word_count_target: int | None = None   # None = génération libre (pas de cible)
    word_count_actual: int = 0
    generation_pass: int = 0                # 0=non généré, 1=1re passe, 2=corrigée
    # True si l'IA n'a pas produit de texte prononçable et qu'un texte de
    # secours (bâti sur le contenu de la page) a dû être utilisé.
    fallback_used: bool = False
    audio_path: str | None = None           # rempli en phase 3
    audio_duration_s: float | None = None   # rempli en phase 3


class Slide(BaseModel):
    """Une slide source (une par page PDF au MVP). Rendue telle quelle (phase 4)."""

    id: str = Field(default_factory=_new_id)
    index: int
    source_page: int
    title: str
    content_blocks: list[ContentBlock] = Field(default_factory=list)
    rendered_path: str | None = None  # image RÉELLE de la page PDF (pas un dessin IA)

    # --- Durées (mêmes règles que Section : cible en amont, réel fait foi) ---
    estimated_narration_words: int = 0      # part du budget de la section (proportionnelle)
    estimated_duration_s: float = 0.0
    actual_duration_s: float | None = None  # mesurée post-TTS = autorité timeline

    script: Script | None = None

    def source_text(self) -> str:
        """Concatène le texte des blocs (contexte pour la génération)."""
        return "\n".join(b.text for b in self.content_blocks if b.text)


class Section(BaseModel):
    """Regroupement pédagogique de slides. Porte la durée cible OPTIONNELLE globale."""

    id: str = Field(default_factory=_new_id)
    index: int
    kind: SectionKind = SectionKind.OTHER
    title: str
    summary: str = ""
    slide_ids: list[str] = Field(default_factory=list)

    # --- Durées (agrégées à partir des slides) ---
    estimated_narration_words: int = 0      # estimé par le LLM à l'analyse (pour toute la section)
    target_duration_s: float | None = None  # INPUT UTILISATEUR optionnel (None = auto)
    estimated_duration_s: float = 0.0        # somme des slides (avant TTS)
    actual_duration_s: float | None = None   # somme des slides (mesurée post-TTS)
    duration_deviation: float | None = None  # écart cible/réel, pour le rapport
    synthesis_note: str | None = None        # avertissement si l'écart persiste après correction


class Course(BaseModel):
    """Racine du job. Sérialisée en JSON dans workspace/{id}/job.json."""

    id: str = Field(default_factory=_new_id)
    title: str
    source_pdf: str
    language: str = "fr"
    voice_profile_id: str = "default"
    status: CourseStatus = CourseStatus.CREATED
    truncated: bool = False  # True si le texte a été tronqué pour l'analyse
    # Pages produites en mode dégradé (IA indisponible, voix en échec) : la
    # vidéo est quand même livrée, mais on dit lesquelles ont souffert.
    degraded_pages: list[str] = Field(default_factory=list)
    subtitles_enabled: bool = False  # désactivés par défaut, activables au planning

    slides: list[Slide] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)

    def slide_by_id(self, slide_id: str) -> Slide | None:
        return next((s for s in self.slides if s.id == slide_id), None)

    def section_by_index(self, index: int) -> Section | None:
        return next((s for s in self.sections if s.index == index), None)

    def section_slides(self, section: Section) -> list[Slide]:
        """Slides d'une section, dans l'ordre déclaré par `slide_ids`."""
        slides = [self.slide_by_id(sid) for sid in section.slide_ids]
        return [s for s in slides if s is not None]
