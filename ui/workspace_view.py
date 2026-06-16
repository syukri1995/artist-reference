"""
workspace_view.py — QGraphicsScene-based infinite canvas for viewing reference images.
"""
import logging
import hashlib
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, QMimeData
from PyQt5.QtGui import QImage, QPainter, QWheelEvent, QMouseEvent, QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QFrame, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget, QShortcut, QInputDialog, QActionGroup,
)
from PyQt5.QtGui import QKeySequence
from PIL import Image

from app_settings import get_settings
from managers.image_manager import ImageManager
from managers.workspace_manager import WorkspaceManager
from managers.tag_manager import TagManager
from ui.workspace_items import GraphicsPixmapItem, StickyNoteItem
from ui.workspace_layout import (
    grid_layout,
    horizontal_layout,
    vertical_layout,
    pack_layout,
    grouped_layout,
    sort_items,
)
from ui.workspace_undo import (
    AddItemsCommand,
    MoveItemsCommand,
    RemoveItemsCommand,
    TransformItemsCommand,
    _ItemSnapshot,
    create_undo_stack,
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
        self.setAcceptDrops(True)

    def set_workspace(self, ws) -> None:
        self._workspace = ws

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        if self._workspace:
            pos = self.mapToScene(event.pos())
            self._workspace._handle_drop(event.mimeData(), pos.x(), pos.y())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

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
        if event.key() == Qt.Key_V and event.modifiers() == Qt.ControlModifier:
            if self._workspace:
                self._workspace._handle_paste()
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
        self.tag_mgr = TagManager()
        self.current_slot = get_settings().get_workspace_slot()
        self.arrange_sort_by = "date"
        self._autosave_enabled = True
        self._slot_buttons: dict[int, QPushButton] = {}
        self._drag_starts: dict[int, object] = {}

        # Pre-initialize checkboxes to avoid AttributeErrors
        self.float_cb = QCheckBox()
        self.topmost_cb = QCheckBox()
        self.fullscreen_cb = QCheckBox()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(lambda *args: self._perform_autosave(manual=False))

        self._undo_stack = create_undo_stack(self)
        self._loading_slot = False
        self._snap_lines = []

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
        self._toolbar_restore_btn.clicked.connect(lambda *args: self._set_toolbar_visible(True))
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
            """
            <div align="center">
            <h2>Workspace is empty</h2>
            <p style="color: #94A3B8;">Add images from the gallery (double-click or Open Workspace)</p>
            <br>
            <table style="color: #64748B; font-size: 12px; margin: 0 auto; border-spacing: 10px;">
              <tr><td align="right"><b>Right-drag / Mid-drag</b></td><td>Pan canvas</td></tr>
              <tr><td align="right"><b>Scroll</b></td><td>Zoom canvas</td></tr>
              <tr><td align="right"><b>Ctrl+Scroll</b></td><td>Scale selected image</td></tr>
              <tr><td align="right"><b>Del / Backspace</b></td><td>Remove image</td></tr>
              <tr><td align="right"><b>Ctrl+Z</b></td><td>Undo</td></tr>
            </table>
            </div>
            """,
            canvas_wrap
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
        bar = QFrame()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(40)
        bar.setStyleSheet("background-color: #161D2F; border-bottom: 1px solid #252F44;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(12)

        menu_btn = QPushButton("Menu \u25be") # Triangle down
        menu_btn.setFixedSize(80, 28)
        menu_btn.setToolTip("Workspace options (`)")
        menu_btn.clicked.connect(self._show_workspace_menu)
        row.addWidget(menu_btn)

        self._compact_slot = QLabel()
        self._compact_slot.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 600;")
        row.addWidget(self._compact_slot)

        row.addStretch()

        gallery_btn = QPushButton("Library")
        gallery_btn.setFixedSize(80, 28)
        gallery_btn.clicked.connect(self.switch_to_gallery_callback)
        row.addWidget(gallery_btn)
        return bar

    def _update_compact_slot_label(self) -> None:
        if hasattr(self, "_compact_slot"):
            name = get_settings().get_workspace_slot_name(self.current_slot)
            self._compact_slot.setText(name)

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
            menu.addAction("Compact bar", lambda *args: self._set_toolbar_visible(False))
        elif self.width() >= self._COMPACT_WIDTH and not self.is_float_mode():
            menu.addAction("Full toolbar", lambda *args: self._set_toolbar_visible(True))

        undo_menu = menu.addMenu("Undo / redo")
        undo_menu.addAction("Undo", self._undo_stack.undo)
        undo_menu.addAction("Redo", self._undo_stack.redo)

        zoom_menu = menu.addMenu("Zoom")
        zoom_menu.addAction("Zoom in", lambda *args: self._zoom_by(1.25))
        zoom_menu.addAction("Zoom out", lambda *args: self._zoom_by(0.8))
        zoom_menu.addAction("Fit all", self._fit_view)
        zoom_menu.addAction("100%", self._reset_view)
        zoom_menu.addAction("Zoom to selection", self._zoom_to_selection)

        edit_menu = menu.addMenu("Edit selection")
        edit_menu.addAction("Flip horizontal", lambda *args: self._flip_selected(horizontal=True))
        edit_menu.addAction("Flip vertical", lambda *args: self._flip_selected(vertical=True))
        edit_menu.addAction("Toggle grayscale", self._toggle_grayscale_selected)
        edit_menu.addAction("Bring forward", self._bring_forward)
        edit_menu.addAction("Send backward", self._send_backward)
        edit_menu.addAction("Delete", self._delete_selected)

        arrange_menu = menu.addMenu("Arrange")
        arrange_menu.addAction("Grid", lambda *args: self._apply_auto_arrange("grid"))
        arrange_menu.addAction("Horizontal", lambda *args: self._apply_auto_arrange("horizontal"))
        arrange_menu.addAction("Vertical", lambda *args: self._apply_auto_arrange("vertical"))
        arrange_menu.addAction("Pack (Mosaic)", lambda *args: self._apply_auto_arrange("pack"))
        arrange_menu.addAction("By Group (Tags)", lambda *args: self._apply_auto_arrange("grouped"))
        arrange_menu.addSeparator()
        
        sort_menu = arrange_menu.addMenu("Sort by")
        date_act = sort_menu.addAction("Date Added")
        date_act.setCheckable(True)
        date_act.setChecked(self.arrange_sort_by == "date")
        date_act.triggered.connect(lambda *args: setattr(self, "arrange_sort_by", "date"))
        
        size_act = sort_menu.addAction("Size")
        size_act.setCheckable(True)
        size_act.setChecked(self.arrange_sort_by == "size")
        size_act.triggered.connect(lambda *args: setattr(self, "arrange_sort_by", "size"))

        menu.addAction("Extract palette", self._extract_palette)
        menu.addAction("Export PNG", self._export)
        menu.addAction("Save slot", self.save_now)
        menu.addSeparator()

        slot_menu = menu.addMenu(f"Workspace slot ({self.current_slot})")
        for i in range(1, 6):
            slot_menu.addAction(f"Slot {i}", lambda *args, s=i: self._load_slot(s))

        menu.addAction("Clear all", self._confirm_clear_all)
        menu.exec_(self._compact_bar.mapToGlobal(self._compact_bar.rect().bottomLeft()))

    def _add_note(self, x=None, y=None) -> None:
        if x is None or y is None:
            # Add to center of view
            center = self.view.mapToScene(self.view.viewport().rect().center())
            x, y = center.x(), center.y()
        
        snap = _ItemSnapshot.from_note("New Note", x, y)
        self._undo_stack.push(AddItemsCommand(self, [snap], text="Add note"))
        self._schedule_save()
        self._update_empty_hint()

    def _build_toolbar(self) -> QWidget:
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar.setFixedHeight(64)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(20, 0, 20, 0)
        tb.setSpacing(12)

        def sep() -> QFrame:
            f = QFrame()
            f.setFrameShape(QFrame.VLine)
            f.setStyleSheet("color: #252F44; margin: 16px 4px;")
            return f

        def btn(label: str, slot, tip: str = "", style: str = "", active: bool = False, large: bool = False) -> QPushButton:
            b = QPushButton(label)
            b.clicked.connect(slot)
            if tip:
                b.setToolTip(tip)
            if large:
                b.setStyleSheet("font-size: 18px; font-weight: bold;")
            if style:
                # Append to existing style if 'large' was set
                existing = b.styleSheet()
                b.setStyleSheet(existing + style)
            return b

        # Navigation
        tb.addWidget(btn("Library", self.switch_to_gallery_callback, "Return to Gallery"))
        tb.addWidget(sep())

        # History
        self._undo_btn = btn("Undo", self._undo_stack.undo, "Undo (Ctrl+Z)")
        self._redo_btn = btn("Redo", self._undo_stack.redo, "Redo (Ctrl+Y)")
        self._undo_stack.canUndoChanged.connect(self._undo_btn.setEnabled)
        self._undo_stack.canRedoChanged.connect(self._redo_btn.setEnabled)
        tb.addWidget(self._undo_btn)
        tb.addWidget(self._redo_btn)
        tb.addWidget(sep())

        # View Controls
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(4)
        z_in = btn("+", lambda *args: self._zoom_by(1.25), "Zoom In", large=True)
        z_out = btn("-", lambda *args: self._zoom_by(0.8), "Zoom Out", large=True)
        z_fit = btn("Fit", self._fit_view, "Fit All")
        for b in (z_in, z_out, z_fit):
            b.setFixedSize(44, 36)
            zoom_row.addWidget(b)
        tb.addLayout(zoom_row)
        tb.addWidget(sep())

        # Edit Selection
        edit_row = QHBoxLayout()
        edit_row.setSpacing(4)
        f_h = btn("Flip H", lambda *args: self._flip_selected(horizontal=True), "Flip Horizontal")
        f_v = btn("Flip V", lambda *args: self._flip_selected(vertical=True), "Flip Vertical")
        gray = btn("Gray", self._toggle_grayscale_selected, "Toggle Grayscale")
        for b in (f_h, f_v, gray):
            edit_row.addWidget(b)
        tb.addLayout(edit_row)
        
        # Arrange Menu
        arrange_btn = QPushButton("Arrange \u25be")
        arrange_btn.setFixedSize(100, 36)
        arrange_menu = QMenu(self)
        arrange_menu.addAction("Grid", lambda *args: self._apply_auto_arrange("grid"))
        arrange_menu.addAction("Horizontal", lambda *args: self._apply_auto_arrange("horizontal"))
        arrange_menu.addAction("Vertical", lambda *args: self._apply_auto_arrange("vertical"))
        arrange_menu.addAction("Pack (Mosaic)", lambda *args: self._apply_auto_arrange("pack"))
        arrange_menu.addAction("By Group (Tags)", lambda *args: self._apply_auto_arrange("grouped"))
        arrange_menu.addSeparator()
        
        sort_menu = arrange_menu.addMenu("Sort by")
        sort_group = QActionGroup(self)
        a_date = sort_menu.addAction("Date Added")
        a_date.setCheckable(True)
        a_date.setChecked(self.arrange_sort_by == "date")
        a_date.triggered.connect(lambda *args: setattr(self, "arrange_sort_by", "date"))
        sort_group.addAction(a_date)
        a_size = sort_menu.addAction("Size")
        a_size.setCheckable(True)
        a_size.setChecked(self.arrange_sort_by == "size")
        a_size.triggered.connect(lambda *args: setattr(self, "arrange_sort_by", "size"))
        sort_group.addAction(a_size)
        
        arrange_btn.setMenu(arrange_menu)
        tb.addWidget(arrange_btn)
        tb.addWidget(sep())

        # Palette & Export
        tb.addWidget(btn("Note", self._add_note, "Add Sticky Note"))
        tb.addWidget(btn("🎨", self._extract_palette, "Extract Palette"))
        tb.addWidget(btn("PNG", self._export, "Export Canvas"))
        
        tb.addStretch()

        # Workspace Modes
        modes_row = QHBoxLayout()
        modes_row.setSpacing(8)
        self.float_cb.setText("Float")
        self.float_cb.stateChanged.connect(self._on_float_toggled)
        self.topmost_cb.setText("Top")
        self.topmost_cb.stateChanged.connect(self._on_topmost_toggled)
        self.fullscreen_cb.setText("Full")
        self.fullscreen_cb.stateChanged.connect(lambda s: self.toggle_fullscreen_cb(s == Qt.Checked))
        modes_row.addWidget(self.float_cb)
        modes_row.addWidget(self.topmost_cb)
        modes_row.addWidget(self.fullscreen_cb)
        tb.addLayout(modes_row)
        tb.addWidget(sep())

        # Slots
        slot_label = QLabel("SLOTS")
        slot_label.setStyleSheet("color: #64748B; font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        tb.addWidget(slot_label)
        slots_row = QHBoxLayout()
        slots_row.setSpacing(4)
        for i in range(1, 6):
            b = QPushButton(str(i))
            b.setFixedSize(32, 32)
            b.clicked.connect(lambda _, slot=i: self._load_slot(slot))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, slot=i: self._show_slot_context_menu(pos, slot))
            self._slot_buttons[i] = b
            slots_row.addWidget(b)
        tb.addLayout(slots_row)
        self._highlight_slot_button()

        tb.addWidget(sep())
        tb.addWidget(btn("Save", self.save_now, "Save Layout", "background-color: #10B981; color: white;"))
        
        hide_btn = btn("×", self._toggle_toolbar, "Hide Toolbar")
        hide_btn.setFixedSize(32, 32)
        hide_btn.setStyleSheet("background: transparent; color: #64748B; border: none; font-size: 18px;")
        tb.addWidget(hide_btn)

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
        counts = self.ws_manager.get_slot_counts()
        for i, b in self._slot_buttons.items():
            name = get_settings().get_workspace_slot_name(i)
            count = counts.get(i, 0)
            b.setToolTip(f"{name} ({count} images)")
            if i == self.current_slot:
                b.setStyleSheet("background-color: #7C3AED; border-color: #6D28D9;")
            else:
                b.setStyleSheet("")
        self._update_compact_slot_label()

    def _show_slot_context_menu(self, pos, slot_id: int) -> None:
        menu = QMenu(self)
        menu.addAction("Rename slot...", lambda *args: self._rename_slot(slot_id))
        menu.addAction("Clear slot", lambda *args: self._confirm_clear_slot(slot_id))
        menu.exec_(self._slot_buttons[slot_id].mapToGlobal(pos))

    def _rename_slot(self, slot_id: int) -> None:
        current_name = get_settings().get_workspace_slot_name(slot_id)
        name, ok = QInputDialog.getText(self, "Rename Slot", "Slot Name:", text=current_name)
        if ok and name:
            get_settings().set_workspace_slot_name(slot_id, name)
            self._highlight_slot_button()
            if self._toast:
                self._toast(f"Renamed slot {slot_id} to '{name}'")

    def _confirm_clear_slot(self, slot_id: int) -> None:
        name = get_settings().get_workspace_slot_name(slot_id)
        if QMessageBox.question(
            self,
            "Clear slot",
            f"Remove all images from {name}?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        if slot_id == self.current_slot:
            self._clear_all()
        else:
            self.ws_manager.save_state([], slot_id)
            self._highlight_slot_button()
            if self._toast:
                self._toast(f"Cleared slot {slot_id}")

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
            with Image.open(path_str) as img:
                pixmap = pil_to_qpixmap(img)
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
        
        # Load Images
        state = self.ws_manager.load_state(slot_id)
        self.scene.clear()

        for image_id, s in (state or {}).items():
            try:
                path = s.get("file_path") or self.image_mgr.get_file_path_by_id(image_id)
                if not path or not Path(path).exists():
                    continue
                with Image.open(path) as img:
                    pixmap = pil_to_qpixmap(img)
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
        
        # Load Notes
        notes = self.ws_manager.load_notes(slot_id)
        for n in notes:
            item = StickyNoteItem(n["text"], n["x"], n["y"], n["width"], n["height"], n["color"])
            item.setZValue(n["z_order"])
            self.scene.addItem(item)

        self._loading_slot = False
        self._update_empty_hint()

    def _perform_autosave(self, manual: bool = False) -> None:
        image_state = []
        note_state = []
        for item in self.scene.items():
            if isinstance(item, GraphicsPixmapItem):
                image_id = item.image_id or self.image_mgr.get_image_id_by_path(item.path)
                if image_id is None:
                    continue
                item.image_id = image_id
                image_state.append({
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
            elif isinstance(item, StickyNoteItem):
                note_state.append({
                    "text": item.text_item.toPlainText(),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "width": item.rect().width(),
                    "height": item.rect().height(),
                    "z_order": int(item.zValue()),
                    "color": item._color.name(),
                })

        try:
            self.ws_manager.save_state(image_state, self.current_slot)
            self.ws_manager.save_notes(note_state, self.current_slot)
            msg = f"Saved workspace slot {self.current_slot}"
            if self._status:
                self._status(msg, 4000)
            if manual and self._toast:
                self._toast(msg)
        except Exception as exc:
            logger.error("Autosave failed: %s", exc)

    def _handle_item_move(self, moving_item, new_pos: QPointF) -> QPointF:
        """Handle snapping and draw alignment guides."""
        if not QApplication.mouseButtons() & Qt.LeftButton:
            self._clear_snap_lines()
            return new_pos

        snap_dist = 10.0 / self.view.transform().m11()
        rect = moving_item.sceneBoundingRect()
        # Offset to apply to new_pos
        dx, dy = 0.0, 0.0
        
        snapped_x, snapped_y = False, False
        lines = []

        # Reference points for the moving item
        m_left = new_pos.x()
        m_right = new_pos.x() + rect.width()
        m_center_x = new_pos.x() + rect.width() / 2.0
        m_top = new_pos.y()
        m_bottom = new_pos.y() + rect.height()
        m_center_y = new_pos.y() + rect.height() / 2.0

        for item in self.scene.items():
            if item == moving_item or not item.isVisible() or isinstance(item, (QGraphicsScene, QGraphicsView)):
                continue
            if not isinstance(item, (GraphicsPixmapItem, StickyNoteItem)):
                continue
                
            r = item.sceneBoundingRect()
            i_left, i_right, i_center_x = r.left(), r.right(), r.center().x()
            i_top, i_bottom, i_center_y = r.top(), r.bottom(), r.center().y()

            # Vertical snapping (X axis)
            if not snapped_x:
                for m_val, m_type in [(m_left, 'l'), (m_right, 'r'), (m_center_x, 'c')]:
                    for i_val in [i_left, i_right, i_center_x]:
                        if abs(m_val - i_val) < snap_dist:
                            dx = i_val - m_val
                            snapped_x = True
                            lines.append(('v', i_val))
                            break
                    if snapped_x: break

            # Horizontal snapping (Y axis)
            if not snapped_y:
                for m_val, m_type in [(m_top, 't'), (m_bottom, 'b'), (m_center_y, 'c')]:
                    for i_val in [i_top, i_bottom, i_center_y]:
                        if abs(m_val - i_val) < snap_dist:
                            dy = i_val - m_val
                            snapped_y = True
                            lines.append(('h', i_val))
                            break
                    if snapped_y: break
        
        self._draw_snap_lines(lines)
        return new_pos + QPointF(dx, dy)

    def _clear_snap_lines(self):
        from PyQt5.QtWidgets import QGraphicsLineItem
        for line in self._snap_lines:
            self.scene.removeItem(line)
        self._snap_lines.clear()

    def _draw_snap_lines(self, lines):
        self._clear_snap_lines()
        from PyQt5.QtWidgets import QGraphicsLineItem
        from PyQt5.QtGui import QPen, QColor
        
        pen = QPen(QColor("#8B5CF6"), 1, Qt.DashLine)
        pen.setCosmetic(True)
        
        scene_rect = self.scene.itemsBoundingRect()
        for type, val in lines:
            if type == 'v':
                l = QGraphicsLineItem(val, scene_rect.top() - 1000, val, scene_rect.bottom() + 1000)
            else:
                l = QGraphicsLineItem(scene_rect.left() - 1000, val, scene_rect.right() + 1000, val)
            l.setPen(pen)
            l.setZValue(10000)
            self.scene.addItem(l)
            self._snap_lines.append(l)

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
        menu.addAction("Add note", lambda: self._add_note(scene_pos.x(), scene_pos.y()))
        menu.addSeparator()
        menu.addAction("Show in gallery", self._show_in_gallery)
        menu.addSeparator()
        toolbar_label = "Compact bar" if self._toolbar.isVisible() else "Full toolbar"
        menu.addAction(toolbar_label, self._toggle_toolbar)
        float_label = "Disable float mode" if self.is_float_mode() else "Enable float mode"
        menu.addAction(float_label, lambda *args: self._set_float_mode(not self.is_float_mode()))
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
        menu.addAction("Flip horizontal", lambda *args: self._flip_selected(horizontal=True))
        menu.addAction("Flip vertical", lambda *args: self._flip_selected(vertical=True))
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
            with Image.open(items[0].path) as img:
                pil_img = img.convert("RGB")
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

    def _handle_drop(self, mime_data: QMimeData, x: float, y: float) -> None:
        if mime_data.hasUrls():
            paths = [u.toLocalFile() for u in mime_data.urls()]
            self._import_and_add_to_canvas(paths, x, y)
        elif mime_data.hasImage():
            # Handle image dropped from browser
            image = mime_data.imageData()
            if isinstance(image, QImage):
                temp_path = self.image_mgr.base_dir / "data" / "temp_drop.png"
                image.save(str(temp_path))
                self._import_and_add_to_canvas([str(temp_path)], x, y)

    def _handle_paste(self) -> None:
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        # Paste at center of view
        center = self.view.mapToScene(self.view.viewport().rect().center())
        self._handle_drop(mime_data, center.x(), center.y())

    def _import_and_add_to_canvas(self, paths: list[str], start_x: float, start_y: float) -> None:
        x, y = start_x, start_y
        new_snaps = []
        imported_count = 0

        for p in paths:
            if not Path(p).exists():
                continue
            
            # 1. Check if already in library by path or hash
            image_id = self.image_mgr.get_image_id_by_path(p)
            if image_id is None:
                # Calculate hash for duplicate check
                try:
                    with open(p, "rb") as f:
                        file_hash = hashlib.md5(f.read()).hexdigest()
                    image_id = self.image_mgr.get_image_id_by_hash(file_hash)
                except Exception:
                    pass

            # 2. If not in library, import it
            if image_id is None:
                if self.image_mgr.import_image(p):
                    image_id = self.image_mgr.get_image_id_by_path(p)
                    imported_count += 1
                else:
                    # Might be a duplicate name but different hash, or just failed
                    # Check if it's a duplicate by hash again in case import_image returned false but it's there
                    pass
            
            # 3. Add to canvas
            actual_path = self.image_mgr.get_file_path_by_id(image_id) if image_id else p
            if actual_path:
                new_snaps.append(_ItemSnapshot.from_path(actual_path, x, y, image_id=image_id))
                x += 20
                y += 20

        if new_snaps:
            self._undo_stack.push(AddItemsCommand(self, new_snaps))
            if imported_count > 0 and self._toast:
                self._toast(f"Imported {imported_count} new image(s) to library")
            self._schedule_save()
            self._update_empty_hint()

    def _apply_auto_arrange(self, mode: str) -> None:
        items = self._selected_pixmap_items() or self._pixmap_items()
        if not items:
            return
        
        # 1. Sort items
        sorted_list = sort_items(items, self.arrange_sort_by, self.image_mgr)
        
        # 2. Capture old positions
        old_positions = [QPointF(item.pos()) for item in sorted_list]
        
        # 3. Calculate new positions
        if mode == "grid":
            new_positions = grid_layout(sorted_list)
        elif mode == "horizontal":
            new_positions = horizontal_layout(sorted_list)
        elif mode == "vertical":
            new_positions = vertical_layout(sorted_list)
        elif mode == "pack":
            new_positions = pack_layout(sorted_list)
        elif mode == "grouped":
            new_positions = grouped_layout(sorted_list, self.tag_mgr)
        else:
            return

        # 4. Apply via Undo Command
        self._undo_stack.push(
            MoveItemsCommand(
                sorted_list,
                old_positions,
                new_positions,
                self._schedule_save,
                text=f"Arrange: {mode.title()}"
            )
        )
        self._fit_view()
        if self._toast:
            self._toast(f"Arranged {len(sorted_list)} images ({mode})")
