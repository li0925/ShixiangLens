import unittest
from PyQt5.QtCore import Qt, QPoint, QPointF, QRect
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtTest import QTest
from test_snaptext import APP, sample
from snaptext.document import ImageDocument, Mark
from snaptext.pin import PinWindow


class DocumentTests(unittest.TestCase):
    def test_annotations_undo_redo_and_export(self):
        document = ImageDocument(sample())
        original = document.render()
        document.add(Mark('rect', [QPointF(10, 10), QPointF(200, 100)], '#ed4141', 5))
        self.assertNotEqual(document.render(), original)
        document.undo()
        self.assertEqual(document.render(), original)
        document.redo()
        self.assertNotEqual(document.render(), original)

    def test_crop_is_undoable_and_keeps_exact_pixels(self):
        document = ImageDocument(sample())
        original = document.render()
        document.crop(QRect(20, 30, 250, 90))
        self.assertEqual(document.render(), original.copy(20, 30, 250, 90))
        document.undo()
        self.assertEqual(document.render(), original)

    def test_mosaic_changes_region_only(self):
        document = ImageDocument(sample())
        original = document.render()
        document.add(Mark('mosaic', [QPointF(20, 30), QPointF(400, 100)]))
        result = document.render()
        self.assertNotEqual(result.copy(20, 30, 380, 70), original.copy(20, 30, 380, 70))
        self.assertEqual(result.copy(500, 0, 100, 220), original.copy(500, 0, 100, 220))

    def test_drawing_tools_render_and_do_not_mutate_source(self):
        for tool in ('ellipse', 'arrow', 'pen', 'text', 'line'):
            original = sample()
            document = ImageDocument(original)
            document.add(Mark(tool, [QPointF(30, 50), QPointF(200, 100)], text='标注'))
            self.assertNotEqual(document.render(), original, tool)
            self.assertEqual(document.base, original)


class DesktopFlowTests(unittest.TestCase):
    def setUp(self):
        from snaptext.desktop import DesktopApp
        self.controller = DesktopApp(APP, enable_hotkeys=False, enable_tray=False)

    def tearDown(self):
        for pin in self.controller.pins:
            if pin.worker:
                pin.worker.wait(30000)
                APP.processEvents()
        self.controller.shutdown()
        APP.processEvents()

    def test_screenshot_creates_editable_pin_without_opening_ocr_window(self):
        self.controller.capture_complete(sample(), QPoint(100, 100))
        self.assertEqual(len(self.controller.pins), 1)
        self.assertFalse(self.controller.pins[0].busy)
        self.assertFalse(self.controller.home.isVisible())
        self.assertFalse(self.controller.pins[0].result_panel.isVisible())

    def test_direct_capture_ocr_uses_inline_pin_result(self):
        self.controller.ocr_after_capture = True
        self.controller.capture_complete(sample(), QPoint(100, 100))
        pin = self.controller.pins[0]
        for _ in range(300):
            APP.processEvents()
            if not pin.busy:
                break
            QTest.qWait(100)
        self.assertIn('Hello Snipaste 123', pin.result_editor.toPlainText())
        self.assertFalse(self.controller.home.isVisible())

    def test_multiple_pins_hide_restore_and_close(self):
        first = self.controller.add_pin(sample())
        second = self.controller.add_pin(sample())
        self.controller.hide_pins()
        self.assertFalse(first.isVisible())
        self.assertFalse(second.isVisible())
        self.controller.show_pins()
        self.assertTrue(first.isVisible())
        self.controller.close_pins()
        self.assertEqual(self.controller.pins, [])


class PinTests(unittest.TestCase):
    def setUp(self):
        self.pin = PinWindow(sample())
        self.pin.show()
        APP.processEvents()

    def tearDown(self):
        if self.pin.worker:
            self.pin.worker.wait(30000)
            APP.processEvents()
        self.pin.close()
        APP.processEvents()

    def wait_ocr(self):
        for _ in range(300):
            APP.processEvents()
            if not self.pin.busy:
                return
            QTest.qWait(100)
        self.fail('OCR timeout')

    def test_right_click_menu_has_direct_ocr_and_annotation(self):
        labels = [action.text() for action in self.pin.create_menu().actions()]
        self.assertIn('识别整张图片', labels)
        self.assertIn('划选区域识别', labels)
        self.assertIn('标注工具', labels)

    def test_whole_image_result_stays_inside_pin(self):
        self.pin.start_ocr()
        self.wait_ocr()
        self.assertIn('Hello Snipaste 123', self.pin.result_editor.toPlainText())
        self.assertIs(self.pin.result_editor.window(), self.pin)
        self.assertTrue(self.pin.result_panel.isVisible())

    def test_ctrl_drag_ocr_works_on_zoomed_image(self):
        self.pin.set_zoom(0.65)
        self.pin.canvas.set_tool('move')
        start = self.pin.canvas.image_to_widget(QPointF(10, 105)).toPoint()
        end = self.pin.canvas.image_to_widget(QPointF(800, 210)).toPoint()
        QTest.mousePress(self.pin.canvas, Qt.LeftButton, Qt.ControlModifier, start)
        QTest.mouseMove(self.pin.canvas, end)
        QTest.mouseRelease(self.pin.canvas, Qt.LeftButton, Qt.ControlModifier, end)
        self.wait_ocr()
        text = self.pin.result_editor.toPlainText()
        self.assertIn('Hello Snipaste 123', text)
        self.assertNotIn('截图', text)

    def test_canvas_rectangle_and_undo(self):
        self.pin.canvas.set_tool('rect')
        original = self.pin.document.render()
        start = self.pin.canvas.image_to_widget(QPointF(10, 10)).toPoint()
        end = self.pin.canvas.image_to_widget(QPointF(280, 140)).toPoint()
        QTest.mousePress(self.pin.canvas, Qt.LeftButton, pos=start)
        QTest.mouseMove(self.pin.canvas, end)
        QTest.mouseRelease(self.pin.canvas, Qt.LeftButton, pos=end)
        self.assertNotEqual(self.pin.document.render(), original)
        self.pin.document.undo()
        self.assertEqual(self.pin.document.render(), original)

    def test_tightly_selected_single_line(self):
        self.pin.start_ocr(QRect(21, 103, 406, 69))
        self.wait_ocr()
        self.assertEqual(self.pin.result_editor.toPlainText(), 'Hello Snipaste 123')

    def test_locked_pin_does_not_change_annotations(self):
        self.pin.locked = True
        self.pin.canvas.set_tool('rect')
        before = self.pin.document.render()
        QTest.mousePress(self.pin.canvas, Qt.LeftButton, pos=QPoint(10, 10))
        QTest.mouseRelease(self.pin.canvas, Qt.LeftButton, pos=QPoint(150, 90))
        self.assertEqual(before, self.pin.document.render())

    def test_closing_during_ocr_waits_without_destroying_thread(self):
        self.pin.start_ocr()
        self.pin.close()
        self.assertTrue(self.pin.busy)
        self.wait_ocr()
        self.assertFalse(self.pin.isVisible())


if __name__ == '__main__':
    unittest.main()
