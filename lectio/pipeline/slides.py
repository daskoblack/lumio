"""Rendu des slides en images PNG (Pillow).

Choix volontairement simple par rapport à un navigateur headless (Playwright) :
pas de dépendance lourde à installer, rendu rapide et suffisant pour un MVP
(titre + texte + éventuelle image). Le module de rendu ne connaît rien des
durées : il ne fait que produire une image par Slide.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..core.models import Slide

_BG = (255, 255, 255)
_TITLE_COLOR = (20, 20, 30)
_TEXT_COLOR = (50, 50, 60)
_MARGIN = 80
_FONT_CANDIDATES = ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]
_FONT_BOLD_CANDIDATES = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"]


def _load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def render_slide(slide: Slide, width: int, height: int, out_path: Path) -> str:
    """Rend une slide en PNG et retourne le chemin du fichier produit."""
    img = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(img)

    title_font = _load_font(_FONT_BOLD_CANDIDATES, size=int(height * 0.06))
    body_font = _load_font(_FONT_CANDIDATES, size=int(height * 0.032))

    max_width = width - 2 * _MARGIN
    y = _MARGIN

    title_lines = _wrap_text(draw, slide.title, title_font, max_width)
    for line in title_lines:
        draw.text((_MARGIN, y), line, font=title_font, fill=_TITLE_COLOR)
        y += int(height * 0.08)

    y += int(height * 0.03)
    draw.line((_MARGIN, y, width - _MARGIN, y), fill=(210, 210, 220), width=2)
    y += int(height * 0.05)

    body_text = "\n\n".join(
        b.text for b in slide.content_blocks if b.kind == "text" and b.text
    )
    for line in _wrap_text(draw, body_text, body_font, max_width):
        if y > height - _MARGIN:
            break  # contenu trop long pour tenir : tronqué visuellement (limite MVP)
        draw.text((_MARGIN, y), line, font=body_font, fill=_TEXT_COLOR)
        y += int(height * 0.045)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return str(out_path)


def render_all(slides: list[Slide], out_dir: Path, width: int, height: int) -> None:
    """Rend toutes les slides et remplit `rendered_path` en place."""
    for slide in slides:
        path = out_dir / f"slide_{slide.index:03d}.png"
        slide.rendered_path = render_slide(slide, width, height, path)
