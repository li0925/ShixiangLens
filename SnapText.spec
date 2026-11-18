# Build with: .venv-latest\Scripts\python.exe -m PyInstaller SnapText.spec --noconfirm
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = collect_all('rapidocr')
datas += copy_metadata('rapidocr') + copy_metadata('onnxruntime')
datas += [('README.md', '.'), ('THIRD_PARTY_NOTICES.md', '.'), ('LICENSE.txt', '.'),
          ('third-party-licenses', 'third-party-licenses'),
          ('snaptext/assets','snaptext/assets'), ('使用说明.txt','.')]
a = Analysis(['main.py'], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=['tkinter', 'matplotlib', 'scipy', 'IPython',
                 'torch', 'paddle', 'openvino', 'tensorrt', 'MNN'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='拾像 Lens',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False,
          icon='snaptext/assets/lens.ico',version='version_info.txt')
