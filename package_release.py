"""Package corresponding source and notices beside the executable."""
from pathlib import Path
import hashlib
import shutil
import zipfile

root = Path(__file__).resolve().parent
destination = root / 'dist'
destination.mkdir(exist_ok=True)
for extension in ('png','ico'):
    shutil.copyfile(root / 'snaptext' / 'assets' / ('lens.'+extension),
                    destination / ('拾像 Lens.'+extension))
for name in ('README.md', 'LICENSE.txt', 'THIRD_PARTY_NOTICES.md', 'VALIDATION.md', 'benchmark-upgrade.json', '使用说明.txt'):
    shutil.copyfile(root / name, destination / name)
shutil.copytree(root / 'third-party-licenses', destination / 'third-party-licenses', dirs_exist_ok=True)
source_files = [root / name for name in (
    'main.py', 'requirements.txt', 'requirements-lock.txt', 'SnapText.spec',
    'prepare_release.py', 'package_release.py', 'download-deps.ps1', 'download-upgrade.ps1',
    '启动源码版.cmd', 'README.md', 'LICENSE.txt', 'THIRD_PARTY_NOTICES.md', 'VALIDATION.md', 'benchmark-upgrade.json', '使用说明.txt','version_info.txt')]
for directory in ('snaptext', 'tests', 'third-party-licenses'):
    source_files.extend(p for p in (root / directory).rglob('*')
                        if p.is_file() and '__pycache__' not in p.parts)
with zipfile.ZipFile(destination / '拾像 Lens-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in source_files:
        archive.write(path, path.relative_to(root))
hashes = []
for filename in ('拾像 Lens.exe', '拾像 Lens-source.zip'):
    path = destination / filename
    hashes.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + filename)
(destination / 'SHA256SUMS.txt').write_text('\n'.join(hashes) + '\n', encoding='utf-8')
print('\n'.join(hashes))
