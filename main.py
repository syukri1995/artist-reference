import sys
import os
from pathlib import Path

# Disable OpenCL for OpenCV globally to prevent driver/build conflicts (CL_BUILD_PROGRAM_FAILURE)
os.environ["OPENCV_OCL4DNN_DISABLE_OPCL"] = "1"
os.environ["OPENCV_OPENCL_RUNTIME"] = "disabled"

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QScrollArea, QShortcut, QStackedWidget,
    QVBoxLayout, QWidget,
)
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt, QTimer

from app_settings import get_settings
from database import init_db
from logging_config import setup_logging
from ui.branding import apply_window_icon
from ui.theme import build_stylesheet
from ui.toast import ToastOverlay
from version import APP_VERSION, UPDATE_URL
from managers.update_manager import UpdateManager
from managers.backup_manager import BackupManager
from managers.ai_manager import AIManager
from ui.gallery_view import GalleryView
from ui.workspace_view import WorkspaceView
from ui.upload_view import UploadView
from ui.danbooru_view import DanbooruView
from ui.update_dialog import UpdateDialog

def load_local_env() -> None:
    base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    env_path = base_dir / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env()

def resource_path(relative_path: str) -> str:
    """Resolve a resource path that works both in dev and when frozen by PyInstaller."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)

# Gallery needs room for sidebar + grid; workspace overlay can be tiny.
_GALLERY_MIN_SIZE = (1000, 640)
_WORKSPACE_MIN_SIZE = (180, 100)

SHORTCUTS_REFERENCE = [
    ("F1", "Toggle keyboard shortcuts reference panel"),
    ("Double-click (gallery)", "Open image in workspace"),
    ("Ctrl + Click", "Toggle image selection in gallery"),
    ("Shift + Click", "Range-select images in gallery"),
    ("Delete / Backspace", "Remove selected image(s) from workspace canvas"),
    ("Ctrl + Z / Ctrl + Y", "Undo / redo canvas edits"),
    ("Arrow keys (gallery)", "Move selection between thumbnails"),
    ("Scroll Wheel", "Zoom canvas in / out"),
    ("Ctrl + Scroll Wheel", "Scale the selected image"),
    ("Right-click drag", "Pan the workspace canvas"),
    ("Middle-click drag", "Pan the workspace canvas"),
    ("` (backtick)", "Toggle workspace toolbar / open compact menu"),
    ("Float mode", "Scale references when resizing window (top bar → Float)"),
]


class DetachedWorkspaceWindow(QMainWindow):
    """Detached workspace window that syncs state back to the main window on close."""

    def __init__(self, app: "Application") -> None:
        super().__init__()
        self._app = app

    def closeEvent(self, event) -> None:
        self._app._on_detached_closed()
        super().closeEvent(event)


class Application(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Artist Reference Manager")
        apply_window_icon(self)
        self.setMinimumSize(*_GALLERY_MIN_SIZE)
        self.setStyleSheet(build_stylesheet())

        self._settings = get_settings()
        geom = self._settings.get_geometry()
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(1440, 900)

        self.statusBar().showMessage("Ready")
        self._toast = ToastOverlay(self)

        init_db()

        # Keyboard shortcuts
        self.shortcut_f1 = QShortcut(QKeySequence("F1"), self)
        self.shortcut_f1.activated.connect(self.toggle_shortcuts_panel)
        self.shortcuts_panel = None

        # Main Central Widget and Layout setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Use QStackedWidget to manage multiple screens
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)
        
        # Initialize views
        self.gallery_view = GalleryView(
            self,
            status_callback=self.show_status,
            toast_callback=self.show_toast,
        )
        self.workspace_view = WorkspaceView(
            self,
            self.show_gallery,
            self.toggle_topmost,
            self.toggle_fullscreen,
            status_callback=self.show_status,
            toast_callback=self.show_toast,
        )
        self.upload_view = UploadView(
            self,
            self.show_gallery,
            self._on_upload_complete,
            status_callback=self.show_status,
            toast_callback=self.show_toast,
            danbooru_callback=self.show_danbooru,
        )
        self.danbooru_view = DanbooruView(
            self,
            back_callback=self.show_gallery,
            status_callback=self.show_status,
            toast_callback=self.show_toast,
            on_import_done=self._on_danbooru_import_done,
        )
        self.workspace_view.current_slot = self._settings.get_workspace_slot()
        opacity = self._settings.get_opacity() / 100.0
        self.setWindowOpacity(opacity)
        
        self.gallery_view.switch_to_workspace.connect(self.show_workspace)
        self.gallery_view.import_to_workspace_slot.connect(self.import_to_workspace_slot)
        self.gallery_view.show_upload.connect(self.show_upload)
        self.gallery_view.show_danbooru.connect(self.show_danbooru)
        self.gallery_view.show_detached_workspace.connect(self.show_detached_workspace)
        self.workspace_view.show_in_gallery_request.connect(self._show_image_in_gallery)
        
        self.stacked_widget.addWidget(self.gallery_view)
        self.stacked_widget.addWidget(self.workspace_view)
        self.stacked_widget.addWidget(self.upload_view)
        self.stacked_widget.addWidget(self.danbooru_view)
        
        self.show_gallery()
        
        # Initialize AI Manager once
        self.ai_manager = AIManager()
        self.ai_manager._progress_callback = self._on_ai_progress

    def _on_ai_progress(self, current, total, image_id=None, status='scanning', tags=None):
        """Handle progress updates from the AI Manager."""
        # Update Gallery UI (thread-safe via QTimer)
        # Capture current values in lambda defaults to avoid closure issues
        QTimer.singleShot(0, lambda c=current, t=total, i=image_id, s=status, tg=tags: 
                          self.gallery_view.set_ai_scan_progress(c, t, i, s, tags=tg))
        
        # Update Settings Dialog if open
        from PyQt5.QtWidgets import QDialog
        for child in self.findChildren(QDialog):
            if hasattr(child, "update_scan_progress"):
                QTimer.singleShot(0, lambda c=child: c.update_scan_progress(current, total))

    def _start_ai_scanner(self, scan_all: bool = False):
        """Request the AI manager to enqueue pending or all images for background analysis."""
        self.ai_manager.scan_pending_images(scan_all=scan_all)

    def _run_auto_backup(self):
        import threading
        import logging
        def run():
            try:
                bm = BackupManager()
                path = bm.auto_backup()
                if path:
                    logging.getLogger(__name__).info(f"Auto-backup created: {path}")
            except Exception as e:
                logging.getLogger(__name__).error(f"Auto-backup startup task failed: {e}")
        threading.Thread(target=run, daemon=True).start()

    def show_status(self, message: str, timeout_ms: int = 5000) -> None:
        self.statusBar().showMessage(message, timeout_ms)

    def show_toast(self, message: str, duration_ms: int = 3000) -> None:
        self._toast.show_message(message, duration_ms)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_toast"):
            self._toast.setGeometry(self.rect())

    def closeEvent(self, event) -> None:
        self._settings.set_geometry(self.saveGeometry())
        self._settings.set_opacity(int(self.windowOpacity() * 100))
        self._settings.set_columns(self.gallery_view.columns)
        self._settings.set_workspace_slot(self.workspace_view.current_slot)
        self._settings.set_gallery_sort(self.gallery_view.sort_by)
        self._settings.sync()
        super().closeEvent(event)

    def _on_upload_complete(self) -> None:
        self.show_gallery()
        self.show_toast("Upload complete")
        self.show_status("Upload finished")
        # Trigger priority AI scan for new uploads
        self._start_ai_scanner(scan_all=False)

    def _run_health_check(self):
        from managers.image_manager import ImageManager
        import threading
        
        def run_check():
            im = ImageManager()
            missing = im.check_health()
            if missing:
                # Use QTimer.singleShot(0) to run UI code safely back on the main thread
                QTimer.singleShot(0, lambda: self._show_health_dialog(im, missing))
                
        threading.Thread(target=run_check, daemon=True).start()
        
    def _show_health_dialog(self, im, missing):
        reply = QMessageBox.question(self, "Health Check", f"Found {len(missing)} missing images in library.\nDo you want to clean them up?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            im.remove_missing_images(missing)
            self.gallery_view.load_gallery()

    def on_update_available(self, latest_version, release_notes, download_url):
        # The update check runs in a background thread; we must show the dialog on the main thread.
        QTimer.singleShot(0, lambda: self._show_update_dialog(latest_version, release_notes, download_url))

    def _show_update_dialog(self, latest_version, release_notes, download_url):
        dialog = UpdateDialog(self, APP_VERSION, latest_version, release_notes, download_url)
        dialog.exec_()

    def toggle_topmost(self, state):
        flag = Qt.WindowStaysOnTopHint
        if state:
            self.setWindowFlags(self.windowFlags() | flag)
        else:
            self.setWindowFlags(self.windowFlags() & ~flag)
        self.show()
        
    def toggle_fullscreen(self, state):
        if state:
            self.showFullScreen()
        else:
            self.showNormal()

    def _set_gallery_min_size(self) -> None:
        self.setMinimumSize(*_GALLERY_MIN_SIZE)
        self.statusBar().show()

    def _set_workspace_min_size(self) -> None:
        self.setMinimumSize(*_WORKSPACE_MIN_SIZE)
        self.statusBar().hide()

    def show_gallery(self):
        self._set_gallery_min_size()
        self.gallery_view.load_gallery()
        self.stacked_widget.setCurrentWidget(self.gallery_view)

    def _show_image_in_gallery(self, image_id: int) -> None:
        self.show_gallery()
        self.gallery_view.focus_image(image_id)

    def show_upload(self):
        self._set_gallery_min_size()
        self.upload_view.reset()
        self.stacked_widget.setCurrentWidget(self.upload_view)

    def show_danbooru(self):
        self._set_gallery_min_size()
        self.stacked_widget.setCurrentWidget(self.danbooru_view)

    def _on_danbooru_import_done(self) -> None:
        from database import rebuild_images_fts
        rebuild_images_fts()
        self.gallery_view.load_gallery()
        self.show_status("Library index updated after import", 4000)
        # Trigger priority AI scan for imported images
        self._start_ai_scanner(scan_all=False)

    def _is_detached_open(self) -> bool:
        return (
            hasattr(self, "detached_win")
            and self.detached_win is not None
            and self.detached_win.isVisible()
        )

    def _sync_workspace_autosave(self) -> None:
        detached_active = self._is_detached_open()
        self.workspace_view.set_autosave_enabled(not detached_active)
        if hasattr(self, "detached_ws") and self.detached_ws is not None:
            self.detached_ws.set_autosave_enabled(detached_active)

    def _on_detached_closed(self) -> None:
        if hasattr(self, "detached_ws") and self.detached_ws is not None:
            self.detached_ws.save_now()
            self.detached_ws.set_autosave_enabled(False)
        self.workspace_view.set_autosave_enabled(True)
        self.workspace_view._load_slot(self.workspace_view.current_slot)

    def show_workspace(self, selected_images=None, replace=True):
        self._set_workspace_min_size()
        paths = [str(p) for p in (selected_images or [])]
        if paths:
            self.gallery_view.image_mgr.mark_as_viewed(paths)
        self.workspace_view.load_images(paths, replace=replace)
        self.stacked_widget.setCurrentWidget(self.workspace_view)
        self._sync_workspace_autosave()

    def import_to_workspace_slot(self, selected_images=None, slot_id: int = 1) -> None:
        """Add selected gallery images to a workspace slot (1–5) without replacing it."""
        slot_id = max(1, min(5, int(slot_id)))
        paths = [str(p) for p in (selected_images or []) if p]
        if not paths:
            self.show_toast("No images selected")
            return
        self.gallery_view.image_mgr.mark_as_viewed(paths)

        ws = self.workspace_view
        on_workspace = self.stacked_widget.currentWidget() == ws
        detached = self._is_detached_open()
        detached_ws = self.detached_ws if detached else None

        if detached_ws and detached_ws.current_slot == slot_id:
            added = detached_ws.load_images(paths, replace=False)
        elif on_workspace and ws.current_slot == slot_id:
            added = ws.load_images(paths, replace=False)
        else:
            added = ws.append_paths_to_slot(slot_id, paths)
            if on_workspace and ws.current_slot == slot_id:
                ws._load_slot(slot_id)
            if detached_ws and detached_ws.current_slot == slot_id:
                detached_ws._load_slot(slot_id)

        if added:
            self.show_toast(f"Added {added} image(s) to Workspace slot {slot_id}")
        else:
            self.show_toast(f"No new images added to Workspace slot {slot_id} (already present)")

    def show_detached_workspace(self, selected_images=None, replace=True):
        if self._is_detached_open():
            self.detached_ws.load_images(selected_images or [], replace=replace)
            self.detached_win.raise_()
            self.detached_win.activateWindow()
            self._sync_workspace_autosave()
            return

        slot = self.workspace_view.current_slot
        self.detached_win = DetachedWorkspaceWindow(self)
        self.detached_win.setWindowTitle(f"References — Slot {slot}")
        apply_window_icon(self.detached_win)
        self.detached_win.setMinimumSize(*_WORKSPACE_MIN_SIZE)
        self.detached_win.resize(640, 480)

        self.detached_ws = WorkspaceView(
            self.detached_win,
            self.detached_win.close,
            lambda s: self._toggle_detached_topmost(self.detached_win, s),
            lambda s: self._toggle_detached_fullscreen(self.detached_win, s),
            status_callback=self.show_status,
            toast_callback=self.show_toast,
        )
        self.detached_ws.current_slot = slot
        self.detached_win.setCentralWidget(self.detached_ws)
        self.detached_ws.load_images(selected_images or [], replace=replace)
        self.detached_ws.show_in_gallery_request.connect(self._show_image_in_gallery)
        self.detached_win.show()
        self._sync_workspace_autosave()
        self.show_toast(
            f"Edits save to Slot {slot}. Embedded workspace updates when you close this window."
        )
        
    def _toggle_detached_topmost(self, win, state):
        flag = Qt.WindowStaysOnTopHint
        if state:
            win.setWindowFlags(win.windowFlags() | flag)
        else:
            win.setWindowFlags(win.windowFlags() & ~flag)
        win.show()
        
    def _toggle_detached_fullscreen(self, win, state):
        if state: win.showFullScreen()
        else: win.showNormal()

    def toggle_shortcuts_panel(self):
        if self.shortcuts_panel and self.shortcuts_panel.isVisible():
            self.shortcuts_panel.close()
            self.shortcuts_panel = None
        else:
            self.shortcuts_panel = QDialog(self)
            self.shortcuts_panel.setWindowTitle("Keyboard Shortcuts")
            self.shortcuts_panel.resize(420, 380)

            root = QVBoxLayout(self.shortcuts_panel)
            title = QLabel("Keyboard Shortcuts")
            title.setStyleSheet("font-size: 18px; font-weight: bold; color: #E2E8F0;")
            root.addWidget(title)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("border: none;")
            content = QWidget()
            rows = QVBoxLayout(content)
            rows.setSpacing(10)

            for shortcut, action in SHORTCUTS_REFERENCE:
                row = QHBoxLayout()
                key_lbl = QLabel(shortcut)
                key_lbl.setStyleSheet(
                    "color: #E2E8F0; font-weight: bold; min-width: 140px;"
                )
                key_lbl.setFixedWidth(160)
                action_lbl = QLabel(action)
                action_lbl.setStyleSheet("color: #94A3B8;")
                action_lbl.setWordWrap(True)
                row.addWidget(key_lbl)
                row.addWidget(action_lbl, stretch=1)
                rows.addLayout(row)

            scroll.setWidget(content)
            root.addWidget(scroll)
            self.shortcuts_panel.show()

if __name__ == "__main__":
    setup_logging()
    app = QApplication(sys.argv)
    apply_window_icon(app)
    window = Application()
    window.show()
    sys.exit(app.exec_())
