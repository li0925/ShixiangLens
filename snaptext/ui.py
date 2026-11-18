from pathlib import Path

from PyQt5.QtCore import Qt, QRect, QPoint, QSize, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import (QImage, QPixmap, QPainter, QColor, QPen, QFont,
                         QKeySequence, QIcon)
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QFileDialog, QSplitter,
    QFrame, QSystemTrayIcon, QMenu, QShortcut, QSizePolicy)

from .ocr import recognize, warmup
from .hotkeys import Hotkeys
from .brand import icon as brand_icon


STYLE = '''
QMainWindow, QWidget#root { background: #f3f5f9; color: #202b3c; }
QWidget { font-family: "Microsoft YaHei UI"; font-size: 13px; }
QFrame#card { background: white; border: 1px solid #e0e5ee; border-radius: 12px; }
QLabel { color: #26344b; background: transparent; }
QLabel#muted { color: #778397; }
QLabel#heading { font-size: 24px; font-weight: 700; }
QLabel#badge { color: #14785d; background: #e5f5ee; border-radius: 12px; padding: 5px 12px; }
QPushButton { background: white; color: #35445b; border: 1px solid #dce2ed;
 border-radius: 7px; padding: 9px 14px; }
QPushButton:hover { background: #edf2fd; border-color: #b8c9f0; }
QPushButton:disabled { color: #a2aaba; background: #f3f5f8; }
QPushButton#primary { color: white; background: #3569e8; border-color: #3569e8; }
QPushButton#primary:hover { background: #2858ce; }
QPlainTextEdit { background: white; border: none; color: #28384f;
 selection-background-color: #d4e2ff; padding: 8px; font-size: 16px; }
QSplitter::handle { background: transparent; width: 16px; }
'''


def app_icon():
    return brand_icon()


class Worker(QThread):
    success = pyqtSignal(object)
    failure = pyqtSignal(str)

    def __init__(self, image, parent):
        super().__init__(parent)
        self.image = image.copy()

    def run(self):
        try:
            self.success.emit(recognize(self.image))
        except Exception as exc:
            self.failure.emit(str(exc))


class WarmupWorker(QThread):
    ready = pyqtSignal()
    failure = pyqtSignal(str)

    def run(self):
        try:
            warmup()
            self.ready.emit()
        except Exception as exc:
            self.failure.emit(str(exc))


