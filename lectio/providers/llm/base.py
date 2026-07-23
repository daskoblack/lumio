"""Interface abstraite du fournisseur LLM.

Toute la pipeline dépend UNIQUEMENT de cette interface : changer de
fournisseur (Groq -> OpenAI -> local) = ajouter une implémentation, sans
toucher au reste de l'application.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Fournisseur de complétions de texte (async par nature I/O réseau)."""

    @abstractmethod
    async def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Retourne le texte de la réponse du modèle.

        json_mode=True demande une sortie JSON stricte (structuration).
        """
        raise NotImplementedError
