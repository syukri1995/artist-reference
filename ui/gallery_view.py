"""
gallery_view.py — Main gallery browser with sidebar navigation and async image loading.
"""
import math
import re
from pathlib import Path

from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPushButton, QScrollArea, QSlider, QSplitter, QVBoxLayout,
    QWidget,
)

from app_settings import get_settings
from managers.collection_manager import CollectionManager
from managers.image_manager import ImageManager
from managers.tag_manager import TagManager
from ui.branding import app_logo_pixmap
from ui.image_load_queue import ImageLoadQueue
from ui.loading_indicator import LoadingSpinner, LoadingStatusBar
from ui.tag_edit_dialog import TagEditDialog


# ---------------------------------------------------------------------------
# Clickable image card
# ---------------------------------------------------------------------------

class ImageCard(QWidget):
    """Thumbnail card with filename, favorite badge, and selection state."""

    clicked = pyqtSignal(object)
    double_clicked = pyqtSignal()
    right_clicked = pyqtSignal(QPoint)

    _STYLE_NORMAL = (
        "ImageCard { background-color: #1E293B; border: 2px solid #334155; border-radius: 8px; }"
    )
    _STYLE_SELECTED = (
        "ImageCard { background-color: #1E293B; border: 2px solid #7C3AED; border-radius: 8px; }"
    )

    def __init__(self, file_path: str, is_favorite: bool = False, missing: bool = False) -> None:
        super().__init__()
        self.file_path = file_path
        self._selected = False
        self._missing = missing
        self.setFixedSize(220, 248)
        self.setAttribute(Qt.WA_StyledBackground, True)
        if missing:
            self.setStyleSheet(
                "ImageCard { background-color: #1E293B; border: 2px solid #DC2626; border-radius: 8px; }"
            )
        self.setToolTip(file_path)
        self.setAccessibleName(Path(file_path).name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 4)
        layout.setSpacing(4)

        thumb_row = QHBoxLayout()
        self.thumb_wrap = QWidget()
        self.thumb_wrap.setFixedSize(200, 200)
        self.thumb_wrap.setAttribute(Qt.WA_StyledBackground, True)
        self._thumb_border_normal = (
            "background-color: #1E293B; border: 2px solid #334155; border-radius: 6px;"
        )
        self._thumb_border_selected = (
            "background-color: #1E293B; border: 3px solid #7C3AED; border-radius: 6px;"
        )
        self._thumb_border_missing = (
            "background-color: #1E293B; border: 2px solid #DC2626; border-radius: 6px;"
        )
        self.thumb_wrap.setStyleSheet(
            self._thumb_border_missing if missing else self._thumb_border_normal
        )
        thumb_inner = QVBoxLayout(self.thumb_wrap)
        thumb_inner.setContentsMargins(0, 0, 0, 0)
        thumb_inner.setAlignment(Qt.AlignCenter)
        self._spinner = LoadingSpinner(40, self.thumb_wrap)
        self.thumb = QLabel()
        self.thumb.setFixedSize(200, 200)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.hide()
        thumb_inner.addWidget(self._spinner, alignment=Qt.AlignCenter)
        thumb_inner.addWidget(self.thumb, alignment=Qt.AlignCenter)
        thumb_row.addWidget(self.thumb_wrap)
        if is_favorite:
            star = QLabel("★")
            star.setStyleSheet("color: #F59E0B; font-size: 14px; border: none;")
            star.setFixedWidth(16)
            thumb_row.addWidget(star, alignment=Qt.AlignTop)
        layout.addLayout(thumb_row)

        name = Path(file_path).name
        if len(name) > 28:
            name = name[:25] + "…"
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("color: #94A3B8; font-size: 11px; border: none;")
        self.name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.name_label)

    def set_loading(self, loading: bool) -> None:
        if loading:
            self._spinner.start()
            self.thumb.hide()
        else:
            self._spinner.stop()

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.set_loading(False)
        self.thumb.setPixmap(
            pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self.thumb.show()

    def set_load_failed(self) -> None:
        self.set_loading(False)
        self.thumb.setText("?")
        self.thumb.setStyleSheet("color: #64748B; font-size: 24px; border: none;")
        self.thumb.show()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if self._missing:
            return
        border = self._thumb_border_selected if selected else self._thumb_border_normal
        self.thumb_wrap.setStyleSheet(border)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(event)
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit(event.globalPos())

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


# ---------------------------------------------------------------------------
# Gallery view
# ---------------------------------------------------------------------------

class GalleryView(QWidget):
    """Main gallery panel: topbar + sidebar + image grid + pagination."""

    switch_to_workspace    = pyqtSignal(list, bool)
    import_to_workspace_slot = pyqtSignal(list, int)
    show_upload            = pyqtSignal()
    show_danbooru          = pyqtSignal()
    show_detached_workspace = pyqtSignal(list, bool)

    _ITEMS_PER_PAGE = 50

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.image_mgr      = ImageManager()
        self.collection_mgr = CollectionManager()
        self.tag_mgr        = TagManager()

        # Filter state
        self.current_collection_id = None
        self.filter_tag_ids        = None
        self.current_search_term   = None
        self.only_favorites        = False
        self.only_recent           = False
        self.current_page          = 1
        self.total_pages           = 1
        self.total_items           = 0
        self.columns               = get_settings().get_columns()
        self.sort_by               = get_settings().get_gallery_sort()
        self._active_filter        = "all"
        self._pending_focus_path: str | None = None
        self._detail_image_id: int | None = None
        self._filter_collection_name = None
        self._filter_tag_name      = None
        self._ordered_paths: list[str] = []
        self._last_clicked_path: str | None = None

        self.selected_images: set  = set()
        self.path_to_id: dict      = {}
        self._cards: dict          = {}

        self._load_queue = ImageLoadQueue(self, worker_count=6)
        self._load_queue.image_ready.connect(self._on_thumbnail_ready)
        self._load_queue.progress.connect(self._on_load_progress)
        self._load_queue.queue_empty.connect(self._on_load_queue_empty)
        self._load_generation = 0
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._on_search_debounced)
        self._nav_buttons: dict[str, QPushButton] = {}

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

    def _main_window(self):
        w = self.window()
        return w if hasattr(w, "show_status") else None

    def _build_topbar(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background-color: #1E293B;")
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(16, 8, 16, 8)
        outer.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(10)
        logo_pix = app_logo_pixmap(40)
        if logo_pix is not None:
            logo_icon = QLabel()
            logo_icon.setPixmap(logo_pix)
            logo_icon.setFixedSize(40, 40)
            logo_icon.setToolTip("Artist Reference Manager")
            row.addWidget(logo_icon)
        logo = QLabel("Artist Reference Manager")
        logo.setStyleSheet("font-size: 20px; font-weight: bold; color: #E2E8F0;")
        row.addWidget(logo)

        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search filenames or tags (FTS)…")
        self.search_entry.setFixedWidth(280)
        self.search_entry.setClearButtonEnabled(True)
        self.search_entry.returnPressed.connect(self._on_search)
        self.search_entry.textChanged.connect(self._on_search_changed)
        row.addWidget(self.search_entry)

        row.addWidget(QLabel("Sort:"))
        self.sort_combo = QComboBox()
        for key, label in (
            ("date_added_desc", "Newest"),
            ("date_added_asc", "Oldest"),
            ("name_asc", "Name A–Z"),
            ("name_desc", "Name Z–A"),
            ("last_viewed_desc", "Recently viewed"),
            ("favorite_first", "Favorites first"),
        ):
            self.sort_combo.addItem(label, key)
        idx = self.sort_combo.findData(self.sort_by)
        if idx >= 0:
            self.sort_combo.setCurrentIndex(idx)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        row.addWidget(self.sort_combo)
        row.addStretch()

        row.addWidget(QLabel("Columns:"))
        self.columns_slider = QSlider(Qt.Horizontal)
        self.columns_slider.setRange(2, 8)
        self.columns_slider.setValue(self.columns)
        self.columns_slider.setFixedWidth(100)
        self.columns_slider.valueChanged.connect(self._set_columns)
        row.addWidget(self.columns_slider)

        self.bulk_tag_btn = QPushButton("Retag Selected")
        self.bulk_tag_btn.setEnabled(False)
        self.bulk_tag_btn.clicked.connect(self._bulk_retag)
        row.addWidget(self.bulk_tag_btn)

        self.ws_open_btn = QPushButton("Open Workspace")
        self.ws_open_btn.clicked.connect(self._open_workspace)
        row.addWidget(self.ws_open_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._open_settings)
        row.addWidget(settings_btn)

        danbooru_btn = QPushButton("Danbooru")
        danbooru_btn.setToolTip("Search and import from Danbooru")
        danbooru_btn.clicked.connect(self.show_danbooru.emit)
        row.addWidget(danbooru_btn)

        upload_btn = QPushButton("Upload")
        upload_btn.setStyleSheet("background-color: #7C3AED; border-color: #6D28D9;")
        upload_btn.clicked.connect(self.show_upload.emit)
        row.addWidget(upload_btn)
        outer.addLayout(row)

        crumb_row = QHBoxLayout()
        self.breadcrumb_label = QLabel("All images")
        self.breadcrumb_label.setStyleSheet("color: #94A3B8; font-size: 12px;")
        crumb_row.addWidget(self.breadcrumb_label)
        crumb_row.addStretch()
        self.clear_filters_btn = QPushButton("Clear filters")
        self.clear_filters_btn.setFlat(True)
        self.clear_filters_btn.setStyleSheet("color: #7C3AED; border: none;")
        self.clear_filters_btn.clicked.connect(self.reset_filters)
        self.clear_filters_btn.hide()
        crumb_row.addWidget(self.clear_filters_btn)
        outer.addLayout(crumb_row)

        return wrapper

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("background-color: #0F172A;")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        def nav_btn(key: str, label: str, slot, style: str = "") -> QPushButton:
            b = QPushButton(label)
            b.clicked.connect(slot)
            if style:
                b.setStyleSheet(style)
            self._nav_buttons[key] = b
            return b

        layout.addWidget(nav_btn("all", "All Images", self.reset_filters))
        layout.addWidget(nav_btn("favorites", "Favorites", self.set_favorites_filter, "color: #F59E0B;"))
        layout.addWidget(nav_btn("recent", "Recently Viewed", self.set_recent_filter, "color: #10B981;"))

        splitter = QSplitter(Qt.Vertical)

        col_widget = QWidget()
        col_layout = QVBoxLayout(col_widget)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.addWidget(self._section_label("Collections"))
        self.collections_list = QListWidget()
        self.collections_list.itemClicked.connect(self._on_collection_clicked)
        col_layout.addWidget(self.collections_list)
        col_layout.addWidget(nav_btn("new_col", "+ New Collection", self._create_collection))
        splitter.addWidget(col_widget)

        smart_widget = QWidget()
        smart_layout = QVBoxLayout(smart_widget)
        smart_layout.setContentsMargins(0, 0, 0, 0)
        smart_layout.addWidget(self._section_label("Smart Collections"))
        self.smart_collections_list = QListWidget()
        self.smart_collections_list.itemClicked.connect(
            lambda item: self.set_smart_collection(item))
        smart_layout.addWidget(self.smart_collections_list)
        smart_layout.addWidget(nav_btn("new_smart", "+ New Smart", self._create_smart_collection))
        splitter.addWidget(smart_widget)

        tag_widget = QWidget()
        tag_layout = QVBoxLayout(tag_widget)
        tag_layout.setContentsMargins(0, 0, 0, 0)
        tag_layout.addWidget(self._section_label("Tags"))
        self.tags_list = QListWidget()
        self.tags_list.itemClicked.connect(self._on_tag_clicked)
        tag_layout.addWidget(self.tags_list)
        tag_layout.addWidget(nav_btn("new_tag", "+ New Tag", self._create_tag))
        splitter.addWidget(tag_widget)

        splitter.setSizes([140, 100, 140])
        layout.addWidget(splitter, stretch=1)

        layout.addWidget(nav_btn("detach", "Detach Workspace", self._open_detached_workspace))
        self._update_active_nav()
        return sidebar

    def _build_gallery_area(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        content_split = QSplitter(Qt.Horizontal)

        self.gallery_scroll = QScrollArea()
        self.gallery_scroll.setWidgetResizable(True)
        self._gallery_widget = QWidget()
        self.gallery_grid = QGridLayout(self._gallery_widget)
        self.gallery_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.gallery_grid.setSpacing(8)
        self.gallery_scroll.setWidget(self._gallery_widget)
        content_split.addWidget(self.gallery_scroll)

        detail = QWidget()
        detail.setMinimumWidth(220)
        detail.setMaximumWidth(320)
        detail.setStyleSheet("background-color: #0F172A;")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        detail_title = QLabel("Details")
        detail_title.setStyleSheet("font-weight: bold; color: #E2E8F0; font-size: 13px;")
        detail_layout.addWidget(detail_title)
        self.detail_panel = QLabel("Select an image to view metadata.")
        self.detail_panel.setWordWrap(True)
        self.detail_panel.setAlignment(Qt.AlignTop)
        self.detail_panel.setStyleSheet("color: #94A3B8; font-size: 12px;")
        detail_layout.addWidget(self.detail_panel)
        detail_layout.addStretch()
        content_split.addWidget(detail)
        content_split.setStretchFactor(0, 1)
        content_split.setSizes([900, 260])

        layout.addWidget(content_split, stretch=1)

        # Pagination bar
        pager = QWidget()
        pager.setStyleSheet("background-color: #1E293B;")
        pager.setFixedHeight(44)
        p_row = QHBoxLayout(pager)
        p_row.setContentsMargins(16, 0, 16, 0)

        self.prev_page_btn = QPushButton("‹ Previous")
        self.prev_page_btn.clicked.connect(self._prev_page)
        p_row.addWidget(self.prev_page_btn)

        self.result_count_label = QLabel("")
        self.result_count_label.setStyleSheet("color: #94A3B8;")
        p_row.addWidget(self.result_count_label)

        self.page_label = QLabel("Page 1 / 1")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setStyleSheet("color: #E2E8F0;")
        p_row.addWidget(self.page_label, stretch=1)

        self.next_page_btn = QPushButton("Next ›")
        self.next_page_btn.clicked.connect(self._next_page)
        p_row.addWidget(self.next_page_btn)

        self._load_status = LoadingStatusBar()
        p_row.addWidget(self._load_status)

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

    def focus_image(self, image_id: int) -> None:
        """Navigate gallery to show and select an image by database id."""
        path = self.image_mgr.get_file_path_by_id(image_id)
        if not path:
            return
        self._clear_filter_state()
        self._active_filter = "all"
        self.collections_list.clearSelection()
        self.tags_list.clearSelection()
        self.smart_collections_list.clearSelection()
        self.current_page = self.image_mgr.get_page_for_image(
            image_id,
            self._ITEMS_PER_PAGE,
            sort_by=self.sort_by,
        )
        self.selected_images = {path}
        self._pending_focus_path = path
        self._detail_image_id = image_id
        self.load_gallery()

    def _on_sort_changed(self) -> None:
        self.sort_by = self.sort_combo.currentData()
        get_settings().set_gallery_sort(self.sort_by)
        self.current_page = 1
        self.load_gallery()

    def load_gallery(self) -> None:
        """Clear the grid and start background image loading."""
        # Remove every item from the grid layout and destroy its widget.
        # Simply calling deleteLater() on tracked cards is not enough — the
        # QGridLayout holds its own references, causing stale widgets to
        # overlap new cards when the column count or page changes.
        while self.gallery_grid.count():
            item = self.gallery_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._cards.clear()
        self.path_to_id.clear()

        total_items = self.image_mgr.count_images(
            collection_id=self.current_collection_id,
            tag_ids=self.filter_tag_ids,
            search_term=self.current_search_term,
            only_favorites=self.only_favorites,
            only_recent=self.only_recent,
        )
        self.total_items = total_items
        self.total_pages = max(1, math.ceil(total_items / self._ITEMS_PER_PAGE))
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages
        self._update_pagination_state()
        self._update_breadcrumb()

        images = self.image_mgr.query_images(
            collection_id=self.current_collection_id,
            tag_ids=self.filter_tag_ids,
            search_term=self.current_search_term,
            only_favorites=self.only_favorites,
            only_recent=self.only_recent,
            limit=self._ITEMS_PER_PAGE,
            offset=(self.current_page - 1) * self._ITEMS_PER_PAGE,
            sort_by=self.sort_by,
        )

        if not images:
            self._load_queue.cancel_all()
            self._load_status.hide_idle()
            self._show_empty_state()
            self._refresh_bulk_tag_button()
            return

        self._load_queue.cancel_all()
        self._load_generation = self._load_queue.generation
        self._render_cards_skeleton(images)
        total = len(images)
        self._load_status.show_busy(f"Loading previews… 0/{total}", total=total)
        for data in images:
            path = data["file_path"]
            self._load_queue.enqueue_file(
                path,
                path,
                data.get("thumbnail_path"),
                max_size=(220, 220),
                preview_only=True,
            )

    def _update_pagination_state(self) -> None:
        self.page_label.setText(f"Page {self.current_page} / {self.total_pages}")
        self.result_count_label.setText(
            f"{self.total_items} image{'s' if self.total_items != 1 else ''}"
        )
        self.prev_page_btn.setEnabled(self.current_page > 1)
        self.next_page_btn.setEnabled(self.current_page < self.total_pages)

    def _show_empty_state(self) -> None:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setAlignment(Qt.AlignCenter)
        if self.total_items == 0 and not self._has_active_filters():
            title = QLabel("Import your first references")
            title.setStyleSheet("font-size: 18px; font-weight: bold; color: #E2E8F0;")
            sub = QLabel("Drag images into Upload or browse your folders.")
            sub.setStyleSheet("color: #94A3B8;")
            upload_btn = QPushButton("Upload images")
            upload_btn.setStyleSheet("background-color: #7C3AED; border-color: #6D28D9;")
            upload_btn.clicked.connect(self.show_upload.emit)
            v.addWidget(title)
            v.addWidget(sub)
            v.addWidget(upload_btn, alignment=Qt.AlignCenter)
        else:
            term = self.current_search_term or ""
            if term:
                title = QLabel(f"No matches for \"{term}\"")
            else:
                title = QLabel("No images match this filter")
            title.setStyleSheet("font-size: 16px; color: #E2E8F0;")
            clear_btn = QPushButton("Clear filters")
            clear_btn.clicked.connect(self.reset_filters)
            v.addWidget(title)
            v.addWidget(clear_btn, alignment=Qt.AlignCenter)
        self.gallery_grid.addWidget(box, 0, 0, 1, max(self.columns, 1))
        self._update_pagination_state()

    def _has_active_filters(self) -> bool:
        return bool(
            self.current_collection_id
            or self.filter_tag_ids
            or self.current_search_term
            or self.only_favorites
            or self.only_recent
        )

    def _update_breadcrumb(self) -> None:
        if self.only_favorites:
            text = "Favorites"
        elif self.only_recent:
            text = "Recently viewed"
        elif self.current_collection_id and self._filter_collection_name:
            text = f"Collection: {self._filter_collection_name}"
        elif self.filter_tag_ids and self._filter_tag_name:
            text = f"Tag: {self._filter_tag_name}"
        elif self.current_search_term:
            text = f"Search: {self.current_search_term}"
        else:
            text = "All images"
        self.breadcrumb_label.setText(text)
        self.clear_filters_btn.setVisible(self._has_active_filters())
        self._update_active_nav()

    def _update_active_nav(self) -> None:
        for key, btn in self._nav_buttons.items():
            active = (
                (key == "all" and self._active_filter == "all")
                or (key == "favorites" and self._active_filter == "favorites")
                or (key == "recent" and self._active_filter == "recent")
            )
            btn.setProperty("activeFilter", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def reset_filters(self) -> None:
        self._stop_search_debounce()
        self.current_collection_id = None
        self.filter_tag_ids        = None
        self.current_search_term   = None
        self.only_favorites        = False
        self.only_recent           = False
        self._active_filter        = "all"
        self._filter_collection_name = None
        self._filter_tag_name      = None
        self.current_page          = 1
        self.collections_list.clearSelection()
        self.tags_list.clearSelection()
        self.smart_collections_list.clearSelection()
        self.search_entry.blockSignals(True)
        self.search_entry.clear()
        self.search_entry.blockSignals(False)
        self.load_gallery()

    def set_favorites_filter(self) -> None:
        self._stop_search_debounce()
        self._clear_filter_state()
        self.only_favorites = True
        self._active_filter = "favorites"
        self.load_gallery()

    def set_recent_filter(self) -> None:
        self._stop_search_debounce()
        self._clear_filter_state()
        self.only_recent = True
        self._active_filter = "recent"
        self.load_gallery()

    def _clear_filter_state(self) -> None:
        self.current_collection_id = None
        self.filter_tag_ids = None
        self.current_search_term = None
        self.only_favorites = False
        self.only_recent = False
        self._filter_collection_name = None
        self._filter_tag_name = None
        self.current_page = 1
        self.search_entry.blockSignals(True)
        self.search_entry.clear()
        self.search_entry.blockSignals(False)

    def _stop_search_debounce(self) -> None:
        self._search_timer.stop()

    def _sync_active_filter_from_state(self) -> None:
        if self.only_favorites:
            self._active_filter = "favorites"
        elif self.only_recent:
            self._active_filter = "recent"
        elif self.current_collection_id is not None:
            self._active_filter = "collection"
        elif self.filter_tag_ids:
            if self._active_filter != "smart":
                self._active_filter = "tag"
        elif self.current_search_term:
            self._active_filter = "search"
        else:
            self._active_filter = "all"

    def _on_collection_clicked(self, item: QListWidgetItem) -> None:
        self._stop_search_debounce()
        cid = item.data(Qt.UserRole)
        self._clear_filter_state()
        self.current_collection_id = cid
        self._filter_collection_name = re.sub(r"\s*\(\d+\)\s*$", "", item.text().strip())
        self._active_filter = "collection"
        self.load_gallery()

    def _on_tag_clicked(self, item: QListWidgetItem) -> None:
        self._stop_search_debounce()
        tid = item.data(Qt.UserRole)
        self._clear_filter_state()
        self.filter_tag_ids = tid
        self._filter_tag_name = re.sub(r"\s*\(\d+\)\s*$", "", item.text().strip())
        self._active_filter = "tag"
        self.load_gallery()

    def set_collection(self, cid) -> None:
        self._stop_search_debounce()
        self._clear_filter_state()
        self.current_collection_id = cid
        self._active_filter = "collection"
        self.load_gallery()

    def set_tag(self, tid) -> None:
        self._stop_search_debounce()
        self._clear_filter_state()
        self.filter_tag_ids = tid
        self._active_filter = "tag"
        self.load_gallery()

    def set_smart_collection(self, item: QListWidgetItem) -> None:
        self._stop_search_debounce()
        tag_ids = item.data(Qt.UserRole)
        self._clear_filter_state()
        self.filter_tag_ids = tag_ids
        self._filter_tag_name = re.sub(r"\s*\(\d+\)\s*$", "", item.text().strip())
        self._active_filter = "smart"
        self.load_gallery()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _on_search(self) -> None:
        self._search_timer.stop()
        self._on_search_debounced()
        self._autocomplete_menu.hide()

    def _on_search_debounced(self) -> None:
        term = self.search_entry.text().strip()
        self.current_page = 1
        if term:
            self._clear_filter_state()
            self.current_search_term = term
            get_settings().add_recent_search(term)
            self._active_filter = "search"
        else:
            self.current_search_term = None
            self._sync_active_filter_from_state()
        self.load_gallery()

    def _on_search_changed(self, text: str) -> None:
        self._search_timer.stop()
        self._search_timer.start()
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
        get_settings().set_columns(val)
        self.load_gallery()

    def _prev_page(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self.load_gallery()

    def _next_page(self) -> None:
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_gallery()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_cards_skeleton(self, images: list) -> None:
        row, col = 0, 0
        self._ordered_paths = []
        for data in images:
            path = data["file_path"]
            self._ordered_paths.append(path)
            self.path_to_id[path] = data["id"]

            missing = not Path(path).exists()
            card = ImageCard(path, is_favorite=bool(data.get("is_favorite")), missing=missing)
            card.set_selected(path in self.selected_images)
            if not missing:
                card.set_loading(True)
            else:
                card.set_load_failed()

            card.clicked.connect(lambda ev, p=path, c=card: self._on_card_clicked(p, c, ev))
            card.double_clicked.connect(
                lambda p=path: self.switch_to_workspace.emit([p], True))
            card.right_clicked.connect(lambda pos, p=path: self._show_context_menu(pos, p))

            self._cards[path] = card
            self.gallery_grid.addWidget(card, row, col)
            col += 1
            if col >= self.columns:
                col, row = 0, row + 1

        self._update_pagination_state()
        self._refresh_bulk_tag_button()
        self._finish_gallery_focus()

    def _on_thumbnail_ready(self, path: str, pixmap: object, generation: int) -> None:
        if generation != self._load_generation:
            return
        card = self._cards.get(path)
        if not card:
            return
        if pixmap:
            card.set_pixmap(pixmap)
        else:
            card.set_load_failed()

    def _on_load_progress(self, done: int, total: int, generation: int) -> None:
        if generation != self._load_generation:
            return
        self._load_status.set_progress(
            done, total, f"Loading previews… {done}/{total}",
        )

    def _on_load_queue_empty(self, generation: int) -> None:
        if generation != self._load_generation:
            return
        self._load_status.hide_idle()
        mw = self._main_window()
        if mw:
            mw.show_status("Gallery previews loaded", 3000)

    def _finish_gallery_focus(self) -> None:
        if self._pending_focus_path and self._pending_focus_path in self._cards:
            card = self._cards[self._pending_focus_path]
            self.gallery_scroll.ensureWidgetVisible(card)
            self._pending_focus_path = None
        if self._detail_image_id:
            self._update_detail_panel(self._detail_image_id)

    def _update_detail_panel(self, image_id: int) -> None:
        detail = self.image_mgr.get_image_detail(image_id)
        if not detail:
            self.detail_panel.setText("Image not found.")
            return
        tags = self.tag_mgr.get_tags_for_image(image_id)
        tag_text = ", ".join(t["name"] for t in tags) if tags else "—"
        cols = self.collection_mgr.get_collections_for_image(image_id)
        col_text = ", ".join(c["name"] for c in cols) if cols else "—"
        path = detail["file_path"]
        exists = Path(path).exists()
        lines = [
            f"<b>{Path(path).name}</b>",
            f"Size: {detail.get('width', '?')} × {detail.get('height', '?')}",
            f"Favorite: {'Yes' if detail.get('is_favorite') else 'No'}",
            f"Added: {detail.get('date_added', '—')}",
            f"Last viewed: {detail.get('last_viewed') or '—'}",
            f"Tags: {tag_text}",
            f"Collections: {col_text}",
            f"File: {'Missing on disk' if not exists else path}",
        ]
        self.detail_panel.setText("<br>".join(lines))

    def keyPressEvent(self, event) -> None:
        if not self._ordered_paths:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key not in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            super().keyPressEvent(event)
            return
        current = next(iter(self.selected_images), None) if len(self.selected_images) == 1 else None
        if current not in self._ordered_paths:
            idx = 0
        else:
            idx = self._ordered_paths.index(current)
        step = 1 if key in (Qt.Key_Right, Qt.Key_Down) else -1
        if key in (Qt.Key_Up, Qt.Key_Down):
            step *= self.columns
        idx = max(0, min(len(self._ordered_paths) - 1, idx + step))
        path = self._ordered_paths[idx]
        self.selected_images = {path}
        for p, c in self._cards.items():
            c.set_selected(p == path)
        self._last_clicked_path = path
        self._detail_image_id = self.path_to_id.get(path)
        if self._detail_image_id:
            self._update_detail_panel(self._detail_image_id)
        if path in self._cards:
            self.gallery_scroll.ensureWidgetVisible(self._cards[path])
        self._refresh_bulk_tag_button()

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _on_card_clicked(self, path: str, card: ImageCard, event) -> None:
        modifiers = event.modifiers()
        if modifiers & Qt.ShiftModifier and self._last_clicked_path:
            self._range_select(self._last_clicked_path, path)
        elif modifiers & (Qt.ControlModifier | Qt.MetaModifier):
            self._toggle_selection(path, card)
        else:
            self._toggle_selection(path, card)
        self._last_clicked_path = path
        self._detail_image_id = self.path_to_id.get(path)
        if self._detail_image_id:
            self._update_detail_panel(self._detail_image_id)
        self._refresh_bulk_tag_button()

    def _range_select(self, anchor: str, target: str) -> None:
        if anchor not in self._ordered_paths or target not in self._ordered_paths:
            return
        i1 = self._ordered_paths.index(anchor)
        i2 = self._ordered_paths.index(target)
        lo, hi = min(i1, i2), max(i1, i2)
        self.selected_images = set(self._ordered_paths[lo : hi + 1])
        for p, c in self._cards.items():
            c.set_selected(p in self.selected_images)
        self._refresh_bulk_tag_button()

    def _toggle_selection(self, path: str, card: ImageCard) -> None:
        if path in self.selected_images:
            self.selected_images.discard(path)
        else:
            self.selected_images.add(path)
        for p, c in self._cards.items():
            c.set_selected(p in self.selected_images)
        self._refresh_bulk_tag_button()

    def _refresh_bulk_tag_button(self) -> None:
        n = len(self.selected_images)
        self.bulk_tag_btn.setEnabled(bool(n))
        self.bulk_tag_btn.setText(f"Retag ({n})" if n else "Retag Selected")
        self.ws_open_btn.setEnabled(bool(n))

    def _clear_selection(self) -> None:
        if not self.selected_images:
            return
        self.selected_images.clear()
        self._last_clicked_path = None
        for card in self._cards.values():
            card.set_selected(False)
        self._refresh_bulk_tag_button()

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
        if self.selected_images:
            menu.addAction("Unselect all").triggered.connect(self._clear_selection)
        menu.addSeparator()
        menu.addAction("▶ Open in Workspace").triggered.connect(
            lambda: self.switch_to_workspace.emit(list(targets), True))
        menu.addAction("＋ Add to Workspace").triggered.connect(
            lambda: self.switch_to_workspace.emit(list(targets), False))
        import_menu = menu.addMenu("Import")
        ws_menu = import_menu.addMenu("Workspace")
        for slot in range(1, 6):
            ws_menu.addAction(f"Slot {slot}").triggered.connect(
                lambda _, s=slot, t=list(targets): self.import_to_workspace_slot.emit(t, s)
            )
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
            mw = self._main_window()
            if mw:
                mw.show_toast(f"Added {len(ids)} image(s) to collection")

    def _remove_from_collection(self, paths: set) -> None:
        ids = [self.path_to_id[p] for p in paths if p in self.path_to_id]
        if ids and self.current_collection_id:
            self.collection_mgr.remove_images_from_collection(ids, self.current_collection_id)
            self.load_gallery()

    def _show_tag_dialog(self, paths: set) -> None:
        ids = [self.path_to_id[p] for p in paths if p in self.path_to_id]
        if not ids:
            return

        def on_saved(count: int) -> None:
            from database import rebuild_images_fts
            rebuild_images_fts()
            mw = self._main_window()
            if mw:
                mw.show_toast(f"Tags updated on {count} image(s)")
            self.load_gallery()

        TagEditDialog(self, self.tag_mgr, ids, on_saved=on_saved).exec_()

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
        main = self._main_window()
        SettingsDialog(main or self).exec_()

    # ------------------------------------------------------------------
    # Sidebar list refresh
    # ------------------------------------------------------------------

    def refresh_collections_list(self) -> None:
        self.collections_list.clear()
        counts = self.collection_mgr.get_collection_image_counts()
        tree: dict = {}
        roots = []
        for c in self.collection_mgr.get_collections():
            pid = c.get('parent_id')
            if pid is None:
                roots.append(c)
            else:
                tree.setdefault(pid, []).append(c)

        def _add_node(node: dict, depth: int) -> None:
            cnt = counts.get(node['id'], 0)
            label = f"{'  ' * depth}{node['name']} ({cnt})"
            item = QListWidgetItem(label)
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
        conn_counts: dict[int, int] = {}
        try:
            from database import get_connection
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT tag_id, COUNT(*) AS cnt FROM image_tags GROUP BY tag_id")
            conn_counts = {int(r["tag_id"]): int(r["cnt"]) for r in cur.fetchall()}
            conn.close()
        except Exception:
            pass
        for t in self.tag_mgr.get_tags():
            cnt = conn_counts.get(t['id'], 0)
            item = QListWidgetItem(f"{t['name']} ({cnt})")
            item.setData(Qt.UserRole, t['id'])
            self.tags_list.addItem(item)

    def _create_tag(self) -> None:
        name, ok = QInputDialog.getText(self, "New Tag", "Tag name:")
        if ok and name and self.tag_mgr.create_tag(name):
            self.refresh_tags_list()
