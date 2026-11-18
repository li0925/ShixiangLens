# v4.1.0 validation

Windows x64, Python 3.9.12, PyQt5 5.15.11, RapidOCR 3.10.0, ONNX Runtime 1.19.2.
35 automated checks passed. The bundled EXE completed offline Chinese/English OCR with the expected brand name and icon. Model-warmed two-line sample inference was about 0.124 s on the development computer; performance varies by image and hardware.

Not yet independently tested on another clean Windows computer. Multi-monitor mixed-DPI combinations and arbitrary owner-drawn UI element detection require more testing. The startup registry option was not enabled during validation.
