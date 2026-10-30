#!/usr/bin/env python3
"""Validate and publish the current author editions without recomputing analyses.

PDFs are committed once, under public/downloads/projects/<id>/current/.
Their authoritative hashes and unchanged author DOCX inputs live in the edition
manifest. A regular offline build requires only Python's standard library; it
never depends on an office application, mutates an author file, or silently
replaces the inputs of the project-specific analytical extractors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

SCHEMA = 'national-projects.current-reports/1'
EDITION = '2026-10-30'
EXPECTED_PROJECTS = (
    'family', 'long_active_life', 'youth_children', 'tourism', 'personnel',
    'life_infrastructure', 'efficient_transport', 'environment',
    'international_export', 'data_economy', 'competitive_economy',
    'health_technologies',
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def local_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError(f'Invalid report path: {relative!r}')
    target = (root / relative).resolve()
    if Path(relative).is_absolute() or not target.is_relative_to(root.resolve()):
        raise ValueError(f'Report path outside project root: {relative}')
    return target


def verify(path: Path, expected: dict, kind: str) -> None:
    if not path.is_file():
        raise ValueError(f'Missing current {kind}: {path}')
    if path.stat().st_size != expected['bytes'] or sha256(path) != expected['sha256']:
        raise ValueError(f'Current {kind} does not match the author edition manifest: {path}')
    with path.open('rb') as stream:
        magic = stream.read(5)
    if kind == 'PDF' and magic != b'%PDF-':
        raise ValueError(f'Invalid PDF signature: {path}')
    if kind == 'DOCX' and not magic.startswith(b'PK\x03\x04'):
        raise ValueError(f'Invalid DOCX signature: {path}')


def write_if_changed(path: Path, content: bytes) -> None:
    if path.exists() and path.read_bytes() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(content)
    temporary.replace(path)


def build(root: Path, edition: str = EDITION) -> dict:
    root = root.resolve()
    if len(edition) != 10 or any(ch not in '0123456789-' for ch in edition):
        raise ValueError('Edition must use YYYY-MM-DD')
    manifest_path = root / 'inputs/revised_expertises' / ('edition-' + edition) / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema') != SCHEMA or manifest.get('edition_date') != edition:
        raise ValueError('Current reports manifest identity mismatch')
    reports = manifest.get('reports', [])
    identities = [report['project_id'] for report in reports]
    if len(identities) != len(set(identities)) or set(identities) != set(EXPECTED_PROJECTS):
        raise ValueError('Current author edition must contain each of the 12 projects exactly once')

    # Check the complete edition before copying or writing any output.
    planned_copies = []
    public_reports = []
    for report in reports:
        identity = report['project_id']
        if report.get('edition_date') != edition or not report.get('title'):
            raise ValueError(f'Invalid current report metadata: {identity}')
        prefix = f'downloads/projects/{identity}/current/'
        for kind in ('pdf', 'docx'):
            info = report[kind]
            if not info['url'].startswith(prefix) or not info['url'].endswith('.' + kind):
                raise ValueError(f'Wrong {kind} publication path: {identity}')
            if Path(info['url']).name != info['filename']:
                raise ValueError(f'Filename and URL disagree: {identity}')
            if not isinstance(info['bytes'], int) or info['bytes'] <= 0:
                raise ValueError(f'Empty report file: {identity}')
        if not isinstance(report['pdf']['pages'], int) or report['pdf']['pages'] <= 0:
            raise ValueError(f'Missing page count: {identity}')
        original = local_file(root, report['source_docx'])
        published_docx = local_file(root / 'public', report['docx']['url'])
        published_pdf = local_file(root / 'public', report['pdf']['url'])
        verify(original, report['docx'], 'DOCX')
        verify(published_pdf, report['pdf'], 'PDF')
        planned_copies.append((original, published_docx, report['docx']))
        public_reports.append({key: report[key] for key in (
            'project_id', 'title', 'edition_date', 'edition_label', 'pdf', 'docx', 'provenance'
        )})

    for original, destination, expected in planned_copies:
        if destination.exists() and destination.stat().st_size == expected['bytes'] and sha256(destination) == expected['sha256']:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + '.tmp')
        shutil.copyfile(original, temporary)
        temporary.replace(destination)
        verify(destination, expected, 'DOCX')

    public_manifest = {
        'schema': SCHEMA,
        'edition_date': edition,
        'source_archive': manifest['source_archive'],
        'reports': public_reports,
    }
    output = root / 'public/data/current-reports.json'
    write_if_changed(output, (json.dumps(public_manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    return public_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--edition', default=EDITION)
    args = parser.parse_args()
    manifest = build(args.root, args.edition)
    reports = manifest['reports']
    print(f"Current author reports: {len(reports)} PDF + {len(reports)} unchanged DOCX; "
          f"{sum(report['pdf']['pages'] for report in reports)} PDF pages; edition {manifest['edition_date']}.")


if __name__ == '__main__':
    main()
