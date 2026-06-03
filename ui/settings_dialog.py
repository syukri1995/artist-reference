import webbrowser
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QSlider, QTabWidget, QVBoxLayout, QWidget,
)

from app_settings import get_settings
from database import get_base_dir

try:
    from version import APP_VERSION
except ImportError:
    APP_VERSION = "Unknown"


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = get_settings()
        self.setWindowTitle("Settings & About")
        self.setFixedSize(450, 420)

        layout = QVBoxLayout(self)
        self.tabview = QTabWidget()
        layout.addWidget(self.tabview)

        self.tab_settings = QWidget()
        self.tab_about = QWidget()
        self.tabview.addTab(self.tab_settings, "Settings")
        self.tabview.addTab(self.tab_about, "About")

        self._build_settings_tab()
        self._build_about_tab()

    def _build_settings_tab(self):
        layout = QVBoxLayout(self.tab_settings)
        layout.setAlignment(Qt.AlignTop)

        op_layout = QHBoxLayout()
        self.opacity_label = QLabel(f"Window Opacity: {self._settings.get_opacity()}%")
        self.opacity_label.setStyleSheet("font-weight: bold; color: #E2E8F0;")
        op_layout.addWidget(self.opacity_label)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(self._settings.get_opacity())
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        op_layout.addWidget(self.opacity_slider)
        layout.addLayout(op_layout)

        hint_lbl = QLabel(
            "Dismiss the canvas hint permanently after you learn pan/zoom controls."
        )
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        layout.addWidget(hint_lbl)

        dismiss_hint_btn = QPushButton("Dismiss workspace hints")
        dismiss_hint_btn.clicked.connect(self._dismiss_canvas_hint)
        layout.addWidget(dismiss_hint_btn)

        log_btn = QPushButton("Open log folder")
        log_btn.clicked.connect(self._open_log_folder)
        layout.addWidget(log_btn)

        backup_btn = QPushButton("Backup library (zip)…")
        backup_btn.clicked.connect(self._backup_library)
        layout.addWidget(backup_btn)

        restore_btn = QPushButton("Restore from backup…")
        restore_btn.clicked.connect(self._restore_library)
        layout.addWidget(restore_btn)

        layout.addStretch()

    def _on_opacity_changed(self, val: int) -> None:
        self.opacity_label.setText(f"Window Opacity: {val}%")
        self._settings.set_opacity(val)
        main = self.parent()
        if main:
            main.setWindowOpacity(val / 100.0)
        self.setWindowOpacity(val / 100.0)

    def _dismiss_canvas_hint(self) -> None:
        self._settings.set_show_canvas_hint(False)
        main = self.parent()
        if main and hasattr(main, "workspace_view"):
            main.workspace_view._hud.hide()

    def _backup_library(self) -> None:
        from managers.backup_manager import BackupManager
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save backup",
            "artist_reference_backup.zip",
            "Zip archives (*.zip)",
        )
        if not path:
            return
        try:
            out = BackupManager().create_backup(path)
            QMessageBox.information(self, "Backup complete", f"Saved to:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))

    def _restore_library(self) -> None:
        from managers.backup_manager import BackupManager
        if QMessageBox.question(
            self,
            "Restore backup",
            "This replaces your database and image folders. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open backup", "", "Zip archives (*.zip)")
        if not path:
            return
        try:
            from database import reset_thread_connection
            reset_thread_connection()
            BackupManager().restore_backup(path)
            QMessageBox.information(
                self,
                "Restore complete",
                "Library restored. Restart the app if the gallery looks stale.",
            )
            main = self.parent()
            if main and hasattr(main, "gallery_view"):
                main.gallery_view.load_gallery()
        except Exception as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))

    def _open_log_folder(self) -> None:
        log_dir = get_base_dir() / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        import os
        import sys
        if sys.platform == "win32":
            os.startfile(str(log_dir))
        else:
            webbrowser.open(log_dir.as_uri())

    def _build_about_tab(self):
        layout = QVBoxLayout(self.tab_about)
        layout.setAlignment(Qt.AlignTop)

        def add_info(title, value, is_link=False):
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("font-weight: bold; color: #E2E8F0;")
            layout.addWidget(title_lbl)

            val_lbl = QLabel(value)
            if is_link:
                val_lbl.setStyleSheet("color: #3B82F6; text-decoration: underline;")
                val_lbl.setCursor(Qt.PointingHandCursor)
                val_lbl.mousePressEvent = lambda e: webbrowser.open(
                    "https://github.com/syukri1995/artist-reference/issues"
                )
            layout.addWidget(val_lbl)

            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("background-color: #334155;")
            layout.addWidget(line)

        add_info("Software Version:", APP_VERSION)
        add_info("License:", "MIT License — free for personal and commercial use.")
        add_info("Requirements:", "Windows 10/11, macOS, or Linux · 4GB RAM · 1280×720 display")
        add_info("Support:", "Report an issue on GitHub", is_link=True)
