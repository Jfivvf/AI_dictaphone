"""Пакет нативных UI-виджетов AxAI (рендеринг формул LaTeX, иконка приложения, обработка аватарки)."""
from .latex_preview import (
    draw_fixed_app_icon_pixmap,
    crop_and_compress_avatar_square,
    pixmap_from_png_bytes,
    LatexLecturePreview,
)

__all__ = [
    "draw_fixed_app_icon_pixmap",
    "crop_and_compress_avatar_square",
    "pixmap_from_png_bytes",
    "LatexLecturePreview",
]
