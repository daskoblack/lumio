"""Interface abstraite du moteur vidéo (implémentation FFmpeg en phase 4).

Contrat figé dès maintenant : le moteur consomme une timeline déjà calculée
(bornes en secondes) + les chemins audio/slides. Il ne connaît RIEN de la
logique pédagogique ni des durées cibles.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class TimelineEntry(BaseModel):
    """Un segment de la vidéo : une image affichée pendant [start_s, end_s].

    `image_path` et `audio_path` sont résolus par `pipeline/timeline.py` à
    partir des slides du Course : le VideoEngine ne connaît jamais les
    modèles pédagogiques. Chaque slide a son propre audio (1:1) : la synchro
    image/narration est garantie par construction, pas par découpage du temps.
    """

    section_id: str
    slide_id: str
    image_path: str
    audio_path: str | None = None
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


class VideoEngine(ABC):
    """Assemble slides + audio en un MP4 selon la timeline."""

    @abstractmethod
    async def assemble(
        self,
        timeline: list[TimelineEntry],
        out_path: str,
    ) -> str:
        """Produit le fichier vidéo final et retourne son chemin."""
        raise NotImplementedError
