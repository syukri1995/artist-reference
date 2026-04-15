"""
gallery_view.py — Main gallery browser with sidebar navigation and async image loading.
"""
import threading
from pathlib import Path

from PyQt5.QtCore import Qt, QPoint, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget,
)
from PIL import Image

from managers.collection_manager import CollectionManager
from managers.image_manager import ImageManager
from managers.tag_manager import TagManager
from utils_image import pil_to_qpixmap


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class GalleryWorker(QThread):
    """Loads thumbnails off the main thread and emits the enriched list."""

    images_loaded = pyqtSignal(list)

    def __init__(self, images: list) -> None:
        super().__init__()
        self.images = images

    def run(self) -> None:
        out = []
        for data in self.images:
            try:
                thumb = data.get('thumbnail_path') or ''
                src = thumb if thumb and Path(thumb).exists() else data['file_path']
                if not Path(src).exists():
                    continue
                img = Image.open(src)
                img.thumbnail((300, 300))
                data['qpixmap'] = pil_to_qpixmap(img)
                out.append(data)
            except Exception as exc:
                print(f"GalleryWorker: {data['file_path']}: {exc}")
            self.msleep(1)
        self.images_loaded.emit(out)


# ---------------------------------------------------------------------------
# Clickable image card
# ---------------------------------------------------------------------------

class ImageCard(QLabel):
    """A square thumbnail card that emits click / right-click signals."""

    clicked = pyqtSignal()
    right_clicked = pyqtSignal(QPoint)

    _STYLE_NORMAL   = "background-color: #1E293B; border-radius: 8px; padding: 4px;"
    _STYLE_SELECTED = "background-color: #7C3AED; border-radius: 8px; padding: 4px;"

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(220, 220)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(self._STYLE_NORMAL)

    def set_selected(self, selected: bool) -> None:
        self.setStyleSheet(self._STYLE_SELECTED if selected else self._STYLE_NORMAL)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit(event.globalPos())


# ---------------------------------------------------------------------------
# Gallery view
# ---------------------------------------------------------------------------

