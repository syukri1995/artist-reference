from PyQt5.QtGui import QImage, QPixmap

def pil_to_qimage(img):
    """Convert PIL Image to QImage (safe for background threads)."""
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    # QImage(data, ...) does not copy data; we must ensure QImage is copied 
    # if the data/img reference is lost.
    qim = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
    return qim.copy() # copy() makes it safe to discard original PIL image data

def pil_to_qpixmap(img):
    """Convert PIL Image to QPixmap (UI thread only)."""
    qim = pil_to_qimage(img)
    return QPixmap.fromImage(qim)
