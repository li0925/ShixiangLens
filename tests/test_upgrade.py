import unittest
from unittest.mock import patch
from importlib.metadata import version

from test_snaptext import sample
from snaptext.ocr import recognize, warmup, backend_info


class UpgradeTests(unittest.TestCase):
    def test_latest_rapidocr_and_v6_models_work_without_network(self):
        self.assertEqual(version('rapidocr'), '3.10.0')
        with patch('snaptext.ocr._engine', None), patch(
                'requests.sessions.Session.request', side_effect=AssertionError('OCR must stay offline')):
            warmup()
            result = recognize(sample())
        self.assertIn('截图文字提取', result.text.replace(' ', ''))
        self.assertIn('Hello Snipaste 123', result.text)
        self.assertEqual(backend_info()['model'], 'PP-OCRv6 Small')

    def test_stage_timings_are_reported(self):
        result = recognize(sample())
        self.assertEqual(len(result.stages), 3)
        self.assertTrue(all(t >= 0 for t in result.stages))


if __name__ == '__main__':
    unittest.main()
