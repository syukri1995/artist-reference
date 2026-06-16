"""Graphics items for the workspace canvas."""

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QImage, QPixmap, QTransform, QColor, QFont, QPen, QBrush
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsTextItem


class StickyNoteItem(QGraphicsRectItem):
    """A resizable, colored text box for the workspace canvas."""

    def __init__(self, text: str = "New Note", x: float = 0, y: float = 0, width: float = 200, height: float = 150, color: str = "#FDE047") -> None:
        super().__init__(0, 0, width, height)
        self.setPos(x, y)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self._color = QColor(color)
        self._locked = False
        
        # Text item
        self.text_item = QGraphicsTextItem(text, self)
        self.text_item.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.text_item.setPos(5, 5)
        self.text_item.setTextWidth(width - 10)
        
        font = QFont("Segoe UI", 12)
        self.text_item.setFont(font)
        
        self.update_appearance()

    def update_appearance(self) -> None:
        self.setBrush(QBrush(self._color))
        # Subtle border
        self.setPen(QPen(self._color.darker(120), 1))
        self.text_item.setDefaultTextColor(Qt.black if self._color.lightness() > 128 else Qt.white)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        if locked:
            self.setFlags(self.flags() & ~QGraphicsItem.ItemIsMovable)
            self.text_item.setTextInteractionFlags(Qt.NoTextInteraction)
        else:
            self.setFlags(self.flags() | QGraphicsItem.ItemIsMovable)
            self.text_item.setTextInteractionFlags(Qt.TextEditorInteraction)

    def paint(self, painter, option, widget) -> None:
        # Custom paint to handle selection state better
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor("#8B5CF6"), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.rect())

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            ws = getattr(self.scene(), "_workspace", None)
            if ws and hasattr(ws, "_handle_item_move"):
                return ws._handle_item_move(self, value)
        return super().itemChange(change, value)


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
