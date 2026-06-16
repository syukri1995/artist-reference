"""App icon and logo assets (assets/app_icon.png, assets/app_icon.ico)."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap

_APP_ICON: QIcon | None = None


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))  # type: ignore[arg-type]
    return Path(__file__).resolve().parent.parent


def asset_path(name: str) -> Path:
    return project_root() / "assets" / name


def icon_path(name: str) -> str:
    """Return the absolute path to an icon SVG file."""
    path = project_root() / "assets" / "icons" / f"{name}.svg"
    return str(path)


def app_icon() -> QIcon:
    global _APP_ICON
    if _APP_ICON is not None:
        return _APP_ICON
    ico = asset_path("app_icon.ico")
    png = asset_path("app_icon.png")
    if ico.is_file():
        _APP_ICON = QIcon(str(ico))
    elif png.is_file():
        _APP_ICON = QIcon(str(png))
    else:
        _APP_ICON = QIcon()
    return _APP_ICON


def app_logo_pixmap(size: int = 36) -> QPixmap | None:
    png = asset_path("app_icon.png")
    if not png.is_file():
        return None
    pixmap = QPixmap(str(png))
    if pixmap.isNull():
        return None
    return pixmap.scaled(
        size,
        size,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )


def apply_window_icon(widget) -> None:
    icon = app_icon()
    if not icon.isNull():
        widget.setWindowIcon(icon)
