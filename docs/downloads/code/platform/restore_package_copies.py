#!/usr/bin/env python3
"""Restore byte-identical published copies omitted only from a compact ZIP.

Source files are always present. The manifest only permits copies into docs/,
and existing files are never overwritten. No network or third-party package is
needed. A normal working repository with complete docs/ needs no restoration.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'PACKAGE_COPIES.json'
SCHEMA = 'national-projects.package-copies/1'
PENDING_SCHEMA = 'national-projects.package-copy-pending/1'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def checked_path(root, value, *, target=False):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('A package copy path must be a relative POSIX path.')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('.', '..') for part in path.parts) or ':' in value:
        raise ValueError('Unsafe package copy path: ' + value)
    if target and (len(path.parts) < 2 or path.parts[0] != 'docs'):
        raise ValueError('Only published docs/ copies may be restored.')
    if not target and path.parts[0] == 'docs':
        raise ValueError('A copy must refer directly to a retained source outside docs/.')
    destination = root.joinpath(*path.parts)
    if not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError('Package copy path escapes its workspace: ' + value)
    return destination


def pending_path(target):
    """Keep a short recovery marker beside a non-atomically copied file."""
    key = hashlib.sha256(target.name.encode('utf-8')).hexdigest()[:24]
    return target.parent / ('.package-copy-' + key + '.pending.json')


def pending_record(entry):
    return {'schema': PENDING_SCHEMA, 'path': entry['path'], 'source': entry['source'],
            'bytes': entry['bytes'], 'sha256': entry['sha256']}


def check_pending(marker, entry):
    """Reject an unknown marker rather than modifying a pre-existing file."""
    if marker.is_symlink() or not marker.is_file():
        raise ValueError('Invalid unfinished package-copy marker: ' + str(marker))
    try:
        recorded = json.loads(marker.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as error:
        raise ValueError('Unreadable unfinished package-copy marker; left unchanged: ' +
                         str(marker)) from error
    if recorded != pending_record(entry):
        raise ValueError('Unfinished package-copy marker differs from the manifest; '
                         'left unchanged: ' + entry['path'])


def check_interrupted_copy(target, entry):
    """A marked file must be complete even when ordinary files are unverified."""
    marker = pending_path(target)
    if not marker.exists() and not marker.is_symlink():
        return False
    check_pending(marker, entry)
    if target.exists():
        if (not target.is_file() or target.stat().st_size != entry['bytes'] or
                digest(target) != entry['sha256']):
            raise ValueError('Incomplete published copy after interrupted restoration; '
                             'left unchanged: ' + entry['path'] +
                             '. Rebuild docs/ or remove only this incomplete copy '
                             'before restoring it from the retained source.')
        return True
    return False


def create_pending(target, entry):
    """Persist recovery evidence before opening a non-atomic destination."""
    marker = pending_path(target)
    try:
        with marker.open('x', encoding='utf-8') as output:
            json.dump(pending_record(entry), output, ensure_ascii=False, sort_keys=True)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        check_pending(marker, entry)
    return marker


def finish_pending(target, entry):
    """Clear only a verified marker whose destination now contains all bytes."""
    if check_interrupted_copy(target, entry):
        pending_path(target).unlink()


def restore(root=ROOT, *, verify_existing=False, dry_run=False):
    root = Path(root).resolve()
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        return {'manifest': False, 'restored': 0, 'present': 0, 'planned': 0, 'bytes_restored': 0}
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    if data.get('schema') != SCHEMA or not isinstance(data.get('copies'), list):
        raise ValueError('Unsupported package copy manifest.')
    pending = []
    seen = set()
    present = 0
    verified_sources = {}
    completed_markers = []
    # Validate every missing copy before writing any file. A damaged retained
    # source cannot produce a partially restored publication.
    for entry in data['copies']:
        target = checked_path(root, entry['path'], target=True)
        source = checked_path(root, entry['source'])
        if entry['path'] in seen:
            raise ValueError('Duplicate target in package manifest: ' + entry['path'])
        seen.add(entry['path'])
        expected = entry['sha256']
        size = entry['bytes']
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
            raise ValueError('Invalid SHA-256 in package copy manifest.')
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError('Invalid file size in package copy manifest.')
        interrupted_complete = check_interrupted_copy(target, entry)
        if target.exists():
            if not target.is_file():
                raise ValueError('Copy destination is not a regular file: ' + entry['path'])
            if verify_existing and (target.stat().st_size != size or digest(target) != expected):
                raise ValueError('Existing copy differs; left unchanged: ' + entry['path'])
            if interrupted_complete:
                completed_markers.append((target, entry))
            present += 1
            continue
        if not source.is_file():
            raise FileNotFoundError('Retained package source is missing: ' + entry['source'])
        signature = (source, size, expected)
        if signature not in verified_sources:
            if source.stat().st_size != size or digest(source) != expected:
                raise ValueError('Retained package source has changed: ' + entry['source'])
            verified_sources[signature] = True
        pending.append((source, target, size, expected, entry))
    if dry_run:
        return {'manifest': True, 'restored': 0, 'present': present, 'planned': len(pending),
                'bytes_restored': 0, 'bytes_planned': sum(p[2] for p in pending)}
    restored = 0
    byte_count = 0
    for target, entry in completed_markers:
        finish_pending(target, entry)
    for source, target, size, expected, entry in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        # A concurrently created or edited file belongs to the user. Never replace it.
        if target.exists():
            finish_pending(target, entry)
            present += 1
            continue
        fd, temporary = tempfile.mkstemp(prefix='package-copy-', suffix='.tmp', dir=target.parent)
        temporary = Path(temporary)
        try:
            with os.fdopen(fd, 'wb') as output, source.open('rb') as input_file:
                shutil.copyfileobj(input_file, output)
            if temporary.stat().st_size != size or digest(temporary) != expected:
                raise ValueError('Source changed while restoring: ' + str(source))
            # Hard-link the completed temporary file atomically without replacing
            # a destination that another process created while bytes were copied.
            try:
                os.link(temporary, target)
            except FileExistsError:
                finish_pending(target, entry)
                present += 1
                continue
            except OSError:
                # Filesystems without hard-link support retain the same no-clobber
                # contract via exclusive creation. A durable marker makes a
                # process-killed partial copy distinguishable from a user edit.
                create_pending(target, entry)
                try:
                    with target.open('xb') as output:
                        try:
                            with temporary.open('rb') as input_file:
                                shutil.copyfileobj(input_file, output)
                        except BaseException:
                            output.close()
                            target.unlink(missing_ok=True)
                            raise
                except FileExistsError:
                    finish_pending(target, entry)
                    present += 1
                    continue
            finish_pending(target, entry)
            restored += 1
            byte_count += size
        finally:
            temporary.unlink(missing_ok=True)
    return {'manifest': True, 'restored': restored, 'present': present,
            'planned': len(pending), 'bytes_restored': byte_count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--verify', action='store_true', help='Also verify existing copies without overwriting them.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    print(json.dumps(restore(args.root, verify_existing=args.verify, dry_run=args.dry_run), ensure_ascii=False))


if __name__ == '__main__':
    main()
