"""
gallery_view.py — Main gallery browser with sidebar navigation and async image loading.
"""
import math
import logging
import threading
from pathlib import Path

from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize, pyqtProperty
from PyQt5.QtGui import QPixmap, QIcon, QColor
from PyQt5.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPushButton, QScrollArea, QSlider, QSplitter, QVBoxLayout,
    QWidget, QGraphicsBlurEffect, QGraphicsOpacityEffect
)

from app_settings import get_settings
from managers.collection_manager import CollectionManager
from managers.image_manager import ImageManager
from managers.tag_manager import TagManager
from ui.branding import app_logo_pixmap, icon_path
from ui.image_load_queue import ImageLoadQueue
from ui.loading_indicator import LoadingSpinner, LoadingStatusBar
from ui.image_viewer import ImageViewer
from ui.tag_edit_dialog import TagEditDialog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UI Components
# ---------------------------------------------------------------------------

class ElidedLabel(QLabel):
    """A label that middle-elides text to fit its width."""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full_text = text

    def setText(self, text):
        self._full_text = text
        super().setText(text)
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QFontMetrics
        painter = QPainter(self)
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self._full_text, Qt.ElideMiddle, self.width())
        painter.drawText(self.rect(), self.alignment(), elided)

class ImageCard(QWidget):
    """Thumbnail card with filename, favorite badge, and selection state."""

    clicked = pyqtSignal(object)
    double_clicked = pyqtSignal()
    right_clicked = pyqtSignal(QPoint)

    def __init__(self, file_path: str, is_favorite: bool = False, missing: bool = False, card_size: int = 220) -> None:
        super().__init__()
        self.file_path = file_path
        self._selected = False
        self._missing = missing
        self._is_favorite = is_favorite
        self._is_sensitive = False
        self._pixmap = None
        self._card_width = card_size
        self._bg_color = QColor("#1E1B4B") # Initial pending color
        
        self.setAttribute(Qt.WA_StyledBackground, True)
        
        # Style Constants (Colors only, border/radius handled in base style)
        self.COLORS = {
            'normal': "#161D2F",
            'normal_hover': "#1C253C",
            'selected': "#1C253C",
            'scanning': "#0F172A",
            'failed': "#450A0A",
            'missing': "#161D2F",
            'pending': "#1E1B4B",
            'pending_hover': "#2E286D",
            'pending_selected': "#2E286D"
        }
        
        self._base_style = "ImageCard { border-radius: 8px; border: 1px solid #252F44; }"
        self._selected_border = "border: 2px solid #8B5CF6;"
        self._scanning_border = "border: 3px solid #00F2FF;"
        self._failed_border = "border: 3px solid #EF4444;"
        self._missing_border = "border: 1px solid #EF4444;"
        self._pending_border = "border: 1px solid #3730A3;"

        self._ai_status = 'pending'
        self.setToolTip(file_path)
        
        # Color Animation Setup
        self._color_anim = QPropertyAnimation(self, b"backgroundColor")
        self._color_anim.setDuration(300)
        self._color_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(6, 6, 6, 6)
        self.root_layout.setSpacing(6)

        # Thumbnail Area
        self.thumb_wrap = QFrame()
        self.thumb_wrap.setObjectName("thumbWrap")
        self.thumb_wrap.setStyleSheet("QFrame#thumbWrap { background-color: #0B0F1A; border-radius: 4px; }")
        
        self.thumb_inner = QVBoxLayout(self.thumb_wrap)
        self.thumb_inner.setContentsMargins(0, 0, 0, 0)
        self.thumb_inner.setAlignment(Qt.AlignCenter)
        
        self._spinner = LoadingSpinner(32, self.thumb_wrap)
        self._spinning_status_container = QWidget()
        self._spinner_layout = QVBoxLayout(self._spinning_status_container)
        self._spinner_layout.setContentsMargins(0, 0, 0, 0)
        self._spinner_layout.setSpacing(8)
        self._spinner_layout.setAlignment(Qt.AlignCenter)
        
        self._scanning_spinner = LoadingSpinner(64, self._spinning_status_container)
        self._scanning_spinner.hide()
        
        self.scanning_label = QLabel("SCANNING...", self._spinning_status_container)
        self.scanning_label.setAlignment(Qt.AlignCenter)
        self.scanning_label.setStyleSheet("""
            background-color: #00F2FF; color: #0F172A; font-size: 11px;
            font-weight: 800; border-radius: 4px; padding: 4px;
        """)
        self.scanning_label.hide()
        
        self._spinner_layout.addWidget(self._scanning_spinner, alignment=Qt.AlignCenter)
        self._spinner_layout.addWidget(self.scanning_label, alignment=Qt.AlignCenter)
        
        self.thumb = QLabel()
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.hide()
        
        self.thumb_inner.addWidget(self._spinner, alignment=Qt.AlignCenter)
        self.thumb_inner.addWidget(self._spinning_status_container, alignment=Qt.AlignCenter)
        self.thumb_inner.addWidget(self.thumb, alignment=Qt.AlignCenter)
        self.root_layout.addWidget(self.thumb_wrap)

        # Blur effect for sensitive content
        self._blur_effect = QGraphicsBlurEffect(self.thumb)
        self._blur_effect.setBlurRadius(25)
        self._blur_effect.setEnabled(False)

        # Meta Info
        self.info_row = QHBoxLayout()
        self.info_row.setContentsMargins(4, 0, 4, 0)
        
        self.name_label = QLabel()
        self.name_label.setStyleSheet("color: #F1F5F9; font-size: 11px; font-weight: 500;")
        self.info_row.addWidget(self.name_label, stretch=1)
        
        self.star_label = QLabel("★")
        self.star_label.setStyleSheet("color: #F59E0B; font-size: 12px;")
        self.star_label.setVisible(is_favorite)
        self.info_row.addWidget(self.star_label)
            
        self.root_layout.addLayout(self.info_row)
        self.update_size(card_size)
        self._update_full_style()

    @pyqtProperty(QColor)
    def backgroundColor(self):
        return self._bg_color

    @backgroundColor.setter
    def backgroundColor(self, color):
        self._bg_color = color
        self._update_full_style()

    def _update_full_style(self):
        """Re-construct the stylesheet using the current background color and border state."""
        border = "border: 1px solid #252F44;" # Default
        if self._missing: border = self._missing_border
        elif self._ai_status == 'scanning': border = self._scanning_border
        elif self._ai_status == 'failed': border = self._failed_border
        elif self._selected: border = self._selected_border
        elif self._ai_status == 'pending': border = self._pending_border
        
        style = f"ImageCard {{ background-color: {self._bg_color.name()}; {border} border-radius: 8px; }}"
        self.setStyleSheet(style)

    def _animate_to_color(self, hex_color):
        target = QColor(hex_color)
        if self._bg_color == target:
            return
        self._color_anim.stop()
        self._color_anim.setStartValue(self._bg_color)
        self._color_anim.setEndValue(target)
        self._color_anim.start()

    def update_size(self, size: int) -> None:
        """Update card dimensions and rescale thumbnail."""
        self._card_width = size
        h = int(size * 1.2)
        self.setFixedSize(size, h)
        
        thumb_size = size - 12
        self.thumb_wrap.setFixedSize(thumb_size, thumb_size)
        self.thumb.setFixedSize(thumb_size, thumb_size)
        
        # Size scanning spinner
        sw = max(32, thumb_size // 3)
        self._scanning_spinner.setFixedSize(sw, sw)
        self._spinning_status_container.setFixedSize(thumb_size, thumb_size)
        
        name = Path(self.file_path).name
        limit = max(10, size // 10)
        if len(name) > limit:
            name = name[:limit-3] + "..."
        self.name_label.setText(name)
        
        if self._pixmap:
            ts = self.thumb.width()
            self.thumb.setPixmap(self._pixmap.scaled(ts, ts, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        self.set_selected(self._selected)

    def set_loading(self, loading: bool) -> None:
        if loading:
            self._spinner.start()
            self.thumb.hide()
        else:
            self._spinner.stop()
            if self._pixmap and self._ai_status != 'scanning':
                self.thumb.show()

    def set_pixmap(self, pixmap: QPixmap) -> None:
        """Set the pixmap and trigger the initial fade-in animation."""
        if pixmap is None or pixmap.isNull():
            self.set_load_failed()
            return
            
        self._pixmap = pixmap
        self.set_loading(False)
        ts = self.thumb.width() or self._card_width - 12
        self.thumb.setPixmap(pixmap.scaled(ts, ts, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        if self._ai_status != 'scanning':
            self.thumb.show()
            # Initial fade-in animation
            eff = QGraphicsOpacityEffect()
            self.thumb.setGraphicsEffect(eff)
            self._fade_anim = QPropertyAnimation(eff, b"opacity")
            self._fade_anim.setDuration(400)
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._fade_anim.finished.connect(self._on_fade_finished)
            self._fade_anim.start()

    def _on_fade_finished(self) -> None:
        self._update_safety_visuals()

    def set_load_failed(self) -> None:
        self.set_loading(False)
        self.thumb.setText("?")
        self.thumb.setStyleSheet("color: #64748B; font-size: 32px;")
        if self._ai_status != 'scanning':
            self.thumb.show()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        color_key = 'normal'
        if self._missing: color_key = 'missing'
        elif self._ai_status == 'pending':
            color_key = 'pending_selected' if selected else 'pending'
        else:
            color_key = 'selected' if selected else 'normal'
            
        self._animate_to_color(self.COLORS[color_key])

    def set_ai_status(self, status: str, tags: list = None) -> None:
        """Update the visual AI scanning status and sensitivity."""
        self._ai_status = status
        if status == 'scanning':
            self.scanning_label.show()
            self._spinning_status_container.show()
            self._scanning_spinner.show()
            self._scanning_spinner.start()
            self.thumb.hide()
            self._spinner.hide()
            self._animate_to_color(self.COLORS['scanning'])
        elif status == 'failed':
            self.scanning_label.hide()
            self._scanning_spinner.stop()
            self._spinning_status_container.hide()
            self.thumb.hide()
            self._spinner.hide()
            self._animate_to_color(self.COLORS['failed'])
        else:
            self.scanning_label.hide()
            self._scanning_spinner.stop()
            self._spinning_status_container.hide()
            if self._pixmap:
                self.thumb.show()
                self._spinner.hide()
            else:
                self.thumb.hide()
                self._spinner.show()
                self._spinner.start()
            self.set_selected(self._selected)
        
        if tags:
            self._is_sensitive = any(t['name'] in ("Sensitive", "Questionable") for t in tags)
            self._update_safety_visuals()

    def _update_safety_visuals(self) -> None:
        safe_mode = get_settings().get_safe_mode()
        should_blur = self._is_sensitive and safe_mode
        if should_blur:
            blur = QGraphicsBlurEffect()
            blur.setBlurRadius(25)
            self.thumb.setGraphicsEffect(blur)
        else:
            if self.thumb.graphicsEffect():
                self.thumb.setGraphicsEffect(None)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(event)
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit(event.globalPos())

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()

    def enterEvent(self, event):
        """Handle hover in."""
        if not self._selected and not self._missing and self._ai_status != 'scanning':
            key = 'pending_hover' if self._ai_status == 'pending' else 'normal_hover'
            self._animate_to_color(self.COLORS[key])
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle hover out."""
        self.set_selected(self._selected)
        super().leaveEvent(event)

# ---------------------------------------------------------------------------
# Gallery View
# ---------------------------------------------------------------------------

class GalleryView(QWidget):
    """Grid-based image explorer with sidebar navigation and async image loading."""

    switch_to_workspace = pyqtSignal(list, bool)
    import_to_workspace_slot = pyqtSignal(list, int)
    show_upload = pyqtSignal()
    show_danbooru = pyqtSignal()
    show_detached_workspace = pyqtSignal(list, bool)

    def __init__(self, parent=None, status_callback=None, toast_callback=None) -> None:
        super().__init__(parent)
        self._status = status_callback
        self._toast = toast_callback
        self.image_mgr = ImageManager()
        self.tag_mgr = TagManager()
        self.col_mgr = CollectionManager()
        
        self.selected_images = set()
        self.path_to_id = {}
        self._cards = {}
        self._ordered_paths = []
        
        self.current_page = 1
        self.columns = get_settings().get_columns() or 4
        self.sort_by = get_settings().get_gallery_sort() or "date_added_desc"
        
        self.current_tag_id = None
        self.current_collection_id = None
        self.current_search = None
        self.only_favorites = False
        self.only_recent = False
        
        self._loading = False
        self._load_queue = ImageLoadQueue(self, worker_count=6)
        self._load_queue.image_ready.connect(self._on_thumbnail_ready)

        self._init_ui()
        self.load_gallery()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Sidebar Navigation
        self.sidebar = self._build_sidebar()
        layout.addWidget(self.sidebar)

        # 2. Splitter for Center and Right Panel
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setStyleSheet("QSplitter::handle { background: #1E293B; width: 1px; }")
        
        # Center Content Area
        self.center_area = QWidget()
        self.center_layout = QVBoxLayout(self.center_area)
        self.center_layout.setContentsMargins(0, 0, 0, 0)
        self.center_layout.setSpacing(0)

        # Top Bar
        self.top_bar = self._build_top_bar()
        self.center_layout.addWidget(self.top_bar)

        # Scrollable Grid
        self.gallery_scroll = QScrollArea()
        self.gallery_scroll.setWidgetResizable(True)
        self.gallery_scroll.setStyleSheet("QScrollArea { border: none; background-color: #0F172A; }")
        
        self.gallery_container = QWidget()
        self.gallery_container.setObjectName("galleryContainer")
        self.gallery_container.setStyleSheet("QWidget#galleryContainer { background-color: #0F172A; }")
        self.gallery_grid = QGridLayout(self.gallery_container)
        self.gallery_grid.setContentsMargins(20, 20, 20, 20)
        self.gallery_grid.setSpacing(20)
        self.gallery_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        self.gallery_scroll.setWidget(self.gallery_container)
        self.center_layout.addWidget(self.gallery_scroll)

        # Pagination Bar
        self.pagination_bar = QWidget()
        self.pagination_bar.setFixedHeight(44)
        self.pagination_bar.setStyleSheet("background-color: #0F172A; border-top: 1px solid #1E293B;")
        pb_layout = QHBoxLayout(self.pagination_bar)
        pb_layout.setContentsMargins(20, 0, 20, 0)

        self.prev_page_btn = QPushButton("‹ Previous")
        self.prev_page_btn.clicked.connect(self._prev_page)
        self.prev_page_btn.setStyleSheet("padding: 6px 12px; background: #1E293B; color: #E2E8F0; border-radius: 4px;")

        self.page_info_lbl = QLabel("Page 1 of 1")
        self.page_info_lbl.setStyleSheet("color: #94A3B8; font-size: 13px; font-weight: bold;")
        self.page_info_lbl.setAlignment(Qt.AlignCenter)

        self.next_page_btn = QPushButton("Next ›")
        self.next_page_btn.clicked.connect(self._next_page)
        self.next_page_btn.setStyleSheet("padding: 6px 12px; background: #1E293B; color: #E2E8F0; border-radius: 4px;")

        pb_layout.addStretch()
        pb_layout.addWidget(self.prev_page_btn)
        pb_layout.addSpacing(10)
        pb_layout.addWidget(self.page_info_lbl)
        pb_layout.addSpacing(10)
        pb_layout.addWidget(self.next_page_btn)
        pb_layout.addStretch()

        self.center_layout.addWidget(self.pagination_bar)

        # Bottom Status Bar
        self._load_status = LoadingStatusBar(self)
        self.center_layout.addWidget(self._load_status)

        self.main_splitter.addWidget(self.center_area)

        # 3. Right Detail Panel
        self.detail_panel_widget = self._build_detail_panel()
        self.main_splitter.addWidget(self.detail_panel_widget)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 1)
        
        layout.addWidget(self.main_splitter)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet("background-color: #0F172A; border-right: 1px solid #1E293B;")
        
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(15, 20, 15, 20)
        sl.setSpacing(10)

        # App Logo
        logo_px = app_logo_pixmap(140)
        if logo_px:
            logo_btn = QPushButton()
            logo_btn.setIcon(QIcon(logo_px))
            logo_btn.setIconSize(logo_px.size())
            logo_btn.setFlat(True)
            logo_btn.setStyleSheet("background: transparent; border: none;")
            logo_btn.setCursor(Qt.PointingHandCursor)
            logo_btn.clicked.connect(self.reset_filters)
            sl.addWidget(logo_btn, alignment=Qt.AlignCenter)
            sl.addSpacing(10)

        # Database Stats Badge
        self.db_stats_badge = QLabel("💎 0 Images in Library")
        self.db_stats_badge.setAlignment(Qt.AlignCenter)
        self.db_stats_badge.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #7C3AED);
                color: #FFFFFF;
                font-size: 11px;
                font-weight: 900;
                padding: 6px;
                border-radius: 8px;
                letter-spacing: 1px;
            }
        """)
        sl.addWidget(self.db_stats_badge)
        sl.addSpacing(10)

        # Smart Filters
        sl.addWidget(self._section_label("EXPLORE"))
        self.nav_group = QButtonGroup(self)
        
        self.all_btn = self._build_nav_btn("All images", "layout-grid")
        self.all_btn.setChecked(True)
        self.all_btn.clicked.connect(self.reset_filters)
        self.nav_group.addButton(self.all_btn)
        sl.addWidget(self.all_btn)

        self.fav_btn = self._build_nav_btn("Favorites", "heart")
        self.fav_btn.clicked.connect(self.set_favorites_filter)
        self.nav_group.addButton(self.fav_btn)
        sl.addWidget(self.fav_btn)

        self.recent_btn = self._build_nav_btn("Recent", "clock")
        self.recent_btn.clicked.connect(self.set_recent_filter)
        self.nav_group.addButton(self.recent_btn)
        sl.addWidget(self.recent_btn)
        
        # Workspace Navigation
        sl.addSpacing(10)
        sl.addWidget(self._section_label("WORKSPACE"))
        ws_btn = QPushButton("Open Workspace")
        ws_btn.setStyleSheet("text-align: left; padding: 10px; color: #E2E8F0; background: #312E81; border-radius: 8px; font-weight: bold;")
        ws_btn.clicked.connect(lambda: self.switch_to_workspace.emit(list(self.selected_images), True))
        sl.addWidget(ws_btn)

        # Collections List
        sl.addSpacing(10)
        sl.addWidget(self._section_label("COLLECTIONS"))
        self.collections_list = QListWidget()
        self.collections_list.setStyleSheet("background: transparent; border: none; outline: none; color: #94A3B8;")
        self.collections_list.itemClicked.connect(self._on_collection_clicked)
        sl.addWidget(self.collections_list, stretch=1)
        
        # Smart Collections
        sl.addWidget(self._section_label("SMART COLLECTIONS"))
        self.smart_collections_list = QListWidget()
        self.smart_collections_list.setStyleSheet("background: transparent; border: none; outline: none; color: #94A3B8;")
        self.smart_collections_list.itemClicked.connect(self.set_smart_collection)
        sl.addWidget(self.smart_collections_list, stretch=1)

        # Tags List
        sl.addWidget(self._section_label("POPULAR TAGS"))
        self.tags_list = QListWidget()
        self.tags_list.setStyleSheet("background: transparent; border: none; outline: none; color: #94A3B8;")
        self.tags_list.itemClicked.connect(self._on_tag_clicked)
        sl.addWidget(self.tags_list, stretch=2)

        # Tools / Import
        sl.addSpacing(10)
        sl.addWidget(self._section_label("IMPORT & TOOLS"))
        
        self.upload_btn = self._build_nav_btn("Local Import", "folder")
        self.upload_btn.clicked.connect(self.show_upload.emit)
        sl.addWidget(self.upload_btn)
        
        self.danbooru_btn = self._build_nav_btn("Danbooru", "search")
        self.danbooru_btn.clicked.connect(self.show_danbooru.emit)
        sl.addWidget(self.danbooru_btn)

        # Settings
        sl.addStretch()
        settings_btn = self._build_nav_btn("Settings & About", "settings")
        settings_btn.clicked.connect(self._open_settings)
        sl.addWidget(settings_btn)

        return sidebar

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(64)
        bar.setStyleSheet("background-color: #0F172A; border-bottom: 1px solid #1E293B;")
        
        tl = QHBoxLayout(bar)
        tl.setContentsMargins(20, 0, 20, 0)
        
        # Breadcrumb / Filter Status
        self.breadcrumb_label = QLabel("All images")
        self.breadcrumb_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #F1F5F9;")
        tl.addWidget(self.breadcrumb_label)
        
        tl.addStretch()

        # Search Bar
        search_wrap = QFrame()
        search_wrap.setObjectName("searchContainer")
        search_wrap.setFixedWidth(320)
        search_wrap.setFixedHeight(36)
        search_layout = QHBoxLayout(search_wrap)
        search_layout.setContentsMargins(12, 0, 12, 0)
        search_layout.setSpacing(8)
        
        # Modern glassmorphism/flat style for search bar
        search_wrap.setStyleSheet("""
            QFrame#searchContainer {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 18px;
            }
            QFrame#searchContainer:focus-within {
                background-color: #0F172A;
                border: 1px solid #8B5CF6;
            }
        """)
        
        search_icon = QLabel()
        search_icon.setPixmap(QIcon(icon_path("search")).pixmap(QSize(16, 16)))
        search_icon.setStyleSheet("background: transparent;")
        search_layout.addWidget(search_icon)
        
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search your library...")
        self.search_entry.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #F1F5F9;
                font-size: 13px;
                padding-bottom: 1px; /* Align text better vertically */
            }
        """)
        self.search_entry.returnPressed.connect(self._on_search)
        search_layout.addWidget(self.search_entry)
        
        tl.addWidget(search_wrap)
        tl.addSpacing(20)

        # Sorting
        tl.addWidget(QLabel("Sort:"))
        self.sort_combo = QComboBox()
        self.sort_combo.setFixedWidth(140)
        
        # Human-readable labels
        options = {
            "date_added_desc": "Newest first",
            "date_added_asc": "Oldest first",
            "name_asc": "Name (A-Z)",
            "name_desc": "Name (Z-A)",
            "last_viewed_desc": "Recently viewed",
            "favorite_first": "Favorites first"
        }
        for key, label in options.items():
            self.sort_combo.addItem(label, key)
            
        self.sort_combo.setCurrentIndex(0) # Default to newest
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        tl.addWidget(self.sort_combo)
        
        # View Controls
        tl.addSpacing(10)
        self.column_slider = QSlider(Qt.Horizontal)
        self.column_slider.setRange(2, 8)
        self.column_slider.setValue(self.columns)
        self.column_slider.setFixedWidth(80)
        self.column_slider.valueChanged.connect(self._set_columns)
        tl.addWidget(QLabel("\u25A6"))
        tl.addWidget(self.column_slider)
        
        # Safe Mode Toggle
        self.safe_mode_btn = QPushButton("Safe: ON")
        self.safe_mode_btn.setCheckable(True)
        self.safe_mode_btn.setChecked(get_settings().get_safe_mode())
        self.safe_mode_btn.clicked.connect(self._toggle_safe_mode)
        self._update_safe_mode_btn_style()
        tl.addWidget(self.safe_mode_btn)

        return bar

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(300)
        panel.setStyleSheet("background-color: #0F172A; border-left: 1px solid #1E293B;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Title
        self.detail_title = QLabel("Selection Details")
        self.detail_title.setStyleSheet("color: #F1F5F9; font-size: 18px; font-weight: bold;")
        self.detail_title.setWordWrap(True)
        layout.addWidget(self.detail_title)

        # Path Section
        path_box = QVBoxLayout()
        path_box.setSpacing(4)
        path_hdr = QLabel("FILE PATH")
        path_hdr.setStyleSheet("color: #475569; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        path_box.addWidget(path_hdr)
        self.detail_path = ElidedLabel("None")
        self.detail_path.setStyleSheet("color: #94A3B8; font-size: 12px;")
        path_box.addWidget(self.detail_path)
        layout.addLayout(path_box)

        # AI Status Section
        status_box = QVBoxLayout()
        status_box.setSpacing(4)
        status_hdr = QLabel("AI SCAN STATUS")
        status_hdr.setStyleSheet("color: #475569; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        status_box.addWidget(status_hdr)
        self.detail_ai_status = QLabel("N/A")
        self.detail_ai_status.setStyleSheet("color: #94A3B8; font-size: 12px;")
        status_box.addWidget(self.detail_ai_status)
        layout.addLayout(status_box)

        # Tags Section
        tags_box = QVBoxLayout()
        tags_box.setSpacing(8)
        tags_hdr = QLabel("TAGS")
        tags_hdr.setStyleSheet("color: #475569; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        tags_box.addWidget(tags_hdr)
        
        self.detail_tags_list = QListWidget()
        self.detail_tags_list.setFlow(QListWidget.LeftToRight)
        self.detail_tags_list.setWrapping(True)
        self.detail_tags_list.setResizeMode(QListWidget.Adjust)
        self.detail_tags_list.setSpacing(6)
        self.detail_tags_list.setStyleSheet("""
            QListWidget { background: transparent; border: none; outline: none; }
            QListWidget::item { 
                background-color: #1E293B; color: #E2E8F0; 
                border-radius: 12px; padding: 4px 10px; font-size: 11px;
            }
        """)
        tags_box.addWidget(self.detail_tags_list)
        layout.addLayout(tags_box)

        layout.addStretch()
        return panel

    def _build_nav_btn(self, text: str, icon_name: str) -> QPushButton:
        btn = QPushButton(f"  {text}")
        btn.setCheckable(True)
        icon = QIcon(icon_path(icon_name))
        btn.setIcon(icon)
        btn.setIconSize(QSize(18, 18))
        btn.setStyleSheet("""
            QPushButton {
                text-align: left; padding: 10px 12px; border-radius: 8px;
                color: #94A3B8; font-weight: 500; background: transparent;
                border: 1px solid transparent;
            }
            QPushButton:hover { background-color: #1E293B; color: #F1F5F9; }
            QPushButton:checked { 
                background-color: #312E81; 
                color: #E2E8F0; 
                border: 1px solid #4F46E5;
            }
        """)
        return btn

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #475569; font-size: 10px; font-weight: 800; letter-spacing: 1px; padding: 10px 0 2px 0;")
        return lbl

    def _update_safe_mode_btn_style(self) -> None:
        active = self.safe_mode_btn.isChecked()
        self.safe_mode_btn.setText(f"Safe: {'ON' if active else 'OFF'}")
        color = "#10B981" if active else "#EF4444"
        self.safe_mode_btn.setStyleSheet(f"color: {color}; border: 1px solid {color}; padding: 4px; border-radius: 4px;")

    def load_gallery(self) -> None:
        """Fetch and render images."""
        try:
            while self.gallery_grid.count():
                item = self.gallery_grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._cards.clear()
            self.path_to_id.clear()

            total = self.image_mgr.count_images(
                collection_id=self.current_collection_id,
                tag_ids=self.current_tag_id,
                search_term=self.current_search,
                only_favorites=self.only_favorites,
                only_recent=self.only_recent
            )
            self.total_items = total
            if hasattr(self._load_status, "label"):
                self._load_status.label.setText(f"{total} images")
            
            ipp = get_settings().get_items_per_page()
            max_page = math.ceil(total / ipp) if total > 0 else 1
            if self.current_page > max_page: self.current_page = max_page
            if self.current_page < 1: self.current_page = 1
            
            self.page_info_lbl.setText(f"Page {self.current_page} of {max_page}")
            self.prev_page_btn.setEnabled(self.current_page > 1)
            self.next_page_btn.setEnabled(self.current_page < max_page)
            
            # Update Overall Library Stats
            all_images_count = self.image_mgr.count_images()
            self.db_stats_badge.setText(f"💎 {all_images_count:,} IMAGES IN LIBRARY")

            self._update_breadcrumb()

            images = self.image_mgr.query_images(
                collection_id=self.current_collection_id,
                tag_ids=self.current_tag_id,
                search_term=self.current_search,
                only_favorites=self.only_favorites,
                only_recent=self.only_recent,
                limit=ipp,
                offset=(self.current_page - 1) * ipp,
                sort_by=self.sort_by
            )

            row, col = 0, 0
            vw = self.gallery_scroll.viewport().width()
            overhead = 20 + (20 * self.columns)
            size = (vw - overhead) // self.columns if vw > 100 else 220
            
            self._ordered_paths = []
            for i, data in enumerate(images):
                path = data["file_path"]
                self._ordered_paths.append(path)
                self.path_to_id[path] = data["id"]
                
                card = ImageCard(path, bool(data.get("is_favorite")), not Path(path).exists(), size)
                card.set_selected(path in self.selected_images)
                card.set_ai_status(data.get("ai_status", "pending"))
                card._is_sensitive = bool(data.get("is_sensitive", 0))
                card._update_safety_visuals()
                
                card.clicked.connect(lambda ev, p=path, c=card: self._on_card_clicked(p, c, ev))
                card.double_clicked.connect(lambda idx=i: self._open_image_viewer(idx))
                card.right_clicked.connect(lambda pos, p=path: self._show_context_menu(pos, p))

                self._cards[path] = card
                self.gallery_grid.addWidget(card, row, col)
                col += 1
                if col >= self.columns:
                    col, row = 0, row + 1
                
                self._load_queue.enqueue_file(path, path, data.get("thumbnail_path"), (size, size))

            self._refresh_sidebar_data()
        except Exception as e:
            logger.error(f"Failed to load gallery: {e}")

    def _refresh_sidebar_data(self) -> None:
        try:
            self.collections_list.clear()
            for c in self.col_mgr.get_collections():
                i = QListWidgetItem(c['name'])
                i.setData(Qt.UserRole, c['id'])
                self.collections_list.addItem(i)
            
            self.smart_collections_list.clear()
            def add_sc(name, tag_names):
                tags = self.tag_mgr.get_tags()
                ids = [t['id'] for t in tags if t['name'] in tag_names]
                if ids:
                    i = QListWidgetItem(name)
                    i.setData(Qt.UserRole, ids)
                    self.smart_collections_list.addItem(i)
            
            add_sc("\u2642 Male Poses", ["Male", "Boy", "Man"])
            add_sc("\u2640 Female Poses", ["Female", "Girl", "Woman"])
            add_sc("\u2601 Backgrounds", ["Background", "Scenery", "Nature"])
            add_sc("\u2694 Action", ["Action", "Fighting", "Running", "Jump"])
            
            self.tags_list.clear()
            for t in self.tag_mgr.get_popular_tags(15):
                i = QListWidgetItem(f"#{t['name']}")
                i.setData(Qt.UserRole, [t['id']])
                self.tags_list.addItem(i)
        except Exception as e:
            logger.error(f"Failed to refresh sidebar: {e}")

    def _update_breadcrumb(self) -> None:
        parts = []
        if self.only_favorites: parts.append("Favorites")
        elif self.only_recent: parts.append("Recent")
        else: parts.append("All images")
        
        if self.current_collection_id:
            parts.append("Collection")
        if self.current_tag_id:
            parts.append("Filtered")
        if self.current_search:
            parts.append(f'"{self.current_search}"')
            
        self.breadcrumb_label.setText(" \u203a ".join(parts))

    def _on_thumbnail_ready(self, path: str, pixmap: QPixmap, gen: int) -> None:
        if path in self._cards:
            self._cards[path].set_pixmap(pixmap)

    def set_ai_scan_progress(self, current: int, total: int, image_id: int = None, status: str = 'scanning') -> None:
        if total > 0:
            percent = int((current / total) * 100)
            self._load_status.set_progress(current, total, f"AI Scanning\u2026 {percent}%")
            if image_id is not None:
                target_id = int(image_id)
                for p, mid in self.path_to_id.items():
                    if int(mid) == target_id and p in self._cards:
                        card = self._cards[p]
                        card.set_ai_status(status)
                        if status == 'scanning':
                            self.gallery_scroll.ensureWidgetVisible(card)
            if current >= total and status == 'idle':
                QTimer.singleShot(2000, self._load_status.hide_idle)
        else:
            self._load_status.hide_idle()

    def reset_filters(self, reload=True):
        self.current_tag_id = self.current_collection_id = self.current_search = None
        self.only_favorites = self.only_recent = False
        self.current_page = 1
        if hasattr(self, "search_entry"):
            self.search_entry.clear()
        if hasattr(self, "all_btn"):
            self.all_btn.setChecked(True)
        if reload:
            self.load_gallery()

    def set_favorites_filter(self):
        self.only_favorites = True
        self.only_recent = False
        self.current_page = 1
        self.load_gallery()

    def set_recent_filter(self):
        self.only_favorites = False
        self.only_recent = True
        self.current_page = 1
        self.load_gallery()

    def _on_collection_clicked(self, item):
        self.current_collection_id = item.data(Qt.UserRole)
        self.current_tag_id = None
        self.current_page = 1
        self.load_gallery()

    def _on_tag_clicked(self, item):
        self.current_tag_id = item.data(Qt.UserRole)
        self.current_collection_id = None
        self.current_page = 1
        self.load_gallery()

    def set_smart_collection(self, item: QListWidgetItem) -> None:
        # Extract data before load_gallery potentially refreshes the list and deletes the item
        tag_id = item.data(Qt.UserRole)
        self.current_tag_id = tag_id
        self.current_collection_id = None
        self.current_page = 1
        self.load_gallery()

    def _on_search(self):
        self.current_search = self.search_entry.text().strip()
        self.current_page = 1
        self.load_gallery()

    def _on_sort_changed(self):
        self.sort_by = self.sort_combo.currentData()
        self.current_page = 1
        self.load_gallery()

    def _set_columns(self, val):
        self.columns = val
        self.load_gallery()

    def _on_card_clicked(self, path, card, event): 
        from PyQt5.QtWidgets import QApplication
        modifiers = QApplication.keyboardModifiers()
        
        if modifiers & Qt.ShiftModifier and hasattr(self, "_last_selected_path") and self._last_selected_path:
            # Shift+Click: Select range
            self._range_select(self._last_selected_path, path)
        elif modifiers & Qt.ControlModifier:
            # Ctrl+Click: Toggle selection
            if path in self.selected_images:
                self.selected_images.remove(path)
                card.set_selected(False)
            else:
                self.selected_images.add(path)
                card.set_selected(True)
        else:
            # Normal click: Select single
            for c in self._cards.values():
                c.set_selected(False)
            self.selected_images = {path}
            card.set_selected(True)
        
        self._last_selected_path = path
        
        if len(self.selected_images) > 1:
            self._update_multi_detail_panel()
        else:
            self._update_detail_panel(self.path_to_id.get(path))

    def _range_select(self, start_path: str, end_path: str):
        if start_path not in self._ordered_paths or end_path not in self._ordered_paths:
            return
        idx1 = self._ordered_paths.index(start_path)
        idx2 = self._ordered_paths.index(end_path)
        low, high = min(idx1, idx2), max(idx1, idx2)
        new_selection = set(self._ordered_paths[low:high+1])
        self.selected_images.update(new_selection)
        for p in new_selection:
            if p in self._cards:
                self._cards[p].set_selected(True)

    def _update_multi_detail_panel(self) -> None:
        count = len(self.selected_images)
        self.detail_title.setText(f"{count} Images Selected")
        self.detail_path.setText("Multiple items...")
        self.detail_ai_status.setText("N/A")
        self.detail_tags_list.clear()
        item = QListWidgetItem("Use right-click for bulk actions")
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.detail_tags_list.addItem(item)

    def _update_detail_panel(self, image_id: int) -> None:
        if not image_id:
            self.detail_title.setText("Selection Details")
            self.detail_path.setText("None")
            self.detail_ai_status.setText("N/A")
            self.detail_tags_list.clear()
            return
        try:
            from database import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM images WHERE id = ?", (image_id,))
            row = cursor.fetchone()
            if not row:
                self.detail_title.setText("Error")
                self.detail_path.setText("Image data not found")
                return
            row_dict = dict(row)
            self.detail_title.setText(Path(row_dict['file_path']).name)
            self.detail_path.setText(row_dict['file_path'])
            self.detail_ai_status.setText(row_dict.get('ai_status', 'pending').upper())
            
            self.detail_tags_list.clear()
            tags = self.tag_mgr.get_tags_for_image(image_id)
            if tags:
                for t in tags:
                    item = QListWidgetItem(t['name'])
                    item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
                    self.detail_tags_list.addItem(item)
            else:
                item = QListWidgetItem("No tags")
                item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
                self.detail_tags_list.addItem(item)
        except Exception as e:
            logger.error(f"Failed to update detail panel: {e}")

    def _show_context_menu(self, pos: QPoint, path: str) -> None:
        # If the right-clicked item isn't selected, make it the only selection
        if path not in self.selected_images:
            for c in self._cards.values():
                c.set_selected(False)
            self.selected_images = {path}
            if path in self._cards:
                self._cards[path].set_selected(True)
            self._update_detail_panel(self.path_to_id.get(path))
            self._last_selected_path = path

        paths = list(self.selected_images)
        count = len(paths)
        
        menu = QMenu(self)
        
        # Primary Action
        open_label = f"Open {'image' if count == 1 else f'{count} images'} in Workspace"
        menu.addAction(open_label).triggered.connect(lambda: self.switch_to_workspace.emit(paths, True))
        
        # Submenu for specific slots
        send_menu = menu.addMenu("Send to Workspace")
        for i in range(1, 6):
            action = send_menu.addAction(f"Slot {i}")
            action.triggered.connect(lambda checked, s=i: self.import_to_workspace_slot.emit(paths, s))
            
        menu.addSeparator()
        menu.addAction("✨ AI Analysis").triggered.connect(lambda: self._trigger_ai_scan(paths))
        menu.addAction("Edit Tags...").triggered.connect(lambda: self._open_tag_editor(paths))
        
        menu.addSeparator()
        delete_action = menu.addAction("Delete from Library")
        delete_action.triggered.connect(lambda: self._delete_selected_images(paths))
        
        menu.exec_(pos)

    def _delete_selected_images(self, paths: list) -> None:
        count = len(paths)
        if QMessageBox.question(
            self,
            "Delete images?",
            f"Are you sure you want to delete {count} image(s) from your library?\n\nThis will remove them from the database and delete the local files in your library folder.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        ) != QMessageBox.Yes:
            return

        success_count = 0
        for p in paths:
            if self.image_mgr.delete_image(p):
                success_count += 1
                if p in self.selected_images:
                    self.selected_images.remove(p)

        if self._toast:
            self._toast(f"Deleted {success_count} image(s)")
        
        self.load_gallery()

    def _trigger_ai_scan(self, paths: list) -> None:
        data = []
        for p in paths:
            if p in self.path_to_id:
                data.append((self.path_to_id[p], p))
        
        if data:
            main = self.window()
            if hasattr(main, "ai_manager"):
                main.ai_manager.enqueue_images(data, priority=True)
                if self._toast:
                    self._toast(f"Enqueued {len(data)} images for AI Analysis")

    def _open_tag_editor(self, paths: list) -> None:
        ids = [self.path_to_id[p] for p in paths if p in self.path_to_id]
        if ids:
            dialog = TagEditDialog(self.window(), self.tag_mgr, ids, self.load_gallery)
            dialog.exec_()

    def _toggle_safe_mode(self): 
        active = self.safe_mode_btn.isChecked()
        get_settings().set_safe_mode(active)
        self._update_safe_mode_btn_style()
        for c in self._cards.values(): c._update_safety_visuals()

    def _open_settings(self):
        from ui.settings_dialog import SettingsDialog
        SettingsDialog(self.window()).exec_()

    def focus_image(self, image_id):
        self.reset_filters()
        self.load_gallery()

    def _open_image_viewer(self, index: int) -> None:
        """Open the full-screen lightbox viewer starting at the given index."""
        if not self._ordered_paths:
            return
            
        viewer = ImageViewer(self.window(), self._ordered_paths, index, self.image_mgr)
        # Connect viewer signal to workspace action (adds without replacing)
        viewer.add_to_workspace.connect(lambda p: self.switch_to_workspace.emit([p], False))
        viewer.exec_()

    def _update_card_sizes(self):
        """Recalculate and update all visible card sizes to fit the current viewport."""
        vw = self.gallery_scroll.viewport().width()
        if vw < 100:
            return
            
        # overhead = margins (20+20) + spacing ((cols-1)*20) = 20 + 20*cols
        overhead = 20 + (20 * self.columns)
        size = (vw - overhead) // self.columns
        
        for card in self._cards.values():
            card.update_size(size)

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_gallery()
            self.gallery_scroll.verticalScrollBar().setValue(0)

    def _next_page(self):
        ipp = get_settings().get_items_per_page()
        max_page = math.ceil(self.total_items / ipp)
        if self.current_page < max_page:
            self.current_page += 1
            self.load_gallery()
            self.gallery_scroll.verticalScrollBar().setValue(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Delay update slightly to ensure viewport width is settled
        QTimer.singleShot(0, self._update_card_sizes)
