import os

APP_VERSION = "1.0.0"

# Using a generic public repo as a placeholder template for GitHub releases checking
# Replace 'your-username/artist-reference-manager' with the actual ones to make it functional.
UPDATE_URL = os.environ.get(
	"ARTIST_REF_UPDATE_URL",
	"https://api.github.com/repos/syukri1995/artist-reference/releases/latest",
)
