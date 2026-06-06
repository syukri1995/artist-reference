import os

try:
    from version_baked import APP_VERSION
except ImportError:
    APP_VERSION = os.environ.get("ARTIST_REF_VERSION", "1.0.0")

UPDATE_URL = os.environ.get(
    "ARTIST_REF_UPDATE_URL",
    "https://api.github.com/repos/syukri1995/artist-reference/releases/latest",
)
