"""Non-blocking toast notifications."""

from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class ToastOverlay(QWidget):
    """Floating toast host; parent should be the main window."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(
            "background-color: #1E293B; color: #E2E8F0; "
            "border: 1px solid #7C3AED; border-radius: 8px; "
            "padding: 12px 20px; font-size: 13px;"
        )
        self._label.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hide)
        self.hide()

    def show_message(self, text: str, duration_ms: int = 3000) -> None:
        if self.parent():
            self.setGeometry(self.parent().rect())
        self._label.setText(text)
        self._label.adjustSize()
        margin = 24
        w = min(self._label.sizeHint().width() + 40, max(280, self.width() - margin * 2))
        h = self._label.sizeHint().height() + 24
        x = (self.width() - w) // 2
        y = self.height() - h - margin - 40
        self._label.setGeometry(x, y, w, h)
        self._label.show()
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def _hide(self) -> None:
        self._label.hide()
        self.hide()
