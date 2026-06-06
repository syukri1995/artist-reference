"""
workspace_view.py — QGraphicsScene-based infinite canvas for viewing reference images.
"""
import logging
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, QRectF, pyqtSignal
from PyQt5.QtGui import QImage, QPainter, QWheelEvent, QMouseEvent
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QFrame, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QSlider,
    QVBoxLayout, QWidget, QShortcut,
)
from PyQt5.QtGui import QKeySequence
from PIL import Image

from app_settings import get_settings
from managers.image_manager import ImageManager
from managers.workspace_manager import WorkspaceManager
from ui.workspace_items import GraphicsPixmapItem
from ui.workspace_undo import (
    AddItemsCommand,
    MoveItemsCommand,
    RemoveItemsCommand,
    TransformItemsCommand,
    _ItemSnapshot,
    create_undo_stack,
    restore_item,
    snapshot_item,
)
from utils_image import pil_to_qpixmap

logger = logging.getLogger(__name__)


class ExtendedGraphicsView(QGraphicsView):
    """QGraphicsView with scroll-to-zoom and middle/right-click pan."""

    def __init__(self, scene: QGraphicsScene, parent=None) -> None:
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("background-color: #121212; border: none;")
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._is_panning = False
        self._pan_start_pos = None
        self._zoom_callback = None
        self._workspace = None

    def set_workspace(self, ws) -> None:
        self._workspace = ws

    def set_zoom_callback(self, cb) -> None:
        self._zoom_callback = cb

    def _notify_zoom(self) -> None:
        if self._zoom_callback:
            self._zoom_callback(self.transform().m11())

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if event.modifiers() == Qt.ControlModifier:
            factor = 1.1 if delta > 0 else 0.9
            if self._workspace:
                self._workspace._apply_scale_selected(factor, uniform=event.modifiers() & Qt.ShiftModifier)
            return
        zoom = 1.25 if delta > 0 else 1 / 1.25
        self.scale(zoom, zoom)
        self._notify_zoom()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.RightButton, Qt.MiddleButton):
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_panning and self._pan_start_pos is not None:
            delta = event.pos() - self._pan_start_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._pan_start_pos = event.pos()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.RightButton, Qt.MiddleButton):
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self._workspace:
                self._workspace._delete_selected()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        old = event.oldSize()
        new = event.size()
        if (
            self._workspace
            and self._workspace.is_float_mode()
            and old.isValid()
            and old.width() > 0
            and old.height() > 0
        ):
            factor = min(new.width() / old.width(), new.height() / old.height())
            if abs(factor - 1.0) > 0.0001:
                self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
                self.scale(factor, factor)
                self._notify_zoom()
        super().resizeEvent(event)


