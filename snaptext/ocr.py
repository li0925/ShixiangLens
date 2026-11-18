"""Local-only RapidOCR 3.10 with bundled PP-OCRv6 Small models."""
from dataclasses import dataclass
from threading import Lock
from pathlib import Path
import os
import time

import numpy as np
from PyQt5.QtGui import QImage, QPainter, QColor


@dataclass
class Recognition:
    text: str
    lines: list
    seconds: float
    stages: tuple = ()


_engine = None
_lock = Lock()


def backend_info():
    from importlib.metadata import version
    return {'engine': 'RapidOCR', 'version': version('rapidocr'),
            'model': 'PP-OCRv6 Small', 'runtime': 'ONNX Runtime CPU',
            'runtime_version': version('onnxruntime'), 'offline': True}


def _get_engine():
    # Caller owns _lock. Both normal OCR and startup warmup share one engine.
    global _engine
    if _engine is None:
        import rapidocr
        from rapidocr import RapidOCR, OCRVersion, ModelType
        models = Path(rapidocr.__file__).resolve().parent / 'models'
        paths = {'Det': models / 'PP-OCRv6_det_small.onnx',
                 'Cls': models / 'ch_ppocr_mobile_v2.0_cls_mobile.onnx',
                 'Rec': models / 'PP-OCRv6_rec_small.onnx'}
        for path in paths.values():
            if not path.is_file():
                raise FileNotFoundError('缺少离线识别模型，请重新解压或下载完整程序：' + path.name)
        params = {
            'Global.log_level': 'error',
            'Global.model_root_dir': str(models),
            'EngineConfig.onnxruntime.intra_op_num_threads': min(4, os.cpu_count() or 2),
            'EngineConfig.onnxruntime.inter_op_num_threads': 1,
            'Det.ocr_version': OCRVersion.PPOCRV6,
            'Det.model_type': ModelType.SMALL,
            'Rec.ocr_version': OCRVersion.PPOCRV6,
            'Rec.model_type': ModelType.SMALL,
            # Do not enlarge every small screenshot to a 736 px short edge.
            'Det.limit_type': 'max',
            'Det.limit_side_len': 1600,
        }
        params.update({f'{stage}.model_path': str(path) for stage, path in paths.items()})
        _engine = RapidOCR(params=params)
    return _engine


def warmup():
    """Load all lazy models on a worker before the first user OCR request."""
    import cv2
    image = np.full((120, 600, 3), 255, dtype=np.uint8)
    cv2.putText(image, 'SnapText 123', (20, 78), cv2.FONT_HERSHEY_SIMPLEX,
                1.8, (0, 0, 0), 3, cv2.LINE_AA)
    with _lock:
        _get_engine()(image)


def recognize(image: QImage) -> Recognition:
    if image.isNull() or image.width() < 2 or image.height() < 2:
        raise ValueError('图片无效，请重新截图。')
    if image.width() * image.height() > 40_000_000:
        raise ValueError('图片过大，请框选需要识别的区域（最多 4000 万像素）。')
    start = time.perf_counter()
    # Composite alpha over white rather than treating transparent black as ink.
    flat = QImage(image.size(), QImage.Format_RGB888)
    flat.fill(QColor('white'))
    painter = QPainter(flat)
    physical = image.copy()
    physical.setDevicePixelRatio(1)
    painter.drawImage(0, 0, physical)
    painter.end()
    pointer = flat.bits()
    pointer.setsize(flat.byteCount())
    rgb = np.frombuffer(pointer, np.uint8).reshape(flat.height(), flat.bytesPerLine())
    rgb = rgb[:, :flat.width() * 3].reshape(flat.height(), flat.width(), 3)
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    with _lock:
        result = _get_engine()(bgr)
    lines = []
    if result.boxes is not None and result.txts is not None:
        lines = [(box.tolist(), text, float(score))
                 for box, text, score in zip(result.boxes, result.txts, result.scores)]
    stages = tuple(float(value) for value in (result.elapse_list or (0, 0, 0)))
    return Recognition('\n'.join(text for _, text, _ in lines), lines,
                       time.perf_counter() - start, stages)