class GalleryView(QWidget):
    """Main gallery panel: topbar + sidebar + image grid + pagination."""

    switch_to_workspace    = pyqtSignal(list, bool)
    show_upload            = pyqtSignal()
    show_detached_workspace = pyqtSignal(list, bool)

    _ITEMS_PER_PAGE = 50

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.image_mgr      = ImageManager()
        self.collection_mgr = CollectionManager()
        self.tag_mgr        = TagManager()

        # Filter state
        self.current_collection_id = None
        self.current_tag_id        = None
        self.current_search_term   = None
        self.only_favorites        = False
        self.only_recent           = False
        self.current_page          = 1
        self.columns               = 4

        # Selection & path→id map
        self.selected_images: set  = set()
        self.path_to_id: dict      = {}
        self._cards: dict          = {}   # file_path -> ImageCard widget

        self._worker: GalleryWorker | None = None

        self._setup_ui()
        self.refresh_collections_list()
        self.refresh_smart_collections_list()
        self.refresh_tags_list()
        self.load_gallery()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())

        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addLayout(self._build_gallery_area(), stretch=1)
        root.addLayout(body, stretch=1)

        self._autocomplete_menu = QMenu(self)

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background-color: #1E293B;")
        bar.setFixedHeight(64)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        logo = QLabel("Artist Reference")
        logo.setStyleSheet("font-size: 20px; font-weight: bold; color: #E2E8F0;")
        layout.addWidget(logo)

        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search filenames or tags…")
        self.search_entry.setFixedWidth(300)
        self.search_entry.returnPressed.connect(self._on_search)
        self.search_entry.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_entry)

        layout.addStretch()

        layout.addWidget(QLabel("Columns:"))
        self.columns_slider = QSlider(Qt.Horizontal)
        self.columns_slider.setRange(2, 8)
        self.columns_slider.setValue(4)
        self.columns_slider.setFixedWidth(100)
        self.columns_slider.valueChanged.connect(lambda v: self._set_columns(v))
        layout.addWidget(self.columns_slider)

        self.bulk_tag_btn = QPushButton("🏷 Retag Selected")
        self.bulk_tag_btn.setEnabled(False)
        self.bulk_tag_btn.clicked.connect(self._bulk_retag)
        layout.addWidget(self.bulk_tag_btn)

        settings_btn = QPushButton("⚙ Settings")
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)

        upload_btn = QPushButton("＋ Upload")
        upload_btn.setStyleSheet("background-color: #7C3AED; border-color: #6D28D9;")
        upload_btn.clicked.connect(self.show_upload.emit)
        layout.addWidget(upload_btn)

        return bar

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(210)
        sidebar.setStyleSheet("background-color: #0F172A;")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignTop)

        def nav_btn(label: str, slot, style: str = "") -> QPushButton:
            b = QPushButton(label)
            b.clicked.connect(slot)
            if style:
                b.setStyleSheet(style)
            return b

        layout.addWidget(nav_btn("All Images",        self.reset_filters))
        layout.addWidget(nav_btn("★ Favorites",       self.set_favorites_filter, "color: #F59E0B;"))
        layout.addWidget(nav_btn("⏱ Recently Viewed", self.set_recent_filter,    "color: #10B981;"))

        layout.addWidget(self._section_label("Collections"))
        self.collections_list = QListWidget()
        self.collections_list.setFixedHeight(120)
        self.collections_list.itemClicked.connect(
            lambda item: self.set_collection(item.data(Qt.UserRole)))
        layout.addWidget(self.collections_list)
        layout.addWidget(nav_btn("＋ New Collection", self._create_collection))

        layout.addWidget(self._section_label("Smart Collections"))
        self.smart_collections_list = QListWidget()
        self.smart_collections_list.setFixedHeight(80)
        self.smart_collections_list.itemClicked.connect(
            lambda item: self.set_tag(item.data(Qt.UserRole)))
        layout.addWidget(self.smart_collections_list)
        layout.addWidget(nav_btn("＋ New Smart", self._create_smart_collection))

        layout.addWidget(self._section_label("Tags"))
        self.tags_list = QListWidget()
        self.tags_list.setFixedHeight(120)
        self.tags_list.itemClicked.connect(
            lambda item: self.set_tag(item.data(Qt.UserRole)))
        layout.addWidget(self.tags_list)
        layout.addWidget(nav_btn("＋ New Tag", self._create_tag))

        layout.addStretch()

        layout.addWidget(nav_btn("▶ Open Workspace",    self._open_workspace))
        layout.addWidget(nav_btn("＋ Add to Workspace", self._add_to_workspace))
        layout.addWidget(nav_btn("⧉ Detach Workspace",  self._open_detached_workspace))

        return sidebar

    def _build_gallery_area(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.gallery_scroll = QScrollArea()
        self.gallery_scroll.setWidgetResizable(True)
        self._gallery_widget = QWidget()
        self.gallery_grid = QGridLayout(self._gallery_widget)
        self.gallery_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.gallery_grid.setSpacing(8)
        self.gallery_scroll.setWidget(self._gallery_widget)
        layout.addWidget(self.gallery_scroll, stretch=1)

        # Pagination bar
        pager = QWidget()
        pager.setStyleSheet("background-color: #1E293B;")
        pager.setFixedHeight(44)
        p_row = QHBoxLayout(pager)
        p_row.setContentsMargins(16, 0, 16, 0)

        self.prev_page_btn = QPushButton("‹ Previous")
        self.prev_page_btn.clicked.connect(self._prev_page)
        p_row.addWidget(self.prev_page_btn)

        self.page_label = QLabel("Page 1")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setStyleSheet("color: #E2E8F0;")
        p_row.addWidget(self.page_label, stretch=1)

        self.next_page_btn = QPushButton("Next ›")
        self.next_page_btn.clicked.connect(self._next_page)
        p_row.addWidget(self.next_page_btn)

        layout.addWidget(pager)
        return layout

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: bold; padding: 8px 0 2px 0;")
        return lbl

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_gallery(self) -> None:
        """Clear the grid and start background image loading."""
        # Clear current cards
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()
        self.path_to_id.clear()

        images = self.image_mgr.query_images(
            collection_id=self.current_collection_id,
            tag_ids=self.current_tag_id,
            search_term=self.current_search_term,
            only_favorites=self.only_favorites,
            only_recent=self.only_recent,
            limit=self._ITEMS_PER_PAGE,
            offset=(self.current_page - 1) * self._ITEMS_PER_PAGE,
        )

        if not images:
            placeholder = QLabel("No images found.")
            placeholder.setAlignment(Qt.AlignCenter)
            self.gallery_grid.addWidget(placeholder, 0, 0)
            self.page_label.setText(f"Page {self.current_page}")
            return

        # Kill any previous worker before starting a new one
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait()

        self._worker = GalleryWorker(images)
        self._worker.images_loaded.connect(self._render_images)
        self._worker.start()

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def reset_filters(self) -> None:
        self.current_collection_id = None
        self.current_tag_id        = None
        self.current_search_term   = None
        self.only_favorites        = False
        self.only_recent           = False
        self.current_page          = 1
        self.search_entry.blockSignals(True)
        self.search_entry.clear()
        self.search_entry.blockSignals(False)
        self.load_gallery()

    def set_favorites_filter(self) -> None:
        self.reset_filters()
        self.only_favorites = True
        self.load_gallery()

    def set_recent_filter(self) -> None:
        self.reset_filters()
        self.only_recent = True
        self.load_gallery()

    def set_collection(self, cid) -> None:
        self.reset_filters()
        self.current_collection_id = cid
        self.load_gallery()

    def set_tag(self, tid) -> None:
        self.reset_filters()
        self.current_tag_id = tid
        self.load_gallery()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _on_search(self) -> None:
        term = self.search_entry.text().strip()
        self.reset_filters()
        if term:
            self.search_entry.blockSignals(True)
            self.search_entry.setText(term)
            self.search_entry.blockSignals(False)
        self.current_search_term = term or None
        self._autocomplete_menu.hide()
        self.load_gallery()

    def _on_search_changed(self, text: str) -> None:
        term = text.strip()
        if len(term) < 2:
            self._autocomplete_menu.hide()
            return
        tags = self.tag_mgr.get_tags()
        matches = [t['name'] for t in tags if term.lower() in t['name'].lower()][:5]
        self._autocomplete_menu.clear()
        for name in matches:
            self._autocomplete_menu.addAction(name).triggered.connect(
                lambda _, n=name: self._apply_autocomplete(n))
        if matches:
            self._autocomplete_menu.popup(
                self.search_entry.mapToGlobal(self.search_entry.rect().bottomLeft()))
        else:
            self._autocomplete_menu.hide()

    def _apply_autocomplete(self, text: str) -> None:
        self.search_entry.setText(text)
        self._autocomplete_menu.hide()
        self._on_search()

    # ------------------------------------------------------------------
    # Columns / pagination
    # ------------------------------------------------------------------

    def _set_columns(self, val: int) -> None:
        self.columns = val
        self.load_gallery()

    def _prev_page(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self.load_gallery()

    def _next_page(self) -> None:
        self.current_page += 1
        self.load_gallery()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_images(self, images: list) -> None:
        row, col = 0, 0
        for data in images:
            path = data['file_path']
            self.path_to_id[path] = data['id']

            card = ImageCard()
            card.set_selected(path in self.selected_images)

            pixmap: QPixmap | None = data.get('qpixmap')
            if pixmap:
                card.setPixmap(pixmap.scaled(
                    200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))

            card.clicked.connect(lambda p=path, c=card: self._toggle_selection(p, c))
            card.right_clicked.connect(lambda pos, p=path: self._show_context_menu(pos, p))

            self._cards[path] = card
            self.gallery_grid.addWidget(card, row, col)
            col += 1
            if col >= self.columns:
                col, row = 0, row + 1

        self.page_label.setText(f"Page {self.current_page}")
        self._refresh_bulk_tag_button()

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _toggle_selection(self, path: str, card: ImageCard) -> None:
        if path in self.selected_images:
            self.selected_images.discard(path)
        else:
            self.selected_images.add(path)
        card.set_selected(path in self.selected_images)
        self._refresh_bulk_tag_button()

    def _refresh_bulk_tag_button(self) -> None:
        n = len(self.selected_images)
        self.bulk_tag_btn.setEnabled(bool(n))
        self.bulk_tag_btn.setText(f"🏷 Retag ({n})" if n else "🏷 Retag Selected")

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos: QPoint, file_path: str) -> None:
        targets = set(self.selected_images) | {file_path}

        menu = QMenu(self)

        col_menu = menu.addMenu("Add to Collection")
        for c in self.collection_mgr.get_collections():
            col_menu.addAction(c['name']).triggered.connect(
                lambda _, cid=c['id']: self._add_to_collection(targets, cid))

        if self.current_collection_id:
            menu.addAction("Remove from this Collection").triggered.connect(
                lambda: self._remove_from_collection(targets))

        menu.addAction("🏷 Edit Tags").triggered.connect(
            lambda: self._show_tag_dialog(targets))
        menu.addAction("★ Toggle Favorite").triggered.connect(
            lambda: self._toggle_favorites(targets))
        menu.addSeparator()
        menu.addAction("▶ Open in Workspace").triggered.connect(
            lambda: self.switch_to_workspace.emit(list(targets), True))
        menu.addAction("＋ Add to Workspace").triggered.connect(
            lambda: self.switch_to_workspace.emit(list(targets), False))
        menu.addSeparator()
        menu.addAction("🗑 Delete Image").triggered.connect(
            lambda: self._delete_images(targets))

        menu.popup(pos)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _add_to_collection(self, paths: set, cid: int) -> None:
        ids = [self.path_to_id[p] for p in paths if p in self.path_to_id]
        if ids:
            self.collection_mgr.add_images_to_collection(ids, cid)

    def _remove_from_collection(self, paths: set) -> None:
        ids = [self.path_to_id[p] for p in paths if p in self.path_to_id]
        if ids and self.current_collection_id:
            self.collection_mgr.remove_images_from_collection(ids, self.current_collection_id)
            self.load_gallery()

    def _show_tag_dialog(self, paths: set) -> None:
        ids = [self.path_to_id[p] for p in paths if p in self.path_to_id]
        if not ids:
            return

        single = len(ids) == 1
        all_tags = self.tag_mgr.get_tags()
        active_ids = {t['id'] for t in (self.tag_mgr.get_tags_for_image(ids[0]) if single else [])}

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Tags")
        layout = QVBoxLayout(dialog)

        checkboxes: dict = {}
        for t in all_tags:
            cb = QCheckBox(t['name'])
            cb.setChecked(t['id'] in active_ids)
            layout.addWidget(cb)
            checkboxes[t['id']] = cb

        def _save() -> None:
            selected = [tid for tid, cb in checkboxes.items() if cb.isChecked()]
            for img_id in ids:
                if single:
                    self.tag_mgr.remove_all_tags_from_image(img_id)
                self.tag_mgr.add_tags_to_image(img_id, selected)
            dialog.accept()

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(_save)
        layout.addWidget(save_btn)
        dialog.exec_()

    def _toggle_favorites(self, paths: set) -> None:
        self.image_mgr.toggle_favorites(paths)
        self.load_gallery()

    def _delete_images(self, paths: set) -> None:
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(paths)} image(s) from library?",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        for p in paths:
            self.image_mgr.delete_image(p)
        self.selected_images -= paths
        self._refresh_bulk_tag_button()
        self.load_gallery()

    def _bulk_retag(self) -> None:
        if self.selected_images:
            self._show_tag_dialog(self.selected_images)

    def _open_workspace(self) -> None:
        self.switch_to_workspace.emit(list(self.selected_images), True)

    def _add_to_workspace(self) -> None:
        if not self.selected_images:
            QMessageBox.warning(self, "Notice", "Select images first.")
            return
        self.switch_to_workspace.emit(list(self.selected_images), False)

    def _open_detached_workspace(self) -> None:
        self.show_detached_workspace.emit(list(self.selected_images), True)

    def _open_settings(self) -> None:
        from ui.settings_dialog import SettingsDialog
        SettingsDialog(self).exec_()

    # ------------------------------------------------------------------
    # Sidebar list refresh
    # ------------------------------------------------------------------

    def refresh_collections_list(self) -> None:
        self.collections_list.clear()
        tree: dict = {}
        roots = []
        for c in self.collection_mgr.get_collections():
            pid = c.get('parent_id')
            if pid is None:
                roots.append(c)
            else:
                tree.setdefault(pid, []).append(c)

        def _add_node(node: dict, depth: int) -> None:
            item = QListWidgetItem("  " * depth + node['name'])
            item.setData(Qt.UserRole, node['id'])
            self.collections_list.addItem(item)
            for child in tree.get(node['id'], []):
                _add_node(child, depth + 1)

        for r in roots:
            _add_node(r, 0)

    def _create_collection(self) -> None:
        name, ok = QInputDialog.getText(
            self, "New Collection", "Name (use / for sub-folders, e.g. People/Portraits):")
        if not ok or not name:
            return
        parts = [p.strip() for p in name.strip('/').split('/') if p.strip()]
        parent_id = None
        for part in parts:
            cols = self.collection_mgr.get_collections()
            match = next((c for c in cols if c['name'] == part and c.get('parent_id') == parent_id), None)
            if not match:
                self.collection_mgr.create_collection(part, parent_id=parent_id)
                cols = self.collection_mgr.get_collections()
                match = next((c for c in cols if c['name'] == part and c.get('parent_id') == parent_id), None)
            if match:
                parent_id = match['id']
        self.refresh_collections_list()

    def refresh_smart_collections_list(self) -> None:
        self.smart_collections_list.clear()
        for sc in self.collection_mgr.get_smart_collections():
            item = QListWidgetItem(sc['name'])
            item.setData(Qt.UserRole, sc['tag_ids'])
            self.smart_collections_list.addItem(item)

    def _create_smart_collection(self) -> None:
        name, ok = QInputDialog.getText(self, "New Smart Collection", "Name:")
        if not ok or not name:
            return
        tags_str, ok2 = QInputDialog.getText(
            self, "New Smart Collection", "Required tags (comma-separated):")
        if not ok2 or not tags_str:
            return
        tag_names = [t.strip().lower() for t in tags_str.split(',') if t.strip()]
        all_tags = self.tag_mgr.get_tags()
        tag_ids = [t['id'] for t in all_tags if t['name'].lower() in tag_names]
        if not tag_ids:
            QMessageBox.warning(self, "Error", "None of the specified tags exist.")
            return
        if self.collection_mgr.create_smart_collection(name, tag_ids):
            self.refresh_smart_collections_list()

    def refresh_tags_list(self) -> None:
        self.tags_list.clear()
        for t in self.tag_mgr.get_tags():
            item = QListWidgetItem(t['name'])
            item.setData(Qt.UserRole, t['id'])
            self.tags_list.addItem(item)

    def _create_tag(self) -> None:
        name, ok = QInputDialog.getText(self, "New Tag", "Tag name:")
        if ok and name and self.tag_mgr.create_tag(name):
            self.refresh_tags_list()
