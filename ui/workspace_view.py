"""
workspace_view.py — QGraphicsScene-based infinite canvas for viewing reference images.

Controls:
  - Left-click drag: move selected image
  - Right/Middle-click drag: pan the canvas
  - Scroll wheel: zoom canvas
  - Ctrl + Scroll: scale selected image(s)
  - Delete / Backspace: remove selected image(s)
"""
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QImage, QPainter, QTransform, QWheelEvent, QMouseEvent, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QGraphicsItem, QGraphicsPixmapItem,
    QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)
from PIL import Image

from managers.workspace_manager import WorkspaceManager
from utils_image import pil_to_qpixmap


# ---------------------------------------------------------------------------
# Graphics item
# ---------------------------------------------------------------------------

class GraphicsPixmapItem(QGraphicsPixmapItem):
    """A movable, selectable pixmap item that tracks flip state."""

    def __init__(self, pixmap: QPixmap, path: str) -> None:
        super().__init__(pixmap)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.path = path
        self.flip_h = False
        self.flip_v = False
        self.base_scale = 1.0

    def flip(self, horizontal: bool = False, vertical: bool = False) -> None:
        if horizontal:
            self.flip_h = not self.flip_h
        if vertical:
            self.flip_v = not self.flip_v
        t = QTransform()
        t.scale(-1 if self.flip_h else 1, -1 if self.flip_v else 1)
        self.setTransform(t)


# ---------------------------------------------------------------------------
# Canvas view
# ---------------------------------------------------------------------------

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
        self._is_panning = False
        self._pan_start_pos = None

    # --- zoom -----------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if event.modifiers() == Qt.ControlModifier:
            # Scale selected items instead of panning
            factor = 1.1 if delta > 0 else 0.9
            for item in self.scene().selectedItems():
                item.setScale(item.scale() * factor)
                item.base_scale = item.scale()
            return

        zoom = 1.25 if delta > 0 else 1 / 1.25
        self.scale(zoom, zoom)

    # --- pan ------------------------------------------------------------

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

    # --- keyboard -------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in self.scene().selectedItems():
                self.scene().removeItem(item)
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Workspace view
# ---------------------------------------------------------------------------

