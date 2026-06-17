# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Artist Reference Manager (Windows one-file build)."""

import os
import sys
import certifi
from pathlib import Path

import PyQt5

# Bake version into the frozen bundle (CI sets ARTIST_REF_VERSION from git tag).
_build_version = os.environ.get("ARTIST_REF_VERSION", "1.0.0")
Path("version_baked.py").write_text(
    f'APP_VERSION = "{_build_version}"\n',
    encoding="utf-8",
)

block_cipher = None


def _openssl_binaries():
    """Collect OpenSSL DLLs and _ssl for HTTPS (conda and CPython layouts)."""
    prefix = Path(sys.prefix)
    search_dirs = [prefix / "Library" / "bin", prefix / "DLLs"]
    names = [
        "libssl-3-x64.dll",
        "libcrypto-3-x64.dll",
        "libssl-1_1-x64.dll",
        "libcrypto-1_1-x64.dll",
    ]
    found = []
    seen = set()
    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for name in names:
            path = directory / name
            if path.is_file() and name not in seen:
                found.append((str(path), "."))
                seen.add(name)

    import _ssl

    ssl_pyd = Path(_ssl.__file__)
    if ssl_pyd.is_file():
        found.append((str(ssl_pyd), "."))
    return found


_qt_plugins = Path(PyQt5.__file__).resolve().parent / "Qt5" / "plugins"
_qt_platforms = _qt_plugins / "platforms"
_qt_styles = _qt_plugins / "styles"
_qt_imageformats = _qt_plugins / "imageformats"

datas = [
    ("assets/app_icon.ico", "assets"),
    ("assets/app_icon.png", "assets"),
    ("assets/icons/*.svg", "assets/icons"),
    (certifi.where(), "certifi"),
    (str(_qt_platforms / "qwindows.dll"), "PyQt5/Qt5/plugins/platforms"),
    (str(_qt_styles / "qwindowsvistastyle.dll"), "PyQt5/Qt5/plugins/styles"),
    (str(_qt_imageformats / "qjpeg.dll"), "PyQt5/Qt5/plugins/imageformats"),
    (str(_qt_imageformats / "qgif.dll"), "PyQt5/Qt5/plugins/imageformats"),
    (str(_qt_imageformats / "qico.dll"), "PyQt5/Qt5/plugins/imageformats"),
    (str(_qt_imageformats / "qwebp.dll"), "PyQt5/Qt5/plugins/imageformats"),
]

binaries = _openssl_binaries()

hiddenimports = [
    "PyQt5.sip",
    "PIL",
    "PIL.Image",
    "PIL.ImageFilter",
    "PIL._webp",
    "PIL.WebPImagePlugin",
    "certifi",
    "requests",
    "sqlite3",
    "cv2",
    "numpy",
    "onnxruntime",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["pyi_rth_openssl.py"],
    excludes=[
        "tkinter",
        "matplotlib",
        "pandas",
        "PyQt5.QtWebEngine",
        "PyQt5.QtWebEngineCore",
        "PyQt5.QtWebEngineWidgets",
        "PyQt5.QtMultimedia",
        "PyQt5.QtBluetooth",
        "PyQt5.QtLocation",
        "PyQt5.QtNfc",
        "PyQt5.QtQuick",
        "PyQt5.QtQml",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ArtistReferenceManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app_icon.ico",
)
