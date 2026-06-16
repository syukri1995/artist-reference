"""Loading spinner and progress helpers for async image loads."""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget


class LoadingSpinner(QWidget):
    """Small circular indeterminate spinner."""

    def __init__(self, size: int = 36, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self._angle = 0
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def _tick(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start(50)
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#8B5CF6")) # Match TOKENS['accent']
        pen.setWidth(3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        margin = 4
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        painter.drawArc(rect, -self._angle * 16, 270 * 16)
        painter.end()


class LoadingStatusBar(QWidget):
    """Spinner + text + optional determinate progress."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.spinner = LoadingSpinner(22)
        row.addWidget(self.spinner)
        self.label = QLabel("")
        self.label.setStyleSheet("color: #94A3B8; font-size: 12px;")
        row.addWidget(self.label, stretch=1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(140)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(8)
        self.progress.hide()
        row.addWidget(self.progress)
        self.hide()

    def show_busy(self, message: str, total: int = 0) -> None:
        self.label.setText(message)
        self.spinner.start()
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(0)
            self.progress.show()
        else:
            self.progress.hide()
        self.show()

    def set_progress(self, done: int, total: int, message: str | None = None) -> None:
        if message:
            self.label.setText(message)
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(min(done, total))
            self.progress.show()
        self.spinner.start()
        self.show()

    def hide_idle(self) -> None:
        self.spinner.stop()
        self.progress.hide()
        self.hide()
