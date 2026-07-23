"""Rendu des slides en images PNG : la page RÉELLE du PDF, telle quelle.

Pas de reconstruction par l'IA (texte redessiné) : on rasterise directement
la page source (PyMuPDF) à haute résolution, puis on la place en incrustation
("letterbox") sur un canvas de taille fixe (`config.slides.width/height`) pour
garantir une résolution vidéo constante même si les pages du PDF ont un
format différent du 16:9.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from ..core.exceptions import ExtractionError
from ..core.models import Slide

_BG = (0, 0, 0)  # bandes noires si le ratio de la page ne remplit pas le canvas


def render_all(source_pdf: str, slides: list[Slide], out_dir: Path, width: int, height: int) -> None:
    """Rend chaque slide = la page PDF correspondante, telle quelle. Remplit `rendered_path`."""
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = fitz.open(source_pdf)
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"PDF illisible pour le rendu des slides : {exc}") from exc

    try:
        for slide in slides:
            page = doc[slide.source_page - 1]
            rect = page.rect
            scale = min(width / rect.width, height / rect.height)
            matrix = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            page_img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            canvas = Image.new("RGB", (width, height), _BG)
            offset = ((width - pix.width) // 2, (height - pix.height) // 2)
            canvas.paste(page_img, offset)

            out_path = out_dir / f"slide_{slide.index:03d}.png"
            canvas.save(out_path)
            slide.rendered_path = str(out_path)
    finally:
        doc.close()
