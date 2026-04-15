# Artist Reference Manager

A fast, local-first desktop application for artists to collect, organise, and reference images during the creative process — inspired by tools like PureRef, but with a persistent library, tagging system, and an infinite workspace canvas.

Built with **Python + PyQt5** and a **SQLite** backend.

---

## ✨ Features

### 📁 Library & Collections
- **Import images** by drag-and-drop or folder browsing — duplicates are detected automatically via MD5 hashing
- **Collections** to group images manually, with full **nested/sub-collection** support (type `People/Portraits` to create a hierarchy)
- **Smart Collections** — auto-populate based on one or more required tags (similar to smart playlists)
- **Tags** — assign multiple tags to each image; filter the gallery by tag from the sidebar
- **Favorites** — star any image for quick access from the sidebar
- **Recently Viewed** — automatically tracks the last images you opened in the workspace

### 🔍 Gallery View
- Responsive grid layout with adjustable column count (2–8 columns via slider in the topbar)
- Background thumbnail loading via `QThread` — the UI stays responsive even with large libraries
- Paginated browsing (50 images per page by default)
- **Search** by filename or tag, with live **tag autocomplete** dropdown as you type
- **Bulk multi-select** — click multiple images, then retag or batch-send them to the workspace in one action
- **Right-click context menu** per image:
  - Add to / remove from collection
  - Edit tags
  - Toggle favourite
  - Open in workspace / add to workspace
  - Delete from library

### 🖼 Infinite Workspace Canvas
- Hardware-accelerated **QGraphicsScene / QGraphicsView** canvas — smooth pan and zoom at any scale
- Drag images freely anywhere on the canvas
- **Scroll wheel** to zoom the canvas; **Ctrl + Scroll** to scale only the selected image
- **Middle-click or Right-click drag** to pan the canvas
- **Flip Horizontal / Flip Vertical** per selected image
- **🎨 Color Palette extractor** — select an image and extract its 6 dominant colours as hex swatches
- **💾 Export Workspace** — renders the entire canvas to a PNG file
- **5 save slots** — save and recall up to 5 independent workspace layouts
- **Auto-save** every 2 minutes to the active slot
- **Delete / Backspace** to remove selected images from the canvas
- **Detachable workspace window** — float the canvas in a separate window so you can keep references visible while painting in another app

### ⚙ Settings & Housekeeping
- **Startup health check** — scans for library entries whose source files no longer exist on disk and offers to remove them
- **Auto-update checker** — polls GitHub Releases on startup and shows a changelog dialog when a new version is available
- **Settings dialog** — appearance and opacity controls
- **F1 keyboard shortcut** — opens the keyboard shortcuts reference panel

---

## 🗂 Project Structure

```
artist-reference/
├── main.py                   # Entry point — QMainWindow, global stylesheet, view routing
├── database.py               # SQLite schema init, auto-migrations, WAL mode
├── version.py                # APP_VERSION constant and GitHub Releases URL
├── utils_image.py            # PIL → QPixmap conversion helper
├── requirements.txt
│
├── managers/
│   ├── image_manager.py      # Import, query, hash, favorites, health check
│   ├── collection_manager.py # Collections, sub-collections, smart collections
│   ├── tag_manager.py        # Tag CRUD and per-image tag assignment
│   ├── workspace_manager.py  # 5-slot workspace state save/load
│   └── update_manager.py     # GitHub Releases update checker
│
└── ui/
    ├── gallery_view.py       # Gallery grid, sidebar, search, context menu
    ├── workspace_view.py     # QGraphicsScene canvas, toolbar, slot controls
    ├── upload_view.py        # Drag-and-drop import screen with async QThread processing
    ├── settings_dialog.py    # Settings QDialog
    └── update_dialog.py      # "Update available" QDialog
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
git clone https://github.com/syukri1995/artist-reference.git
cd artist-reference
pip install -r requirements.txt
```

### Running

```bash
python main.py
```

The SQLite database and image thumbnails are stored locally under `data/` in the project directory, or next to the `.exe` if packaged.

---

## ⌨ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `F1` | Toggle keyboard shortcuts reference panel |
| `Delete` / `Backspace` | Remove selected image(s) from workspace canvas |
| `Scroll Wheel` | Zoom canvas in / out |
| `Ctrl + Scroll Wheel` | Scale the selected image |
| `Right-click drag` | Pan the workspace canvas |
| `Middle-click drag` | Pan the workspace canvas |

---

## 📦 Building a Standalone Executable

The project ships with a PyInstaller spec file:

```bash
pip install pyinstaller
pyinstaller artist_ref_manager.spec
```

The `.exe` is output to `dist/`. The `data/` folder (database + thumbnails) is created automatically next to the executable on first run.

---

## 🗄 Database Schema

All data is stored in `data/artist_reference.db` (SQLite, WAL journal mode).

| Table | Purpose |
|---|---|
| `images` | Library entries — file path, MD5 hash, dimensions, favourite flag, last viewed timestamp |
| `collections` | Named groups; `parent_id` enables unlimited nesting |
| `collection_images` | Many-to-many join: images ↔ collections |
| `tags` | Global tag list |
| `image_tags` | Many-to-many join: images ↔ tags |
| `smart_collections` | Named filter presets storing required `tag_ids` |
| `workspace_state` | Per-slot canvas layout — position (x/y), scale, z-order, flip state |

Schema migrations run automatically on startup via `init_db()` so existing databases are upgraded in-place without data loss.

---

## 🛠 Architecture Notes

| Layer | Technology |
|---|---|
| UI Framework | PyQt5 |
| Canvas | `QGraphicsScene` + `QGraphicsView` (OpenGL-backed, hardware-accelerated) |
| Async image loading | `QThread` + `pyqtSignal` / `pyqtSlot` |
| Image processing | Pillow (PIL) |
| Storage | SQLite via `sqlite3` (WAL mode, thread-local persistent connections) |
| Duplicate detection | MD5 file hash computed at import time |

The backend (`managers/`, `database.py`) is fully decoupled from the UI layer. All database access goes through dedicated manager classes, making it straightforward to swap the UI toolkit or add a REST API in the future.

---

## 📋 Roadmap / Planned Features

- [ ] Keyboard shortcut customisation
- [ ] Image annotation / sticky notes per image
- [ ] Colour-grading and filter overlays on the workspace canvas
- [ ] Export workspace as PDF
- [ ] Recursive folder import (preserving folder structure as nested collections)
- [ ] Plugin system for custom importers

---

## 📄 License

MIT License — see `LICENSE` for details.

---

> Made for artists, by an artist. Inspired by PureRef.