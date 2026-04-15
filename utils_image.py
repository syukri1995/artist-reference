from PyQt5.QtGui import QImage, QPixmap

def pil_to_qpixmap(img):
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    # Need to keep a reference to data to avoid GC before QImage is rendered
    qim = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
    # The QImage constructor from raw data doesn't copy the data.
    # But QPixmap.fromImage(qim) will create a deep copy, making it safe to discard `img` and `data`.
    return QPixmap.fromImage(qim)
