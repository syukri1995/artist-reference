Artist Reference Manager — Quick Start
======================================

NOTE: ANTIVIRUS FALSE POSITIVES
-------------------------------
Because this executable is unsigned and built with PyInstaller, Windows 
Defender or other antivirus software may flag it as a "false positive" 
on first run.
  - Windows SmartScreen: Click "More info" and then "Run anyway".
  - Antivirus blocks: You may need to add an exclusion for the app.

FIRST RUN
---------
Double-click ArtistReferenceManager.exe.
On first launch the app creates a "data" folder next to the exe:
  - data/artist_reference.db   (your library database)
  - data/images/               (imported reference images)
  - data/thumbnails/           (gallery previews)
  - data/logs/                 (troubleshooting logs)

Keep the exe and data folder together when moving the app.

BASIC USE
---------
Gallery  — browse, tag, and search your library
Workspace — infinite canvas for reference layout while you draw
Upload   — drag-and-drop or folder import
Danbooru — search and import from Danbooru (optional, needs internet)
Settings — opacity, backup/restore, Danbooru API key (gear icon in gallery)

Press F1 inside the app for keyboard shortcuts.

DANBOORU API KEY (OPTIONAL)
---------------------------
Anonymous search works without an account but has lower rate limits.

To use your own Danbooru API key:
  1. Create an account at https://danbooru.donmai.us
  2. Open your profile page and copy your API key
  3. In the app: Gallery → Settings (gear) → Danbooru tab
  4. Enter username + API key → Save credentials
  5. Search immediately — no restart needed

You can also click "API key…" on the Danbooru screen.

BACKUP
------
Settings → "Backup library (zip)…" saves database + images.
Restore replaces your current library — back up first.

ADVANCED CONFIG (.env)
----------------------
Optional: place a .env file next to the exe (see .env.example).
Environment variables override Settings for Danbooru credentials.

UPDATES
-------
The app checks GitHub Releases on startup when online.
Download updates from: https://github.com/syukri1995/artist-reference/releases

SUPPORT
-------
Issues: https://github.com/syukri1995/artist-reference/issues
License: MIT (see LICENSE)
