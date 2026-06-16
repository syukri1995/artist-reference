# PureRef Project Instructions

Foundational mandates and architectural patterns for the PureRef / Artist Reference Manager project.

## Project Overview
A desktop application for artists to manage reference images, featuring a local gallery, tag management, and an infinite canvas workspace.

## Tech Stack
- **Language:** Python 3.12+
- **UI Framework:** PyQt5
- **Database:** SQLite
- **Image Processing:** OpenCV, ONNX Runtime (for AI)

## Coding Standards & Conventions
- When user prompt suggestion make sure don't agree to everything instead make sure there are pro and cons

### UI Development (PyQt5)
- **Composition over Inheritance:** Prefer building complex widgets through composition.
- **Styling:** Use external stylesheets (QSS) or centralized constants for colors and borders. Avoid hardcoding styles in every method.
- **Animations:** Use `QPropertyAnimation` for smooth visual transitions (e.g., color fades, opacity changes).
- **Thread Safety:** Always use `QTimer.singleShot(0, ...)` or Signals/Slots when updating the UI from background threads (like AI workers).

### Database (SQLite)
- **Migrations:** Add new columns or tables in `database.py` with `IF NOT EXISTS` or migration check logic.
- **FTS5:** Use the `images_fts` virtual table for all text-based searching (filenames, tags).

### AI & Background Tasks
- **Resource Management:** Ensure GPU/Hardware acceleration fallbacks are handled gracefully (e.g., OpenCV OpenCL conflicts).
- **Progress Reporting:** Always provide real-time UI feedback for long-running tasks using the `_progress_callback` pattern.

## Workflow Rules
- **Surgical Edits:** Use the `replace` tool for targeted changes to minimize token usage and avoid regressions.
- **Verification:** Always run the application or relevant scripts to verify UI changes, especially animations and layout updates.
- **Safety Mode:** Respect the "Safe Mode" settings for sensitive content; always blur thumbnails when enabled.
