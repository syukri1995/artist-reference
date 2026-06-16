"""Undo/redo commands for the workspace canvas."""

from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QUndoCommand, QUndoStack

from ui.workspace_items import GraphicsPixmapItem, StickyNoteItem


class _ItemSnapshot:
    """Serializable state for one canvas item."""

    def __init__(self, item) -> None:
        self.type = "pixmap" if isinstance(item, GraphicsPixmapItem) else "note"
        self.pos = QPointF(item.pos())
        self.z = item.zValue()
        self.locked = item._locked
        
        if self.type == "pixmap":
            self.path = item.path
            self.image_id = item.image_id
            self.scale = item.scale()
            self.flip_h = item.flip_h
            self.flip_v = item.flip_v
            self.grayscale = item.grayscale
            self.opacity = item.opacity()
            self.base_scale = item.base_scale
        else:
            self.text = item.text_item.toPlainText()
            self.width = item.rect().width()
            self.height = item.rect().height()
            self.color = item._color.name()

    @classmethod
    def from_path(
        cls,
        path: str,
        x: float,
        y: float,
        *,
        image_id: int | None = None,
    ) -> "_ItemSnapshot":
        """Pending add — used before the item exists on the scene."""
        snap = cls.__new__(cls)
        snap.type = "pixmap"
        snap.path = path
        snap.image_id = image_id
        snap.pos = QPointF(x, y)
        snap.scale = 1.0
        snap.z = 0.0
        snap.flip_h = False
        snap.flip_v = False
        snap.grayscale = False
        snap.opacity = 1.0
        snap.base_scale = 1.0
        snap.locked = False
        return snap

    @classmethod
    def from_note(
        cls,
        text: str,
        x: float,
        y: float,
        width: float = 200,
        height: float = 150,
        color: str = "#FDE047"
    ) -> "_ItemSnapshot":
        snap = cls.__new__(cls)
        snap.type = "note"
        snap.text = text
        snap.pos = QPointF(x, y)
        snap.width = width
        snap.height = height
        snap.z = 0.0
        snap.color = color
        snap.locked = False
        return snap


def snapshot_item(item) -> _ItemSnapshot:
    return _ItemSnapshot(item)


def restore_item(scene, snap: _ItemSnapshot):
    if snap.type == "pixmap":
        from PIL import Image
        from utils_image import pil_to_qpixmap

        try:
            with Image.open(snap.path) as img:
                pixmap = pil_to_qpixmap(img)
        except Exception:
            return None
        item = GraphicsPixmapItem(pixmap, snap.path)
        item.image_id = snap.image_id
        item.setPos(snap.pos)
        item.setScale(snap.scale)
        item.base_scale = snap.base_scale
        item.setZValue(snap.z)
        item.setOpacity(snap.opacity)
        item.set_locked(snap.locked)
        item.set_flip(snap.flip_h, snap.flip_v)
        item.set_grayscale(getattr(snap, "grayscale", False))
        scene.addItem(item)
        return item
    else:
        item = StickyNoteItem(snap.text, snap.pos.x(), snap.pos.y(), snap.width, snap.height, snap.color)
        item.setZValue(snap.z)
        item.set_locked(snap.locked)
        scene.addItem(item)
        return item


class AddItemsCommand(QUndoCommand):
    def __init__(self, workspace, snapshots: list[_ItemSnapshot], text: str = "Add images") -> None:
        super().__init__(text)
        self._ws = workspace
        self._snaps = snapshots
        self._items: list[GraphicsPixmapItem] = []

    def undo(self) -> None:
        for item in self._items:
            self._ws.scene.removeItem(item)
        self._items.clear()
        self._ws._schedule_save()

    def redo(self) -> None:
        self._items.clear()
        for snap in self._snaps:
            item = restore_item(self._ws.scene, snap)
            if item:
                self._items.append(item)
        self._ws._schedule_save()


class RemoveItemsCommand(QUndoCommand):
    def __init__(self, workspace, items: list[GraphicsPixmapItem], text: str = "Remove images") -> None:
        super().__init__(text)
        self._ws = workspace
        self._snaps = [snapshot_item(i) for i in items]
        self._items = items

    def undo(self) -> None:
        for snap in self._snaps:
            restore_item(self._ws.scene, snap)
        self._ws._schedule_save()

    def redo(self) -> None:
        for item in self._items:
            self._ws.scene.removeItem(item)
        self._ws._schedule_save()


class MoveItemsCommand(QUndoCommand):
    def __init__(
        self,
        items: list[GraphicsPixmapItem],
        old_positions: list[QPointF],
        new_positions: list[QPointF],
        on_change,
        text: str = "Move",
    ) -> None:
        super().__init__(text)
        self._items = items
        self._old = old_positions
        self._new = new_positions
        self._on_change = on_change

    def _apply(self, positions: list[QPointF]) -> None:
        for item, pos in zip(self._items, positions):
            item.setPos(pos)
        self._on_change()

    def undo(self) -> None:
        self._apply(self._old)

    def redo(self) -> None:
        self._apply(self._new)


class TransformItemsCommand(QUndoCommand):
    """Undo scale, flip, opacity, or z-order changes."""

    def __init__(
        self,
        workspace,
        items: list[GraphicsPixmapItem],
        before: list[_ItemSnapshot],
        after: list[_ItemSnapshot],
        text: str = "Transform",
    ) -> None:
        super().__init__(text)
        self._ws = workspace
        self._items = items
        self._before = before
        self._after = after

    def _apply_snaps(self, snaps: list[_ItemSnapshot]) -> None:
        for item, snap in zip(self._items, snaps):
            item.setPos(snap.pos)
            item.setZValue(snap.z)
            item.set_locked(snap.locked)
            
            if snap.type == "pixmap":
                item.setScale(snap.scale)
                item.base_scale = snap.base_scale
                item.setOpacity(snap.opacity)
                item.set_flip(snap.flip_h, snap.flip_v)
                item.set_grayscale(getattr(snap, "grayscale", False))
            else:
                item.text_item.setPlainText(snap.text)
                item.setRect(0, 0, snap.width, snap.height)
                item.text_item.setTextWidth(snap.width - 10)
                item._color = QColor(snap.color)
                item.update_appearance()
        self._ws._schedule_save()

    def undo(self) -> None:
        self._apply_snaps(self._before)

    def redo(self) -> None:
        self._apply_snaps(self._after)


def create_undo_stack(workspace) -> QUndoStack:
    stack = QUndoStack(workspace)
    stack.setUndoLimit(50)
    return stack
