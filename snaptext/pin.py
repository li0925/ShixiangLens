"""Desktop pins: annotation, region OCR and inline results in one window."""
from pathlib import Path

from PyQt5.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize, pyqtSignal, QTimer
from PyQt5.QtGui import (QPainter, QPen, QColor, QImage, QKeySequence, QPolygonF,
                         QCursor, QFont)
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QToolButton, QToolBar, QActionGroup, QPlainTextEdit, QPushButton, QMenu,
    QFileDialog, QColorDialog, QInputDialog, QShortcut, QFrame, QSizePolicy)

from .document import ImageDocument, Mark, draw_mark
from .ui import Worker, app_icon
from .icons import tool_icon


TOOLS = [('move', '移动', '拖动贴图'), ('rect', '矩形', '矩形标注'),
         ('ellipse', '椭圆', '椭圆标注'), ('arrow', '箭头', '箭头标注'),
         ('line', '直线', '直线标注'), ('pen', '画笔', '自由画笔'),
         ('text', '文字', '点击图片添加文字'), ('mosaic', '马赛克', '框选区域打马赛克'),
         ('blur', '模糊', '高斯模糊'), ('highlight', '马克笔', '半透明高亮'), ('eraser', '橡皮', '白色橡皮擦'),
         ('ocr', '识字', '划选区域识别文字'), ('crop', '裁剪', '框选后裁剪图片')]


class DragBar(QFrame):
    def mouseReleaseEvent(self,event):
        self.window().changed.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.window().locked:
            self.offset = event.globalPos() - self.window().pos()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and hasattr(self, 'offset') and not self.window().locked:
            self.window().move(event.globalPos() - self.offset)