class WorkspaceView(QWidget):
    """Main workspace panel: toolbar + infinite canvas."""

    show_in_gallery_request = pyqtSignal(int)

    _AUTOSAVE_INTERVAL_MS = 120_000
    _COMPACT_WIDTH = 820

    def __init__(
        self,
        master,
        switch_to_gallery_callback,
        toggle_topmost_cb,
        toggle_fullscreen_cb,
        status_callback=None,
        toast_callback=None,
    ) -> None:
        super().__init__(master)
        self.switch_to_gallery_callback = switch_to_gallery_callback
        self.toggle_topmost_cb = toggle_topmost_cb
        self.toggle_fullscreen_cb = toggle_fullscreen_cb
        self._status = status_callback
        self._toast = toast_callback
        self.ws_manager = WorkspaceManager()
        self.image_mgr = ImageManager()
        self.current_slot = get_settings().get_workspace_slot()
        self._autosave_enabled = True
        self._slot_buttons: dict[int, QPushButton] = {}
        self._drag_starts: dict[int, object] = {}
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(lambda: self._perform_autosave(manual=False))

        self._undo_stack = create_undo_stack(self)
        self._loading_slot = False

        self._setup_ui()

        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._perform_autosave)
        self.set_autosave_enabled(True)

        QShortcut(QKeySequence.Undo, self, self._undo_stack.undo)
        QShortcut(QKeySequence.Redo, self, self._undo_stack.redo)
        QShortcut(QKeySequence("`"), self, self._toggle_toolbar)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._toolbar = self._build_toolbar()
        layout.addWidget(self._toolbar)
        self._compact_bar = self._build_compact_bar()
        layout.addWidget(self._compact_bar)
        self._compact_bar.hide()

        canvas_wrap = QWidget()
        self._canvas_wrap = canvas_wrap
        canvas_layout = QVBoxLayout(canvas_wrap)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        self.scene = QGraphicsScene()
        self.scene._workspace = self
        self.view = ExtendedGraphicsView(self.scene, canvas_wrap)
        self.view.set_workspace(self)
        self.view.set_zoom_callback(self._update_hud_zoom)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_canvas_context_menu)
        canvas_layout.addWidget(self.view)

        self._toolbar_restore_btn = QPushButton("Show toolbar")
        self._toolbar_restore_btn.setParent(canvas_wrap)
        self._toolbar_restore_btn.setToolTip("Show workspace toolbar (`)")
        self._toolbar_restore_btn.setStyleSheet(
            "background-color: rgba(30, 41, 59, 220); color: #E2E8F0; "
            "border: 1px solid #475569; border-radius: 6px; padding: 4px 10px;"
        )
        self._toolbar_restore_btn.clicked.connect(lambda: self._set_toolbar_visible(True))
        self._toolbar_restore_btn.hide()

        self._hud = QLabel(canvas_wrap)
        self._hud.setStyleSheet(
            "background-color: rgba(15, 23, 42, 180); color: #94A3B8; "
            "padding: 8px 12px; border-radius: 6px; font-size: 11px;"
        )
        self._hud.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._update_hud_text(100)
        if get_settings().get_show_canvas_hint():
            self._hud.show()
        else:
            self._hud.hide()

        self._empty_hint = QLabel(
            "Add images from the gallery (double-click or Open Workspace)", canvas_wrap
        )
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setStyleSheet("color: #64748B; font-size: 14px; background: transparent;")
        self._empty_hint.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout.addWidget(canvas_wrap, stretch=1)
        self._set_float_mode(get_settings().get_workspace_float_mode(), persist=False)
        self._sync_chrome()
        QTimer.singleShot(0, self._position_overlays)

    def is_float_mode(self) -> bool:
        return get_settings().get_workspace_float_mode()

    def _set_float_mode(self, enabled: bool, *, persist: bool = True) -> None:
        if persist:
            get_settings().set_workspace_float_mode(enabled)
        if hasattr(self, "float_cb"):
            self.float_cb.blockSignals(True)
            self.float_cb.setChecked(enabled)
            self.float_cb.blockSignals(False)
        if enabled:
            self.view.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        else:
            self.view.setResizeAnchor(QGraphicsView.NoAnchor)
        self._sync_chrome()
        if hasattr(self, "view"):
            self._update_hud_text(int(self.view.transform().m11() * 100))

    def _on_float_toggled(self, state: int) -> None:
        self._set_float_mode(state == Qt.Checked)

    def _on_topmost_toggled(self, state: int) -> None:
        checked = state == Qt.Checked
        self.toggle_topmost_cb(checked)
        if checked:
            self._set_float_mode(True)

    def _sync_chrome(self) -> None:
        user_hid_full = not get_settings().get_workspace_toolbar_visible()
        float_on = self.is_float_mode()
        narrow = self.width() < self._COMPACT_WIDTH
        use_compact = float_on or narrow or user_hid_full

        self._toolbar.setVisible(not use_compact)
        if hasattr(self, "_compact_bar"):
            self._compact_bar.setVisible(use_compact)
        show_restore = user_hid_full and use_compact and not narrow
        if hasattr(self, "_toolbar_restore_btn"):
            self._toolbar_restore_btn.setVisible(show_restore)
        self._update_compact_slot_label()
        QTimer.singleShot(0, self._position_overlays)

    def _set_toolbar_visible(self, visible: bool) -> None:
        get_settings().set_workspace_toolbar_visible(visible)
        self._sync_chrome()

    def _toggle_toolbar(self) -> None:
        if self._compact_bar.isVisible():
            self._show_workspace_menu()
            return
        if self._toolbar.isVisible():
            self._set_toolbar_visible(False)
        else:
            self._set_toolbar_visible(True)

    def _schedule_save(self) -> None:
        if self._loading_slot:
            return
        self._save_timer.start()

    def _begin_item_drag(self, item: GraphicsPixmapItem) -> None:
        self._drag_starts[id(item)] = item.pos()

    def _end_item_drag(self, item: GraphicsPixmapItem) -> None:
        key = id(item)
        start = self._drag_starts.pop(key, None)
        if start is None or start == item.pos():
            return
        self._undo_stack.push(
            MoveItemsCommand(
                [item],
                [start],
                [item.pos()],
                self._schedule_save,
            )
        )

    def _position_overlays(self) -> None:
        parent = self.view.parentWidget()
        if not parent:
            return
        w, h = parent.width(), parent.height()
        if self._toolbar_restore_btn.isVisible():
            self._toolbar_restore_btn.adjustSize()
            self._toolbar_restore_btn.move(12, 12)
            self._toolbar_restore_btn.raise_()
        self._hud.adjustSize()
        self._hud.move(w - self._hud.width() - 12, h - self._hud.height() - 12)
        self._empty_hint.setGeometry(0, h // 2 - 20, w, 40)
        self._update_empty_hint()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_chrome()

    def _update_hud_zoom(self, scale: float) -> None:
        self._update_hud_text(int(scale * 100))

    def _update_hud_text(self, zoom_pct: int) -> None:
        if self.is_float_mode():
            extra = "  |  ` menu" if not self._toolbar.isVisible() else ""
            self._hud.setText(f"{zoom_pct}%{extra}")
            return
        hint = ""
        if get_settings().get_show_canvas_hint():
            hint = "  |  Right-drag: pan  |  Scroll: zoom  |  Ctrl+Z undo"
        if not self._toolbar.isVisible():
            hint += "  |  ` toolbar"
        self._hud.setText(f"Zoom {zoom_pct}%{hint}")

    def _update_empty_hint(self) -> None:
        has_items = any(isinstance(i, GraphicsPixmapItem) for i in self.scene.items())
        self._empty_hint.setVisible(not has_items)

    def _build_compact_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(34)
        bar.setStyleSheet(
            "background-color: #1E293B; border-bottom: 1px solid #334155;"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(8)

        menu_btn = QPushButton("\u2630")
        menu_btn.setFixedSize(30, 28)
        menu_btn.setToolTip("Workspace menu (`)")
        menu_btn.clicked.connect(self._show_workspace_menu)
        row.addWidget(menu_btn)

        self._compact_slot = QLabel()
        self._compact_slot.setStyleSheet("color: #94A3B8; font-size: 11px;")
        row.addWidget(self._compact_slot)

        row.addStretch()

        gallery_btn = QPushButton("Gallery")
        gallery_btn.setToolTip("Return to library")
        gallery_btn.clicked.connect(self.switch_to_gallery_callback)
        row.addWidget(gallery_btn)
        return bar

    def _update_compact_slot_label(self) -> None:
        if hasattr(self, "_compact_slot"):
            self._compact_slot.setText(f"Slot {self.current_slot}")

    def _show_workspace_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Gallery", self.switch_to_gallery_callback)
        menu.addSeparator()

        float_action = menu.addAction("Float mode (scale with window)")
        float_action.setCheckable(True)
        float_action.setChecked(self.is_float_mode())
        float_action.triggered.connect(lambda checked: self._set_float_mode(checked))

        top_action = menu.addAction("Topmost")
        top_action.setCheckable(True)
        top_action.setChecked(self.topmost_cb.isChecked())
        top_action.triggered.connect(
            lambda checked: self.topmost_cb.setChecked(checked)
        )

        fs_action = menu.addAction("Fullscreen")
        fs_action.setCheckable(True)
        fs_action.setChecked(self.fullscreen_cb.isChecked())
        fs_action.triggered.connect(
            lambda checked: self.fullscreen_cb.setChecked(checked)
        )
        menu.addSeparator()

        if self._toolbar.isVisible():
            menu.addAction("Compact bar", lambda: self._set_toolbar_visible(False))
        elif self.width() >= self._COMPACT_WIDTH and not self.is_float_mode():
            menu.addAction("Full toolbar", lambda: self._set_toolbar_visible(True))

        undo_menu = menu.addMenu("Undo / redo")
        undo_menu.addAction("Undo", self._undo_stack.undo)
        undo_menu.addAction("Redo", self._undo_stack.redo)

        zoom_menu = menu.addMenu("Zoom")
        zoom_menu.addAction("Zoom in", lambda: self._zoom_by(1.25))
        zoom_menu.addAction("Zoom out", lambda: self._zoom_by(0.8))
        zoom_menu.addAction("Fit all", self._fit_view)
        zoom_menu.addAction("100%", self._reset_view)
        zoom_menu.addAction("Zoom to selection", self._zoom_to_selection)

        edit_menu = menu.addMenu("Edit selection")
        edit_menu.addAction("Flip horizontal", lambda: self._flip_selected(horizontal=True))
        edit_menu.addAction("Flip vertical", lambda: self._flip_selected(vertical=True))
        edit_menu.addAction("Toggle grayscale", self._toggle_grayscale_selected)
        edit_menu.addAction("Bring forward", self._bring_forward)
        edit_menu.addAction("Send backward", self._send_backward)
        edit_menu.addAction("Delete", self._delete_selected)

        menu.addAction("Extract palette", self._extract_palette)
        menu.addAction("Export PNG", self._export)
        menu.addAction("Save slot", self.save_now)
        menu.addSeparator()

        slot_menu = menu.addMenu(f"Workspace slot ({self.current_slot})")
        for i in range(1, 6):
            slot_menu.addAction(f"Slot {i}", lambda _, s=i: self._load_slot(s))

        menu.addAction("Clear all", self._confirm_clear_all)
        menu.exec_(self._compact_bar.mapToGlobal(self._compact_bar.rect().bottomLeft()))

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #1E293B;")
        toolbar.setFixedHeight(56)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 4, 16, 4)

        def sep() -> QFrame:
            f = QFrame()
            f.setFrameShape(QFrame.VLine)
            f.setStyleSheet("color: #334155;")
            return f

        def btn(label: str, slot, tip: str = "", style: str = "") -> QPushButton:
            b = QPushButton(label)
            b.clicked.connect(slot)
            if tip:
                b.setToolTip(tip)
            if style:
                b.setStyleSheet(style)
            return b

        tb.addWidget(btn("Gallery", self.switch_to_gallery_callback, "Return to library"))
        self._undo_btn = btn("Undo", self._undo_stack.undo, "Undo (Ctrl+Z)")
        self._redo_btn = btn("Redo", self._undo_stack.redo, "Redo (Ctrl+Y)")
        self._undo_stack.canUndoChanged.connect(self._undo_btn.setEnabled)
        self._undo_stack.canRedoChanged.connect(self._redo_btn.setEnabled)
        self._undo_btn.setEnabled(False)
        self._redo_btn.setEnabled(False)
        tb.addWidget(self._undo_btn)
        tb.addWidget(self._redo_btn)
        tb.addWidget(sep())
        tb.addWidget(btn("Zoom In", lambda: self._zoom_by(1.25), "Zoom canvas in"))
        tb.addWidget(btn("Zoom Out", lambda: self._zoom_by(0.8), "Zoom canvas out"))
        tb.addWidget(btn("Fit", self._fit_view, "Fit all images in view"))
        tb.addWidget(btn("100%", self._reset_view, "Reset canvas zoom to 100%"))
        tb.addWidget(btn("Sel", self._zoom_to_selection, "Zoom to selection"))
        tb.addWidget(sep())
        tb.addWidget(btn("Flip H", lambda: self._flip_selected(horizontal=True), "Flip selected horizontally"))
        tb.addWidget(btn("Flip V", lambda: self._flip_selected(vertical=True), "Flip selected vertically"))
        tb.addWidget(btn("Gray", self._toggle_grayscale_selected, "Toggle grayscale on selected image"))
        tb.addWidget(btn("Front", self._bring_forward, "Bring selected forward"))
        tb.addWidget(btn("Back", self._send_backward, "Send selected backward"))
        tb.addWidget(sep())
        tb.addWidget(btn("Palette", self._extract_palette, "Extract dominant colors"))
        tb.addWidget(btn("Export", self._export, "Export canvas as PNG"))
        tb.addStretch()

        self.float_cb = QCheckBox("Float")
        self.float_cb.setToolTip(
            "Scale references when resizing the window (ideal for topmost overlay)"
        )
        self.float_cb.stateChanged.connect(self._on_float_toggled)
        tb.addWidget(self.float_cb)

        self.topmost_cb = QCheckBox("Topmost")
        self.topmost_cb.setToolTip("Keep window above other apps (enables Float mode)")
        self.topmost_cb.stateChanged.connect(self._on_topmost_toggled)
        tb.addWidget(self.topmost_cb)

        self.fullscreen_cb = QCheckBox("Fullscreen")
        self.fullscreen_cb.setToolTip("Toggle fullscreen")
        self.fullscreen_cb.stateChanged.connect(lambda s: self.toggle_fullscreen_cb(s == Qt.Checked))
        tb.addWidget(self.fullscreen_cb)

        tb.addWidget(sep())
        slot_label = QLabel("Slot:")
        slot_label.setStyleSheet("color: #94A3B8;")
        tb.addWidget(slot_label)
        slots_row = QHBoxLayout()
        slots_row.setSpacing(4)
        for i in range(1, 6):
            b = QPushButton(str(i))
            b.setFixedSize(32, 32)
            b.setToolTip(f"Load workspace layout slot {i}")
            b.clicked.connect(lambda _, slot=i: self._load_slot(slot))
            self._slot_buttons[i] = b
            slots_row.addWidget(b)
        tb.addLayout(slots_row)
        self._highlight_slot_button()

        tb.addWidget(btn("Save", self.save_now, "Save layout to current slot"))
        tb.addWidget(sep())
        tb.addWidget(
            btn(
                "Clear All",
                self._confirm_clear_all,
                "Remove all images from canvas",
                "background-color: #DC2626; border-color: #991B1B;",
            ),
        )
        tb.addWidget(sep())
        tb.addWidget(btn("Hide bar", self._toggle_toolbar, "Hide toolbar (`)"))
        return toolbar

    def _zoom_by(self, factor: float) -> None:
        self.view.scale(factor, factor)
        self.view._notify_zoom()

    def _reset_view(self) -> None:
        self.view.resetTransform()
        self.view._notify_zoom()

    def _zoom_to_selection(self) -> None:
        items = [i for i in self.scene.selectedItems() if isinstance(i, GraphicsPixmapItem)]
        if not items:
            return
        bounds = items[0].sceneBoundingRect()
        for item in items[1:]:
            bounds = bounds.united(item.sceneBoundingRect())
        if not bounds.isEmpty():
            self.view.fitInView(bounds, Qt.KeepAspectRatio)
            self.view._notify_zoom()

    def _highlight_slot_button(self) -> None:
        for i, b in self._slot_buttons.items():
            if i == self.current_slot:
                b.setStyleSheet("background-color: #7C3AED; border-color: #6D28D9;")
            else:
                b.setStyleSheet("")
        self._update_compact_slot_label()

    def set_autosave_enabled(self, enabled: bool) -> None:
        self._autosave_enabled = enabled
        if enabled:
            if not self._autosave_timer.isActive():
                self._autosave_timer.start(self._AUTOSAVE_INTERVAL_MS)
        else:
            self._autosave_timer.stop()

    def save_now(self) -> None:
        self._perform_autosave(manual=True)

    def _pixmap_items(self) -> list[GraphicsPixmapItem]:
        return [i for i in self.scene.items() if isinstance(i, GraphicsPixmapItem)]

    @staticmethod
    def _norm_path(path_str: str) -> str:
        try:
            return str(Path(path_str).resolve())
        except OSError:
            return str(Path(path_str))

    def _resolve_image_id(self, path_str: str, norm_path: str) -> int | None:
        for candidate in (path_str, norm_path):
            image_id = self.image_mgr.get_image_id_by_path(candidate)
            if image_id is not None:
                return int(image_id)
        return None

    def _add_item_from_path(self, path_str: str, x: float, y: float) -> GraphicsPixmapItem | None:
        try:
            pixmap = pil_to_qpixmap(Image.open(path_str))
            item = GraphicsPixmapItem(pixmap, path_str)
            item.image_id = self.image_mgr.get_image_id_by_path(path_str)
            item.setPos(x, y)
            self.scene.addItem(item)
            return item
        except Exception as exc:
            logger.warning("Could not open %s: %s", path_str, exc)
            return None

    def load_images(self, selected_images: list, replace: bool = True) -> int:
        paths = [str(p) for p in (selected_images or [])]
        if replace and not paths:
            self._load_slot(self.current_slot)
            self._fit_view()
            self._update_empty_hint()
            return 0

        if replace and paths:
            self._undo_stack.clear()
            self.scene.clear()

        existing_paths: set[str] = set()
        existing_ids: set[int] = set()
        for item in self._pixmap_items():
            existing_paths.add(self._norm_path(item.path))
            if item.image_id:
                existing_ids.add(int(item.image_id))

        x, y = 50, 50
        new_snaps: list[_ItemSnapshot] = []
        seen_paths: set[str] = set()
        seen_ids: set[int] = set()
        for path_str in paths:
            norm = self._norm_path(path_str)
            if norm in existing_paths or norm in seen_paths:
                continue
            image_id = self._resolve_image_id(path_str, norm)
            if image_id is not None and (image_id in existing_ids or image_id in seen_ids):
                continue
            new_snaps.append(_ItemSnapshot.from_path(path_str, x, y, image_id=image_id))
            seen_paths.add(norm)
            existing_paths.add(norm)
            if image_id is not None:
                seen_ids.add(image_id)
                existing_ids.add(image_id)
            x += 20
            y += 20

        # QUndoStack.push() calls redo() — do not add items to the scene before this.
        if new_snaps:
            self._undo_stack.push(AddItemsCommand(self, new_snaps))
        if new_snaps or (replace and paths):
            self._fit_view()
        self._update_empty_hint()
        return len(new_snaps)

    def append_paths_to_slot(self, slot_id: int, paths: list) -> int:
        """Merge images into a workspace slot on disk (skip duplicates)."""
        paths = [str(p) for p in (paths or []) if p]
        if not paths:
            return 0

        state = dict(self.ws_manager.load_state(slot_id) or {})
        existing_paths: set[str] = set()
        existing_ids: set[int] = set()
        max_z = 0
        anchor_x, anchor_y = 50.0, 50.0

        for image_id, s in state.items():
            path = s.get("file_path") or self.image_mgr.get_file_path_by_id(image_id)
            if path:
                existing_paths.add(self._norm_path(path))
            existing_ids.add(int(image_id))
            max_z = max(max_z, int(s.get("z_order", 0)))
            anchor_x = max(anchor_x, float(s.get("x", 50)) + 20)
            anchor_y = max(anchor_y, float(s.get("y", 50)) + 20)

        added = 0
        x, y = anchor_x, anchor_y
        seen_paths: set[str] = set()
        seen_ids: set[int] = set()

        for path_str in paths:
            if not Path(path_str).exists():
                continue
            norm = self._norm_path(path_str)
            if norm in existing_paths or norm in seen_paths:
                continue
            image_id = self._resolve_image_id(path_str, norm)
            if image_id is None:
                continue
            if image_id in existing_ids or image_id in seen_ids:
                continue

            max_z += 1
            state[image_id] = {
                "file_path": path_str,
                "x": x,
                "y": y,
                "scale": 1.0,
                "z_order": max_z,
                "flip_h": False,
                "flip_v": False,
                "opacity": 1.0,
                "grayscale": False,
            }
            seen_paths.add(norm)
            existing_paths.add(norm)
            seen_ids.add(image_id)
            existing_ids.add(image_id)
            added += 1
            x += 20
            y += 20

        if added:
            state_list = []
            for iid, s in state.items():
                entry = dict(s)
                entry["image_id"] = int(iid)
                state_list.append(entry)
            self.ws_manager.save_state(state_list, slot_id)
        return added

    def _load_slot(self, slot_id: int) -> None:
        self._loading_slot = True
        self._undo_stack.clear()
        self.current_slot = slot_id
        get_settings().set_workspace_slot(slot_id)
        self._highlight_slot_button()
        state = self.ws_manager.load_state(slot_id)
        self.scene.clear()

        for image_id, s in (state or {}).items():
            try:
                path = s.get("file_path") or self.image_mgr.get_file_path_by_id(image_id)
                if not path or not Path(path).exists():
                    continue
                pixmap = pil_to_qpixmap(Image.open(path))
                item = GraphicsPixmapItem(pixmap, path)
                item.image_id = image_id
                item.setPos(s["x"], s["y"])
                item.setScale(s["scale"])
                item.base_scale = s["scale"]
                item.setZValue(s["z_order"])
                item.setOpacity(float(s.get("opacity", 1.0)))
                item.set_flip(s.get("flip_h", False), s.get("flip_v", False))
                item.set_grayscale(s.get("grayscale", False))
                self.scene.addItem(item)
            except Exception as exc:
                logger.warning("Could not restore image_id %s: %s", image_id, exc)
        self._loading_slot = False
        self._update_empty_hint()

    def _perform_autosave(self, manual: bool = False) -> None:
        state = []
        for item in self._pixmap_items():
            image_id = item.image_id or self.image_mgr.get_image_id_by_path(item.path)
            if image_id is None:
                continue
            item.image_id = image_id
            state.append({
                "image_id": image_id,
                "file_path": item.path,
                "x": item.pos().x(),
                "y": item.pos().y(),
                "scale": item.scale(),
                "z_order": int(item.zValue()),
                "flip_h": item.flip_h,
                "flip_v": item.flip_v,
                "opacity": item.opacity(),
                "grayscale": item.grayscale,
            })
        try:
            self.ws_manager.save_state(state, self.current_slot)
            msg = f"Saved workspace slot {self.current_slot}"
            if self._status:
                self._status(msg, 4000)
            if manual and self._toast:
                self._toast(msg)
        except Exception as exc:
            logger.error("Autosave failed: %s", exc)

    def _confirm_clear_all(self) -> None:
        if QMessageBox.question(
            self,
            "Clear workspace",
            "Remove all images from the workspace canvas?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self._clear_all()

    def _clear_all(self) -> None:
        self._undo_stack.clear()
        self.scene.clear()
        try:
            self.ws_manager.save_state([], self.current_slot)
            if self._toast:
                self._toast(f"Cleared slot {self.current_slot}")
        except Exception as exc:
            logger.error("Clear save failed: %s", exc)
        self._update_empty_hint()

    def _fit_view(self) -> None:
        bounds = self.scene.itemsBoundingRect()
        if not bounds.isEmpty():
            self.view.fitInView(bounds, Qt.KeepAspectRatio)
            self.view._notify_zoom()

    def _selected_pixmap_items(self) -> list[GraphicsPixmapItem]:
        return [i for i in self.scene.selectedItems() if isinstance(i, GraphicsPixmapItem)]

    def _apply_scale_selected(self, factor: float, uniform: bool = False) -> None:
        items = self._selected_pixmap_items()
        if not items:
            return
        before = [snapshot_item(i) for i in items]
        for item in items:
            new_scale = item.scale() * factor
            if uniform and before:
                base = before[0].scale
                new_scale = base * factor
            item.setScale(new_scale)
            item.base_scale = item.scale()
        after = [snapshot_item(i) for i in items]
        self._undo_stack.push(TransformItemsCommand(self, items, before, after, text="Scale"))
        self._schedule_save()

    def _flip_selected(self, horizontal: bool = False, vertical: bool = False) -> None:
        items = self._selected_pixmap_items()
        if not items:
            return
        before = [snapshot_item(i) for i in items]
        for item in items:
            item.flip(horizontal, vertical)
        after = [snapshot_item(i) for i in items]
        self._undo_stack.push(TransformItemsCommand(self, items, before, after, text="Flip"))
        self._schedule_save()

    def _toggle_grayscale_selected(self) -> None:
        items = self._selected_pixmap_items()
        if not items:
            return
        before = [snapshot_item(i) for i in items]
        for item in items:
            item.toggle_grayscale()
        after = [snapshot_item(i) for i in items]
        self._undo_stack.push(TransformItemsCommand(self, items, before, after, text="Grayscale"))
        self._schedule_save()

    def _set_opacity_selected(self, opacity: float) -> None:
        items = self._selected_pixmap_items()
        if not items:
            return
        before = [snapshot_item(i) for i in items]
        for item in items:
            item.setOpacity(opacity)
        after = [snapshot_item(i) for i in items]
        self._undo_stack.push(TransformItemsCommand(self, items, before, after, text="Opacity"))
        self._schedule_save()

    def _bring_forward(self) -> None:
        items = self._selected_pixmap_items()
        if not items:
            return
        before = [snapshot_item(i) for i in items]
        max_z = max((i.zValue() for i in self._pixmap_items()), default=0)
        for item in items:
            item.setZValue(max_z + 1)
            max_z += 1
        after = [snapshot_item(i) for i in items]
        self._undo_stack.push(TransformItemsCommand(self, items, before, after, text="Z-order"))
        self._schedule_save()

    def _send_backward(self) -> None:
        items = self._selected_pixmap_items()
        if not items:
            return
        before = [snapshot_item(i) for i in items]
        min_z = min((i.zValue() for i in self._pixmap_items()), default=0)
        for item in items:
            item.setZValue(min_z - 1)
            min_z -= 1
        after = [snapshot_item(i) for i in items]
        self._undo_stack.push(TransformItemsCommand(self, items, before, after, text="Z-order"))
        self._schedule_save()

    def _toggle_lock_selected(self) -> None:
        items = self._selected_pixmap_items()
        if not items:
            return
        before = [snapshot_item(i) for i in items]
        for item in items:
            item.set_locked(not item._locked)
        after = [snapshot_item(i) for i in items]
        self._undo_stack.push(TransformItemsCommand(self, items, before, after, text="Lock"))
        self._schedule_save()

    def _delete_selected(self) -> None:
        items = self._selected_pixmap_items()
        if not items:
            return
        self._undo_stack.push(RemoveItemsCommand(self, items))

    def _show_in_gallery(self) -> None:
        items = self._selected_pixmap_items()
        if not items:
            return
        item = items[0]
        image_id = item.image_id or self.image_mgr.get_image_id_by_path(item.path)
        if image_id:
            self.show_in_gallery_request.emit(int(image_id))

    def _show_canvas_context_menu(self, pos) -> None:
        scene_pos = self.view.mapToScene(self.view.mapFromGlobal(self.view.mapToGlobal(pos)))
        item = self.scene.itemAt(scene_pos, self.view.transform())
        if isinstance(item, GraphicsPixmapItem) and not item.isSelected():
            self.scene.clearSelection()
            item.setSelected(True)

        menu = QMenu(self)
        menu.addAction("Show in gallery", self._show_in_gallery)
        menu.addSeparator()
        toolbar_label = "Compact bar" if self._toolbar.isVisible() else "Full toolbar"
        menu.addAction(toolbar_label, self._toggle_toolbar)
        float_label = "Disable float mode" if self.is_float_mode() else "Enable float mode"
        menu.addAction(float_label, lambda: self._set_float_mode(not self.is_float_mode()))
        menu.addSeparator()
        menu.addAction("Bring forward", self._bring_forward)
        menu.addAction("Send backward", self._send_backward)
        menu.addAction("Toggle lock", self._toggle_lock_selected)
        menu.addSeparator()

        opacity_menu = menu.addMenu("Opacity")
        for pct in (100, 75, 50, 25):
            opacity_menu.addAction(f"{pct}%").triggered.connect(
                lambda _, v=pct / 100.0: self._set_opacity_selected(v)
            )

        menu.addSeparator()
        menu.addAction("Flip horizontal", lambda: self._flip_selected(horizontal=True))
        menu.addAction("Flip vertical", lambda: self._flip_selected(vertical=True))
        menu.addAction("Toggle grayscale", self._toggle_grayscale_selected)
        menu.addAction("Delete", self._delete_selected)
        menu.exec_(self.view.mapToGlobal(pos))

    def _copy_palette_color(self, hex_color: str) -> None:
        QApplication.clipboard().setText(hex_color.upper())
        if self._toast:
            self._toast(f"Copied {hex_color.upper()}")

    def _extract_palette(self) -> None:
        items = self._selected_pixmap_items()
        if not items:
            return
        try:
            pil_img = Image.open(items[0].path).convert("RGB")
            pil_img.thumbnail((150, 150))
            quantized = pil_img.quantize(colors=6)
            raw_palette = quantized.getpalette() or []
            colors = [
                f"#{raw_palette[i]:02x}{raw_palette[i+1]:02x}{raw_palette[i+2]:02x}"
                for i in range(0, 18, 3)
            ]

            dialog = QDialog(self)
            dialog.setWindowTitle("Color Palette")
            layout = QVBoxLayout(dialog)
            hint = QLabel("Click a color to copy its hex code")
            hint.setStyleSheet("color: #94A3B8; font-size: 12px;")
            layout.addWidget(hint)

            for hex_color in colors:
                row_widget = QWidget()
                row_widget.setCursor(Qt.PointingHandCursor)
                row_widget.setToolTip("Click to copy")
                row = QHBoxLayout(row_widget)
                row.setContentsMargins(4, 4, 4, 4)
                swatch = QLabel()
                swatch.setFixedSize(30, 30)
                swatch.setStyleSheet(
                    f"background-color: {hex_color}; border: 1px solid #334155; border-radius: 4px;"
                )
                hex_label = QLabel(hex_color.upper())
                hex_label.setStyleSheet("color: #E2E8F0; font-weight: bold;")
                row.addWidget(swatch)
                row.addWidget(hex_label)
                row.addStretch()
                row_widget.mousePressEvent = lambda _event, c=hex_color: self._copy_palette_color(c)
                layout.addWidget(row_widget)
            dialog.exec_()
        except Exception as exc:
            logger.error("Palette extraction failed: %s", exc)

    def _export(self) -> None:
        rect = self.scene.itemsBoundingRect()
        if rect.isEmpty():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Workspace", "", "PNG Images (*.png)")
        if not path:
            return
        img = QImage(rect.size().toSize(), QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        painter = QPainter(img)
        self.scene.render(painter, target=QRectF(img.rect()), source=rect)
        painter.end()
        img.save(path)
        if self._toast:
            self._toast("Workspace exported")
