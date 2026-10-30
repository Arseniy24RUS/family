"""Shared publication filter for project download manifests.

Atomic-write remnants may have a random suffix after ``.tmp``. Checking only
Path.suffix misses them, and an extension allowlist does not exclude files in
hidden directories. Apply one path policy before reading any candidate bytes.
"""
from pathlib import Path
import hashlib

_TEMP_SUFFIXES = {'.tmp', '.pyc', '.pyo', '.bak', '.backup', '.old', '.orig', '.swp', '.swo'}
_PRIVATE_DIRECTORIES = {'__pycache__', 'node_modules', 'backup', 'backups'}


def publishable_download(relative):
    parts = Path(relative).parts
    if not parts or any(part.startswith('.') or part.casefold() in _PRIVATE_DIRECTORIES
                        for part in parts):
        return False
    name = parts[-1]
    if name.endswith('~') or (name.startswith('#') and name.endswith('#')):
        return False
    return not any(suffix.casefold() in _TEMP_SUFFIXES for suffix in Path(name).suffixes)


def download_records(directory, public_root, *, suffixes=None):
    """Return the existing URL/bytes/SHA schema in stable path order.

An optional extension allowlist retains each project's previous document scope.
Regular source files are read only; none are renamed, removed or modified.
"""
    directory, public_root = Path(directory), Path(public_root)
    records = []
    # Path ordering follows platform case rules; published URLs must use the
    # same case-sensitive POSIX order on Windows and Linux.
    for candidate in sorted(directory.rglob('*'),
                            key=lambda path: path.relative_to(public_root).as_posix()):
        relative = candidate.relative_to(public_root)
        if not publishable_download(relative) or candidate.is_symlink() or not candidate.is_file():
            continue
        if suffixes is not None and candidate.suffix not in suffixes:
            continue
        digest = hashlib.sha256()
        size = 0
        with candidate.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                size += len(block)
                digest.update(block)
        records.append({'url': relative.as_posix(), 'bytes': size, 'sha256': digest.hexdigest()})
    return records