class ImageCanvas(QWidget):
    def __init__(self, pin):
        super().__init__(pin)
        self.pin = pin
        self.tool = 'move'
        self.zoom = 1.0
        self.current = None
        self.dragging = False
        self.active_tool = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.OpenHandCursor)

    def image_rect(self):
        image = self.pin.document.base
        width, height = image.width() * self.zoom, image.height() * self.zoom
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def widget_to_image(self, point):
        rect = self.image_rect()
        image = self.pin.document.base
        return QPointF(max(0, min(image.width(), (point.x() - rect.x()) / self.zoom)),
                       max(0, min(image.height(), (point.y() - rect.y()) / self.zoom)))

    def image_to_widget(self, point):
        rect = self.image_rect()
        return QPointF(rect.x() + point.x() * self.zoom, rect.y() + point.y() * self.zoom)

    def update_size(self):
        image = self.pin.document.base
        self.setFixedSize(max(80 if self.pin.compact else 360, round(image.width() * self.zoom)),
                          max(40 if self.pin.compact else 80, round(image.height() * self.zoom)))
        self.update()

    def set_tool(self, tool):
        if self.pin.movie and tool!='move': self.pin.movie.stop()
        self.tool = tool
        self.cancel_gesture()
        self.setCursor(Qt.OpenHandCursor if tool == 'move' else Qt.CrossCursor)
        if tool in self.pin.tool_actions:
            self.pin.tool_actions[tool].setChecked(True)
        if not self.pin.busy:
            self.pin.status.setText('按住 Ctrl 在图上拖选，也可直接识别局部文字' if tool == 'move'
                                    else dict((key, tip) for key, _, tip in TOOLS)[tool])

    def cancel_gesture(self):
        self.dragging = False
        self.current = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#edf0f5'))
        image = self.pin.document.render()
        if self.current and self.active_tool not in ('ocr', 'crop', 'eraser'):
            draw_mark(image, self.current)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(self.image_rect(), image)
        if self.pin.show_boxes:
            painter.setPen(QPen(QColor('#2474ed'), 1))
            for box in self.pin.boxes:
                painter.drawPolygon(QPolygonF([self.image_to_widget(QPointF(x, y)) for x, y in box]))
        if self.current and self.active_tool in ('ocr', 'crop', 'eraser'):
            rect = QRectF(self.image_to_widget(self.current.points[0]),
                          self.image_to_widget(self.current.points[-1])).normalized()
            painter.setPen(QPen(QColor('#2474ed'), 2, Qt.DashLine))
            painter.fillRect(rect, QColor(36, 116, 237, 35))
            painter.drawRect(rect)
        painter.setPen(QPen(QColor('#aeb8c9'), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.setFocus()
        tool = 'ocr' if event.modifiers() & Qt.ControlModifier else self.tool
        if self.pin.locked and tool != 'ocr':
            return
        if tool == 'move':
            self.drag_offset = event.globalPos() - self.pin.pos()
            self.active_tool = 'move'
            self.dragging = True
            self.setCursor(Qt.ClosedHandCursor)
            return
        if self.pin.busy or not self.image_rect().contains(QPointF(event.pos())):
            return
        point = self.widget_to_image(event.pos())
        if tool == 'text':
            text, accepted = QInputDialog.getMultiLineText(self.pin, '添加文字标注', '文字内容：')
            if accepted and text.strip():
                self.pin.document.add(Mark('text', [point], self.pin.color, self.pin.stroke, text))
            return
        self.active_tool = tool
        self.dragging = True
        self.current = Mark(tool, [point, point], self.pin.color, self.pin.stroke)
        self.update()

    def mouseMoveEvent(self, event):
        if event.modifiers() & Qt.AltModifier and self.image_rect().contains(QPointF(event.pos())):
            point = self.widget_to_image(event.pos()).toPoint()
            image = self.pin.document.render()
            point.setX(min(image.width()-1,point.x()))
            point.setY(min(image.height()-1,point.y()))
            self.pin.picked_color = image.pixelColor(point).name().upper()
            self.pin.status.setText(self.pin.picked_color + ' · C 复制颜色')
            from PyQt5.QtWidgets import QToolTip
            QToolTip.showText(event.globalPos(),self.pin.picked_color,self)
        if not self.dragging:
            return
        if self.active_tool == 'move':
            if not self.pin.locked:
                self.pin.move(event.globalPos() - self.drag_offset)
        elif self.current:
            point = self.widget_to_image(event.pos())
            if self.active_tool == 'pen':
                self.current.points.append(point)
            else:
                self.current.points[-1] = point
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self.dragging:
            return
        self.dragging = False
        if self.active_tool == 'move':
            self.setCursor(Qt.OpenHandCursor)
            self.pin.changed.emit()
            return
        mark, self.current = self.current, None
        if not mark:
            return
        mark.points[-1] = self.widget_to_image(event.pos())
        region = QRectF(mark.points[0], mark.points[-1]).normalized().toAlignedRect()
        if self.active_tool in ('ocr', 'crop'):
            if region.width() >= 4 and region.height() >= 4:
                if self.active_tool == 'ocr':
                    self.pin.start_ocr(region)
                else:
                    self.pin.document.crop(region)
            self.set_tool('move')
        elif self.active_tool == 'pen' or region.width() > 1 or region.height() > 1:
            self.pin.document.add(mark)
        self.update()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.pin.setWindowOpacity(max(.15,min(1,self.pin.windowOpacity()+(.05 if event.angleDelta().y()>0 else -.05))))
        elif self.pin.movie and self.pin.movie.state()==self.pin.movie.Running:
            self.pin.movie.setSpeed(max(10,min(1000,self.pin.movie.speed()+(10 if event.angleDelta().y()>0 else -10))))
        else:
            self.pin.set_zoom(self.zoom * (1.12 if event.angleDelta().y() > 0 else 1 / 1.12))
        event.accept()

    def mouseDoubleClickEvent(self,event):
        if event.button() == Qt.LeftButton:
            if event.modifiers() & Qt.ShiftModifier: self.pin.toggle_thumbnail()
            elif self.tool == 'move': self.pin.hide()

    def keyPressEvent(self,event):
        if not self.pin.handle_key(event): super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = self.pin.create_menu()
        menu.exec_(event.globalPos())
        menu.deleteLater()


class PinWindow(QWidget):
    closed = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, image, position=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint)
        self.document = ImageDocument(image)
        self.color = '#ed4141'
        self.stroke = 3
        self.locked = False
        self.group_name = '默认'
        self.picked_color = ''
        self.thumbnail_zoom = None
        self.compact = False
        self.movie = None
        self.busy = False
        self.worker = None
        self.close_pending = False
        self.boxes = []
        self.last_recognition = None
        self.show_boxes = False
        self.tool_actions = {}
        self.ocr_offset = QPoint()
        self.setWindowTitle('拾像 Lens · 桌面贴图')
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.setStyleSheet('''
            QWidget {font-family: "Microsoft YaHei UI"; font-size: 12px; color: #26354a;}
            PinWindow {background: #fff; border: 1px solid #b8c4d8;}
            QToolBar {background: #f5f7fb; border: none; spacing: 1px; padding: 3px;}
            QToolButton {border: none; padding: 6px 5px; border-radius: 3px;}
            QToolButton:hover, QToolButton:checked {background: #dce8ff; color: #195bd5;}
            QPushButton {background: #edf3ff; border: 1px solid #cfddf5; border-radius: 4px; padding: 5px 10px;}
            QPlainTextEdit {border: 1px solid #d8e0ed; background: #fff; font-size: 14px; padding: 5px;}
            QMenu {background: #fff; border: 1px solid #d6ddea; padding: 5px;}
            QMenu::item {padding: 7px 28px 7px 15px;}
            QMenu::item:selected {background: #e7efff; color: #195bd5;}
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.bar = DragBar()
        self.bar.setStyleSheet('background: #f5f7fb;')
        top = QHBoxLayout(self.bar)
        top.setContentsMargins(9, 0, 3, 0)
        self.caption = QLabel()
        self.caption.setAttribute(Qt.WA_TransparentForMouseEvents)
        top.addWidget(self.caption, 1)
        self.add_top_button(top, '识字', lambda: self.start_ocr(), '识别整张图片')
        self.add_top_button(top, '−', self.hide, '暂时隐藏，可从托盘找回')
        self.add_top_button(top, '×', self.close, '关闭贴图')
        layout.addWidget(self.bar)
        self.canvas = ImageCanvas(self)
        layout.addWidget(self.canvas, 0, Qt.AlignHCenter)
        self.toolbar = QToolBar()
        self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.toolbar.setIconSize(QSize(22,22))
        self.group = QActionGroup(self)
        self.group.setExclusive(True)
        for key, label, tooltip in TOOLS:
            action = self.toolbar.addAction(label)
            action.setToolTip(tooltip)
            action.setIcon(tool_icon(key))
            action.setCheckable(True)
            self.group.addAction(action)
            action.triggered.connect(lambda checked=False, tool=key: self.canvas.set_tool(tool))
            self.tool_actions[key] = action
        self.tool_actions['move'].setChecked(True)
        self.toolbar.addSeparator()
        self.toolbar.addAction('颜色', self.choose_color)
        self.toolbar.addAction('撤销', self.undo)
        self.toolbar.addAction('复制', self.copy_image)
        self.toolbar.addAction('保存', self.save_image)
        layout.addWidget(self.toolbar)
        self.optionsbar=QToolBar()
        self.optionsbar.setIconSize(QSize(16,16))
        for color in ('#ed4141','#ffba08','#20ad73','#2878ed','#a84fee','#ffffff','#172236'):
            from PyQt5.QtGui import QPixmap,QIcon
            swatch=QPixmap(16,16)
            swatch.fill(QColor(color))
            action=self.optionsbar.addAction(QIcon(swatch),color)
            action.triggered.connect(lambda checked=False,value=color:setattr(self,'color',value))
        from PyQt5.QtWidgets import QSlider
        slider=QSlider(Qt.Horizontal)
        slider.setRange(1,16)
        slider.setValue(self.stroke)
        slider.setFixedWidth(90)
        slider.setToolTip('线条粗细 / 文字大小')
        slider.valueChanged.connect(lambda value:setattr(self,'stroke',value))
        self.optionsbar.addWidget(slider)
        layout.addWidget(self.optionsbar)
        self.result_panel = QWidget()
        result_layout = QVBoxLayout(self.result_panel)
        result_layout.setContentsMargins(9, 8, 9, 8)
        result_layout.setSpacing(5)
        result_header = QHBoxLayout()
        result_header.addWidget(QLabel('识别结果'))
        result_header.addStretch()
        for text, callback in [('复制文字', self.copy_text), ('保存 TXT', self.save_text), ('收起', self.hide_results)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            result_header.addWidget(button)
        result_layout.addLayout(result_header)
        self.result_editor = QPlainTextEdit()
        self.result_editor.setFixedHeight(120)
        self.result_editor.setPlaceholderText('正在本机识别…')
        result_layout.addWidget(self.result_editor)
        self.result_panel.hide()
        layout.addWidget(self.result_panel)
        self.status = QLabel('拖动移动 · 滚轮缩放 · Ctrl + 拖选识字 · 右键更多操作')
        self.status.setStyleSheet('color: #6b7a90; padding: 5px 8px; background: #f5f7fb;')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.document.changed.connect(self.document_changed)
        self.document.changed.connect(self.changed)
        for sequence, callback in [('Ctrl+Z', self.undo), ('Ctrl+Y', self.redo),
                                   ('Ctrl+S', self.save_image), ('Ctrl+C', self.smart_copy),
                                   ('Ctrl+V', self.paste_image), ('Escape', self.escape),
                                   ('Ctrl+Return', lambda: self.start_ocr()),
                                   ('Ctrl+W', self.close)]:
            QShortcut(QKeySequence(sequence), self, activated=callback)
        screen = QApplication.primaryScreen().availableGeometry()
        self.set_zoom(min(1.0, (screen.width() - 100) / image.width(),
                          (screen.height() - 330) / image.height()))
        if position is None:
            self.move(screen.center() - self.rect().center())
        else:
            self.move(position)
        self.keep_on_screen()

    def add_top_button(self, layout, text, callback, tip):
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.clicked.connect(callback)
        layout.addWidget(button)

    def set_zoom(self, zoom):
        screen = self.screen().availableGeometry() if self.screen() else QApplication.primaryScreen().availableGeometry()
        image = self.document.base
        max_zoom = min(4.0, max(.05, (screen.width() - 30) / image.width()),
                       max(.05, (screen.height() - 320) / image.height()))
        self.canvas.zoom = max(.05, min(max_zoom, zoom))
        self.canvas.update_size()
        self.caption.setText(f'拾像 Lens  ·  {image.width()} × {image.height()}  ·  {self.canvas.zoom:.0%}')
        self.fit_window()

    def fit_window(self):
        self.setFixedWidth(max(self.canvas.width()+2,360 if self.result_panel.isVisible() else 0))
        self.layout().activate()
        self.setFixedHeight(self.layout().sizeHint().height())
        self.keep_on_screen()

    def keep_on_screen(self):
        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                  max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))

    def document_changed(self):
        self.boxes = []
        self.result_editor.clear()
        self.result_panel.hide()
        self.set_zoom(self.canvas.zoom)
        self.status.setText('图片已更新 · 复制或保存会包含当前标注')

    def set_compact(self, compact):
        self.compact = compact
        self.bar.setVisible(not compact)
        self.status.setVisible(not compact)
        self.toolbar.setVisible(not compact)
        self.optionsbar.setVisible(not compact)
        self.canvas.update_size()
        self.fit_window()

    def load_movie(self,path):
        self.release_movie()
        from PyQt5.QtGui import QMovie
        self.movie=QMovie(path,parent=self)
        if not self.movie.isValid():
            self.movie=None
            return
        def frame():
            old_size=self.document.base.size()
            self.document.base=self.movie.currentImage().copy()
            self.document.base.setDevicePixelRatio(1)
            self.document.marks=[]
            self.document._cache=None
            if old_size!=self.document.base.size(): self.set_zoom(self.canvas.zoom)
            self.canvas.update()
        self.movie.frameChanged.connect(frame)
        self.movie.start()

    def release_movie(self):
        if self.movie:
            self.movie.stop()
            self.movie.frameChanged.disconnect()
            self.movie.setFileName('')
            self.movie.deleteLater()
            self.movie=None

    def toggle_thumbnail(self):
        if self.thumbnail_zoom is None:
            self.thumbnail_zoom = self.canvas.zoom
            self.set_zoom(min(160/self.document.base.width(),100/self.document.base.height()))
        else:
            value,self.thumbnail_zoom = self.thumbnail_zoom,None
            self.set_zoom(value)

    def handle_key(self,event):
        key, modifiers = event.key(),event.modifiers()
        if key == Qt.Key_Space:
            self.set_compact(not self.compact if self.compact else self.toolbar.isVisible())
        elif key in (Qt.Key_Plus,Qt.Key_Equal,Qt.Key_Minus):
            if modifiers & Qt.ControlModifier:
                self.setWindowOpacity(max(.15,min(1,self.windowOpacity()+(-.05 if key==Qt.Key_Minus else .05))))
            else: self.set_zoom(self.canvas.zoom*(1/1.12 if key==Qt.Key_Minus else 1.12))
        elif key in (Qt.Key_1,Qt.Key_2,Qt.Key_3,Qt.Key_4) and not self.busy and not self.locked:
            if self.movie and key in (Qt.Key_1,Qt.Key_2):
                self.movie.stop()
                count=max(1,self.movie.frameCount())
                self.movie.jumpToFrame((self.movie.currentFrameNumber()+(1 if key==Qt.Key_2 else -1))%count)
            elif key in (Qt.Key_1,Qt.Key_2): self.document.rotate(90 if key==Qt.Key_1 else -90)
            else: self.document.mirror(key==Qt.Key_3)
        elif key==Qt.Key_C and self.picked_color:
            QApplication.clipboard().setText(self.picked_color)
        else: return False
        return True

    def keyPressEvent(self,event):
        if not self.handle_key(event): super().keyPressEvent(event)

    def set_click_through(self, enabled):
        self.setWindowFlag(Qt.WindowTransparentForInput,enabled)
        self.show()

    def move_group(self):
        name,ok = QInputDialog.getText(self,'贴图分组','分组名称：',text=self.group_name)
        if ok and name.strip():
            self.group_name=name.strip()
            self.changed.emit()

    def undo(self):
        if self.result_editor.hasFocus():
            self.result_editor.undo()
        elif not self.busy and not self.locked:
            self.document.undo()

    def redo(self):
        if self.result_editor.hasFocus():
            self.result_editor.redo()
        elif not self.busy and not self.locked:
            self.document.redo()

    def start_ocr(self, region=None):
        if self.movie: self.movie.stop()
        if self.busy:
            self.status.setText('正在识别，请稍候…')
            return
        image = self.document.render()
        if isinstance(region, QRect):
            region = region.intersected(image.rect())
            if region.width() < 4 or region.height() < 4:
                return
            self.ocr_offset = region.topLeft()
            image = image.copy(region)
            # A little context prevents tight single-line crops being split by
            # the detector. Keep offsets in original physical image pixels.
            padded = QImage(image.width() + 96, image.height() + 96, QImage.Format_RGB32)
            padded.fill(QColor('white'))
            painter = QPainter(padded)
            painter.drawImage(48, 48, image)
            painter.end()
            image = padded
            self.ocr_offset -= QPoint(48, 48)
        else:
            self.ocr_offset = QPoint()
        self.busy = True
        self.boxes = []
        self.result_editor.clear()
        self.result_panel.show()
        self.status.setText('正在本机识别… 图片不会上传')
        self.fit_window()
        self.worker = Worker(image, self)
        self.worker.success.connect(self.ocr_success)
        self.worker.failure.connect(self.ocr_failure)
        self.worker.finished.connect(self.ocr_finished)
        self.worker.start()

    def ocr_success(self, result):
        self.last_recognition = result
        self.result_editor.setPlainText(result.text)
        self.boxes = [[[x + self.ocr_offset.x(), y + self.ocr_offset.y()] for x, y in box]
                      for box, _, _ in result.lines]
        self.status.setText(f'识别完成 · {len(result.lines)} 行 · {result.seconds:.1f} 秒 · 可在下方编辑、复制'
                            if result.text else '未找到文字，请放大原内容后重新截图，或重新划选区域。')
        self.canvas.update()

    def ocr_failure(self, message):
        self.result_editor.setPlaceholderText('识别失败，可重新尝试')
        self.status.setText('识别失败：' + message)

    def ocr_finished(self):
        self.busy = False
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        if self.close_pending:
            QTimer.singleShot(0, self.close)

    def hide_results(self):
        self.result_panel.hide()
        self.fit_window()

    def copy_text(self):
        text = self.result_editor.toPlainText()
        if text.strip():
            QApplication.clipboard().setText(text)
            self.status.setText('文字已复制到剪贴板')
        else:
            self.status.setText('还没有可复制的文字')

    def smart_copy(self):
        if self.result_editor.hasFocus():
            self.result_editor.copy()
        else:
            self.copy_image()

    def copy_image(self):
        QApplication.clipboard().setImage(self.document.render())
        self.status.setText('图片已复制（包含当前标注）')

    def save_image(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存标注图片', '截图.png', 'PNG 图片 (*.png);;JPEG 图片 (*.jpg)')
        if path:
            image = self.document.render()
            self.status.setText('图片已保存' if image.save(path) else '保存失败，请检查路径和权限')

    def save_text(self):
        if not self.result_editor.toPlainText().strip():
            self.status.setText('还没有可保存的文字')
            return
        path, _ = QFileDialog.getSaveFileName(self, '保存文字', '识别结果.txt', '文本 (*.txt)')
        if path:
            try:
                Path(path).write_text(self.result_editor.toPlainText(), encoding='utf-8-sig')
                self.status.setText('文字已保存')
            except OSError as exc:
                self.status.setText('保存失败：' + str(exc))

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, '标注颜色')
        if color.isValid():
            self.color = color.name()

    def paste_image(self):
        if self.result_editor.hasFocus() and not QApplication.clipboard().mimeData().hasImage():
            self.result_editor.paste()
            return
        if self.busy or self.locked:
            return
        image = QApplication.clipboard().image()
        if not image.isNull():
            self.release_movie()
            self.document.replace(image)

    def set_topmost(self, checked):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.show()

    def toggle_toolbar(self, checked):
        self.set_compact(not checked)

    def escape(self):
        if self.canvas.tool != 'move' or self.canvas.dragging:
            self.canvas.set_tool('move')
        elif self.result_panel.isVisible():
            self.hide_results()
        else:
            self.hide()

    def create_menu(self):
        menu = QMenu(self)
        menu.addAction('复制图像', self.copy_image, QKeySequence('Ctrl+C'))
        menu.addAction('图像另存为…', self.save_image, QKeySequence('Ctrl+S'))
        menu.addSeparator()
        menu.addAction('识别整张图片', lambda: self.start_ocr())
        menu.addAction('划选区域识别', lambda: self.canvas.set_tool('ocr'))
        copy = menu.addAction('复制识别文字', self.copy_text)
        copy.setEnabled(bool(self.result_editor.toPlainText().strip()))
        if not self.result_editor.toPlainText().strip():
            menu.addAction('Ctrl + 拖动：直接划选识字').setEnabled(False)
        action = menu.addAction('显示文字位置')
        action.setCheckable(True)
        action.setChecked(self.show_boxes)
        action.triggered.connect(self.toggle_boxes)
        menu.addSeparator()
        tools = menu.addMenu('标注工具')
        for key, label, tip in TOOLS:
            action = tools.addAction(label, lambda checked=False, tool=key: self.canvas.set_tool(tool))
            action.setEnabled(not self.locked or key == 'ocr')
        tools.addSeparator()
        tools.addAction('颜色…', self.choose_color)
        widths = tools.addMenu('线条粗细 / 字号')
        for width in (2, 3, 5, 8, 12):
            action = widths.addAction(f'{width} px  ·  文字 {max(16, width * 6)} px')
            action.setCheckable(True)
            action.setChecked(width == self.stroke)
            action.triggered.connect(lambda checked=False, value=width: setattr(self, 'stroke', value))
        undo = menu.addAction('撤销', self.undo, QKeySequence('Ctrl+Z'))
        undo.setEnabled(bool(self.document.past) and not self.busy and not self.locked)
        redo = menu.addAction('重做', self.redo, QKeySequence('Ctrl+Y'))
        redo.setEnabled(bool(self.document.future) and not self.busy and not self.locked)
        menu.addSeparator()
        toolbar = menu.addAction('显示工具栏')
        toolbar.setCheckable(True)
        toolbar.setChecked(self.toolbar.isVisible())
        toolbar.triggered.connect(self.toggle_toolbar)
        topmost = menu.addAction('窗口置顶')
        topmost.setCheckable(True)
        topmost.setChecked(bool(self.windowFlags() & Qt.WindowStaysOnTopHint))
        topmost.triggered.connect(self.set_topmost)
        lock = menu.addAction('锁定位置和标注')
        lock.setCheckable(True)
        lock.setChecked(self.locked)
        lock.triggered.connect(lambda checked: setattr(self, 'locked', checked))
        scale = menu.addMenu('缩放（也可滚轮）')
        for value in (.25, .5, .75, 1.0, 1.5, 2.0):
            scale.addAction(f'{value:.0%}', lambda checked=False, zoom=value: self.set_zoom(zoom))
        image = menu.addMenu('图像处理')
        rotate = image.addAction('顺时针旋转 90°', self.document.rotate)
        rotate.setEnabled(not self.busy and not self.locked)
        image.addAction('划选裁剪', lambda: self.canvas.set_tool('crop')).setEnabled(not self.busy and not self.locked)
        image.addAction('清除当前标注', self.document.reset).setEnabled(not self.busy and not self.locked)
        opacity = menu.addMenu('透明度')
        for value in (1.0, .85, .65, .4):
            opacity.addAction(f'{value:.0%}', lambda checked=False, alpha=value: self.setWindowOpacity(alpha))
        menu.addSeparator()
        menu.addAction('移动到分组…',self.move_group)
        through = menu.addAction('鼠标穿透（托盘可取消）')
        through.setCheckable(True)
        through.setChecked(bool(self.windowFlags() & Qt.WindowTransparentForInput))
        through.triggered.connect(self.set_click_through)
        menu.addAction('缩略图 / 恢复',self.toggle_thumbnail)
        menu.addAction('隐藏（可从托盘找回）', self.hide)
        menu.addAction('关闭贴图', self.close, QKeySequence('Ctrl+W'))
        return menu

    def toggle_boxes(self, checked):
        self.show_boxes = checked
        self.canvas.update()

    def contextMenuEvent(self, event):
        menu = self.create_menu()
        menu.exec_(event.globalPos())
        menu.deleteLater()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy and not self.locked:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.busy or self.locked:
            return
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            image = QImage(urls[0].toLocalFile())
            if not image.isNull():
                self.release_movie()
                self.document.replace(image)
                if urls[0].toLocalFile().lower().endswith('.gif'): self.load_movie(urls[0].toLocalFile())

    def closeEvent(self, event):
        if self.busy:
            self.close_pending = True
            self.hide()
            event.ignore()
        else:
            self.release_movie()
            event.accept()
            self.closed.emit(self)
