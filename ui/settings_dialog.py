import webbrowser

from pathlib import Path



from PyQt5.QtCore import Qt

from PyQt5.QtWidgets import (

    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,

    QPushButton, QSlider, QTabWidget, QVBoxLayout, QWidget,

)



from app_settings import get_settings

from database import get_base_dir



try:

    from version import APP_VERSION

except ImportError:

    APP_VERSION = "Unknown"



DANBOORU_API_HELP_URL = "https://danbooru.donmai.us/profile"





class SettingsDialog(QDialog):

    TAB_SETTINGS = 0

    TAB_DANBOORU = 1

    TAB_ABOUT = 2



    def __init__(self, parent=None, initial_tab: int = 0):

        super().__init__(parent)

        self._settings = get_settings()

        self.setWindowTitle("Settings & About")

        self.setFixedSize(480, 520)



        layout = QVBoxLayout(self)

        self.tabview = QTabWidget()

        layout.addWidget(self.tabview)



        self.tab_settings = QWidget()

        self.tab_danbooru = QWidget()

        self.tab_about = QWidget()

        self.tabview.addTab(self.tab_settings, "Settings")

        self.tabview.addTab(self.tab_danbooru, "Danbooru")

        self.tabview.addTab(self.tab_about, "About")



        self._build_settings_tab()

        self._build_danbooru_tab()

        self._build_about_tab()

        self.tabview.setCurrentIndex(max(0, min(initial_tab, self.tabview.count() - 1)))



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



    def _build_danbooru_tab(self) -> None:

        layout = QVBoxLayout(self.tab_danbooru)

        layout.setAlignment(Qt.AlignTop)



        intro = QLabel(

            "Optional Danbooru account credentials for higher rate limits and "

            "restricted content access. Saved on this computer only."

        )

        intro.setWordWrap(True)

        intro.setStyleSheet("color: #94A3B8; font-size: 11px;")

        layout.addWidget(intro)



        help_row = QHBoxLayout()

        help_lbl = QLabel(

            f'<a href="{DANBOORU_API_HELP_URL}">Open Danbooru profile (API key)</a>'

        )

        help_lbl.setOpenExternalLinks(True)

        help_lbl.setStyleSheet("color: #A78BFA; font-size: 11px;")

        help_row.addWidget(help_lbl)

        help_row.addStretch()

        layout.addLayout(help_row)



        layout.addWidget(QLabel("Username"))

        self.danbooru_login_edit = QLineEdit()
        self.danbooru_login_edit.setClearButtonEnabled(True)

        self.danbooru_login_edit.setPlaceholderText("Your Danbooru username")

        self.danbooru_login_edit.setText(self._settings.get_danbooru_login())

        layout.addWidget(self.danbooru_login_edit)



        layout.addWidget(QLabel("API key"))

        self.danbooru_api_key_edit = QLineEdit()
        self.danbooru_api_key_edit.setClearButtonEnabled(True)

        self.danbooru_api_key_edit.setPlaceholderText("Paste API key from your Danbooru profile")

        self.danbooru_api_key_edit.setEchoMode(QLineEdit.Password)

        self.danbooru_api_key_edit.setText(self._settings.get_danbooru_api_key())

        layout.addWidget(self.danbooru_api_key_edit)



        show_key_btn = QPushButton("Show / hide API key")

        show_key_btn.setFlat(True)

        show_key_btn.setStyleSheet("color: #94A3B8; text-align: left;")

        show_key_btn.clicked.connect(self._toggle_api_key_visibility)

        layout.addWidget(show_key_btn)



        env_hint = QLabel(

            "Tip: a .env file next to the exe can also set DANBOORU_LOGIN and "

            "DANBOORU_API_KEY (overrides saved settings)."

        )

        env_hint.setWordWrap(True)

        env_hint.setStyleSheet("color: #64748B; font-size: 10px;")

        layout.addWidget(env_hint)



        btn_row = QHBoxLayout()

        save_btn = QPushButton("Save credentials")

        save_btn.setStyleSheet("background-color: #7C3AED;")

        save_btn.clicked.connect(self._save_danbooru_credentials)

        btn_row.addWidget(save_btn)

        clear_btn = QPushButton("Clear")

        clear_btn.clicked.connect(self._clear_danbooru_credentials)

        btn_row.addWidget(clear_btn)

        btn_row.addStretch()

        layout.addLayout(btn_row)



        self._danbooru_status = QLabel("")

        self._danbooru_status.setStyleSheet("color: #94A3B8; font-size: 11px;")

        layout.addWidget(self._danbooru_status)

        self._update_danbooru_status_label()



        layout.addStretch()



    def _toggle_api_key_visibility(self) -> None:

        if self.danbooru_api_key_edit.echoMode() == QLineEdit.Password:

            self.danbooru_api_key_edit.setEchoMode(QLineEdit.Normal)

        else:

            self.danbooru_api_key_edit.setEchoMode(QLineEdit.Password)



    def _update_danbooru_status_label(self) -> None:

        login = self.danbooru_login_edit.text().strip()

        key = self.danbooru_api_key_edit.text().strip()

        if login and key:

            self._danbooru_status.setText(f"Ready — signed in as {login}")

        elif login or key:

            self._danbooru_status.setText("Enter both username and API key to authenticate.")

        else:

            self._danbooru_status.setText("No credentials — anonymous search (lower rate limits).")



    def _apply_danbooru_credentials_to_app(self) -> None:

        main = self.parent()

        if main and hasattr(main, "danbooru_view"):

            main.danbooru_view.refresh_credentials()



    def _save_danbooru_credentials(self) -> None:

        login = self.danbooru_login_edit.text().strip()

        api_key = self.danbooru_api_key_edit.text().strip()

        if (login and not api_key) or (api_key and not login):

            QMessageBox.warning(

                self,

                "Incomplete credentials",

                "Please enter both username and API key, or clear both fields.",

            )

            return

        self._settings.set_danbooru_login(login)

        self._settings.set_danbooru_api_key(api_key)

        self._settings.sync()

        self._apply_danbooru_credentials_to_app()

        self._update_danbooru_status_label()

        if login and api_key:

            QMessageBox.information(

                self,

                "Danbooru",

                "Credentials saved. You can search immediately — no restart needed.",

            )

        else:

            QMessageBox.information(

                self,

                "Danbooru",

                "Credentials cleared. Anonymous search will be used.",

            )



    def _clear_danbooru_credentials(self) -> None:

        self.danbooru_login_edit.clear()

        self.danbooru_api_key_edit.clear()

        self._settings.clear_danbooru_credentials()

        self._settings.sync()

        self._apply_danbooru_credentials_to_app()

        self._update_danbooru_status_label()



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

        add_info("Requirements:", "Windows 10/11 (64-bit) · 4 GB RAM · 1280×720 display")

        add_info("Support:", "Report an issue on GitHub", is_link=True)


