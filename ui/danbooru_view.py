"""
danbooru_view.py — Search Danbooru and import images into the library.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app_settings import get_settings
from managers.danbooru_manager import DanbooruError, DanbooruManager, DanbooruPost
from managers.image_manager import ImageManager
from managers.tag_manager import TagManager
from ui.image_load_queue import ImageLoadQueue, pixmap_from_bytes
from ui.loading_indicator import LoadingSpinner, LoadingStatusBar

logger = logging.getLogger(__name__)

QUICK_TAGS = (
    "1girl",
    "landscape",
    "solo",
    "reference_sheet",
    "official_art",
    "scenery",
)


class TagSuggestWorker(QThread):
    finished = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, mgr: DanbooruManager, prefix: str) -> None:
        super().__init__()
        self._mgr = mgr
        self._prefix = prefix

    def run(self) -> None:
        try:
            self.finished.emit(self._mgr.suggest_tags(self._prefix, limit=12))
        except Exception as exc:
            self.failed.emit(str(exc))


class CountWorker(QThread):
    finished = pyqtSignal(int)

    def __init__(self, mgr: DanbooruManager, tags: str) -> None:
        super().__init__()
        self._mgr = mgr
        self._tags = tags

    def run(self) -> None:
        count = self._mgr.count_posts(self._tags)
        self.finished.emit(count if count is not None else -1)


class SearchWorker(QThread):
    finished = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(
        self,
        mgr: DanbooruManager,
        tags: str,
        *,
        page: int = 1,
        before_id: int | None = None,
        after_id: int | None = None,
        limit: int = 40,
    ) -> None:
        super().__init__()
        self._mgr = mgr
        self._tags = tags
        self._page = page
        self._before_id = before_id
        self._after_id = after_id
        self._limit = limit

    def run(self) -> None:
        try:
            posts = self._mgr.search_posts(
                self._tags,
                page=self._page,
                limit=self._limit,
                before_id=self._before_id,
                after_id=self._after_id,
            )
            self.finished.emit(posts)
        except Exception as exc:
            self.failed.emit(str(exc))


@dataclass
class _CachedPage:
    posts: list[DanbooruPost]
    previews: dict[int, QPixmap] = field(default_factory=dict)
    first_id: int = 0
    last_id: int = 0


class ImportWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, int)
    failed = pyqtSignal(str)

    def __init__(
        self,
        mgr: DanbooruManager,
        image_mgr: ImageManager,
        tag_mgr: TagManager,
        posts: list[DanbooruPost],
        import_tags: bool,
        max_tags: int,
    ) -> None:
        super().__init__()
        self._mgr = mgr
        self._image_mgr = image_mgr
        self._tag_mgr = tag_mgr
        self._posts = posts
        self._import_tags = import_tags
        self._max_tags = max_tags
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        if self._import_tags and self._posts:
            self._mgr.enrich_posts_with_tags(self._posts)
        imported = 0
        skipped = 0
        total = len(self._posts)
        for idx, post in enumerate(self._posts, start=1):
            if self._cancelled:
                break
            step = (
                f"Downloading and tagging #{post.id}…"
                if self._import_tags
                else f"Downloading full resolution #{post.id}…"
            )
            self.progress.emit(idx, total, step)
            try:
                path = self._mgr.download_post(post)
                file_hash = ImageManager._compute_file_hash(path)
                was_new = self._image_mgr.import_image(str(path))
                image_id = self._image_mgr.get_image_id_by_hash(file_hash)
                if image_id is None:
                    skipped += 1
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    continue
                if was_new:
                    imported += 1
                else:
                    skipped += 1
                if self._import_tags:
                    self._apply_tags(post, image_id)
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            except Exception as exc:
                logger.warning("Import post %s failed: %s", post.id, exc)
                skipped += 1
        self.finished.emit(imported, skipped)

    def _tag_names_for_post(self, post: DanbooruPost) -> list[str]:
        if not post.tag_list:
            post.tag_string = self._mgr.fetch_post_tag_string(post.id)
        return post.tag_list

    def _apply_tags(self, post: DanbooruPost, image_id: int) -> None:
        names = self._tag_names_for_post(post)[: self._max_tags]
        if names:
            self._tag_mgr.apply_danbooru_tags_to_image(image_id, names)


class PostCard(QWidget):
    clicked = pyqtSignal(int, bool)

    def __init__(self, post: DanbooruPost) -> None:
        super().__init__()
        self.post_id = post.id
        self._selected = False
        self.setFixedSize(160, 200)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.thumb_wrap = QWidget()
        self.thumb_wrap.setFixedSize(150, 150)
        self.thumb_wrap.setAttribute(Qt.WA_StyledBackground, True)
        self._thumb_border_normal = (
            "background-color: #1E293B; border: 2px solid #334155; border-radius: 6px;"
        )
        self._thumb_border_selected = (
            "background-color: #1E293B; border: 3px solid #7C3AED; border-radius: 6px;"
        )
        self.thumb_wrap.setStyleSheet(self._thumb_border_normal)
        thumb_inner = QVBoxLayout(self.thumb_wrap)
        thumb_inner.setContentsMargins(0, 0, 0, 0)
        thumb_inner.setAlignment(Qt.AlignCenter)
        self._spinner = LoadingSpinner(32, self.thumb_wrap)
        self.thumb = QLabel()
        self.thumb.setFixedSize(150, 150)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.hide()
        thumb_inner.addWidget(self._spinner, alignment=Qt.AlignCenter)
        thumb_inner.addWidget(self.thumb, alignment=Qt.AlignCenter)
        self._spinner.start()
        layout.addWidget(self.thumb_wrap)
        self.meta = QLabel(f"#{post.id} · {post.rating or '?'}")
        self.meta.setAlignment(Qt.AlignCenter)
        self.meta.setStyleSheet("color: #94A3B8; font-size: 10px;")
        layout.addWidget(self.meta)
        self._preview_badge = QLabel("Preview")
        self._preview_badge.setAlignment(Qt.AlignCenter)
        self._preview_badge.setStyleSheet("color: #64748B; font-size: 9px;")
        layout.addWidget(self._preview_badge)
        self._apply_style()

    def set_import_available(self, available: bool) -> None:
        if available:
            self._preview_badge.setText("Preview · full res on import")
            self.setToolTip("Low-resolution preview. Import downloads the original file.")
        else:
            self._preview_badge.setText("Preview only — cannot import")
            self.setToolTip("No original file URL available for import.")

    def set_preview(self, pixmap: QPixmap | None) -> None:
        self._spinner.stop()
        if pixmap:
            self.thumb.setPixmap(
                pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            self.thumb.show()
        else:
            self.thumb.setText("?")
            self.thumb.setStyleSheet("color: #64748B; font-size: 20px; border: none;")
            self.thumb.show()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_style()

    def is_selected(self) -> bool:
        return self._selected

    def _apply_style(self) -> None:
        self.thumb_wrap.setStyleSheet(
            self._thumb_border_selected if self._selected else self._thumb_border_normal
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.set_selected(not self._selected)
            self.clicked.emit(self.post_id, self._selected)
        super().mousePressEvent(event)


class DanbooruView(QWidget):
    """Search Danbooru and import posts into the local library."""

    def __init__(
        self,
        parent=None,
        back_callback=None,
        status_callback=None,
        toast_callback=None,
        on_import_done=None,
    ) -> None:
        super().__init__(parent)
        self._back = back_callback
        self._status = status_callback
        self._toast = toast_callback
        self._on_import_done = on_import_done
        self._mgr = DanbooruManager()
        self._image_mgr = ImageManager()
        self._tag_mgr = TagManager()
        self._posts: list[DanbooruPost] = []
        self._cards: dict[int, PostCard] = {}
        self._selected: set[int] = set()
        self._selected_posts: dict[int, DanbooruPost] = {}
        self._page = 1
        self._search_tags_key = ""
        self._page_cache: dict[int, _CachedPage] = {}
        self._page_cursors: dict[int, tuple[int, int]] = {}
        self._current_page_previews: dict[int, QPixmap] = {}
        self._total_count: int | None = None
        self._count_worker: CountWorker | None = None
        self._search_worker: SearchWorker | None = None
        # ~6 parallel previews keeps total HTTP near Danbooru's 10 req/s read limit.
        self._preview_queue = ImageLoadQueue(self, worker_count=6)
        self._preview_queue.image_ready.connect(self._on_preview_ready)
        self._preview_queue.progress.connect(self._on_preview_progress)
        self._preview_queue.queue_empty.connect(self._on_preview_queue_empty)
        self._preview_generation = 0
        self._import_worker: ImportWorker | None = None
        self._tag_suggest_worker: TagSuggestWorker | None = None
        self._tag_debounce = QTimer(self)
        self._tag_debounce.setSingleShot(True)
        self._tag_debounce.setInterval(500)
        self._tag_debounce.timeout.connect(self._fetch_tag_suggestions)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        top = QHBoxLayout()
        back_btn = QPushButton("← Gallery")
        back_btn.clicked.connect(self._go_back)
        top.addWidget(back_btn)
        title = QLabel("Danbooru")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #E2E8F0;")
        top.addWidget(title)
        top.addStretch()
        cred = "API key set" if self._mgr.has_credentials() else "No API key (lower rate limits)"
        top.addWidget(QLabel(cred))
        root.addLayout(top)

        hint = QLabel(
            "Click thumbnails to select (kept across pages) · Ctrl+click also toggles · "
            "Import downloads full resolution · Cached searches load faster"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748B; font-size: 11px;")
        root.addWidget(hint)

        search_row = QHBoxLayout()
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Start typing a tag… e.g. nami")
        self.tag_input.returnPressed.connect(self._on_tag_return)
        self.tag_input.textChanged.connect(self._on_tag_text_changed)
        search_row.addWidget(self.tag_input, stretch=1)
        self._tag_popup = QMenu(self)

        search_row.addWidget(QLabel("Rating:"))
        self.rating_combo = QComboBox()
        for key, label in (
            ("all", "All"),
            ("general", "General"),
            ("sensitive", "Sensitive"),
            ("questionable", "Questionable"),
            ("explicit", "Explicit"),
        ):
            self.rating_combo.addItem(label, key)
        search_row.addWidget(self.rating_combo)

        self.search_btn = QPushButton("Search")
        self.search_btn.setStyleSheet("background-color: #7C3AED;")
        self.search_btn.clicked.connect(self._search)
        search_row.addWidget(self.search_btn)
        root.addLayout(search_row)

        recent_row = QHBoxLayout()
        recent_row.addWidget(QLabel("Recent:"))
        self._recent_tags_host = QHBoxLayout()
        recent_row.addLayout(self._recent_tags_host, stretch=1)
        root.addLayout(recent_row)
        self._rebuild_recent_chips()

        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel("Popular:"))
        for tag in QUICK_TAGS:
            chip = QPushButton(tag)
            chip.setFlat(True)
            chip.setStyleSheet(
                "color: #A78BFA; border: 1px solid #475569; border-radius: 10px; padding: 2px 10px;"
            )
            chip.clicked.connect(lambda _, t=tag: self._use_tag(t, search=False))
            quick_row.addWidget(chip)
        quick_row.addStretch()
        root.addLayout(quick_row)

        suggest_header = QHBoxLayout()
        suggest_header.addWidget(QLabel("Tag suggestions"))
        self._suggest_status = QLabel("")
        self._suggest_status.setStyleSheet("color: #64748B; font-size: 11px;")
        suggest_header.addWidget(self._suggest_status)
        suggest_header.addStretch()
        root.addLayout(suggest_header)

        self.tag_suggest_list = QListWidget()
        self.tag_suggest_list.setMaximumHeight(120)
        self.tag_suggest_list.setFlow(QListWidget.LeftToRight)
        self.tag_suggest_list.setWrapping(True)
        self.tag_suggest_list.setSpacing(4)
        self.tag_suggest_list.setStyleSheet(
            "QListWidget { background: #0F172A; border: 1px solid #334155; border-radius: 8px; }"
            "QListWidget::item { color: #E2E8F0; padding: 6px 10px; }"
            "QListWidget::item:selected { background: #7C3AED; }"
        )
        self.tag_suggest_list.itemClicked.connect(self._on_suggest_item_clicked)
        self.tag_suggest_list.itemDoubleClicked.connect(self._on_suggest_item_double_clicked)
        root.addWidget(self.tag_suggest_list)

        page_row = QHBoxLayout()
        self.prev_btn = QPushButton("‹ Prev")
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self._prev_page)
        self.page_label = QLabel("Page 1")
        self.page_label.setStyleSheet("color: #94A3B8;")
        self.next_btn = QPushButton("Next ›")
        self.next_btn.clicked.connect(self._next_page)
        page_row.addWidget(self.prev_btn)
        page_row.addWidget(self.page_label)
        page_row.addWidget(self.next_btn)
        page_row.addStretch()
        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: #94A3B8;")
        page_row.addWidget(self.result_label)
        self._preview_load_status = LoadingStatusBar()
        page_row.addWidget(self._preview_load_status)
        root.addLayout(page_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)
        self._empty_label = QLabel(
            "Search Danbooru tags (use underscores, e.g. nami_(one_piece)).\n"
            "First search can take about a minute on slow connections."
        )
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("color: #94A3B8; font-size: 13px; padding: 24px;")
        self.grid.addWidget(self._empty_label, 0, 0, 1, 6)
        root.addWidget(self.scroll, stretch=1)

        self._import_banner = QFrame()
        self._import_banner.setObjectName("importBanner")
        self._import_banner.hide()
        self._import_banner.setStyleSheet(
            "QFrame#importBanner { background-color: #1E293B; border: 1px solid #334155; "
            "border-radius: 8px; padding: 4px; }"
        )
        banner_layout = QHBoxLayout(self._import_banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        self._import_banner_icon = QLabel()
        self._import_banner_icon.setFixedWidth(24)
        banner_layout.addWidget(self._import_banner_icon)
        banner_col = QVBoxLayout()
        banner_col.setSpacing(2)
        self._import_banner_title = QLabel("")
        self._import_banner_title.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #E2E8F0; border: none;"
        )
        self._import_banner_detail = QLabel("")
        self._import_banner_detail.setStyleSheet(
            "font-size: 12px; color: #94A3B8; border: none;"
        )
        self._import_banner_detail.setWordWrap(True)
        banner_col.addWidget(self._import_banner_title)
        banner_col.addWidget(self._import_banner_detail)
        banner_layout.addLayout(banner_col, stretch=1)
        self._import_banner_dismiss = QPushButton("Dismiss")
        self._import_banner_dismiss.setFlat(True)
        self._import_banner_dismiss.setStyleSheet("color: #94A3B8; border: none;")
        self._import_banner_dismiss.clicked.connect(self._hide_import_banner)
        self._import_banner_dismiss.hide()
        banner_layout.addWidget(self._import_banner_dismiss)
        root.addWidget(self._import_banner)

        opts = QHBoxLayout()
        self.import_tags_cb = QCheckBox("Add Danbooru tags to library when importing (max 30 per image)")
        self.import_tags_cb.setChecked(True)
        self.import_tags_cb.setToolTip(
            "Creates library tags from each post's tag_string and links them to the imported image."
        )
        opts.addWidget(self.import_tags_cb)
        self._selection_label = QLabel("No images selected")
        self._selection_label.setStyleSheet("color: #94A3B8; font-size: 12px;")
        opts.addWidget(self._selection_label)
        opts.addStretch()
        self.select_page_btn = QPushButton("Select page")
        self.select_page_btn.setToolTip("Select all posts on this page")
        self.select_page_btn.clicked.connect(self._select_page)
        opts.addWidget(self.select_page_btn)
        self.clear_sel_btn = QPushButton("Clear all")
        self.clear_sel_btn.setToolTip("Clear selection on all pages")
        self.clear_sel_btn.clicked.connect(self._clear_selection)
        opts.addWidget(self.clear_sel_btn)
        root.addLayout(opts)

        action = QHBoxLayout()
        self.import_btn = QPushButton("Import selected (0)")
        self.import_btn.setStyleSheet(
            "background-color: #7C3AED; border-color: #6D28D9; padding: 10px 20px; font-weight: bold;"
        )
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self._import_selected)
        action.addStretch()
        action.addWidget(self.import_btn)
        root.addLayout(action)

    def reset(self) -> None:
        self._clear_grid()
        self._posts.clear()
        self._clear_selection()
        self._page = 1
        self._search_tags_key = ""
        self._page_cache.clear()
        self._page_cursors.clear()
        self._current_page_previews.clear()
        self._total_count = None
        self.page_label.setText("Page 1")
        self.result_label.setText("")
        self._hide_import_banner()
        self._rebuild_recent_chips()
        self.tag_suggest_list.clear()
        self._suggest_status.setText("")

    def _rebuild_recent_chips(self) -> None:
        while self._recent_tags_host.count():
            item = self._recent_tags_host.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        recent = get_settings().get_danbooru_recent_tags()
        if not recent:
            lbl = QLabel("—")
            lbl.setStyleSheet("color: #64748B;")
            self._recent_tags_host.addWidget(lbl)
            return
        for tag in recent:
            chip = QPushButton(tag)
            chip.setFlat(True)
            chip.setToolTip(f"Search {tag}")
            chip.setStyleSheet(
                "color: #10B981; border: 1px solid #475569; border-radius: 10px; padding: 2px 10px;"
            )
            chip.clicked.connect(lambda _, t=tag: self._use_tag(t, search=True))
            self._recent_tags_host.addWidget(chip)

    def _current_token(self) -> str:
        return DanbooruManager.current_token(self.tag_input.text())

    def _use_tag(self, tag_name: str, search: bool = False) -> None:
        self.tag_input.setText(DanbooruManager.normalize_user_tags(tag_name))
        self._tag_popup.hide()
        self.tag_suggest_list.clear()
        if search:
            self._search()
        else:
            self._on_tag_text_changed(self.tag_input.text())

    def _insert_tag_token(self, tag_name: str) -> None:
        self.tag_input.setText(
            DanbooruManager.apply_tag_token(self.tag_input.text(), tag_name)
        )
        self._tag_popup.hide()
        self._on_tag_text_changed(self.tag_input.text())

    def _on_tag_return(self) -> None:
        if self.tag_suggest_list.count() > 0 and self.tag_suggest_list.currentRow() < 0:
            item = self.tag_suggest_list.item(0)
            if item:
                self._insert_tag_token(item.data(Qt.UserRole))
                return
        self._tag_popup.hide()
        self._search()

    def _on_tag_text_changed(self, _text: str) -> None:
        self._tag_debounce.stop()
        token = self._current_token()
        if len(token) < 2:
            self.tag_suggest_list.clear()
            self._suggest_status.setText("Type 2+ characters for tag ideas")
            self._tag_popup.hide()
            return
        self._suggest_status.setText(f"Looking up tags matching “{token}”…")
        self._tag_debounce.start()

    def _fetch_tag_suggestions(self) -> None:
        token = self._current_token()
        if len(token) < 2:
            return
        if self._tag_suggest_worker and self._tag_suggest_worker.isRunning():
            return
        self._tag_suggest_worker = TagSuggestWorker(self._mgr, token)
        self._tag_suggest_worker.finished.connect(self._on_tag_suggestions)
        self._tag_suggest_worker.failed.connect(self._on_tag_suggest_failed)
        self._tag_suggest_worker.start()

    def _on_tag_suggest_failed(self, msg: str) -> None:
        self._suggest_status.setText("Tag lookup failed")
        logger.debug("Tag suggest: %s", msg)

    def _on_tag_suggestions(self, suggestions: list) -> None:
        self.tag_suggest_list.clear()
        self._tag_popup.clear()
        if not suggestions:
            self._suggest_status.setText("No matching tags — try a longer name")
            return
        self._suggest_status.setText(f"{len(suggestions)} tags — click to add, double-click to search")
        for s in suggestions:
            name = s["name"]
            cnt = s.get("post_count", 0)
            label = f"{name}  ({cnt:,})" if cnt else name
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, name)
            item.setToolTip(f"Click: add tag · Double-click: search {name}")
            self.tag_suggest_list.addItem(item)
            action = self._tag_popup.addAction(label)
            action.triggered.connect(lambda _, n=name: self._insert_tag_token(n))
        self._tag_popup.popup(
            self.tag_input.mapToGlobal(self.tag_input.rect().bottomLeft())
        )

    def _on_suggest_item_clicked(self, item: QListWidgetItem) -> None:
        if item:
            self._insert_tag_token(item.data(Qt.UserRole))

    def _on_suggest_item_double_clicked(self, item: QListWidgetItem) -> None:
        if item:
            self._insert_tag_token(item.data(Qt.UserRole))
            self._search()

    def _go_back(self) -> None:
        if self._import_worker and self._import_worker.isRunning():
            self._import_worker.cancel()
        if self._back:
            self._back()

    def _tags_query(self) -> str:
        user = self.tag_input.text().strip()
        rating = self.rating_combo.currentData()
        return DanbooruManager.build_tags_query(user, rating)

    def _search(self) -> None:
        self._page = 1
        self._clear_selection()
        query = self._tags_query()
        if query:
            get_settings().add_danbooru_recent_tag(self.tag_input.text().strip())
            self._rebuild_recent_chips()
        self._tag_popup.hide()
        self._search_tags_key = self._tags_query()
        self._page_cache.clear()
        self._page_cursors.clear()
        self._current_page_previews.clear()
        self._total_count = None
        self._fetch_result_count()
        self._run_search()

    def _prev_page(self) -> None:
        if self._page > 1:
            self._save_current_page_cache()
            self._page -= 1
            self._run_search()

    def _next_page(self) -> None:
        self._save_current_page_cache()
        self._page += 1
        self._run_search()

    def _fetch_result_count(self) -> None:
        tags = self._search_tags_key or self._tags_query()
        if self._count_worker and self._count_worker.isRunning():
            return
        self._count_worker = CountWorker(self._mgr, tags)
        self._count_worker.finished.connect(self._on_count_ready)
        self._count_worker.start()

    def _on_count_ready(self, count: int) -> None:
        if count >= 0:
            self._total_count = count
        self._update_result_label()

    def _save_current_page_cache(self) -> None:
        if not self._posts:
            return
        previews = {
            pid: pix.copy()
            for pid, pix in self._current_page_previews.items()
            if pix and not pix.isNull()
        }
        entry = _CachedPage(
            posts=list(self._posts),
            previews=previews,
            first_id=self._posts[0].id,
            last_id=self._posts[-1].id,
        )
        self._page_cache[self._page] = entry
        self._page_cursors[self._page] = (entry.first_id, entry.last_id)

    def _cursor_params(self, target_page: int) -> dict:
        """Danbooru default order is newest-first (id desc).

        Next page (older posts): page=b{lowest_id_on_previous_page}
        Prev page without cache (newer posts): page=a{highest_id_on_current_page}
        """
        if target_page == 1:
            return {"page": 1}
        prev = target_page - 1
        if prev in self._page_cursors:
            _first, last_id = self._page_cursors[prev]
            return {"before_id": last_id}
        if self._posts and target_page < self._page:
            first_id = self._posts[0].id
            return {"after_id": first_id}
        return {"page": target_page}

    def _restore_cached_page(self, entry: _CachedPage) -> None:
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search")
        self._preview_queue.cancel_all()
        self._posts = list(entry.posts)
        self._current_page_previews = {
            pid: pix.copy() for pid, pix in entry.previews.items() if not pix.isNull()
        }
        self._page_cursors[self._page] = (entry.first_id, entry.last_id)
        self._clear_grid()
        self._cards.clear()
        self.page_label.setText(f"Page {self._page}")
        self.prev_btn.setEnabled(self._page > 1)

        if not self._posts:
            self._show_no_results()
            self._update_result_label()
            return

        self._empty_label.hide()
        row, col, cols = 0, 0, 6
        for post in self._posts:
            card = PostCard(post)
            card.set_import_available(self._mgr.can_import_full_resolution(post))
            card.set_selected(post.id in self._selected)
            card.clicked.connect(self._on_card_clicked)
            self._cards[post.id] = card
            cached_pix = self._current_page_previews.get(post.id)
            if cached_pix and not cached_pix.isNull():
                card.set_preview(cached_pix)
            self.grid.addWidget(card, row, col)
            col += 1
            if col >= cols:
                col, row = 0, row + 1

        self._preview_load_status.hide_idle()
        self._update_result_label()
        self._update_import_btn()
        if self._status:
            self._status(f"Danbooru page {self._page} (cached)", 2500)

    def _update_result_label(self) -> None:
        on_page = len(self._posts)
        if self._total_count is not None:
            total_s = f"{self._total_count:,} total"
        else:
            total_s = "…"
        if on_page:
            self.result_label.setText(f"{total_s} · {on_page} on page {self._page}")
        else:
            self.result_label.setText(f"{total_s} · page {self._page}")

    def _run_search(self) -> None:
        if self._search_worker and self._search_worker.isRunning():
            return
        tags = self._tags_query()
        if tags != self._search_tags_key:
            self._search_tags_key = tags
            self._page_cache.clear()
            self._page_cursors.clear()
            self._total_count = None
            self._fetch_result_count()

        cached = self._page_cache.get(self._page)
        if cached is not None:
            self._restore_cached_page(cached)
            return

        self._preview_queue.cancel_all()
        self._current_page_previews.clear()
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Searching…")
        self.page_label.setText(f"Page {self._page}")
        self.prev_btn.setEnabled(self._page > 1)
        self._show_empty_message(f"Searching for: {tags}\nPlease wait…")
        if self._status:
            self._status(f"Danbooru: {tags}")

        cursor = self._cursor_params(self._page)
        self._search_worker = SearchWorker(
            self._mgr,
            tags,
            page=cursor.get("page", self._page),
            before_id=cursor.get("before_id"),
            after_id=cursor.get("after_id"),
            limit=40,
        )
        self._search_worker.finished.connect(self._on_search_done)
        self._search_worker.failed.connect(self._on_search_failed)
        self._search_worker.start()

    def _on_search_failed(self, msg: str) -> None:
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search")
        QMessageBox.warning(self, "Danbooru search failed", msg)

    def _on_search_done(self, posts: list) -> None:
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search")
        self.prev_btn.setEnabled(self._page > 1)
        self._posts = posts
        self._current_page_previews.clear()
        self._clear_grid()
        self._cards.clear()

        if not self._posts:
            self._show_no_results()
            self._update_result_label()
            self._update_import_btn()
            return

        self._page_cursors[self._page] = (self._posts[0].id, self._posts[-1].id)

        self._empty_label.hide()
        row, col, cols = 0, 0, 6
        for post in self._posts:
            card = PostCard(post)
            card.set_import_available(self._mgr.can_import_full_resolution(post))
            card.set_selected(post.id in self._selected)
            card.clicked.connect(self._on_card_clicked)
            self._cards[post.id] = card
            self.grid.addWidget(card, row, col)
            col += 1
            if col >= cols:
                col, row = 0, row + 1

        self._enqueue_previews()

    def _enqueue_previews(self) -> None:
        self._preview_queue.cancel_all()
        self._preview_generation = self._preview_queue.generation
        posts = self._posts[:40]
        if not posts:
            self._preview_load_status.hide_idle()
            return
        total = len(posts)
        self._preview_load_status.show_busy(f"Loading previews… 0/{total}", total=total)
        self._update_result_label()
        self._update_import_btn()
        mgr = self._mgr

        for post in posts:
            key = str(post.id)

            def make_loader(p=post, m=mgr):
                def loader():
                    data = m.fetch_preview_bytes(p)
                    if data:
                        return pixmap_from_bytes(data, max_size=(120, 120))
                    return None
                return loader

            self._preview_queue.enqueue_callable(key, make_loader())

    def _on_preview_ready(self, key: str, pixmap: object, generation: int) -> None:
        if generation != self._preview_generation:
            return
        try:
            post_id = int(key)
        except ValueError:
            return
        card = self._cards.get(post_id)
        if card and pixmap:
            card.set_preview(pixmap)
            copy = pixmap.copy()
            self._current_page_previews[post_id] = copy
            cached_page = self._page_cache.get(self._page)
            if cached_page is not None:
                cached_page.previews[post_id] = copy
        elif card:
            card.set_preview(None)

    def _on_preview_progress(self, done: int, total: int, generation: int) -> None:
        if generation != self._preview_generation:
            return
        self._preview_load_status.set_progress(
            done, total, f"Loading previews… {done}/{total}",
        )

    def _on_preview_queue_empty(self, generation: int) -> None:
        if generation != self._preview_generation:
            return
        self._preview_load_status.hide_idle()
        self._save_current_page_cache()
        self._update_result_label()
        if self._status:
            self._status("Danbooru previews loaded", 3000)

    def _show_no_results(self) -> None:
        query = self.tag_input.text().strip()
        msg = (
            f"No posts for: {self._tags_query()}\n\n"
            "Danbooru needs full tag names with underscores.\n"
            "Click a suggestion below or type e.g. nami_(one_piece)"
        )
        self._show_empty_message(msg)
        try:
            suggestions = self._mgr.suggest_tags(query.replace(" ", "_"), limit=6)
        except Exception as exc:
            logger.debug("Tag suggest failed: %s", exc)
            suggestions = []
        row = 1
        for s in suggestions:
            name = s["name"]
            cnt = s.get("post_count", 0)
            btn = QPushButton(f"{name} ({cnt})")
            btn.setStyleSheet("text-align: left; padding: 6px;")
            btn.clicked.connect(lambda _, n=name: self._search_tag(n))
            self.grid.addWidget(btn, row, 0, 1, 6)
            row += 1

    def _search_tag(self, tag_name: str) -> None:
        self._use_tag(tag_name, search=True)

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w and w is not self._empty_label:
                w.deleteLater()
        if self._empty_label.parent() is None:
            self.grid.addWidget(self._empty_label, 0, 0, 1, 6)

    def _show_empty_message(self, text: str) -> None:
        self._empty_label.setText(text)
        if self.grid.indexOf(self._empty_label) < 0:
            self.grid.addWidget(self._empty_label, 0, 0, 1, 6)
        self._empty_label.show()

    def _register_selection(self, post_id: int, selected: bool) -> None:
        post = next((p for p in self._posts if p.id == post_id), None)
        if selected:
            self._selected.add(post_id)
            if post:
                self._selected_posts[post_id] = post
        else:
            self._selected.discard(post_id)
            self._selected_posts.pop(post_id, None)

    def _on_card_clicked(self, post_id: int, selected: bool) -> None:
        self._register_selection(post_id, selected)
        self._sync_selection_ui()

    def _select_page(self) -> None:
        for post in self._posts:
            self._register_selection(post.id, True)
            card = self._cards.get(post.id)
            if card:
                card.set_selected(True)
        self._sync_selection_ui()

    def _clear_selection(self) -> None:
        self._selected.clear()
        self._selected_posts.clear()
        for card in self._cards.values():
            card.set_selected(False)
        self._sync_selection_ui()

    def _sync_selection_ui(self) -> None:
        n = len(self._selected)
        self.import_btn.setText(f"Import selected ({n})")
        busy = self._import_worker and self._import_worker.isRunning()
        self.import_btn.setEnabled(n > 0 and not busy)
        if n == 0:
            self._selection_label.setText("No images selected")
        elif n == 1:
            self._selection_label.setText("1 image selected (kept across pages)")
        else:
            self._selection_label.setText(f"{n} images selected (kept across pages)")

    def _show_import_banner(
        self,
        kind: str,
        title: str,
        detail: str,
        show_dismiss: bool = True,
    ) -> None:
        styles = {
            "success": ("✓", "#064E3B", "#10B981", "#A7F3D0"),
            "error": ("✕", "#7F1D1D", "#EF4444", "#FECACA"),
            "warning": ("!", "#422006", "#F59E0B", "#FDE68A"),
            "progress": ("◌", "#1E3A5F", "#3B82F6", "#93C5FD"),
        }
        icon, bg, border, text = styles.get(kind, styles["progress"])
        self._import_banner_icon.setText(icon)
        self._import_banner_icon.setStyleSheet(f"color: {text}; font-size: 18px; border: none;")
        self._import_banner_title.setText(title)
        self._import_banner_title.setStyleSheet(
            f"font-weight: bold; font-size: 13px; color: {text}; border: none;"
        )
        self._import_banner_detail.setText(detail)
        self._import_banner.setStyleSheet(
            f"QFrame#importBanner {{ background-color: {bg}; border: 1px solid {border}; "
            "border-radius: 8px; }}"
        )
        self._import_banner_dismiss.setVisible(show_dismiss)
        self._import_banner.show()

    def _hide_import_banner(self) -> None:
        self._import_banner.hide()

    def _update_import_btn(self) -> None:
        self._sync_selection_ui()

    def _import_selected(self) -> None:
        posts = list(self._selected_posts.values())
        if not posts:
            posts = [
                p for p in self._posts
                if p.id in self._selected
            ]
        if not posts:
            return
        importable = [p for p in posts if self._mgr.can_import_full_resolution(p)]
        skipped_preview = len(posts) - len(importable)
        if not importable:
            QMessageBox.warning(
                self,
                "Cannot import",
                "Selected posts have no full-resolution file available.",
            )
            return
        msg = (
            f"Download and import {len(importable)} full-resolution image(s) into your library?\n\n"
            "Previews in the grid are compressed; import fetches the original files."
        )
        if skipped_preview:
            msg += f"\n\n{skipped_preview} selected post(s) skipped (preview only)."
        if QMessageBox.question(
            self,
            "Import full resolution",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        posts = importable
        total = len(posts)

        self.import_btn.setEnabled(False)
        self.search_btn.setEnabled(False)
        self._show_import_banner(
            "progress",
            f"Importing {total} image{'s' if total != 1 else ''}…",
            "Downloading full-resolution files. You can stay on this page.",
            show_dismiss=False,
        )
        self._import_worker = ImportWorker(
            self._mgr,
            self._image_mgr,
            self._tag_mgr,
            posts,
            import_tags=self.import_tags_cb.isChecked(),
            max_tags=30,
        )
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.failed.connect(self._on_import_failed)
        self._import_worker.start()

    def _on_import_progress(self, cur: int, total: int, msg: str) -> None:
        self.import_btn.setText(f"Importing {cur}/{total}…")
        self._show_import_banner(
            "progress",
            f"Importing {cur} of {total}…",
            msg,
            show_dismiss=False,
        )
        if self._status:
            self._status(msg)

    def _on_import_failed(self, msg: str) -> None:
        self.search_btn.setEnabled(True)
        self._show_import_banner(
            "error",
            "Import failed",
            msg,
            show_dismiss=True,
        )
        self._sync_selection_ui()
        if self._status:
            self._status("Import failed")

    def _on_import_finished(self, imported: int, skipped: int) -> None:
        self.search_btn.setEnabled(True)
        total = imported + skipped
        if imported > 0 and skipped == 0:
            kind = "success"
            title = f"Successfully imported {imported} image{'s' if imported != 1 else ''}"
            detail = (
                "Added to your library at full resolution"
                + (" with Danbooru tags." if self.import_tags_cb.isChecked() else ".")
                + " Selection kept — browse more pages or import again."
            )
        elif imported > 0:
            kind = "warning"
            title = f"Imported {imported} of {total} image{'s' if total != 1 else ''}"
            detail = f"{skipped} skipped (duplicate or error). Your library has been updated."
        else:
            kind = "error"
            title = "Nothing was imported"
            detail = f"All {skipped} image{'s' if skipped != 1 else ''} were skipped (duplicates or download errors)."

        self._show_import_banner(kind, title, detail, show_dismiss=True)
        if self._toast:
            self._toast(title)
        if self._status:
            self._status(title)
        self._sync_selection_ui()
        if self._on_import_done:
            self._on_import_done()
