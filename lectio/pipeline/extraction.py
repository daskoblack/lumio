"""Extraction PDF : texte + images + layout (PyMuPDF).

Produit une Slide par page (au MVP) et le texte concaténé avec des marqueurs
de page, consommé ensuite par l'analyse LLM. Aucune dépendance au LLM ici :
module testable indépendamment.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from ..core.exceptions import ExtractionError
from ..core.models import ContentBlock, Slide

# Seuil en dessous duquel on considère le PDF comme non exploitable (scanné/vide).
_MIN_CHARS_PER_PAGE = 20


def extract(pdf_path: str, images_dir: Path) -> tuple[list[Slide], str]:
    """Extrait les slides et le texte complet du PDF.

    Retourne (slides, texte_avec_marqueurs_de_page).
    Lève ExtractionError si le document ne contient pas de texte exploitable
    (cas d'un PDF scanné : OCR hors périmètre MVP).
    """
    path = Path(pdf_path)
    if not path.exists():
        raise ExtractionError(f"Fichier introuvable : {pdf_path}")

    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"PDF illisible : {exc}") from exc

    images_dir.mkdir(parents=True, exist_ok=True)
    slides: list[Slide] = []
    full_text_parts: list[str] = []
    total_chars = 0

    for page_index, page in enumerate(doc):
        page_num = page_index + 1
        text = page.get_text("text").strip()
        total_chars += len(text)

        blocks: list[ContentBlock] = []
        # Première ligne non vide = titre présumé de la page.
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        title = lines[0] if lines else f"Page {page_num}"
        if text:
            blocks.append(ContentBlock(kind="text", text=text))

        # Extraction best-effort des images matricielles de la page.
        for img_index, img in enumerate(page.get_images(full=True)):
            try:
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:  # CMYK/autre -> conversion RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                img_path = images_dir / f"p{page_num}_img{img_index}.png"
                pix.save(img_path)
                blocks.append(ContentBlock(kind="image", image_path=str(img_path)))
            except Exception:  # noqa: BLE001 - image non critique, on ignore
                continue

        slides.append(
            Slide(
                index=page_index,
                source_page=page_num,
                title=title[:120],
                content_blocks=blocks,
            )
        )
        full_text_parts.append(f"=== PAGE {page_num} ===\n{text}")

    doc.close()

    if total_chars < _MIN_CHARS_PER_PAGE * max(1, len(slides)):
        raise ExtractionError(
            "Ce PDF ne contient pas assez de texte exploitable : c'est "
            "probablement un document scanné, ou une suite d'images. Lumio a "
            "besoin d'un PDF dont le texte peut être sélectionné."
        )

    return slides, "\n\n".join(full_text_parts)
