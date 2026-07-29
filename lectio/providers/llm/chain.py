"""Chaîne de repli entre plusieurs fournisseurs/modèles LLM.

Problème résolu : quand le quota quotidien d'un fournisseur tombe en pleine
génération, toute la vidéo échouait. Ici, la chaîne bascule automatiquement
vers le candidat suivant (modèle plus léger, puis autre fournisseur) et la
génération se poursuit.

Ordre = celui de la config : du plus capable au plus modeste. Un candidat
marqué épuisé (quota du jour, clé invalide) est écarté pour le reste de la
session — inutile de re-tenter à chaque page.
"""

from __future__ import annotations

from ...core.exceptions import LLMError
from .base import LLMProvider
from .errors import QuotaExhaustedError


class LLMChain(LLMProvider):
    """Essaie chaque candidat dans l'ordre, bascule au suivant si épuisé."""

    def __init__(self, candidates: list[tuple[str, LLMProvider]]) -> None:
        if not candidates:
            raise LLMError(
                "Aucun fournisseur d'IA configuré. Ajoute au moins une clé API "
                "dans les Réglages (Groq, Cerebras, Gemini ou Mistral)."
            )
        self._candidates = candidates
        self._exhausted: set[int] = set()

    @property
    def active_label(self) -> str:
        """Meilleur candidat encore disponible (pour l'affichage)."""
        labels = self.available_labels
        return labels[0] if labels else "aucun"

    @property
    def available_labels(self) -> list[str]:
        return [label for i, (label, _) in enumerate(self._candidates) if i not in self._exhausted]

    async def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        last_error: Exception | None = None

        # On repart toujours du meilleur candidat encore disponible : un échec
        # ponctuel ne doit pas nous bloquer durablement sur un modèle plus faible.
        for index, (_label, provider) in enumerate(self._candidates):
            if index in self._exhausted:
                continue
            try:
                return await provider.complete(
                    system, user,
                    json_mode=json_mode, temperature=temperature, max_tokens=max_tokens,
                )
            except QuotaExhaustedError as exc:
                # Épuisé pour la session : on ne le re-tentera plus.
                self._exhausted.add(index)
                last_error = exc
            except LLMError as exc:
                # Échec ponctuel (réseau, réponse invalide) : on tente le suivant
                # sans condamner définitivement ce candidat.
                last_error = exc

        raise LLMError(
            "Tous les fournisseurs d'IA configurés sont indisponibles ou à court "
            f"de quota. Dernière erreur : {last_error}"
        )
