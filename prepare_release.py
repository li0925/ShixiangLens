"""Retain dependency license texts alongside the GPL application source."""
from importlib.metadata import distributions
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
folder = root / 'third-party-licenses'
folder.mkdir(exist_ok=True)
for distribution in distributions():
    name = distribution.metadata['Name']
    for item in distribution.files or []:
        if any(word in str(item).lower() for word in ('license', 'copying', 'notice')) and '.dist-info/' in str(item):
            source = Path(distribution.locate_file(item))
            if source.is_file():
                destination = folder / name / Path(str(item)).name
                destination.parent.mkdir(exist_ok=True)
                shutil.copyfile(source, destination)
    (folder / (name + '-metadata.txt')).write_text(str(distribution.metadata), encoding='utf-8')
print('Retained dependency notices:', folder)
