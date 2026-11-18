"""Resident desktop application: screenshot -> editable pin -> inline OCR."""
from PyQt5.QtCore import QObject, Qt, QTimer, QPoint
from PyQt5.QtGui import QImage, QCursor, QKeySequence, QIcon
from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QWidget,
    QVBoxLayout, QLabel, QPushButton, QFileDialog, QShortcut)

from .hotkeys import Hotkeys
from .pin import PinWindow
from .ui import app_icon, WarmupWorker
from .capture import CaptureOverlay
from .preferences import Preferences, PreferencesDialog
from .clipboard import clipboard_image
from .brand import NAME, VERSION, TEAM, TAGLINE, guide
from pathlib import Path
import json


class DesktopApp(QObject):
    def __init__(self, app, enable_hotkeys=True, enable_tray=True, preload=False, persist=False):
        super().__init__()
        self.app = app
        self.pins = []
        self.overlays = []
        self.restore_pins = []
        self.capture_pending = False
        self.ocr_after_capture = False
        self.quitting = False
        self.hotkeys = None
        self.tray = None
        self.preload_worker = None
        self.prefs = Preferences()
        self.persist = persist
        self.session_timer = QTimer(self)
        self.session_timer.setSingleShot(True)
        self.session_timer.setInterval(1500)
        self.session_timer.timeout.connect(self.backup_session)
        self.home = self.make_home()
        if enable_hotkeys:
            self.hotkeys = Hotkeys(app, [
                ('F1', self.prefs.data['capture_key'], self.capture),
                ('F3', self.prefs.data['paste_key'], self.paste_pin),
                ('O', self.prefs.data['ocr_key'], self.capture_ocr)])
            if self.hotkeys.failed:
                self.message.setText('快捷键被占用：' + '、'.join(self.hotkeys.failed) +
                    '\n仍可使用托盘菜单和按钮；释放快捷键后重新启动。')
        if enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(self.prefs.data['tray_icon']) if self.prefs.data['tray_icon'] else app_icon(), self)
            self.tray.setToolTip('拾像 Lens · 截图 / 标注 / 文字识别')
            menu = QMenu()
            menu.addAction('截图  ' + self.prefs.data['capture_key'], self.capture)
            menu.addAction('贴图  ' + self.prefs.data['paste_key'], self.paste_pin)
            menu.addAction('框选文字识别  Ctrl+Alt+O', self.capture_ocr)
            menu.addAction('打开图片并贴图…', self.open_image)
            menu.addSeparator()
            menu.addAction('显示全部贴图', self.show_pins)
            menu.addAction('隐藏全部贴图', self.hide_pins)
            menu.addAction('关闭全部贴图', self.close_pins)
            menu.addAction('取消所有鼠标穿透', self.clear_click_through)
            groups=menu.addMenu('贴图分组')
            groups.aboutToShow.connect(lambda:self.group_menu(groups))
            menu.addSeparator()
            menu.addAction('使用说明', self.show_help)
            menu.addAction('关于拾像 Lens',self.about)
            menu.addAction('首选项…', self.preferences)
            menu.addAction('退出', self.quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.capture() if reason == QSystemTrayIcon.DoubleClick else None)
            self.tray.show()
        if preload:
            QTimer.singleShot(100, self.start_preload)
        if persist and self.prefs.data['restore']:
            QTimer.singleShot(300,self.restore_session)

    def preferences(self):
        if PreferencesDialog(self.prefs,self.home).exec_():
            if self.hotkeys:
                self.hotkeys.close()
                self.hotkeys=Hotkeys(self.app,[(self.prefs.data[k],self.prefs.data[k],callback)
                    for k,callback in [('capture_key',self.capture),('paste_key',self.paste_pin),('ocr_key',self.capture_ocr)]])
                self.message.setText('快捷键冲突：'+', '.join(self.hotkeys.failed) if self.hotkeys.failed else '首选项已保存')
            for pin in self.pins: self.style_pin(pin)
            if self.tray:
                from PyQt5.QtGui import QIcon
                self.tray.setIcon(QIcon(self.prefs.data['tray_icon']) if self.prefs.data['tray_icon'] else app_icon())

    def style_pin(self,pin):
        was_visible=pin.isVisible()
        data=self.prefs.data
        if not hasattr(pin,'base_style'): pin.base_style=pin.styleSheet()
        pin.setStyleSheet(pin.base_style+f'\nQWidget {{font-family:"{data["font"]}"; font-size:{data["font_size"]}pt;}} QToolButton:checked {{background:{data["theme"]}; color:white;}}')
        pin.setWindowFlag(Qt.NoDropShadowWindowHint,not data['shadow'])
        pin.set_compact(not data['toolbar'])
        if was_visible: pin.show()

    def clear_click_through(self):
        for pin in self.pins: pin.set_click_through(False)

    def group_menu(self,menu):
        menu.clear()
        for name in sorted(set(pin.group_name for pin in self.pins)):
            menu.addAction('显示 '+name,lambda checked=False,n=name:self.show_group(n))

    def show_group(self,name):
        for pin in self.pins: pin.setVisible(pin.group_name==name)

    def backup_session(self):
        try: self.write_session()
        except OSError as error: self.message.setText('贴图备份暂未保存：'+str(error))

    def write_session(self):
        if not self.persist or not self.prefs.data['restore']: return
        folder=self.prefs.path.parent/'session'
        folder.mkdir(parents=True,exist_ok=True)
        records=[]
        for i,pin in enumerate(self.pins[:30]):
            path=folder/f'pin-{i}.png'
            temp=folder/f'pin-{i}.tmp'
            if pin.document.render().save(str(temp),'PNG'):
                temp.replace(path)
                records.append(dict(file=path.name,x=pin.x(),y=pin.y(),zoom=pin.canvas.zoom,
                    opacity=pin.windowOpacity(),group=pin.group_name,visible=pin.isVisible()))
        temp=folder/'session.tmp'
        temp.write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8')
        temp.replace(folder/'session.json')

    def restore_session(self):
        folder=self.prefs.path.parent/'session'
        try:
            records=json.loads((folder/'session.json').read_text(encoding='utf-8'))
            for record in records[:30]:
                path=folder/Path(record['file']).name
                pin=self.add_pin(QImage(str(path)),QPoint(record['x'],record['y']))
                if pin:
                    pin.set_zoom(record['zoom'])
                    pin.group_name=record.get('group','默认')
                    pin.setWindowOpacity(record.get('opacity',1))
                    pin.setVisible(record.get('visible',True))
        except (OSError,ValueError,KeyError,TypeError): pass

    def start_preload(self):
        if self.quitting or self.preload_worker:
            return
        self.preload_worker = WarmupWorker(self)
        self.preload_worker.failure.connect(lambda error: self.message.setText('识别引擎加载失败：' + error))
        self.preload_worker.finished.connect(self.preload_finished)
        self.preload_worker.start()

    def preload_finished(self):
        if self.preload_worker:
            self.preload_worker.deleteLater()
            self.preload_worker = None

    def make_home(self):
        home = QWidget()
        home.setWindowTitle('拾像 Lens · 截图、标注、文字识别')
        home.setWindowIcon(app_icon())
        home.setFixedWidth(470)
        home.setStyleSheet('''QWidget {background: #f5f7fb; color: #28364c; font-family: "Microsoft YaHei UI"; font-size: 13px;}
            QPushButton {background: #142c54; color: #fff; border: none; border-radius: 6px; padding: 12px;}
            QPushButton:hover {background: #1b5570;}''')
        layout = QVBoxLayout(home)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(13)
        logo=QLabel()
        logo.setPixmap(app_icon().pixmap(76,76))
        layout.addWidget(logo,0,Qt.AlignHCenter)
        title = QLabel(NAME)
        title.setStyleSheet('font-size: 26px; font-weight: 700;')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(QLabel(TAGLINE+'  ·  一分钟上手'))
        for label, callback in [('截图  F1', self.capture),
                                ('贴图  F3', self.paste_pin),
                                ('打开图片…', self.open_image)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            layout.addWidget(button)
        hint = QLabel('贴图上右键：识别整图 / 划选区域识别\n'
                      '按住 Ctrl 在图上拖选：直接识别局部文字\n'
                      '普通拖动：移动贴图；滚轮：缩放\n\n'
                      '识别结果在当前贴图下方展开，无需切换窗口。\n'
                      '关闭此说明窗口后，程序继续驻留系统托盘。\n'
                      '中英文离线识别，截图不上传。')
        hint.setText(f'① {self.prefs.data["capture_key"]} 框选截图，Enter 复制。\n'
            f'② {self.prefs.data["paste_key"]} 贴图；拖动移动，滚轮缩放。\n'
            '③ 空格打开标注工具栏。\n'
            '④ Ctrl+拖选识字；右键可识别整图。\n'
            '⑤ 双击隐藏；托盘右键找回。')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #63748c; line-height: 1.7;')
        layout.addWidget(hint)
        help_button=QPushButton('查看完整使用说明')
        help_button.clicked.connect(self.show_help)
        layout.addWidget(help_button)
        self.message = QLabel('就绪')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        signature=QLabel(TEAM+'\n拾像 Lens '+VERSION)
        signature.setWordWrap(True)
        signature.setAlignment(Qt.AlignCenter)
        signature.setStyleSheet('font-size:11px;color:#7d899c;')
        layout.addWidget(signature)
        QShortcut(QKeySequence('Ctrl+V'), home, activated=self.paste_pin)
        return home

    def about(self):
        from PyQt5.QtWidgets import QMessageBox
        box=QMessageBox(self.home)
        box.setWindowTitle('关于 '+NAME)
        box.setWindowIcon(app_icon())
        box.setIconPixmap(app_icon().pixmap(96,96))
        box.setText(NAME+'  '+VERSION)
        box.setInformativeText(TAGLINE+'\n\n'+TEAM+'\n\n三拱门 · 空天轨道\n离线文字识别，图片留在本机。')
        box.exec_()

    def show_help(self):
        from PyQt5.QtWidgets import QDialog,QTextBrowser,QDialogButtonBox
        dialog=QDialog(self.home)
        dialog.setWindowTitle(NAME+' · 使用说明')
        dialog.setWindowIcon(app_icon())
        dialog.resize(540,450)
        layout=QVBoxLayout(dialog)
        browser=QTextBrowser()
        browser.setPlainText(NAME+' · 一分钟上手\n\n'+guide(
            self.prefs.data['capture_key'],self.prefs.data['paste_key'])+'\n\n'+TEAM)
        layout.addWidget(browser)
        buttons=QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec_()

    def show_home(self):
        self.home.showNormal()
        self.home.raise_()
        self.home.activateWindow()

    def notify(self, text):
        self.message.setText(text)
        if self.tray:
            self.tray.showMessage('拾像 Lens', text, QSystemTrayIcon.Information, 3000)
        else:
            self.show_home()

    def add_pin(self, image, position=None):
        if image.isNull():
            self.notify('无法读取图片，请使用 PNG、JPG 或 BMP。')
            return None
        if image.width() * image.height() > 40_000_000:
            self.notify('图片超过 4000 万像素，请先缩小图片。')
            return None
        pin = PinWindow(image, position)
        self.style_pin(pin)
        pin.changed.connect(self.session_timer.start)
        pin.closed.connect(self.remove_pin)
        self.pins.append(pin)
        pin.show()
        pin.raise_()
        pin.activateWindow()
        self.session_timer.start()
        self.home.hide()
        return pin

    def remove_pin(self, pin):
        if pin in self.pins:
            self.pins.remove(pin)
            if not self.quitting: self.session_timer.start()
            pin.deleteLater()

    def paste_pin(self):
        if self.capture_pending or self.overlays:
            return
        image = clipboard_image(QApplication.clipboard().mimeData())
        if image.isNull():
            if self.pins: self.show_pins()
            else: self.notify('剪贴板没有可贴出的内容。支持图像、文本、HTML、颜色和图片文件。')
        else:
            pin=self.add_pin(image, QCursor.pos() + QPoint(18, 18))
            mime=QApplication.clipboard().mimeData()
            if pin and mime.hasUrls() and mime.urls()[0].toLocalFile().lower().endswith('.gif'):
                pin.load_movie(mime.urls()[0].toLocalFile())

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(self.home, '打开图片并贴图', '',
            '图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.ico *.gif)')
        if path:
            pin=self.add_pin(QImage(path))
            if pin and path.lower().endswith('.gif'): pin.load_movie(path)

    def capture(self):
        self.begin_capture(False)

    def capture_ocr(self):
        self.begin_capture(True)

    def begin_capture(self, ocr=False):
        if self.capture_pending or self.overlays or self.quitting:
            return
        self.capture_pending = True
        self.ocr_after_capture = ocr
        self.restore_pins = [pin for pin in self.pins if pin.isVisible()]
        self.home_was_visible = self.home.isVisible()
        self.home.hide()
        for pin in self.restore_pins:
            pin.hide()
        QTimer.singleShot(220, self.show_capture)

    def show_capture(self):
        self.capture_pending = False
        if self.quitting:
            return
        # Snapshot every monitor before displaying any overlay.
        for screen in QApplication.screens():
            overlay = CaptureOverlay(screen,self.prefs.data['auto_detect'],self.prefs.data['magnifier'])
            overlay.completed.connect(self.capture_action)
            overlay.cancelled.connect(self.cancel_capture)
            self.overlays.append(overlay)
        for overlay in self.overlays:
            overlay.show()
            if overlay.geometry().contains(QCursor.pos()):
                overlay.activateWindow()

    def end_capture(self):
        for overlay in self.overlays:
            overlay.close()
            overlay.deleteLater()
        self.overlays.clear()
        for pin in self.restore_pins:
            if pin in self.pins:
                pin.show()
        self.restore_pins.clear()

    def capture_complete(self, image, position):
        self.end_capture()
        pin = self.add_pin(image, position)
        if pin and self.ocr_after_capture:
            pin.start_ocr()

    def capture_action(self,image,position,mode):
        self.end_capture()
        QApplication.clipboard().setImage(image)
        if mode in ('pin','ocr') or self.ocr_after_capture:
            pin=self.add_pin(image,position)
            if pin and (mode=='ocr' or self.ocr_after_capture): pin.start_ocr()
        else: self.notify('截图已复制，按 F3 贴出。')

    def cancel_capture(self):
        self.end_capture()
        if self.home_was_visible:
            self.show_home()

    def show_pins(self):
        for pin in self.pins:
            if not pin.close_pending:
                pin.show()
                pin.raise_()

    def hide_pins(self):
        for pin in self.pins:
            pin.hide()

    def close_pins(self):
        for pin in list(self.pins):
            pin.close()

    def quit(self):
        if any(pin.busy for pin in self.pins):
            self.notify('文字识别仍在进行，请完成后退出。')
            return
        self.shutdown()
        self.app.quit()

    def shutdown(self):
        if self.quitting: return
        self.session_timer.stop()
        self.backup_session()
        self.quitting = True
        if self.preload_worker and self.preload_worker.isRunning():
            self.preload_worker.wait()
        if self.hotkeys:
            self.hotkeys.close()
            self.hotkeys = None
        if self.tray:
            self.tray.hide()
        self.end_capture()
        self.close_pins()
        self.home.close()
