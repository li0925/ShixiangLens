"""Portable preferences and a compact tabbed preferences dialog."""
import json
import os
from pathlib import Path
from PyQt5.QtCore import QStandardPaths
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout,
    QCheckBox, QPushButton, QColorDialog, QFontComboBox, QSpinBox, QDialogButtonBox,
    QKeySequenceEdit, QLabel)


class Preferences:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) / 'preferences.json'
        self.data = dict(theme='#2878ed', font='Microsoft YaHei UI', font_size=10,
            capture_key='F1', paste_key='F3', ocr_key='Ctrl+Alt+O', restore=True,
            auto_detect=True, magnifier=True, toolbar=False, shadow=True, startup=False)
        self.data['tray_icon']=''
        try:
            loaded = json.loads(self.path.read_text(encoding='utf-8'))
            self.data.update({k: v for k, v in loaded.items() if k in self.data})
        except (OSError, ValueError, TypeError):
            pass

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)


class PreferencesDialog(QDialog):
    def __init__(self, prefs, parent=None):
        super().__init__(parent)
        self.prefs = prefs
        self.setWindowTitle('拾像 Lens 首选项')
        self.resize(460, 360)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)
        self.fields = {}
        general = QWidget()
        form = QFormLayout(general)
        self.font = QFontComboBox()
        self.font.setCurrentFont(QFont(prefs.data['font']))
        form.addRow('界面字体', self.font)
        self.size = QSpinBox()
        self.size.setRange(8, 20)
        self.size.setValue(prefs.data['font_size'])
        form.addRow('字号', self.size)
        self.theme = prefs.data['theme']
        color = QPushButton('选择主题颜色…')
        def choose():
            value = QColorDialog.getColor(QColor(self.theme), self)
            if value.isValid():
                self.theme = value.name()
                color.setStyleSheet('background:' + self.theme)
        color.clicked.connect(choose)
        form.addRow('主题', color)
        self.startup=QCheckBox('开机启动')
        self.startup.setChecked(prefs.data['startup'])
        form.addRow(self.startup)
        self.icon_path=prefs.data['tray_icon']
        icon=QPushButton('选择通知栏图标…')
        def choose_icon():
            from PyQt5.QtWidgets import QFileDialog
            path,_=QFileDialog.getOpenFileName(self,'通知栏图标','','图标 (*.ico *.png)')
            if path: self.icon_path=path
        icon.clicked.connect(choose_icon)
        form.addRow(icon)
        tabs.addTab(general, '常规')
        for name, options in [('截图', [('auto_detect', '自动检测窗口区域'), ('magnifier', '显示像素放大镜')]),
                              ('贴图', [('toolbar', '默认显示标注工具栏'), ('shadow', '显示窗口阴影'),
                                       ('restore', '自动备份并恢复贴图')])]:
            page = QWidget()
            layout = QVBoxLayout(page)
            for key, label in options:
                widget = QCheckBox(label)
                widget.setChecked(prefs.data[key])
                self.fields[key] = widget
                layout.addWidget(widget)
            layout.addStretch()
            tabs.addTab(page, name)
        page = QWidget()
        form = QFormLayout(page)
        self.keys = {}
        from PyQt5.QtGui import QKeySequence
        for key, label in [('capture_key', '截图'), ('paste_key', '贴图'), ('ocr_key', '直接识字')]:
            field = QKeySequenceEdit(QKeySequence(prefs.data[key]))
            self.keys[key] = field
            form.addRow(label, field)
        form.addRow(QLabel('按下新快捷键进行修改。若被占用，会提示冲突。'))
        tabs.addTab(page, '热键')
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def accept(self):
        keys = [field.keySequence().toString() for field in self.keys.values()]
        if any(not key or ',' in key for key in keys) or len(set(keys)) != len(keys):
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, '快捷键无效', '请设置三个不同的单组快捷键。')
            return
        self.prefs.data.update({k: w.isChecked() for k, w in self.fields.items()})
        self.prefs.data.update({k: w.keySequence().toString() for k, w in self.keys.items()})
        self.prefs.data.update(theme=self.theme, font=self.font.currentFont().family(), font_size=self.size.value())
        try:
            if self.startup.isChecked()!=self.prefs.data['startup']:
                import winreg,sys
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as registry:
                    if self.startup.isChecked():
                        command='"'+sys.executable+'"'
                        if not getattr(sys,'frozen',False): command+=' "'+str(Path(__file__).resolve().parent.parent/'main.py')+'"'
                        winreg.SetValueEx(registry,'SnapText',0,winreg.REG_SZ,command)
                    else:
                        try: winreg.DeleteValue(registry,'SnapText')
                        except FileNotFoundError: pass
            self.prefs.data.update(startup=self.startup.isChecked(),tray_icon=self.icon_path)
            self.prefs.save()
        except OSError as error:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self,'保存失败',str(error))
            return
        super().accept()
