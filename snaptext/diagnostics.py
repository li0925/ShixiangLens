"""Explicit --verify mode, also exercises the frozen executable's models."""
import json
from pathlib import Path
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QImage, QPainter, QColor, QFont
from .desktop import DesktopApp
from .ocr import backend_info


def verify(app, destination):
    folder = Path(destination)
    folder.mkdir(parents=True, exist_ok=True)
    controller = DesktopApp(app, enable_hotkeys=True, enable_tray=False, preload=True)
    image = QImage(960, 240, QImage.Format_RGB32)
    image.fill(QColor('white'))
    painter = QPainter(image)
    painter.setFont(QFont('Microsoft YaHei', 28))
    painter.setPen(QColor('#18243b'))
    painter.drawText(30, 80, '截图文字提取 2026')
    painter.drawText(30, 170, 'Hello Snipaste 123')
    painter.end()
    image.save(str(folder / 'sample.png'))
    window = controller.add_pin(image)
    timer = QTimer(window)
    timer.setInterval(100)
    runs = []

    def complete():
        if window.busy:
            return
        text = window.result_editor.toPlainText()
        runs.append({'seconds': window.last_recognition.seconds if window.last_recognition else None,
                     'text': text})
        if len(runs) == 1:
            window.start_ocr()
            return
        success = '截图文字提取' in text.replace(' ', '') and 'Hello Snipaste 123' in text
        report = {'ok': success, 'text': text, 'status': window.status.text(),
                  'hotkeys_failed': controller.hotkeys.failed,
                  'inline_result': window.result_editor.window() is window,
                  'backend': backend_info(),
                  'seconds': window.last_recognition.seconds if window.last_recognition else None,
                  'runs': runs,
                  'name': window.windowTitle(),
                  'icon_loaded': not window.windowIcon().isNull(),
                  'menu_items': [action.text() for action in window.create_menu().actions()]}
        (folder / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        window.grab().save(str(folder / 'preview.png'))
        window.set_compact(False)
        window.grab().save(str(folder / 'toolbar.png'))
        from .preferences import PreferencesDialog
        dialog=PreferencesDialog(controller.prefs)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(folder/'preferences.png'))
        dialog.close()
        timer.stop()
        controller.home.show()
        app.processEvents()
        controller.home.grab().save(str(folder/'welcome.png'))
        controller.home.hide()
        def capture_help():
            modal=app.activeModalWidget()
            if modal:
                modal.grab().save(str(folder/'help.png'))
                modal.reject()
        QTimer.singleShot(100,capture_help)
        controller.show_help()
        controller.shutdown()
        app.exit(0 if success else 1)

    timer.timeout.connect(complete)
    def begin():
        window.start_ocr()
        timer.start()
    QTimer.singleShot(200, begin)
    QTimer.singleShot(60000, lambda: app.exit(2))
    return app.exec_()
