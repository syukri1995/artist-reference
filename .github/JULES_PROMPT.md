# Jules AI Coding Agent Prompt
## Artist Reference Manager

### Project Overview
**Artist Reference Manager** is a desktop application built with Python + PyQt5 for artists to collect, organize, and reference images during creative work. It includes:
- **Gallery view** with tagging, collections, and smart collections
- **Infinite workspace canvas** (QGraphicsScene-based) for arranging references
- **SQLite database** backend with thumbnails
- **Danbooru import** integration
- **5-slot workspace saves** with auto-save

**Repository:** https://github.com/syukri1995/artist-reference

---

## 🎯 Your Role
You are an AI coding agent tasked with implementing features, bug fixes, and improvements to the Artist Reference Manager. Follow these guidelines for every task.

---

## 📋 Development Standards

### Code Style & Quality

#### Python Standards
- **Style Guide:** PEP 8 (https://pep8.org/)
- **Line Length:** 100 characters maximum
- **Indentation:** 4 spaces (no tabs)
- **Type Hints:** Use type hints for all function parameters and return types (Python 3.10+ syntax)

#### Naming Conventions
- **Classes:** PascalCase (e.g., `ImageManager`, `GalleryView`)
- **Functions/Methods:** snake_case (e.g., `import_image`, `toggle_favorite`)
- **Constants:** UPPER_SNAKE_CASE (e.g., `MAX_THUMBNAIL_SIZE`, `DEFAULT_COLUMNS`)
- **Private methods/attributes:** Prefix with `_` (e.g., `_compute_file_hash`)

#### Module Organization
- Keep related functionality in dedicated files under appropriate directories
  - `managers/` — business logic and data operations
  - `ui/` — UI components and views
  - `.github/workflows/` — CI/CD automation
  - `scripts/` — build and utility scripts
- Import order: stdlib → third-party → local
- Keep imports organized and remove unused imports

---

## 🧪 Testing Requirements

### Test Framework
- **Framework:** `unittest` (built-in Python testing framework)
- **Test Location:** `tests/` directory at repository root
- **Test Naming:** `test_*.py` files with `Test*` classes and `test_*` methods

### Test Coverage
- Write tests for all new functionality
- Aim for **80%+ code coverage** in modified modules
- Tests must pass before merging (enforced by CI)

### Running Tests Locally
```bash
# Run all tests
python -m unittest discover -s tests -v

# Run specific test file
python -m unittest tests.test_image_manager -v

# Run specific test class
python -m unittest tests.test_image_manager.TestImageManager -v

# Run specific test method
python -m unittest tests.test_image_manager.TestImageManager.test_import_image -v
```

### Writing Tests
```python
import unittest
from managers.image_manager import ImageManager

class TestImageManager(unittest.TestCase):
    def setUp(self):
        """Run before each test."""
        self.mgr = ImageManager()
    
    def tearDown(self):
        """Run after each test."""
        pass
    
    def test_compute_file_hash(self):
        """Test MD5 hash computation."""
        # Arrange
        test_file = Path("test_data/sample.jpg")
        
        # Act
        hash_result = self.mgr._compute_file_hash(test_file)
        
        # Assert
        self.assertEqual(len(hash_result), 32)  # MD5 is 32 hex chars
        self.assertTrue(all(c in "0123456789abcdef" for c in hash_result))
```

### Test Categories
- **Unit Tests:** Test individual functions/methods in isolation
- **Integration Tests:** Test interactions between modules (e.g., import → database → UI update)
- **Smoke Tests:** Basic validation (already in `scripts/smoke_test_exe.ps1`)

---

## 🔍 Linting & Code Quality

### Linting Tools (To Be Installed)
```bash
# Install linting dependencies
pip install flake8 pylint black isort
```

### Flake8 (PEP 8 Compliance)
```bash
# Check code style
flake8 . --count --statistics --show-source --max-line-length=100 \
  --exclude=.git,.venv,dist,build,*.egg-info

# Exit codes:
# 0 = all good
# 1 = style violations
# 2+ = configuration errors
```

**Flake8 Configuration** (create if needed):
```ini
# .flake8
[flake8]
max-line-length = 100
exclude = .git,.venv,dist,build,*.egg-info,.pytest_cache
ignore = E203,W503
```

### Pylint (Code Analysis)
```bash
# Check code quality
pylint --rcfile=.pylintrc . --fail-under=8.0
```

**Pylint Configuration** (create `.pylintrc` if needed):
```ini
[MASTER]
max-line-length = 100
disable = 
    missing-docstring,
    too-few-public-methods,
```

### Black (Auto-Formatting)
```bash
# Format code
black . --line-length 100

# Check without modifying
black . --check --line-length 100
```

### isort (Import Sorting)
```bash
# Sort imports
isort . --profile black --line-length 100

# Check without modifying
isort . --check-only --profile black --line-length 100
```

---

## 🚀 CI/CD Workflow

### GitHub Actions Workflow Files

#### `.github/workflows/test.yml` (Already Exists)
Runs on every push and pull request:
1. Checks out code
2. Sets up Python 3.11
3. Installs dependencies
4. **Runs tests:** `python -m unittest discover -s tests -v`

#### `.github/workflows/build.yml` (Already Exists)
Triggered on version tags (`v*`):
1. Checks out code
2. Sets up Python 3.11
3. **Runs tests** before building
4. Builds Windows executable with PyInstaller
5. Runs smoke tests
6. Packages and creates GitHub Release

### CI/CD Checklist Before Commit
- [ ] All tests pass locally: `python -m unittest discover -s tests -v`
- [ ] Code formatted with black: `black . --line-length 100`
- [ ] Imports sorted with isort: `isort . --profile black --line-length 100`
- [ ] No flake8 violations: `flake8 . --max-line-length=100`
- [ ] Type hints added for new functions
- [ ] Docstrings added for public methods
- [ ] No debug print statements or commented code left behind

---

## 📝 Git & Commit Standards

### Commit Messages
Format: `<type>: <description>`

Examples:
```
feat: Add keyboard shortcut customization UI
fix: Prevent workspace autosave race condition
refactor: Extract DatabaseConnection into separate module
test: Add comprehensive tests for ImageManager
docs: Update README with Linux installation steps
chore: Update dependencies to latest versions
```

**Types:**
- `feat` — new feature
- `fix` — bug fix
- `refactor` — code restructuring without behavior change
- `test` — test additions or fixes
- `docs` — documentation updates
- `chore` — dependency updates, build config, etc.

### Pull Request Checklist
- [ ] Descriptive title and description
- [ ] References any related issues
- [ ] Screenshots for UI changes
- [ ] All tests pass
- [ ] Code follows PEP 8 and styling guidelines
- [ ] New functions have type hints and docstrings

---

## 🏗️ Architecture & Design Patterns

### Current Structure
```
artist-reference/
├── main.py                       # App entry point, QMainWindow
├── database.py                   # SQLite init and migrations
├── app_settings.py               # User preferences (geometry, opacity, etc.)
├── version.py                    # Version constant and update URL
├── logging_config.py             # Logger setup
├── utils_image.py                # PIL → QPixmap helpers
├── managers/                     # Business logic layer
│   ├── image_manager.py          # Import, query, duplicate detection
│   ├── collection_manager.py     # Collections and smart collections
│   ├── tag_manager.py            # Tag CRUD
│   ├── workspace_manager.py      # Workspace state (5 slots)
│   ├── backup_manager.py         # Library backup/restore
│   ├── danbooru_manager.py       # Danbooru API integration
│   └── update_manager.py         # GitHub Releases check
├── ui/                           # Presentation layer
│   ├── gallery_view.py           # Gallery grid + sidebar
│   ├── workspace_view.py         # Canvas (QGraphicsScene)
│   ├── upload_view.py            # Drag-and-drop import
│   ├── danbooru_view.py          # Danbooru search UI
│   ├── settings_dialog.py        # Settings QDialog
│   ├── update_dialog.py          # Update available dialog
│   ├── theme.py                  # Stylesheet generation
│   ├── branding.py               # Window icon setup
│   ├── toast.py                  # Toast notifications
│   └── ...
├── tests/                        # Unit and integration tests
├── scripts/                      # Build and utility scripts
├── requirements.txt              # Runtime dependencies
├── requirements-build.txt        # Build dependencies (PyInstaller)
└── artist_ref_manager.spec       # PyInstaller build spec
```

### Design Principles
- **Separation of Concerns:** Managers handle data/logic; UI handles presentation
- **Thread Safety:** Database queries return detached dicts; async loading uses QThread
- **Error Recovery:** Graceful degradation when files move or external APIs fail
- **Resource Cleanup:** Properly close file handles and DB connections

### When Adding Features
1. **Data Layer:** Add manager methods or database operations
2. **Business Logic:** Implement in appropriate manager
3. **Presentation:** Add UI components in `ui/` directory
4. **Integration:** Wire signals/slots in `main.py` and views
5. **Testing:** Write unit tests for manager logic
6. **Documentation:** Update README if user-facing feature

---

## 🔧 Common Tasks & Workflows

### Adding a New Feature
1. Create feature branch: `git checkout -b feat/feature-name`
2. Implement in appropriate manager or UI module
3. Write tests in `tests/`
4. Update README if needed
5. Format code: `black . --line-length 100`
6. Run all tests: `python -m unittest discover -s tests -v`
7. Commit and push
8. Create PR with description

### Fixing a Bug
1. Create issue if not already exists
2. Create branch: `git checkout -b fix/issue-number-description`
3. Write failing test first (TDD)
4. Implement fix
5. Ensure test passes
6. Check no regressions: `python -m unittest discover -s tests -v`
7. Commit with reference: `fix: Description (fixes #123)`
8. Create PR

### Performance Optimization
- Profile with: `python -m cProfile -s cumtime main.py > profile.txt`
- Check database query performance using SQLite EXPLAIN QUERY PLAN
- Monitor memory usage for large image libraries (1000+)
- Test canvas performance with many objects (50+)

### Cross-Platform Testing
- **Windows:** Primary target (CI tests on windows-latest)
- **macOS:** Manual testing before major releases
- **Linux:** Not currently supported; future consideration

---

## 🐛 Debugging Tips

### Logging
- Logs are written to `logging_config.py`
- View application logs in:
  - **Frozen (exe):** `data/logs/artist_ref_manager.log`
  - **Dev mode:** Check console output

### Common Issues

**"Database locked" errors:**
- Check for unclosed connections
- Ensure `conn.close()` is called in finally blocks
- Consider connection pooling if issue persists

**Thumbnail generation failures:**
- Check Pillow can open the image format
- Verify file permissions
- Look for corrupted image files

**UI freezes during import:**
- Ensure import logic runs in background thread (QThread)
- Check for blocking operations on main thread
- Use `QTimer.singleShot()` to defer UI updates

**Workspace save/load issues:**
- Verify image IDs remain stable after import
- Check file paths resolve correctly on load
- Validate workspace slot boundaries (1–5)

---

## 📚 Dependencies

### Runtime (`requirements.txt`)
- **PyQt5==5.15.11** — UI framework
- **Pillow==10.4.0** — Image processing
- **certifi>=2024.2.2** — SSL certificates
- **requests>=2.31.0** — HTTP client for Danbooru API

### Build (`requirements-build.txt`)
- **PyInstaller** — Package as .exe
- **All runtime deps**

### Development (For Local Setup)
```bash
pip install -r requirements.txt
pip install -r requirements-build.txt

# For linting & formatting
pip install flake8 pylint black isort

# For testing
# (unittest is built-in)
```

---

## 🎯 Performance Targets

### UI Responsiveness
- Gallery load: < 2 seconds for 1000+ images
- Image import: Non-blocking, background thread
- Workspace interaction: 60 FPS (smooth panning/zooming)
- Search: < 500 ms for common queries

### Memory Usage
- Base app: < 100 MB
- Per 1000 images: + 50-100 MB (thumbnails cached in memory)
- Workspace with 50 images: < 200 MB additional

### Database
- Import 100 images: < 5 seconds
- Search with filters: < 500 ms
- Auto-save workspace: < 1 second

---

## 🚦 Quality Gates

**All PRs must pass:**
- ✅ Unit tests: `python -m unittest discover -s tests -v`
- ✅ Linting: `flake8 . --max-line-length=100` (no violations)
- ✅ Type hints: All new functions must have type annotations
- ✅ Code review: At least one approval
- ✅ No console errors: Application runs without warnings/errors

---

## 📖 Resources & References

- **PyQt5 Docs:** https://www.riverbankcomputing.com/static/Docs/PyQt5/
- **SQLite:** https://www.sqlite.org/lang.html
- **Pillow (PIL):** https://pillow.readthedocs.io/
- **Danbooru API:** https://danbooru.donmai.us/wiki_pages/43568 (tags API)
- **PEP 8:** https://pep8.org/
- **Python Type Hints:** https://docs.python.org/3.10/library/typing.html

---

## 🤝 Communication

When implementing tasks:
1. **Clarify requirements** if ambiguous
2. **Ask before major refactors** affecting multiple modules
3. **Report blockers** early (missing dependencies, unclear specs)
4. **Suggest alternatives** if a simpler approach exists
5. **Document decisions** in commit messages or PR descriptions

---

## ✅ Pre-Submission Checklist

Before submitting any code:
- [ ] All tests pass locally
- [ ] Code formatted with black
- [ ] Imports sorted with isort
- [ ] No flake8 violations
- [ ] Type hints on all new functions
- [ ] Docstrings on public methods
- [ ] Commit message follows format
- [ ] PR description is clear and references issues
- [ ] No debug code or console.log left behind
- [ ] Performance targets met (if applicable)

---

**Last Updated:** June 2026
**Maintained By:** syukri1995
