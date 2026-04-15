import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def resource_path(relative_path: str) -> str:
    """Resolve a resource path that works both in dev and when frozen by PyInstaller."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)

from PyQt5.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QShortcut, QStackedWidget, QVBoxLayout, QWidget,
)
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtCore import Qt, QTimer

from database import init_db
from version import APP_VERSION, UPDATE_URL
from managers.update_manager import UpdateManager
from ui.gallery_view import GalleryView
from ui.workspace_view import WorkspaceView
from ui.upload_view import UploadView
from ui.update_dialog import UpdateDialog

class Application(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Artist Reference Manager")
        self.resize(1440, 900)
        self.setMinimumSize(1200, 800)
        
        # Apply Global Dark Theme Style
        self.setStyleSheet("""
            QMainWindow { background-color: #0F172A; }
            QWidget { color: #E2E8F0; font-family: 'Segoe UI'; font-size: 13px; background-color: transparent; }
            QScrollArea { border: none; }
            QScrollArea > QWidget > QWidget { background-color: transparent; }

            QPushButton {
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 5px 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #334155; border-color: #7C3AED; }
            QPushButton:pressed { background-color: #7C3AED; border-color: #7C3AED; }
            QPushButton:disabled { color: #64748B; border-color: #1E293B; }

            QMenu {
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item { padding: 6px 24px 6px 12px; border-radius: 4px; }
            QMenu::item:selected { background-color: #7C3AED; color: #FFFFFF; }
            QMenu::separator { height: 1px; background: #334155; margin: 4px 8px; }

            QLineEdit { background-color: #1E293B; color: #E2E8F0; border-radius: 6px; padding: 6px; border: 1px solid #334155; }
            QLineEdit:focus { border: 1px solid #7C3AED; }

            QLabel { color: #94A3B8; background-color: transparent; }

            QListWidget {
                background-color: #0F172A;
                color: #E2E8F0;
                border: 1px solid #1E293B;
                border-radius: 4px;
            }
            QListWidget::item { padding: 4px 8px; border-radius: 3px; }
            QListWidget::item:selected { background-color: #7C3AED; color: #FFFFFF; }
            QListWidget::item:hover { background-color: #1E293B; }

            QCheckBox { color: #E2E8F0; spacing: 6px; }
            QCheckBox::indicator { width: 16px; height: 16px; border-radius: 3px; border: 1px solid #475569; background-color: #1E293B; }
            QCheckBox::indicator:checked { background-color: #7C3AED; border-color: #7C3AED; }

            QSlider::groove:horizontal { height: 4px; background: #334155; border-radius: 2px; }
            QSlider::handle:horizontal { background: #7C3AED; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #7C3AED; border-radius: 2px; }

            QScrollBar:vertical { background: #0F172A; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #334155; border-radius: 4px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #7C3AED; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar:horizontal { background: #0F172A; height: 8px; border-radius: 4px; }
            QScrollBar::handle:horizontal { background: #334155; border-radius: 4px; min-width: 30px; }
            QScrollBar::handle:horizontal:hover { background: #7C3AED; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        """)

        # Database initialization
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
        self.gallery_view = GalleryView(self)
        self.workspace_view = WorkspaceView(self, self.show_gallery, self.toggle_topmost, self.toggle_fullscreen)
        self.upload_view = UploadView(self, self.show_gallery, self.show_gallery)
        
        self.gallery_view.switch_to_workspace.connect(self.show_workspace)
        self.gallery_view.show_upload.connect(self.show_upload)
        self.gallery_view.show_detached_workspace.connect(self.show_detached_workspace)
        
        self.stacked_widget.addWidget(self.gallery_view)
        self.stacked_widget.addWidget(self.workspace_view)
        self.stacked_widget.addWidget(self.upload_view)
        
        self.show_gallery()
        
        # Check for updates silently
        self.update_manager = UpdateManager(APP_VERSION, UPDATE_URL)
        QTimer.singleShot(1000, lambda: self.update_manager.check_for_updates(self.on_update_available))
        QTimer.singleShot(500, self._run_health_check)

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

    def show_gallery(self):
        self.gallery_view.load_gallery()
        self.stacked_widget.setCurrentWidget(self.gallery_view)

    def show_upload(self):
        self.upload_view.reset()
        self.stacked_widget.setCurrentWidget(self.upload_view)

    def show_workspace(self, selected_images=None, replace=True):
        self.workspace_view.load_images(selected_images or [], replace=replace)
        self.stacked_widget.setCurrentWidget(self.workspace_view)

    def show_detached_workspace(self, selected_images=None, replace=True):
        if hasattr(self, 'detached_win') and self.detached_win and self.detached_win.isVisible():
            self.detached_ws.load_images(selected_images or [], replace=replace)
            self.detached_win.raise_()
            self.detached_win.activateWindow()
            return
            
        self.detached_win = QMainWindow(self)
        self.detached_win.setWindowTitle("Artist Reference - Detached Workspace")
        self.detached_win.resize(1000, 700)
        
        self.detached_ws = WorkspaceView(self.detached_win, self.detached_win.close, 
                                         lambda s: self._toggle_detached_topmost(self.detached_win, s), 
                                         lambda s: self._toggle_detached_fullscreen(self.detached_win, s))
        self.detached_win.setCentralWidget(self.detached_ws)
        self.detached_ws.load_images(selected_images or [], replace=replace)
        self.detached_win.show()
        
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
            self.shortcuts_panel.resize(400, 500)
            layout = QVBoxLayout(self.shortcuts_panel)
            label = QLabel("Shortcuts Cheatsheet")
            label.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
            layout.addWidget(label)
            self.shortcuts_panel.show()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Application()
    window.show()
    sys.exit(app.exec_())
