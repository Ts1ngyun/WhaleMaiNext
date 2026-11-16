"""Create deterministic source-only archives from reviewed release paths."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from privacy_check import check

ROOT = Path(__file__).resolve().parent
VERSION = '0.1.0'
ROOT_FILES = (
    '.gitignore', 'AGENTS.md', 'LICENSE', 'NOTICE.md', 'README.md',
    'Build-VoiceWorker.ps1', 'Prepare-Source.ps1', 'Setup.ps1', 'Start-WhaleMaiNext.cmd',
    'build_source.py', 'deployment.py', 'desktop.py', 'emoji_payload.py', 'global.json', 'hub.py',
    'maibot-sdk.txt', 'maibot.lock.txt', 'privacy_check.py', 'relay.lock.txt',
    'remote_console.py', 'requirements.txt', 'setup_local.py', 'smoke_local.py',
    'test_emoji.py', 'test_relay.py', 'test_remote.py', 'voice_intent.py',
)
TREES = ('audio', 'docs', 'licenses', 'plugin', 'remote', 'upstream-overlay', 'voice-worker')
EXCLUDED = {'__pycache__', 'obj', 'bin'}


def sources():
    result = [ROOT / filename for filename in ROOT_FILES]
    for tree in TREES:
        result.extend(path for path in (ROOT / tree).rglob('*')
                      if path.is_file() and not EXCLUDED.intersection(path.relative_to(ROOT).parts))
    return sorted(result)


def archive(path, members, base, prefix=''):
    with ZipFile(path, 'w') as output:
        for item in members:
            assert item.resolve().is_relative_to(base) and not item.is_symlink()
            info = ZipInfo(prefix + item.relative_to(base).as_posix())
            info.external_attr = 0o100644 << 16
            output.writestr(info, item.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    return sha256(path.read_bytes()).hexdigest()


def build():
    paths = sources()
    errors = check(paths)
    if errors:
        for path, reason in errors:
            print(f'{path} — {reason}')
        raise SystemExit('Source archive blocked by privacy scan')
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    products = (
        (f'WhaleMaiNext-{VERSION}-source.zip', paths, ROOT, 'WhaleMaiNext/'),
        (f'WhaleMaiNext-Adapter-{VERSION}.zip',
         [ROOT / 'plugin' / name for name in ('_manifest.json', 'plugin.py', 'LICENSE')],
         ROOT / 'plugin', ''),
    )
    lines = []
    for name, members, base, prefix in products:
        digest = archive(destination / name, members, base, prefix)
        lines.append(f'{digest}  {name}')
    (destination / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='ascii', newline='\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    build()
