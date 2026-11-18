"""Editable image and non-destructive annotation history in physical pixels."""
from dataclasses import dataclass, field
import math

from PyQt5.QtCore import QObject, pyqtSignal, QPointF, QRect, QRectF, Qt
from PyQt5.QtGui import QImage, QPainter, QPen, QColor, QPolygonF, QFont, QTransform


@dataclass
class Mark:
    tool: str
    points: list
    color: str = '#ed4141'
    width: int = 3
    text: str = ''


def draw_mark(image, mark):
    if not mark.points:
        return
    a, b = mark.points[0], mark.points[-1]
    rect = QRectF(a, b).normalized()
    if mark.tool in ('mosaic', 'blur'):
        region = rect.toAlignedRect().intersected(image.rect())
        if region.isEmpty():
            return
        # Apply mosaic in image space so zoom never changes the export.
        patch = image.copy(region).scaled(max(1, region.width() // 14),
            max(1, region.height() // 14), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        patch = patch.scaled(region.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation)
        if mark.tool == 'blur':
            import numpy as np
            import cv2
            source = image.copy(region).convertToFormat(QImage.Format_RGBA8888)
            ptr = source.bits()
            ptr.setsize(source.byteCount())
            pixels = np.frombuffer(ptr,np.uint8).reshape(source.height(),source.width(),4)
            blurred = cv2.GaussianBlur(pixels,(0,0),max(2,mark.width))
            patch = QImage(blurred.data,source.width(),source.height(),source.width()*4,QImage.Format_RGBA8888).copy()
        painter = QPainter(image)
        painter.drawImage(region.topLeft(), patch)
        painter.end()
        return
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(mark.color), mark.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if mark.tool == 'rect':
        painter.drawRect(rect)
    elif mark.tool == 'ellipse':
        painter.drawEllipse(rect)
    elif mark.tool in ('line', 'arrow'):
        painter.drawLine(a, b)
        if mark.tool == 'arrow' and a != b:
            angle = math.atan2(b.y() - a.y(), b.x() - a.x())
            length = max(14, mark.width * 4)
            painter.setBrush(QColor(mark.color))
            painter.drawPolygon(QPolygonF([b, QPointF(b.x() - length * math.cos(angle - .45),
                b.y() - length * math.sin(angle - .45)), QPointF(b.x() - length * math.cos(angle + .45),
                b.y() - length * math.sin(angle + .45))]))
    elif mark.tool == 'pen':
        if len(mark.points) == 1:
            painter.drawPoint(a)
        else:
            painter.drawPolyline(QPolygonF(mark.points))
    elif mark.tool == 'highlight':
        color = QColor(mark.color)
        color.setAlpha(85)
        painter.fillRect(rect,color)
    elif mark.tool == 'eraser':
        painter.fillRect(rect, Qt.white)
    elif mark.tool == 'text':
        font = QFont('Microsoft YaHei')
        font.setPixelSize(max(16, mark.width * 6))
        painter.setFont(font)
        painter.drawText(QRectF(a.x(), a.y(), max(100, image.width() - a.x()),
            max(100, image.height() - a.y())), Qt.TextWordWrap, mark.text)
    painter.end()


class ImageDocument(QObject):
    changed = pyqtSignal()

    def __init__(self, image):
        super().__init__()
        if image.isNull():
            raise ValueError('图片无效')
        self.base = image.copy()
        self.base.setDevicePixelRatio(1)
        self.marks = []
        self.past = []
        self.future = []
        self._cache = None

    def _checkpoint(self):
        self.past.append((self.base, list(self.marks)))
        self.past = self.past[-30:]
        self.future.clear()

    def _changed(self):
        self._cache = None
        self.changed.emit()

    def render(self):
        if self._cache is None:
            self._cache = self.base.copy()
            for mark in self.marks:
                draw_mark(self._cache, mark)
        return QImage(self._cache)

    def add(self, mark):
        self._checkpoint()
        if mark.tool == 'eraser':
            region=QRectF(mark.points[0],mark.points[-1]).normalized()
            self.marks=[item for item in self.marks if not region.intersects(
                QRectF(item.points[0],item.points[-1]).normalized().adjusted(-item.width,-item.width,item.width,item.width))]
            self._changed()
            return
        self.marks.append(mark)
        self._changed()

    def undo(self):
        if self.past:
            self.future.append((self.base, list(self.marks)))
            self.base, self.marks = self.past.pop()
            self._changed()

    def redo(self):
        if self.future:
            self.past.append((self.base, list(self.marks)))
            self.base, self.marks = self.future.pop()
            self._changed()

    def replace(self, image):
        if image.isNull():
            return
        self._checkpoint()
        self.base = image.copy()
        self.base.setDevicePixelRatio(1)
        self.marks = []
        self._changed()

    def crop(self, region):
        region = region.intersected(self.base.rect())
        if region.width() >= 2 and region.height() >= 2:
            self.replace(self.render().copy(region))

    def rotate(self, degrees=90):
        self.replace(self.render().transformed(QTransform().rotate(degrees)))

    def mirror(self, horizontal=True):
        self.replace(self.render().mirrored(horizontal, not horizontal))

    def reset(self):
        if self.marks:
            self._checkpoint()
            self.marks = []
            self._changed()
