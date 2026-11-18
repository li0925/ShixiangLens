import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtTest import QTest
from test_snaptext import APP, sample
from snaptext.pin import PinWindow
from snaptext.document import ImageDocument, Mark


class PolishTests(unittest.TestCase):
    def test_function_hotkey_and_animated_image(self):
        from snaptext.hotkeys import Hotkeys
        hotkey=Hotkeys(APP,[('F24','F24',lambda:None)])
        try: self.assertEqual(hotkey.failed,[])
        finally: hotkey.close()
        from PIL import Image
        with TemporaryDirectory() as folder:
            path=Path(folder)/'animated.gif'
            Image.new('RGB',(100,80),'red').save(path,save_all=True,
                append_images=[Image.new('RGB',(100,80),'blue')],duration=100,loop=0)
            pin=PinWindow(sample())
            pin.load_movie(str(path))
            self.assertIsNotNone(pin.movie)
            self.assertEqual(pin.movie.frameCount(),2)
            pin.movie.stop()
            pin.close()

    def test_new_annotation_tools_undo(self):
        for tool in ('blur', 'highlight'):
            doc = ImageDocument(sample())
            before = doc.render()
            doc.add(Mark(tool, [QPointF(20, 30), QPointF(400, 100)], '#ffff00', 12))
            self.assertNotEqual(before, doc.render(), tool)
            doc.undo()
            self.assertEqual(before, doc.render())

    def test_eraser_removes_annotations_without_erasing_source(self):
        doc=ImageDocument(sample())
        original=doc.render()
        doc.add(Mark('rect',[QPointF(20,30),QPointF(400,100)]))
        doc.add(Mark('eraser',[QPointF(0,0),QPointF(450,120)]))
        self.assertEqual(doc.render(),original)

    def test_text_html_and_color_clipboard(self):
        from PyQt5.QtCore import QMimeData
        from snaptext.clipboard import clipboard_image
        for kind,value in [('text','中英文 Text'),('html','<b>文本</b>'),('text','#123456')]:
            mime=QMimeData()
            (mime.setHtml if kind=='html' else mime.setText)(value)
            image=clipboard_image(mime)
            self.assertFalse(image.isNull())
            if value.startswith('#'): self.assertEqual(image.pixelColor(0,0).name(),value)

    def test_session_restores_image_and_group(self):
        from snaptext.desktop import DesktopApp
        from snaptext.preferences import Preferences
        with TemporaryDirectory() as folder:
            first=DesktopApp(APP,False,False)
            first.prefs=Preferences(Path(folder)/'prefs.json')
            first.persist=True
            pin=first.add_pin(sample())
            pin.group_name='参考图'
            first.backup_session()
            first.persist=False
            first.shutdown()
            second=DesktopApp(APP,False,False)
            second.prefs=first.prefs
            second.restore_session()
            self.assertEqual(len(second.pins),1)
            self.assertEqual(second.pins[0].group_name,'参考图')
            self.assertEqual(second.pins[0].document.render(),sample())
            second.shutdown()

    def test_pin_keyboard_rotation_flip_thumbnail_and_space(self):
        pin = PinWindow(sample())
        pin.show()
        APP.processEvents()
        before = pin.document.render()
        QTest.keyClick(pin.canvas, Qt.Key_1)
        self.assertEqual(pin.document.base.width(), before.height())
        QTest.keyClick(pin.canvas, Qt.Key_2)
        self.assertEqual(pin.document.render(), before)
        shown = pin.toolbar.isVisible()
        QTest.keyClick(pin.canvas, Qt.Key_Space)
        self.assertNotEqual(shown, pin.toolbar.isVisible())
        pin.close()

    def test_settings_roundtrip(self):
        from snaptext.preferences import Preferences
        with TemporaryDirectory() as folder:
            prefs = Preferences(Path(folder) / 'settings.json')
            self.assertEqual(prefs.data['capture_key'], 'F1')
            prefs.data['theme'] = '#ed4141'
            prefs.save()
            self.assertEqual(Preferences(prefs.path).data['theme'], '#ed4141')

    def test_capture_waits_for_confirmation_and_resizes(self):
        from snaptext.capture import CaptureOverlay
        from PyQt5.QtCore import QPoint
        overlay = CaptureOverlay(APP.primaryScreen())
        completed = []
        overlay.completed.connect(lambda *args: completed.append(args))
        overlay.show()
        APP.processEvents()
        QTest.mousePress(overlay, Qt.LeftButton, pos=QPoint(30, 60))
        QTest.mouseRelease(overlay, Qt.LeftButton, pos=QPoint(250, 180))
        self.assertTrue(overlay.has_selection)
        self.assertFalse(completed)
        before = overlay.selection.width()
        QTest.keyClick(overlay, Qt.Key_Right, Qt.ShiftModifier)
        self.assertEqual(overlay.selection.width(), before + 1)
        QTest.keyClick(overlay, Qt.Key_Return)
        self.assertEqual(len(completed), 1)
        overlay.close()


if __name__ == '__main__':
    unittest.main()
