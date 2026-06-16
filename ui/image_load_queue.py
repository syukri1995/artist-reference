"""Queue-based parallel image loading with progress signals."""

from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path
from typing import Callable

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage
from PIL import Image

from utils_image import pil_to_qimage

logger = logging.getLogger(__name__)

# Parallel workers — local thumbs decode fast; network previews benefit most.
DEFAULT_WORKER_COUNT = 6
_FAST_RESAMPLE = Image.Resampling.BILINEAR


def image_from_file(
    file_path: str,
    thumbnail_path: str | None = None,
    max_size: tuple[int, int] = (300, 300),
    *,
    preview_only: bool = False,
) -> QImage | None:
    """Decode an image file to QImage (safe to call off the UI thread).

    When preview_only is True, only the thumbnail path is used — never the full image file.
    """
    try:
        if preview_only:
            if not thumbnail_path or not Path(thumbnail_path).exists():
                return None
            src = thumbnail_path
        else:
            src = file_path
            if thumbnail_path and Path(thumbnail_path).exists():
                src = thumbnail_path
        if not Path(src).exists():
            return None
        with Image.open(src) as img:
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            img.thumbnail(max_size, _FAST_RESAMPLE)
            return pil_to_qimage(img)
    except Exception as exc:
        logger.debug("image_from_file %s: %s", file_path, exc)
        return None


def image_from_bytes(data: bytes, max_size: tuple[int, int] = (300, 300)) -> QImage | None:
    try:
        import io
        with Image.open(io.BytesIO(data)) as img:
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            img.thumbnail(max_size, _FAST_RESAMPLE)
            return pil_to_qimage(img)
    except Exception as exc:
        logger.debug("image_from_bytes: %s", exc)
        return None


class _QueueItem:
    __slots__ = ("generation", "key", "loader")

    def __init__(self, generation: int, key: str, loader: Callable[[], QImage | None]) -> None:
        self.generation = generation
        self.key = key
        self.loader = loader


class ImageLoadQueue(QObject):
    """
    FIFO image load queue processed by multiple background threads.
    Emits per-image results and aggregate progress for UI indicators.
    """

    image_ready = pyqtSignal(str, object, int)  # key, QPixmap|None, generation
    progress = pyqtSignal(int, int, int)  # done, total, generation
    queue_empty = pyqtSignal(int)  # generation

    def __init__(self, parent=None, worker_count: int = DEFAULT_WORKER_COUNT) -> None:
        super().__init__(parent)
        self._work_q: queue.Queue = queue.Queue()
        self._total = 0
        self._done = 0
        self._generation = 0
        self._lock = threading.Lock()
        self._workers: list[_ImageLoadWorker] = []
        for _ in range(max(1, worker_count)):
            worker = _ImageLoadWorker(self._work_q)
            worker.result.connect(self._on_result)
            worker.start()
            self._workers.append(worker)

    @property
    def generation(self) -> int:
        return self._generation

    def cancel_all(self) -> None:
        """Invalidate pending work and reset counters."""
        with self._lock:
            self._generation += 1
            self._total = 0
            self._done = 0
            while True:
                try:
                    self._work_q.get_nowait()
                except queue.Empty:
                    break

    def enqueue_file(
        self,
        key: str,
        file_path: str,
        thumbnail_path: str | None = None,
        max_size: tuple[int, int] = (300, 300),
        *,
        preview_only: bool = False,
    ) -> None:
        path, thumb, size, po = file_path, thumbnail_path, max_size, preview_only

        def loader() -> QImage | None:
            return image_from_file(path, thumb, size, preview_only=po)

        self._enqueue(key, loader)

    def enqueue_bytes(self, key: str, data: bytes, max_size: tuple[int, int] = (300, 300)) -> None:
        def loader() -> QImage | None:
            return image_from_bytes(data, max_size)

        self._enqueue(key, loader)

    def enqueue_callable(self, key: str, loader: Callable[[], QImage | None]) -> None:
        self._enqueue(key, loader)

    def _enqueue(self, key: str, loader: Callable[[], QImage | None]) -> None:
        with self._lock:
            gen = self._generation
            self._total += 1
        self._work_q.put(_QueueItem(gen, key, loader))

    def _on_result(self, key: str, img: object, generation: int) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._done += 1
            done, total, _gen = self._done, self._total, self._generation
        
        pixmap = None
        if isinstance(img, QImage):
            pixmap = QPixmap.fromImage(img)
            
        self.image_ready.emit(key, pixmap, generation)
        self.progress.emit(done, total, generation)
        if done >= total:
            self.queue_empty.emit(generation)


class _ImageLoadWorker(QThread):
    result = pyqtSignal(str, object, int)

    def __init__(self, work_q: queue.Queue) -> None:
        super().__init__()
        self._work_q = work_q

    def run(self) -> None:
        while not self.isInterruptionRequested():
            try:
                item = self._work_q.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is None:
                continue
            try:
                img = item.loader()
            except Exception as exc:
                logger.debug("Image load %s failed: %s", item.key, exc)
                img = None
            self.result.emit(item.key, img, item.generation)
