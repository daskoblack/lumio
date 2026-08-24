"""Analyse de structure : le LLM propose un découpage pédagogique en sections.

Cette étape ne fait QUE l'appel LLM et le parsing. La transformation en objets
Section (et le calcul des durées) est faite par `sectioning.py`, pour garder
la séparation pédagogie / conversion.

Contrainte de fenêtre : le document doit tenir dans un budget de caractères.
Le couper à la fin faisait disparaître les dernières pages de l'analyse — sur
un cours de 40 pages denses, la moitié était découpée en sections, dotée d'un
contexte pédagogique et d'une durée SANS QUE LE MODÈLE N'AIT VU SON CONTENU.
On envoie donc un EXTRAIT de chaque page plutôt que l'intégralité des
premières : le document entier est représenté, à budget identique.
"""

from __future__ import annotations

from ..core.jsonutil import parse_json
from ..providers.llm.base import LLMProvider

# En dessous, un extrait ne dit plus rien d'utile sur le sujet d'une page.
# Un document assez long pour descendre sous ce seuil garde ce minimum : le
# budget total est alors légèrement dépassé, ce qui reste préférable à un
# découpage à l'aveugle.
_MIN_EXCERPT_CHARS = 200

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
- Estime le nombre de mots qu'une narration orale originale (pas une lecture \
du PDF) nécessiterait pour expliquer CORRECTEMENT UNE SEULE page de cette \
section (entre 70 et 150 mots dans la grande majorité des cas). CE CHIFFRE \
NE DOIT PAS DIMINUER quand la section regroupe plus de pages : chaque page \
garde besoin d'une explication complète, qu'elle soit seule dans sa section \
ou entourée de neuf autres.
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
      "estimated_words_per_page": 100
    }}
  ]
}}

Texte du cours :
{document}"""


def build_analysis_document(
    pages: list[tuple[int, str]], max_chars: int
) -> tuple[str, bool]:
    """Assemble le texte envoyé à l'analyse. Retourne (document, abrégé).

    CHAQUE page y figure toujours, même sur un document très long : si le
    texte intégral ne tient pas dans `max_chars`, on prend un extrait de
    début de chaque page plutôt que d'abandonner les dernières. Le modèle
    connaît ainsi le sujet de toutes les pages au moment de découper en
    sections, d'écrire leur contexte et d'estimer les durées.

    `abrégé` vaut True quand les pages ont dû être extraites (utile pour en
    informer l'utilisateur), False quand le document a été envoyé entier.
    """
    if not pages:
        return "", False

    # Par page : le marqueur, son saut de ligne, le séparateur « \n\n » qui
    # la relie à la suivante, et le « … » ajouté quand la page est abrégée.
    overhead = sum(len(f"=== PAGE {number} ===\n\n\n…") for number, _ in pages)
    full_body = sum(len(text) for _, text in pages)
    if overhead + full_body <= max_chars:
        document = "\n\n".join(f"=== PAGE {n} ===\n{t}" for n, t in pages)
        return document, False

    budget = max(_MIN_EXCERPT_CHARS, (max_chars - overhead) // len(pages))
    parts = []
    for number, text in pages:
        excerpt = text[:budget].rstrip()
        if len(text) > budget:
            excerpt += "…"
        parts.append(f"=== PAGE {number} ===\n{excerpt}")
    return "\n\n".join(parts), True


async def analyze_structure(
    llm: LLMProvider, pages: list[tuple[int, str]], max_chars: int
) -> tuple[dict, bool]:
    """Retourne (structure_json, abrégé).

    `pages` est la liste (numéro de page, texte) dans l'ordre du document.
    `abrégé` indique que seul un extrait de chaque page a pu être envoyé.
    """
    document, shortened = build_analysis_document(pages, max_chars)

    raw = await llm.complete(
        system=_SYSTEM,
        user=_USER_TEMPLATE.format(document=document),
        json_mode=True,
        temperature=0.3,
    )
    data = parse_json(raw)
    return data, shortened
