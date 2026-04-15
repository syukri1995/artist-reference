# Artist Reference Manager

A fast, local-first desktop application for artists to collect, organise, and reference images during the creative process — inspired by tools like PureRef, but with a persistent library, tagging system, and infinite workspace canvas.

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
- Responsive grid layout with adjustable column count (slider in the topbar)
- Background thumbnail loading via `QThread` — the UI stays responsive even with large libraries
- Paginated browsing (50 images per page by default)
- **Search** by filename or tag, with live **tag autocomplete** dropdown
- **Bulk multi-select** — click multiple images, then retag or batch-send to workspace
- **Right-click context menu** per image:
  - Add to / remove from collection
  - Edit tags
  - Toggle favourite
  - Open in workspace / add to workspace
  - Delete from library

### 🖼 Infinite Workspace Canvas
- Hardware-accelerated **QGraphicsScene / QGraphicsView** canvas — smooth pan and zoom at any scale
- Drag images freely anywhere on the canvas
- **Scroll** to zoom the canvas; **Ctrl + Scroll** to resize the selected image only
- **Middle/Right-click drag** to pan
- **Flip Horizontal / Flip Vertical** per selected image
- **🎨 Color Palette** extractor — select an image and extract its 6 dominant colours as hex swatches
- **💾 Export Workspace** — renders the full canvas to a PNG
- **5 save slots** — save and recall up to 5 independent workspace layouts
- **Auto-save** every 2 minutes to the active slot
- **Delete / Backspace** to remove selected images from the canvas
- **Detachable workspace** window — keep references visible while you paint in another application

### ⚙ Settings & Housekeeping
- **Startup health check** — scans for images whose files no longer exist on disk and offers to clean them up
- **Auto-update checker** — polls GitHub Releases on startup and shows a changelog dialog when a new version is available
- **Settings dialog** — appearance and opacity controls
- **F1 keyboard shortcut** — opens the keyboard shortcuts reference panel

---

## 🗂 Project Structure

```
artist-reference/
├── main.py                  # Application entry point, QMainWindow, global stylesheet
├── database.py              # SQLite schema, migrations, WAL mode
├── version.py               # APP_VERSION constant and GitHub update URL
├── utils_image.py           # PIL → QPixmap conversion helper
├── requirements.txt
│
├── managers/
│   ├── image_manager.py     # Import, query, hash, favorites, health check
│   ├── collection_manager.py # Collections, sub-collections, smart collections
│   ├── tag_manager.py       # Tag CRUD, per-image tag assignment
│   ├── workspace_manager.py # 5-slot workspace state save/load
│   └── update_manager.py   # GitHub Releases update checker
│
└── ui/
    ├── gallery_view.py      # Gallery grid, sidebar, search, context menu
    ├── workspace_view.py    # QGraphicsScene canvas, toolbar, slot controls
    ├── upload_view.py       # Drag-and-drop import screen with QThread processing
    ├── settings_dialog.py   # Settings QDialog
    └── update_dialog.py     # Update available QDialog
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

The SQLite database and image thumbnails are stored locally under `data/` in the project directory (or next to the `.exe` if packaged).

---

## ⌨ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `F1` | Toggle keyboard shortcuts panel |
| `Delete` / `Backspace` | Remove selected image(s) from workspace canvas |
| `Ctrl + Scroll` | Resize selected image on canvas |
| `Scroll` | Zoom canvas in/out |
| `Right/Middle click drag` | Pan the workspace canvas |

---

## 📦 Building a Standalone Executable

The project includes a PyInstaller spec file:

```bash
pip install pyinstaller
pyinstaller artist_ref_manager.spec
```

The `.exe` will be output to `dist/`. The database and `data/` folder will be created next to the executable on first run.

---

## 🗄 Database Schema

All data is stored in `data/artist_reference.db` (SQLite, WAL mode).

| Table | Purpose |
|---|---|
| `images` | Library entries — path, hash, dimensions, favorite flag, last viewed |
| `collections` | Named groups with optional `parent_id` for nesting |
| `collection_images` | Many-to-many: images ↔ collections |
| `tags` | Global tag list |
| `image_tags` | Many-to-many: images ↔ tags |
| `smart_collections` | Named filter presets storing required `tag_ids` |
| `workspace_state` | Per-slot canvas layout (position, scale, z-order, flip state) |

Schema migrations run automatically on startup via `init_db()` so existing databases are upgraded without data loss.

---

## 🛠 Architecture Notes

| Layer | Technology |
|---|---|
| UI framework | PyQt5 |
| Canvas | `QGraphicsScene` + `QGraphicsView` (hardware-accelerated) |
| Async image loading | `QThread` + `pyqtSignal` / `pyqtSlot` |
| Image processing | Pillow (PIL) |
| Storage | SQLite via `sqlite3` (WAL mode, thread-local connections) |
| Duplicate detection | MD5 file hash on import |

The backend (`managers/`, `database.py`) is fully decoupled from the UI layer. All database access goes through manager classes, making it straightforward to swap the UI toolkit or add an API layer in the future.

---

## 📋 Roadmap / Planned Features

- [ ] Keyboard shortcut customisation
- [ ] Image annotation / notes per image
- [ ] Colour-grading / filter overlays on the workspace canvas
- [ ] Export workspace as PDF / PureRef `.pur` format
- [ ] Plugin system for custom importers

---

## 📄 License

MIT License — see `LICENSE` for details.

---

> Made for artists, by an artist. Inspired by PureRef.