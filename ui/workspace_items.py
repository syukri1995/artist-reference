"""Graphics items for the workspace canvas."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap, QTransform
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsPixmapItem


class GraphicsPixmapItem(QGraphicsPixmapItem):
    """A movable, selectable pixmap item that tracks flip and grayscale state."""

    def __init__(self, pixmap, path: str) -> None:
        super().__init__(pixmap)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.path = path
        self.image_id = None
        self.base_pixmap = pixmap
        self.flip_h = False
        self.flip_v = False
        self.grayscale = False
        self.base_scale = 1.0
        self._locked = False

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        if locked:
            self.setFlags(self.flags() & ~QGraphicsItem.ItemIsMovable)
        else:
            self.setFlags(
                self.flags()
                | QGraphicsItem.ItemIsMovable
            )

    def _refresh_pixmap(self) -> None:
        pm = self.base_pixmap
        if self.grayscale:
            gray = pm.toImage().convertToFormat(QImage.Format_Grayscale8)
            pm = QPixmap.fromImage(gray)
        t = QTransform()
        t.scale(-1 if self.flip_h else 1, -1 if self.flip_v else 1)
        self.setPixmap(pm.transformed(t, Qt.SmoothTransformation))

    def set_flip(self, flip_h: bool, flip_v: bool) -> None:
        self.flip_h = flip_h
        self.flip_v = flip_v
        self._refresh_pixmap()

    def set_grayscale(self, grayscale: bool) -> None:
        self.grayscale = grayscale
        self._refresh_pixmap()

    def flip(self, horizontal: bool = False, vertical: bool = False) -> None:
        if horizontal:
            self.flip_h = not self.flip_h
        if vertical:
            self.flip_v = not self.flip_v
        self._refresh_pixmap()

    def toggle_grayscale(self) -> None:
        self.set_grayscale(not self.grayscale)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            modifiers = event.modifiers()
            if not (modifiers & (Qt.ControlModifier | Qt.ShiftModifier)):
                self.scene().clearSelection()
            self.setSelected(True)
            ws = getattr(self.scene(), "_workspace", None)
            if ws:
                ws._begin_item_drag(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        ws = getattr(self.scene(), "_workspace", None)
        if ws:
            ws._end_item_drag(self)
