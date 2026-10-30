#!/usr/bin/env python3
"""Build and verify a size-limited GitHub Pages publication from complete docs/.

The complete docs/ tree and its source data are read-only inputs. Normalized
series and large runtime JSON receive a lossless transport encoding in the
separate output: an original-URL envelope and a deterministic .json.gz file.
Downloadable source documents are never transformed. The application and static
research pages opt in through a meta tag; their JSON downloads retain the exact
original bytes as well.

Default copying is portable and isolates output bytes. --link is an explicit
space-saving option for local QA; every altered output is written atomically so
that a hardlink can never alter its source. Do not edit docs/ during this build.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import os
import posixpath
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import BinaryIO
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA = 'national-projects.series-transport/2'
LEGACY_MANIFEST_SCHEMA = 'national-projects.series-transport/1'
REDIRECT_SCHEMA = 'national-projects.series-redirect/1'
REPORT_SCHEMA = 'national-projects.pages-build/1'
MANIFEST_PATH = 'data/series-transport.json'
SERIES = re.compile(r'data/projects/[a-zA-Z0-9_-]+/series/[a-zA-Z0-9_-]+\.json\Z')
RUNTIME_JSON = re.compile(r'data/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+\.json\Z')
RUNTIME_MIN_BYTES = 64 * 1024
STATIC_ENTRY = 'src/core/data-transport-entry.js'
META = b'<meta name="series-transport" content="data/series-transport.json">'
LIMIT_BYTES = 1_000_000_000
CHUNK = 8 * 1024 * 1024
IGNORED_DIRS = {'node_modules', '__pycache__', 'qa', 'deliverables'}
TEMP_SUFFIXES = {'.tmp', '.pyc', '.pyo', '.swp', '.swo'}
# Deliberate allowlist of static assets, research documents and downloadable code.
# Unknown non-hidden files fail the build rather than disappearing silently.
PUBLISHABLE_SUFFIXES = {
    '.html', '.htm', '.css', '.js', '.mjs', '.cjs', '.json', '.geojson',
    '.jsonl', '.webmanifest', '.xml', '.txt', '.md', '.csv', '.tsv',
    '.zip', '.gz', '.pdf', '.docx', '.xlsx', '.xls', '.ipynb',
    '.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif', '.ico', '.avif',
    '.woff', '.woff2', '.ttf', '.otf', '.eot', '.wasm',
    '.py', '.sh', '.bat', '.ps1', '.yaml', '.yml', '.toml',
    '.ts', '.tsx', '.jsx', '.mp4', '.webm', '.mp3', '.ogg', '.wav',
}


def fingerprint_stream(stream: BinaryIO) -> tuple[int, str]:
    size, digest = 0, hashlib.sha256()
    for block in iter(lambda: stream.read(CHUNK), b''):
        size += len(block)
        digest.update(block)
    return size, digest.hexdigest()


def fingerprint(path: Path) -> tuple[int, str]:
    with path.open('rb') as stream:
        return fingerprint_stream(stream)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf-8')


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp',
                                        dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_gzip(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.' + destination.name + '.',
                                        suffix='.tmp', dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            # GzipFile omits an original filename and writes a stable OS byte.
            # mtime=0 makes identical inputs produce identical transport bytes.
            with gzip.GzipFile(filename='', mode='wb', fileobj=output,
                               compresslevel=9, mtime=0) as compressed:
                with source.open('rb') as incoming:
                    shutil.copyfileobj(incoming, compressed, CHUNK)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def source_inventory(source: Path) -> tuple[list[Path], list[dict[str, str]]]:
    files: list[Path] = []
    excluded: list[dict[str, str]] = []
    for directory, directories, filenames in os.walk(source, followlinks=False):
        parent = Path(directory)
        retained = []
        for name in sorted(directories):
            path = parent / name
            relative = path.relative_to(source).as_posix()
            if name.startswith('.') or name in IGNORED_DIRS:
                excluded.append({'path': relative + '/', 'reason': 'unpublished_directory'})
            elif path.is_symlink():
                raise ValueError('A publishable directory is a symlink: ' + relative)
            else:
                retained.append(name)
        directories[:] = retained
        for name in sorted(filenames):
            path = parent / name
            relative = path.relative_to(source).as_posix()
            if ((name.startswith('.') and relative != '.nojekyll') or
                    path.suffix.lower() in TEMP_SUFFIXES or name.endswith('~')):
                excluded.append({'path': relative, 'reason': 'hidden_or_temporary'})
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError('A publishable asset is not a regular file: ' + relative)
            if relative != '.nojekyll' and path.suffix.lower() not in PUBLISHABLE_SUFFIXES:
                raise ValueError('File type is outside the publication allowlist: ' + relative)
            files.append(path)
    return sorted(files), excluded


def injected_index(source_bytes: bytes, relative: str = 'index.html') -> bytes:
    if re.search(rb'<meta\b[^>]*\bname\s*=\s*[\'"]series-transport[\'"]',
                 source_bytes, flags=re.I):
        raise ValueError('Source index.html already opts into series transport; use complete docs/.')
    match = re.search(rb'</head\s*>', source_bytes, flags=re.I)
    if not match:
        raise ValueError('Source index.html has no closing head element.')
    directory = posixpath.dirname(relative) or '.'
    manifest_path = posixpath.relpath(MANIFEST_PATH, directory)
    meta = f'<meta name="series-transport" content="{manifest_path}">'.encode()
    # Standalone articles do not run app.js. Install the same adapter there so
    # existing direct JSON links still download the source, never its envelope.
    entry = b''
    if relative != 'index.html':
        entry_path = posixpath.relpath(STATIC_ENTRY, directory)
        entry = f'<script type="module" src="{entry_path}"></script>\n'.encode()
    return source_bytes[:match.start()] + meta + b'\n' + entry + source_bytes[match.start():]


def transport_selected(relative: str, size: int) -> bool:
    return bool(SERIES.fullmatch(relative) or
                (RUNTIME_JSON.fullmatch(relative) and size >= RUNTIME_MIN_BYTES))


def needs_adapter(relative: str) -> bool:
    return relative == 'index.html' or (relative.startswith('research/') and
                                       relative.endswith('.html'))


def rewrite_runtime_links(source_bytes: bytes, relative: str,
                          transport_paths: set[str]) -> tuple[bytes, int]:
    """Static readers without JavaScript receive a real gzip, never a JSON stub.

    The download adapter recognizes the same .json.gz URL and restores the plain
    filename when JavaScript is available. Source documents and external URLs
    are untouched. Resolve only package-relative links, preserving query/hash.
    """
    count = 0

    def replace(match):
        nonlocal count
        value = html.unescape(match.group(3).decode('utf-8'))
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or parsed.path.startswith('/'):
            return match.group(0)
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), parsed.path))
        if resolved not in transport_paths:
            return match.group(0)
        updated = urlunsplit((parsed.scheme, parsed.netloc, parsed.path + '.gz',
                              parsed.query, parsed.fragment))
        count += 1
        return match.group(1) + match.group(2) + html.escape(updated, quote=True).encode('utf-8') + match.group(2)

    return re.sub(rb'(\bhref\s*=\s*)([\'\"])([^\'\"]+)\2', replace, source_bytes, flags=re.I), count


def validate_output_target(source: Path, output: Path) -> None:
    if output == ROOT or ROOT.is_relative_to(output):
        raise ValueError('Output cannot be the repository or an ancestor of it.')
    if source == output or source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError('Source and publication output must be separate, non-nested directories.')
    if output.is_symlink():
        raise ValueError('Output cannot be a symlink.')
    if not output.exists():
        return
    if not output.is_dir():
        raise ValueError('Output already exists and is not a directory.')
    if not any(output.iterdir()):
        return
    marker = output / MANIFEST_PATH
    try:
        manifest = json.loads(marker.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('Refusing to replace a nonempty output without a generated transport manifest: '
                         + str(output)) from error
    if manifest.get('schema') not in {MANIFEST_SCHEMA, LEGACY_MANIFEST_SCHEMA} or not isinstance(manifest.get('files'), list):
        raise ValueError('Existing output does not identify a publication generated by this script.')


def publish_stage(stage: Path, output: Path) -> None:
    """Replace only a preflight-checked generated output after full verification."""
    if not output.exists():
        os.replace(stage, output)
        return
    backup = Path(tempfile.mkdtemp(prefix='.' + output.name + '.previous-', dir=output.parent))
    backup.rmdir()
    os.replace(output, backup)
    try:
        os.replace(stage, output)
    except BaseException:
        os.replace(backup, output)
        raise
    else:
        shutil.rmtree(backup)


def build(source: Path, output: Path, *, link: bool = False,
          report_path: Path | None = None) -> dict[str, object]:
    source = source.resolve(strict=True)
    # Check the leaf before resolving, then normalize relative paths and '..'.
    if output.is_symlink():
        raise ValueError('Output cannot be a symlink.')
    output = output.resolve()
    if not source.is_dir():
        raise ValueError('Source must be a complete docs/ directory.')
    validate_output_target(source, output)
    if report_path is not None:
        if report_path.is_symlink():
            raise ValueError('Build report cannot be a symlink.')
        report_path = report_path.resolve()
        if (report_path == source or report_path.is_relative_to(source) or
                report_path == output or report_path.is_relative_to(output)):
            raise ValueError('Build report must be outside both source and publication output.')
    files, excluded = source_inventory(source)
    relative_paths = {path.relative_to(source).as_posix() for path in files}
    if not {'index.html', '.nojekyll'}.issubset(relative_paths):
        raise ValueError('Complete docs/ must contain index.html and .nojekyll.')
    if MANIFEST_PATH in relative_paths:
        raise ValueError('The source already contains a publication transport manifest.')
    series_paths = sorted(path for path in relative_paths if SERIES.fullmatch(path))
    if not series_paths:
        raise ValueError('No normalized project-series JSON was found.')
    transport_paths = {p.relative_to(source).as_posix() for p in files
                       if transport_selected(p.relative_to(source).as_posix(), p.stat().st_size)}
    adapted_html = {p for p in relative_paths if needs_adapter(p)}
    if len(adapted_html) > 1 and STATIC_ENTRY not in relative_paths:
        raise ValueError('Static research pages require the JSON download adapter: ' + STATIC_ENTRY)
    collisions = [path + '.gz' for path in transport_paths if path + '.gz' in relative_paths]
    if collisions:
        raise ValueError('Compressed transport names collide with source files: ' + ', '.join(collisions))
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + output.name + '.build-', dir=output.parent))
    records: list[dict[str, object]] = []
    originals: dict[str, tuple[int, str]] = {}
    expected: dict[str, tuple[int, str]] = {}
    linked_count, copied_count, rewritten_link_count = 0, 0, 0
    try:
        for source_file in files:
            relative = source_file.relative_to(source).as_posix()
            original = fingerprint(source_file)
            originals[relative] = original
            destination = stage / relative
            if relative in transport_paths:
                compressed_path = relative + '.gz'
                atomic_gzip(source_file, stage / compressed_path)
                compressed = fingerprint(stage / compressed_path)
                record: dict[str, object] = {
                    'path': relative, 'compressed_path': compressed_path,
                    'bytes': original[0], 'sha256': original[1],
                    'compressed_bytes': compressed[0], 'compressed_sha256': compressed[1],
                }
                records.append(record)
                stub = json_bytes({'schema': REDIRECT_SCHEMA, **record})
                atomic_write(destination, stub)
                expected[relative] = (len(stub), hashlib.sha256(stub).hexdigest())
                expected[compressed_path] = compressed
            elif relative in adapted_html:
                html_bytes, rewritten = rewrite_runtime_links(source_file.read_bytes(), relative, transport_paths)
                rewritten_link_count += rewritten
                index = injected_index(html_bytes, relative)
                atomic_write(destination, index)
                expected[relative] = (len(index), hashlib.sha256(index).hexdigest())
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if link:
                    os.link(source_file, destination)
                    linked_count += 1
                else:
                    shutil.copy2(source_file, destination)
                    copied_count += 1
                expected[relative] = original
        manifest = {'schema': MANIFEST_SCHEMA, 'files': records}
        manifest_bytes = json_bytes(manifest)
        atomic_write(stage / MANIFEST_PATH, manifest_bytes)
        expected[MANIFEST_PATH] = (len(manifest_bytes), hashlib.sha256(manifest_bytes).hexdigest())

        actual_paths = set()
        for path in stage.rglob('*'):
            if path.is_symlink():
                raise ValueError('Output unexpectedly contains a symlink: ' + str(path))
            if path.is_file():
                actual_paths.add(path.relative_to(stage).as_posix())
        if actual_paths != set(expected):
            missing = sorted(set(expected) - actual_paths)
            extra = sorted(actual_paths - set(expected))
            raise ValueError('Publication file inventory differs from the verified plan. '
                             f'Missing ({len(missing)}): {missing[:12]}; '
                             f'extra ({len(extra)}): {extra[:12]}.')
        for relative, required in expected.items():
            if fingerprint(stage / relative) != required:
                raise ValueError('Published bytes differ from the plan: ' + relative)
        for record in records:
            with gzip.open(stage / str(record['compressed_path']), 'rb') as stream:
                decoded = fingerprint_stream(stream)
            if decoded != (record['bytes'], record['sha256']):
                raise ValueError('Gzip roundtrip does not reproduce source bytes: ' + str(record['path']))
            stub = json.loads((stage / str(record['path'])).read_text(encoding='utf-8'))
            if stub != {'schema': REDIRECT_SCHEMA, **record}:
                raise ValueError('Forwarding envelope does not match its transport record.')
        if json.loads((stage / MANIFEST_PATH).read_text(encoding='utf-8')) != manifest:
            raise ValueError('Published transport manifest differs from the verified records.')
        # Source immutability includes every published file, even during --link.
        for relative, required in originals.items():
            if fingerprint(source / relative) != required:
                raise ValueError('Source changed during publication build: ' + relative)
        after_files, _ = source_inventory(source)
        if {p.relative_to(source).as_posix() for p in after_files} != relative_paths:
            raise ValueError('Source file inventory changed during publication build.')
        total = sum(size for size, _ in expected.values())
        if total > LIMIT_BYTES:
            raise ValueError(f'Publication is {total:,} bytes; maximum is {LIMIT_BYTES:,}.')
        original_total = sum(size for size, _ in originals.values())
        report: dict[str, object] = {
            'schema': REPORT_SCHEMA,
            'source': str(source), 'output': str(output),
            'copy_mode': 'hardlink_unchanged_files' if link else 'independent_copies',
            'input_files': len(originals), 'output_files': len(expected),
            'input_bytes': original_total, 'output_bytes': total,
            'limit_bytes': LIMIT_BYTES, 'headroom_bytes': LIMIT_BYTES - total,
            'saved_bytes': original_total - total,
            'series_count': sum(bool(SERIES.fullmatch(str(r['path']))) for r in records),
            'series_original_bytes': sum(int(r['bytes']) for r in records if SERIES.fullmatch(str(r['path']))),
            'series_compressed_bytes': sum(int(r['compressed_bytes']) for r in records if SERIES.fullmatch(str(r['path']))),
            'runtime_json_count': sum(not SERIES.fullmatch(str(r['path'])) for r in records),
            'transport_count': len(records),
            'transport_original_bytes': sum(int(r['bytes']) for r in records),
            'transport_compressed_bytes': sum(int(r['compressed_bytes']) for r in records),
            'html_adapters_injected': len(adapted_html),
            'static_json_links_rewritten': rewritten_link_count,
            'unchanged_files_verified': len(originals) - len(records) - len(adapted_html),
            'source_files_verified_unchanged': len(originals),
            'gzip_roundtrips_verified': len(records),
            'copied_files': copied_count, 'linked_files': linked_count,
            'excluded_paths': excluded,
            'checks': {
                'every_source_unchanged': True,
                'every_unmodified_output_byte_identical': True,
                'every_transport_hash_and_roundtrip': True,
                'every_forwarding_envelope': True,
                'exact_output_inventory': True,
                'publication_within_size_limit': True,
            },
            'transport_manifest': MANIFEST_PATH,
            'transport_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
            'original_index_sha256': originals['index.html'][1],
            'published_index_sha256': expected['index.html'][1],
        }
        validate_output_target(source, output)
        publish_stage(stage, output)
        if report_path is not None:
            atomic_write(report_path, json_bytes(report))
        return report
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'docs',
                        help='Complete, validated static source (default: docs/).')
    parser.add_argument('--output', '--target', dest='output', type=Path,
                        default=ROOT / '.pages', help='Separate publication directory (default: .pages/).')
    parser.add_argument('--link', action='store_true',
                        help='Hardlink unchanged files for local QA; default creates independent copies.')
    parser.add_argument('--report', type=Path,
                        help='Write a verification JSON outside source and output directories.')
    arguments = parser.parse_args()
    try:
        report = build(arguments.source, arguments.output, link=arguments.link,
                       report_path=arguments.report)
    except (OSError, ValueError, EOFError) as error:
        print('Publication build failed: ' + str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, separators=(',', ':'), allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