class Preview(QLabel):
    def __init__(self):
        super().__init__()
        self.image = QImage()
        self.setMinimumSize(220, 240)
        self.setAlignment(Qt.AlignCenter)
        self.setObjectName('muted')
        self.setText('截图预览\n\n把图片拖到这里，或从剪贴板读取')

    def set_image(self, image):
        self.image = image.copy()
        self.refresh()

    def refresh(self):
        if not self.image.isNull():
            self.setPixmap(QPixmap.fromImage(self.image).scaled(
                self.size() - QSize(16, 16),
                Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()


class CaptureOverlay(QWidget):
    selected = pyqtSignal(QImage)
    selectedAt = pyqtSignal(QImage, QPoint)
    cancelled = pyqtSignal()

    def __init__(self, screen):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.screen_geometry = screen.geometry()
        self.snapshot = screen.grabWindow(0)
        self.start = self.end = QPoint()
        self.dragging = False
        self.setGeometry(self.screen_geometry)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.snapshot)
        painter.fillRect(self.rect(), QColor(8, 18, 35, 110))
        selection = QRect(self.start, self.end).normalized().intersected(self.rect())
        if self.dragging:
            painter.save()
            painter.setClipRect(selection)
            painter.drawPixmap(self.rect(), self.snapshot)
            painter.restore()
            painter.setPen(QPen(QColor('#6697ff'), 2))
            painter.drawRect(selection)
        painter.setPen(Qt.white)
        painter.setFont(QFont('Microsoft YaHei', 12))
        painter.drawText(24, 35, '拖动框选截图区域  ·  Esc / 右键取消')

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.cancelled.emit()
        elif event.button() == Qt.LeftButton:
            self.start = self.end = event.pos()
            self.dragging = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self.dragging:
            return
        self.end = event.pos()
        region = QRect(self.start, self.end).normalized().intersected(self.rect())
        if region.width() < 4 or region.height() < 4:
            self.dragging = False
            self.update()
            return
        # Map logical screen coordinates to physical screenshot pixels.
        sx = self.snapshot.width() / self.width()
        sy = self.snapshot.height() / self.height()
        image = self.snapshot.toImage().copy(QRect(round(region.x() * sx),
            round(region.y() * sy), round(region.width() * sx), round(region.height() * sy)))
        image.setDevicePixelRatio(1)
        self.selected.emit(image)
        self.selectedAt.emit(image, self.screen_geometry.topLeft() + region.topLeft())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()


class MainWindow(QMainWindow):
    def __init__(self, enable_hotkeys=True, enable_tray=True):
        super().__init__()
        self.busy = False
        self.worker = None
        self.image = QImage()
        self.overlays = []
        self.quitting = False
        self.capture_pending = False
        self.tray = None
        self.hotkeys = None
        self.setWindowTitle('拾像 Lens · 截图文字提取')
        self.setWindowIcon(app_icon())
        self.resize(1040, 700)
        self.setMinimumSize(820, 540)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)
        header = QHBoxLayout()
        heading = QLabel('拾像 Lens')
        heading.setObjectName('heading')
        header.addWidget(heading)
        subtitle = QLabel('截图里的文字，一键带走')
        subtitle.setObjectName('muted')
        header.addWidget(subtitle)
        header.addStretch()
        badge = QLabel('本机离线识别 · 中 / 英文')
        badge.setObjectName('badge')
        header.addWidget(badge)
        layout.addLayout(header)
        hint = QLabel('Snipaste 截图并复制  →  Ctrl + Alt + O  →  编辑或复制文字')
        layout.addWidget(hint)
        actions = QHBoxLayout()
        self.clipboard_btn = self.button('读取剪贴板  Ctrl+Alt+O', self.read_clipboard, True)
        self.capture_btn = self.button('框选识别  Ctrl+Alt+A', self.capture)
        self.file_btn = self.button('打开图片', self.open_file)
        self.retry_btn = self.button('重新识别', self.retry)
        for button in (self.clipboard_btn, self.capture_btn, self.file_btn, self.retry_btn):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        splitter = QSplitter(Qt.Horizontal)
        left, left_layout = self.card('原始图片')
        self.preview = Preview()
        left_layout.addWidget(self.preview, 1)
        self.image_info = QLabel('支持粘贴图片、拖入文件或直接框选')
        self.image_info.setObjectName('muted')
        self.image_info.setWordWrap(True)
        left_layout.addWidget(self.image_info)
        image_actions = QHBoxLayout()
        image_actions.addWidget(self.button('保存图片', self.save_image))
        image_actions.addWidget(self.button('贴图置顶', self.pin_image))
        left_layout.addLayout(image_actions)
        right, right_layout = self.card('识别结果')
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText('识别的文字会显示在这里。\n\n你可以直接修改，再复制到其他软件。')
        right_layout.addWidget(self.editor, 1)
        result_actions = QHBoxLayout()
        result_actions.addWidget(self.button('复制文字', self.copy_text, True))
        result_actions.addWidget(self.button('保存 TXT', self.save_text))
        result_actions.addStretch()
        self.count = QLabel('0 字')
        self.count.setObjectName('muted')
        result_actions.addWidget(self.count)
        right_layout.addLayout(result_actions)
        self.editor.textChanged.connect(lambda: self.count.setText(f'{len(self.editor.toPlainText())} 字'))
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([410, 550])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        self.status = QLabel('就绪 · 图片留在本机，识别结果不会自动覆盖剪贴板')
        self.status.setWordWrap(True)
        self.status.setObjectName('muted')
        layout.addWidget(self.status)
        QShortcut(QKeySequence('Ctrl+V'), self, activated=self.paste)
        QShortcut(QKeySequence('Ctrl+O'), self, activated=self.open_file)
        self.pins = []
        if enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip('拾像 Lens · Ctrl+Alt+O 提取截图文字')
            menu = QMenu(self)
            for label, callback in [('显示窗口', self.bring_forward), ('读取剪贴板', self.read_clipboard),
                                    ('框选识别', self.capture), ('退出', self.quit_app)]:
                menu.addAction(label, callback)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.bring_forward() if reason == QSystemTrayIcon.DoubleClick else None)
            self.tray.show()
        if enable_hotkeys:
            self.hotkeys = Hotkeys(QApplication.instance(), [
                ('O', 'Ctrl+Alt+O', self.read_clipboard), ('A', 'Ctrl+Alt+A', self.capture)])
            if self.hotkeys.failed:
                self.status.setText('快捷键被占用：' + '、'.join(self.hotkeys.failed) + '。请释放占用后重启；当前仍可点击按钮操作。')

    def button(self, text, callback, primary=False):
        button = QPushButton(text)
        if primary:
            button.setObjectName('primary')
        button.clicked.connect(callback)
        return button

    def card(self, title):
        frame = QFrame()
        frame.setObjectName('card')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 16)
        label = QLabel(title)
        label.setStyleSheet('font-weight: 700;')
        layout.addWidget(label)
        return frame, layout

    def bring_forward(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def set_busy(self, value):
        self.busy = value
        for button in (self.clipboard_btn, self.capture_btn, self.file_btn, self.retry_btn):
            button.setEnabled(not value)

    def paste(self):
        if QApplication.clipboard().mimeData().hasImage():
            self.read_clipboard()
        elif self.editor.hasFocus():
            self.editor.paste()

    def read_clipboard(self):
        if self.busy or self.capture_pending or self.overlays:
            return
        image = QApplication.clipboard().image()
        self.bring_forward()
        if image.isNull():
            self.status.setText('剪贴板里没有图片。请先用 Snipaste 截图，并选择“复制到剪贴板”。')
            return
        self.load_image(image)

    def load_image(self, image):
        if self.busy:
            return
        if image.isNull():
            self.status.setText('无法读取图片，请尝试 PNG、JPG 或 BMP 文件。')
            return
        self.image = image.copy()
        self.preview.set_image(self.image)
        self.image_info.setText(f'{image.width()} × {image.height()} 像素 · 原图保留')
        self.editor.clear()
        self.set_busy(True)
        self.status.setText('正在本机识别… 首次加载模型可能需要几秒钟。')
        self.worker = Worker(self.image, self)
        self.worker.success.connect(self.on_success)
        self.worker.failure.connect(self.on_failure)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_success(self, result):
        self.editor.setPlainText(result.text)
        self.status.setText(f'识别完成 · {len(result.lines)} 行 · {result.seconds:.1f} 秒 · 可编辑后复制'
                            if result.text else '未识别到文字。请尝试更清晰的截图，或缩小框选区域。')

    def on_failure(self, message):
        self.status.setText('识别失败：' + message)

    def on_finished(self):
        self.set_busy(False)
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def retry(self):
        if self.image.isNull():
            self.status.setText('请先读取一张截图。')
        else:
            self.load_image(self.image)

    def open_file(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, '打开图片', '', '图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)')
        if path:
            self.load_image(QImage(path))

    def copy_text(self):
        text = self.editor.toPlainText()
        if text.strip():
            QApplication.clipboard().setText(text)
            self.status.setText('文字已复制到剪贴板。')
        else:
            self.status.setText('还没有可复制的文字。')

    def save_text(self):
        if not self.editor.toPlainText().strip():
            self.status.setText('还没有可保存的文字。')
            return
        path, _ = QFileDialog.getSaveFileName(self, '保存识别结果', '识别结果.txt', '文本 (*.txt)')
        if path:
            try:
                Path(path).write_text(self.editor.toPlainText(), encoding='utf-8-sig')
                self.status.setText('文字已保存：' + path)
            except OSError as exc:
                self.status.setText('保存失败：' + str(exc))

    def save_image(self):
        if self.image.isNull():
            self.status.setText('请先读取一张截图。')
            return
        path, _ = QFileDialog.getSaveFileName(self, '保存图片', '截图.png', 'PNG 图片 (*.png)')
        if path:
            self.status.setText('图片已保存：' + path if self.image.save(path, 'PNG') else '保存失败，请检查文件夹权限。')

    def pin_image(self):
        if self.image.isNull():
            self.status.setText('请先读取一张截图。')
            return
        pin = QLabel(None, Qt.Window | Qt.WindowStaysOnTopHint)
        pin.setWindowTitle('拾像 Lens 贴图 · 关闭窗口即可取消')
        pin.setAttribute(Qt.WA_DeleteOnClose)
        pin.setAlignment(Qt.AlignCenter)
        pin.setPixmap(QPixmap.fromImage(self.image).scaled(900, 650, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.pins.append(pin)
        pin.destroyed.connect(lambda: self.pins.remove(pin) if pin in self.pins else None)
        pin.show()

    def capture(self):
        if self.busy or self.overlays or self.capture_pending:
            return
        self.capture_pending = True
        self.hide()
        QTimer.singleShot(220, self.begin_capture)

    def begin_capture(self):
        self.capture_pending = False
        for screen in QApplication.screens():
            overlay = CaptureOverlay(screen)
            overlay.selected.connect(self.finish_capture)
            overlay.cancelled.connect(self.cancel_capture)
            self.overlays.append(overlay)
        for overlay in self.overlays:
            overlay.show()
        from PyQt5.QtGui import QCursor
        for overlay in self.overlays:
            if overlay.geometry().contains(QCursor.pos()):
                overlay.activateWindow()

    def clear_overlays(self):
        for overlay in self.overlays:
            overlay.close()
            overlay.deleteLater()
        self.overlays.clear()

    def finish_capture(self, image):
        self.clear_overlays()
        self.bring_forward()
        self.load_image(image)

    def cancel_capture(self):
        self.clear_overlays()
        self.bring_forward()
        self.status.setText('已取消框选。')

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile() and not self.busy:
            self.load_image(QImage(urls[0].toLocalFile()))

    def closeEvent(self, event):
        if not self.quitting and self.tray:
            self.hide()
            event.ignore()
            self.tray.showMessage('拾像 Lens 已驻留托盘', 'Ctrl+Alt+O 提取文字；右键托盘图标可退出。', QSystemTrayIcon.Information, 2500)
        elif self.busy:
            self.status.setText('识别仍在进行，请完成后再退出。')
            event.ignore()
        else:
            event.accept()

    def shutdown(self):
        self.quitting = True
        if self.hotkeys:
            self.hotkeys.close()
            self.hotkeys = None
        if self.tray:
            self.tray.hide()
        self.clear_overlays()
        for pin in list(self.pins):
            pin.close()

    def quit_app(self):
        if self.busy:
            self.bring_forward()
            self.status.setText('识别仍在进行，请完成后再退出。')
            return
        self.shutdown()
        QApplication.quit()