class WorkspaceView(QWidget):
    """Main workspace panel: toolbar + infinite canvas."""

    _AUTOSAVE_INTERVAL_MS = 120_000  # 2 minutes

    def __init__(self, master, switch_to_gallery_callback, toggle_topmost_cb, toggle_fullscreen_cb) -> None:
        super().__init__(master)
        self.switch_to_gallery_callback = switch_to_gallery_callback
        self.toggle_topmost_cb = toggle_topmost_cb
        self.toggle_fullscreen_cb = toggle_fullscreen_cb
        self.ws_manager = WorkspaceManager()
        self.current_slot = 1

        self._setup_ui()

        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._perform_autosave)
        self._autosave_timer.start(self._AUTOSAVE_INTERVAL_MS)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_toolbar())

        self.scene = QGraphicsScene()
        self.view = ExtendedGraphicsView(self.scene)
        layout.addWidget(self.view)

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #1E293B;")
        toolbar.setFixedHeight(56)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 4, 16, 4)

        def btn(label: str, slot, style: str = "") -> QPushButton:
            b = QPushButton(label)
            b.clicked.connect(slot)
            if style:
                b.setStyleSheet(style)
            return b

        tb.addWidget(btn("← Gallery",       self.switch_to_gallery_callback))
        tb.addWidget(btn("Zoom In",          lambda: self.view.scale(1.25, 1.25)))
        tb.addWidget(btn("Zoom Out",         lambda: self.view.scale(0.8, 0.8)))
        tb.addWidget(btn("Fit View",         self._fit_view))
        tb.addWidget(btn("Flip H",           lambda: self._flip_selected(horizontal=True)))
        tb.addWidget(btn("Flip V",           lambda: self._flip_selected(vertical=True)))
        tb.addWidget(btn("🎨 Palette",       self._extract_palette))
        tb.addWidget(btn("💾 Export",        self._export))
        tb.addWidget(btn("🗑 Clear All",     self._clear_all,
                         "background-color: #DC2626; border-color: #991B1B;"))
        tb.addStretch()

        self.topmost_cb = QCheckBox("Topmost")
        self.topmost_cb.stateChanged.connect(lambda s: self.toggle_topmost_cb(s == Qt.Checked))
        tb.addWidget(self.topmost_cb)

        self.fullscreen_cb = QCheckBox("Fullscreen")
        self.fullscreen_cb.stateChanged.connect(lambda s: self.toggle_fullscreen_cb(s == Qt.Checked))
        tb.addWidget(self.fullscreen_cb)

        # Slot buttons (1-5)
        slots_row = QHBoxLayout()
        slots_row.setSpacing(4)
        for i in range(1, 6):
            b = QPushButton(str(i))
            b.setFixedSize(30, 30)
            b.clicked.connect(lambda _, slot=i: self._load_slot(slot))
            slots_row.addWidget(b)
        tb.addLayout(slots_row)

        tb.addWidget(btn("Save",  self._perform_autosave))

        return toolbar

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_images(self, selected_images: list, replace: bool = True) -> None:
        """Load saved slot state, then append any newly selected images."""
        self._load_slot(self.current_slot)

        existing = {item.path for item in self.scene.items() if isinstance(item, GraphicsPixmapItem)}
        x, y = 50, 50
        for path in selected_images:
            path_str = str(path)
            if path_str in existing:
                continue
            try:
                pixmap = pil_to_qpixmap(Image.open(path_str))
                item = GraphicsPixmapItem(pixmap, path_str)
                item.setPos(x, y)
                self.scene.addItem(item)
                x += 20
                y += 20
            except Exception as exc:
                print(f"WorkspaceView: could not open {path}: {exc}")

    # ------------------------------------------------------------------
    # Slot management
    # ------------------------------------------------------------------

    def _load_slot(self, slot_id: int) -> None:
        self.current_slot = slot_id
        state = self.ws_manager.load_state(slot_id)
        self._clear_all()

        for path, s in (state or {}).items():
            try:
                if not Path(path).exists():
                    continue
                pixmap = pil_to_qpixmap(Image.open(path))
                item = GraphicsPixmapItem(pixmap, path)
                item.setPos(s['x'], s['y'])
                item.setScale(s['scale'])
                item.base_scale = s['scale']
                item.setZValue(s['z_order'])
                if s.get('flip_h') or s.get('flip_v'):
                    item.flip(s.get('flip_h', False), s.get('flip_v', False))
                self.scene.addItem(item)
            except Exception as exc:
                print(f"WorkspaceView: could not restore {path}: {exc}")

        self._fit_view()

    def _perform_autosave(self) -> None:
        state = [
            {
                "file_path": item.path,
                "x": item.pos().x(),
                "y": item.pos().y(),
                "scale": item.base_scale,
                "z_order": int(item.zValue()),
                "flip_h": item.flip_h,
                "flip_v": item.flip_v,
            }
            for item in self.scene.items()
            if isinstance(item, GraphicsPixmapItem)
        ]
        try:
            self.ws_manager.save_state(state, self.current_slot)
        except Exception as exc:
            print(f"WorkspaceView: autosave failed: {exc}")

    # ------------------------------------------------------------------
    # Canvas helpers
    # ------------------------------------------------------------------

    def _clear_all(self) -> None:
        self.scene.clear()

    def _fit_view(self) -> None:
        bounds = self.scene.itemsBoundingRect()
        if not bounds.isEmpty():
            self.view.fitInView(bounds, Qt.KeepAspectRatio)

    def _flip_selected(self, horizontal: bool = False, vertical: bool = False) -> None:
        for item in self.scene.selectedItems():
            if isinstance(item, GraphicsPixmapItem):
                item.flip(horizontal, vertical)

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _extract_palette(self) -> None:
        items = self.scene.selectedItems()
        if not items or not isinstance(items[0], GraphicsPixmapItem):
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
            for hex_color in colors:
                row = QHBoxLayout()
                swatch = QLabel()
                swatch.setFixedSize(30, 30)
                swatch.setStyleSheet(f"background-color: {hex_color}; border-radius: 4px;")
                row.addWidget(swatch)
                row.addWidget(QLabel(hex_color.upper()))
                layout.addLayout(row)
            dialog.exec_()
        except Exception as exc:
            print(f"WorkspaceView: palette extraction failed: {exc}")

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
