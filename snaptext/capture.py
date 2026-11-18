"""Adjustable capture selection, window detection, magnifier and pixel control."""
import ctypes
import sys
from ctypes import wintypes
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QCursor
from PyQt5.QtWidgets import QWidget, QToolBar, QApplication


class CaptureOverlay(QWidget):
    completed = pyqtSignal(object, object, str)
    cancelled = pyqtSignal()
    history = []

    def __init__(self, screen, auto_detect=True, magnifier=True):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.screen_geometry = screen.geometry()
        self.snapshot = screen.grabWindow(0)
        self.setGeometry(self.screen_geometry)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.cursor = self.mapFromGlobal(QCursor.pos())
        self.selection = QRect()
        self.has_selection = False
        self.dragging = False
        self.detect = auto_detect
        self.magnifier = magnifier
        self.windows = self.window_rects()
        self.toolbar = QToolBar(self)
        self.toolbar.setStyleSheet('QToolBar {background:white; border:1px solid #2878ed; padding:4px;} QToolButton {padding:6px;}')
        for text, mode in [('复制 Enter', 'copy'), ('贴图 F3', 'pin'), ('识字', 'ocr'), ('取消 Esc', 'cancel')]:
            self.toolbar.addAction(text, lambda checked=False, action=mode: self.finish(action))
        self.toolbar.hide()
        self.history_index = len(self.history)

    def window_rects(self):
        rectangles = []
        self.control_regions={}
        if sys.platform != 'win32' or not self.detect:
            return rectangles
        user = ctypes.WinDLL('user32')
        ratio = self.snapshot.width() / max(1, self.width())
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, param):
            if user.IsWindowVisible(hwnd):
                rect = wintypes.RECT()
                user.GetWindowRect(hwnd, ctypes.byref(rect))
                region = QRect(round(rect.left / ratio) - self.x(), round(rect.top / ratio) - self.y(),
                    round((rect.right - rect.left) / ratio), round((rect.bottom - rect.top) / ratio)).intersected(self.rect())
                if region.width() > 40 and region.height() > 30:
                    rectangles.append(region)
                    children=[]
                    @ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
                    def child_callback(child,param):
                        if user.IsWindowVisible(child):
                            cr=wintypes.RECT()
                            user.GetWindowRect(child,ctypes.byref(cr))
                            item=QRect(round(cr.left/ratio)-self.x(),round(cr.top/ratio)-self.y(),
                                round((cr.right-cr.left)/ratio),round((cr.bottom-cr.top)/ratio)).intersected(region)
                            if item.width()>12 and item.height()>12: children.append(item)
                        return True
                    user.EnumChildWindows(hwnd,child_callback,0)
                    self.control_regions[(region.x(),region.y(),region.width(),region.height())]=sorted(children,key=lambda r:r.width()*r.height())
            return True
        user.EnumWindows(callback, 0)
        return rectangles

    def pixel(self):
        image = self.snapshot.toImage()
        x = max(0, min(image.width() - 1, round(self.cursor.x() * image.width() / self.width())))
        y = max(0, min(image.height() - 1, round(self.cursor.y() * image.height() / self.height())))
        return image, x, y

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.snapshot)
        p.fillRect(self.rect(), QColor(0, 0, 0, 100))
        region = self.selection
        if not region.isEmpty():
            p.save()
            p.setClipRect(region)
            p.drawPixmap(self.rect(), self.snapshot)
            p.restore()
            p.setPen(QPen(QColor('#2878ed'), 1))
            p.drawRect(region)
            if self.has_selection:
                for point in (region.topLeft(), region.topRight(), region.bottomLeft(), region.bottomRight(),
                              QPoint(region.center().x(), region.top()), QPoint(region.center().x(), region.bottom()),
                              QPoint(region.left(), region.center().y()), QPoint(region.right(), region.center().y())):
                    p.fillRect(QRect(point - QPoint(3, 3), point + QPoint(3, 3)), Qt.white)
                    p.drawRect(QRect(point - QPoint(3, 3), point + QPoint(3, 3)))
            p.fillRect(region.x(), max(0, region.y() - 24), 170, 23, QColor('#172236'))
            p.setPen(Qt.white)
            sx = self.snapshot.width() / self.width()
            p.drawText(region.x() + 7, max(17, region.y() - 7), f'{round(region.width()*sx)} × {round(region.height()*sx)}')
        if self.magnifier and not self.has_selection:
            image, x, y = self.pixel()
            box = QRect(min(self.width() - 170, self.cursor.x() + 24), min(self.height() - 170, self.cursor.y() + 24), 152, 152)
            p.fillRect(box.adjusted(-2,-2,2,2), QColor('#172236'))
            patch = image.copy(QRect(x-9, y-7, 19, 15).intersected(image.rect()))
            p.drawImage(QRect(box.x(), box.y(), 152, 120), patch)
            p.setPen(QPen(Qt.red,1))
            p.drawLine(box.center().x(), box.top(), box.center().x(), box.top()+120)
            p.drawLine(box.left(), box.top()+60, box.right(), box.top()+60)
            p.setPen(Qt.white)
            p.drawText(box.x()+5,box.y()+139,image.pixelColor(x,y).name().upper() + '   C 复制颜色')
        p.setPen(Qt.white)
        p.drawText(20, 25, '拖动框选 / 点击窗口 · 调整后 Enter 复制，F3 贴图 · C 取色 · , / . 历史 · Esc 取消')

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            if self.has_selection:
                self.has_selection = False
                self.selection = QRect()
                self.toolbar.hide()
                self.update()
            else:
                self.cancelled.emit()
            return
        if event.button() != Qt.LeftButton:
            return
        self.anchor = event.pos()
        self.original = QRect(self.selection)
        self.handle = ''
        if self.has_selection:
            r = self.selection
            if abs(event.x()-r.left()) < 8: self.handle += 'l'
            if abs(event.x()-r.right()) < 8: self.handle += 'r'
            if abs(event.y()-r.top()) < 8: self.handle += 't'
            if abs(event.y()-r.bottom()) < 8: self.handle += 'b'
            if not self.handle and r.contains(event.pos()): self.handle = 'move'
        self.dragging = True
        self.toolbar.hide()

    def mouseMoveEvent(self, event):
        self.cursor = event.pos()
        if self.dragging:
            delta = event.pos() - self.anchor
            r = QRect(self.original)
            if self.handle == 'move': r.translate(delta)
            elif self.handle:
                if 'l' in self.handle: r.setLeft(r.left()+delta.x())
                if 'r' in self.handle: r.setRight(r.right()+delta.x())
                if 't' in self.handle: r.setTop(r.top()+delta.y())
                if 'b' in self.handle: r.setBottom(r.bottom()+delta.y())
            else: r = QRect(self.anchor, event.pos()).normalized()
            self.selection = r.normalized().intersected(self.rect())
        elif not self.has_selection:
            self.selection = next((r for r in self.windows if r.contains(event.pos())), QRect())
            r=self.selection
            children=self.control_regions.get((r.x(),r.y(),r.width(),r.height()),[])
            self.selection=next((item for item in children if item.contains(event.pos())),r)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self.dragging:
            return
        if (event.pos()-self.anchor).manhattanLength() > 2:
            self.mouseMoveEvent(event)
        self.dragging = False
        self.has_selection = self.selection.width() >= 4 and self.selection.height() >= 4
        if self.has_selection:
            self.toolbar.adjustSize()
            self.toolbar.move(max(0,min(self.selection.right()-self.toolbar.width(), self.width()-self.toolbar.width())),
                min(self.height()-self.toolbar.height(), self.selection.bottom()+12))
            self.toolbar.show()
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self.has_selection: self.finish('copy')

    def finish(self, mode):
        if mode == 'cancel':
            self.cancelled.emit()
            return
        if not self.has_selection: return
        sx, sy = self.snapshot.width()/self.width(), self.snapshot.height()/self.height()
        r = self.selection
        image = self.snapshot.toImage().copy(QRect(round(r.x()*sx),round(r.y()*sy),round(r.width()*sx),round(r.height()*sy)))
        image.setDevicePixelRatio(1)
        self.history.append(QRect(r))
        del self.history[:-20]
        self.completed.emit(image, self.screen_geometry.topLeft()+r.topLeft(), mode)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape: self.cancelled.emit()
        elif key in (Qt.Key_Return, Qt.Key_Enter): self.finish('copy')
        elif key == Qt.Key_F3: self.finish('pin')
        elif key == Qt.Key_C:
            if event.modifiers() & Qt.ControlModifier and self.has_selection: self.finish('copy')
            else:
                image,x,y = self.pixel()
                QApplication.clipboard().setText(image.pixelColor(x,y).name().upper())
                self.cancelled.emit()
        elif key in (Qt.Key_Comma, Qt.Key_Period) and self.history:
            self.history_index = (self.history_index + (-1 if key == Qt.Key_Comma else 1)) % len(self.history)
            self.selection = self.history[self.history_index].intersected(self.rect())
            self.has_selection = True
            self.update()
        elif key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            dx = (-1 if key == Qt.Key_Left else 1 if key == Qt.Key_Right else 0)
            dy = (-1 if key == Qt.Key_Up else 1 if key == Qt.Key_Down else 0)
            if self.has_selection:
                if event.modifiers() & Qt.ShiftModifier: self.selection.adjust(0,0,dx,dy)
                else: self.selection.translate(dx,dy)
                self.selection = self.selection.intersected(self.rect())
            else:
                self.cursor += QPoint(dx,dy)
                QCursor.setPos(self.mapToGlobal(self.cursor))
            self.update()
