"""Copy upstream license notices into an existing development distribution."""
from importlib import metadata
from pathlib import Path
import shutil
import sys

if __name__ == '__main__':
    destination = Path(sys.argv[1]).resolve()
    if not (destination / 'ModelCheck.exe').is_file():
        raise SystemExit('Choose an existing ModelCheck development build folder.')
    notices = destination / 'THIRD-PARTY-LICENSES'
    notices.mkdir(exist_ok=True)
    for distribution in metadata.distributions():
        name = distribution.metadata['Name']
        version = distribution.version
        for file in distribution.files or []:
            basename = Path(str(file)).name.upper()
            if 'LICENSE' not in basename and 'COPYING' not in basename and 'NOTICE' not in basename and basename != 'METADATA':
                continue
            source = Path(distribution.locate_file(file))
            if not source.is_file():
                continue
            # Flatten relative wheel paths so package metadata cannot escape the destination.
            safe = str(file).replace('\\', '_').replace('/', '_').replace(':', '_')
            folder = notices / (name.replace('/', '_').replace('\\', '_') + '-' + version)
            folder.mkdir(exist_ok=True)
            shutil.copyfile(source, folder / safe)
    root = Path(__file__).resolve().parents[1]
    for source in [root / 'LICENSE', root / 'THIRD_PARTY.md', *(root / 'licenses').glob('*.txt')]:
        shutil.copyfile(source, notices / source.name)
    print('Dependency notices copied to development distribution.')
