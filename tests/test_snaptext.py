import os
import unittest
from pathlib import Path

# On Windows, Qt's offscreen plugin does not load the system font engine.
# Test through the actual desktop platform so fixtures contain real glyphs.
os.environ.setdefault('QT_QPA_PLATFORM', 'windows' if os.name == 'nt' else 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage, QPainter, QColor, QFont

from snaptext.ocr import recognize
from snaptext.ui import MainWindow


APP = QApplication.instance() or QApplication([])


def setUpModule():
    from PyQt5.QtCore import QMimeData
    global saved_clipboard
    saved_clipboard = QMimeData()
    current = APP.clipboard().mimeData()
    for fmt in current.formats():
        saved_clipboard.setData(fmt, current.data(fmt))


def tearDownModule():
    APP.clipboard().setMimeData(saved_clipboard)


def sample(text='截图文字提取 2026\nHello Snipaste 123'):
    image = QImage(960, 220, QImage.Format_RGB32)
    image.fill(QColor('white'))
    painter = QPainter(image)
    painter.setPen(QColor('black'))
    painter.setFont(QFont('Microsoft YaHei', 28))
    for row, line in enumerate(text.splitlines()):
        painter.drawText(35, 75 + row * 80, line)
    painter.end()
    return image


class OcrTests(unittest.TestCase):
    def test_real_chinese_and_english(self):
        result = recognize(sample())
        self.assertIn('截图文字提取', result.text.replace(' ', ''))
        self.assertIn('Hello Snipaste 123', result.text)
        self.assertGreater(len(result.lines), 1)

    def test_blank_image_is_empty(self):
        image = QImage(300, 100, QImage.Format_RGB32)
        image.fill(QColor('white'))
        self.assertEqual(recognize(image).text, '')

    def test_null_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '图片'):
            recognize(QImage())

    def test_high_dpi_clipboard_preserves_physical_text_size(self):
        image = sample()
        normal = recognize(image)
        image.setDevicePixelRatio(2)
        high_dpi = recognize(image)
        self.assertEqual(high_dpi.text, normal.text)
        self.assertLess(abs(high_dpi.lines[0][0][2][0] - normal.lines[0][0][2][0]), 3)

    def test_transparent_background_is_readable(self):
        image = QImage(800, 120, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.setPen(QColor('black'))
        painter.setFont(QFont('Microsoft YaHei', 28))
        painter.drawText(25, 75, 'Transparent OCR 567')
        painter.end()
        self.assertIn('Transparent OCR 567', recognize(image).text)


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow(enable_hotkeys=False, enable_tray=False)

    def tearDown(self):
        self.window.shutdown()
        self.window.close()

    def test_real_worker_displays_text(self):
        from PyQt5.QtTest import QTest
        self.window.load_image(sample())
        for _ in range(300):
            APP.processEvents()
            if not self.window.busy:
                break
            QTest.qWait(100)
        self.assertFalse(self.window.busy)
        self.assertIn('Hello Snipaste 123', self.window.editor.toPlainText())

    def test_missing_clipboard_image_shows_help(self):
        APP.clipboard().setText('no image')
        self.window.read_clipboard()
        self.assertIn('剪贴板', self.window.status.text())
        self.assertFalse(self.window.busy)

    def test_result_can_be_edited_and_copied(self):
        self.window.editor.setPlainText('用户修改的文字 ABC')
        self.window.copy_text()
        self.assertEqual(APP.clipboard().text(), '用户修改的文字 ABC')

    def test_capture_reverse_drag_selects_real_screen_pixels(self):
        from PyQt5.QtTest import QTest
        from PyQt5.QtCore import Qt, QPoint
        from snaptext.ui import CaptureOverlay
        overlay = CaptureOverlay(APP.primaryScreen())
        selected = []
        overlay.selected.connect(selected.append)
        overlay.show()
        APP.processEvents()
        QTest.mousePress(overlay, Qt.LeftButton, pos=QPoint(210, 140))
        QTest.mouseMove(overlay, QPoint(30, 30))
        QTest.mouseRelease(overlay, Qt.LeftButton, pos=QPoint(30, 30))
        overlay.close()
        self.assertEqual(len(selected), 1)
        self.assertFalse(selected[0].isNull())
        self.assertGreater(selected[0].width(), 100)

    @unittest.skipUnless(os.name == 'nt', 'Windows global hotkeys')
    def test_native_hotkey_event_dispatches_callback(self):
        import ctypes
        from PyQt5.QtTest import QTest
        from snaptext.hotkeys import Hotkeys
        called = []
        hotkeys = Hotkeys(APP, [('J', 'Ctrl+Alt+J', lambda: called.append(True))])
        try:
            self.assertEqual(hotkeys.failed, [])
            native_id = next(iter(hotkeys.handlers))
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            self.assertTrue(user32.PostThreadMessageW(kernel32.GetCurrentThreadId(), 0x0312, native_id, 0))
            for _ in range(20):
                APP.processEvents()
                if called:
                    break
                QTest.qWait(10)
            self.assertEqual(called, [True])
        finally:
            hotkeys.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows global hotkeys')
    def test_hotkey_conflict_is_reported(self):
        from snaptext.hotkeys import Hotkeys
        first = Hotkeys(APP, [('J', 'Ctrl+Alt+J', lambda: None)])
        second = Hotkeys(APP, [('J', 'Ctrl+Alt+J', lambda: None)])
        try:
            self.assertEqual(first.failed, [], 'Test requires a free Ctrl+Alt+J hotkey')
            self.assertEqual(second.failed, ['Ctrl+Alt+J'])
        finally:
            first.close()
            second.close()


if __name__ == '__main__':
    unittest.main()
