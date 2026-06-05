"""Ensure bundled OpenSSL DLLs are on the search path (conda + PyInstaller)."""

import os
import sys

if sys.platform == "win32" and getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", "")
    if base:
        os.environ["PATH"] = base + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(base)
