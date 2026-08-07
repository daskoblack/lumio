"""Analyse de structure : le LLM propose un découpage pédagogique en sections.

Cette étape ne fait QUE l'appel LLM et le parsing. La transformation en objets
Section (et le calcul des durées) est faite par `sectioning.py`, pour garder
la séparation pédagogie / conversion.
"""

from __future__ import annotations

from ..core.jsonutil import parse_json
from ..providers.llm.base import LLMProvider

_SYSTEM = """Tu es un concepteur pédagogique. On te donne le texte brut d'un \
support de cours (PDF), page par page. Tu dois le découper en sections \
pédagogiques cohérentes destinées à devenir une vidéo avec un professeur.

Règles :
- Chaque section regroupe une ou plusieurs pages sur un même point.
- Pour chaque section, rédige un CONTEXTE de 3 à 5 phrases. Il sera relu par \
un autre professeur avant CHAQUE page de cette section — y compris la \
dixième page d'une longue section — pour qu'il reste ancré au bon sujet au \
lieu de dériver ou de se répéter avec le temps. Il doit préciser : ce que \
cette section couvre exactement, le vocabulaire et les notions clés à \
employer, et ce qui est déjà traité dans une AUTRE section et ne doit donc \
PAS être répété ici.
- Estime le nombre de mots qu'une NARRATION ORALE originale (pas une lecture \
du PDF) nécessiterait pour bien expliquer cette section.
- Réponds STRICTEMENT en JSON, sans texte autour."""

_USER_TEMPLATE = """Découpe ce cours en sections.

Réponds avec cet objet JSON exact :
{{
  "course_title": "titre global du cours",
  "sections": [
    {{
      "title": "titre de la section",
      "kind": "intro|concept|example|exercise|summary|other",
      "context": "3 à 5 phrases : ce que couvre précisément cette partie, le vocabulaire et les notions clés à employer, ce qui est traité ailleurs et à ne pas répéter",
      "source_pages": [1, 2],
      "estimated_narration_words": 180
    }}
  ]
}}

Texte du cours :
{document}"""


async def analyze_structure(
    llm: LLMProvider, document_text: str, max_chars: int
) -> tuple[dict, bool]:
    """Retourne (structure_json, truncated).

    `truncated` indique si le texte a dû être coupé pour tenir dans la fenêtre.
    """
    truncated = len(document_text) > max_chars
    doc = document_text[:max_chars] if truncated else document_text

    raw = await llm.complete(
        system=_SYSTEM,
        user=_USER_TEMPLATE.format(document=doc),
        json_mode=True,
        temperature=0.3,
    )
    data = parse_json(raw)
    return data, truncated
