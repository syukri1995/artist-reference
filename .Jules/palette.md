## 2024-03-22 - Workspace Canvas Placeholder Hints
**Learning:** Hidden canvas interactions (like Alt+Scrub to scale, Middle-click to pan) are often completely undiscoverable by users without reading external documentation. In an artist reference app, users are staring at the empty canvas immediately upon opening the workspace.
**Action:** Always utilize empty states not just as placeholders ("Images go here"), but as contextual educational surfaces. A centered, well-formatted list of shortcuts immediately unlocks advanced functionality for the user without requiring them to search for help. Re-show the empty state when all content is cleared to reinforce the learning.
## 2024-05-18 - Rich UI with HTML in PyQt Labels
**Learning:** PyQt `QLabel` widgets fully support a subset of HTML for rich text formatting. This is extremely useful for designing informative empty states without having to construct complex nested layout hierarchies or custom widgets. Using HTML `<table>` tags allows for perfect alignment of keyboard shortcut hints.
**Action:** When creating empty states or informational banners in PyQt, utilize HTML strings within `QLabel` to easily style and align content, rather than writing custom paint events or layout code.
## 2024-05-18 - QLineEdit Clear Button
**Learning:** PyQt5's `QLineEdit` has a native `setClearButtonEnabled(True)` method that instantly adds a clear button to text inputs. This is extremely helpful for search boxes and configuration fields, eliminating the need to select and delete text manually.
**Action:** Consistently use `setClearButtonEnabled(True)` for any `QLineEdit` instances used as search boxes, filters, or text inputs where clearing the entire string is a common action.
