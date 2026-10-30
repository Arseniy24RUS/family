#!/usr/bin/env python3
"""Import the current Long and Active Life EMISS snapshot with self-contained source inputs.

python scripts/import_longlife_release.py --release /path/NationalProjects_Analytics_1.2.0
python scripts/import_longlife_release.py --from-inputs

The replay route needs no database or network. All 42 confirmed source contracts,
missing cells and original Excel, grid JSON or SDMX files are retained.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

from lxml import html
from longlife_data import ROOT, DATA, DOWNLOADS, RELEASE, STATISTICAL_AS_OF, source_rules, load, atomic, sha256, encode, normalize_payload, region_aliases, territory_key


def relative_path(value):
    return '/'.join(part for part in value.replace('\\', '/').split('/') if part)


def passport_fields(path):
    tree = html.fromstring(path.read_bytes())
    def after(label):
        elements = tree.xpath('//*[normalize-space(text())=$label]', label=label)
        values = []
        for element in elements:
            sibling = element.getnext()
            if sibling is not None:
                values.append(' '.join(sibling.text_content().split()))
        return values
    unit = after('Единицы измерения')
    if len(set(unit)) != 1:
        raise ValueError(f'Expected one explicit passport unit: {path}')
    methodology = tree.xpath('//*[@id="methodologyFull"]')
    return {'unit': unit[0], 'methodology': ' '.join(methodology[0].text_content().split()) if methodology else '',
            'periodicity': ' / '.join(after('Периодичность сбора (разработки) и временной ряд показателя')),
            'metadata_sha256': sha256(path)}


def make_bundle(path, payload, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr('input.json', encode(payload))
        for name, source in files.items():
            archive.write(source, 'source/' + name)


def run(root=ROOT, release=None, from_inputs=False):
    root = Path(root)
    registry = load(root / DATA / 'indicators.json')['items']
    aliases = region_aliases(root)
    regions = {str(r['id']): r for r in load(root / 'public/data/catalog.json')['regions']}
    contracts, payloads = [], []
    if not from_inputs:
        if release is None:
            raise ValueError('--release is required')
        release = Path(release)
        source_root = release / 'source_statistics'
        db = sqlite3.connect((source_root / 'data/national_projects.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        for indicator in registry:
            for sid in indicator['source_ids']:
                src = dict(db.execute('SELECT * FROM sources WHERE source_id=?', (sid,)).fetchone())
                snap_row = db.execute('SELECT s.* FROM snapshots s JOIN current_sources c USING(snapshot_id,source_id) WHERE source_id=?', (sid,)).fetchone()
                snapshot = dict(snap_row) if snap_row else None
                meta_paths = sorted((source_root / 'raw').glob('*/' + sid + '/metadata.html'))
                if not meta_paths:
                    raise FileNotFoundError('Saved official metadata missing: ' + sid)
                meta_path = meta_paths[-1]
                if snapshot:
                    original_meta = next((entry for entry in json.loads(snapshot['raw_manifest_json']) if entry.get('kind') == 'metadata'), None)
                    if original_meta:
                        meta_path = source_root / relative_path(original_meta['path'])
                passport = passport_fields(meta_path)
                metadata = json.loads(src['metadata_json'])
                config = {'source_id': sid, 'indicator_id': sid, 'indicator_codes': [indicator['indicator_code']],
                          'indicator_level': indicator['indicator_level'], 'federal_project_name': indicator['federal_project_name'],
                          'titles': list(dict.fromkeys([src['source_title'], *metadata.get('source_titles', [])])),
                          'title': src['source_title'], 'source_url': src['source_url'],
                          'unit': passport['unit'], 'first_year': 2025, 'dimension_defaults': {}, 'field_overrides': {},
                          'min_regional_count': 0, 'expected_period_types': ['год', 'месяц', 'накопительно с января'],
                          'methodology': passport['methodology'], 'periodicity': passport['periodicity'],
                          'metadata_sha256': passport['metadata_sha256'],
                          **source_rules(sid, src['source_title'], passport['unit'])}
                observations = []
                files = {meta_path.relative_to(source_root).as_posix(): meta_path}
                if snapshot:
                    if snapshot['acquired_at'][:10] > STATISTICAL_AS_OF:
                        raise ValueError('Research source lies after declared cutoff')
                    observations = [dict(r) for r in db.execute('SELECT * FROM observations WHERE snapshot_id=? ORDER BY observation_key', (snapshot['snapshot_id'],))]
                    snapshot_meta = json.loads(snapshot['metadata_json'])
                    territory_fields = [f for f in snapshot_meta.get('filters', []) if str(f.get('title', '')).startswith(('ОКАТО', 'ОКТМО', 'ОКСМ'))]
                    if len(territory_fields) > 1:
                        raise ValueError('Ambiguous original geography axis: ' + sid)
                    if territory_fields:
                        config['field_overrides']['territory'] = str(territory_fields[0]['field_id'])
                    regional_count = len({aliases.get(territory_key(r['territory_name'])) for r in observations if r['value_numeric'] is not None} - {None})
                    config['min_regional_count'] = int(regional_count * .6)
                    manifest = json.loads(snapshot['raw_manifest_json'])
                    config['export_format'] = 'excel' if any(e['path'].endswith('.xls') for e in manifest) else 'grid' if any(e['path'].endswith('.json.gz') for e in manifest) else 'sdmx'
                    for entry in manifest:
                        name = relative_path(entry['path'])
                        p = source_root / name
                        content = gzip.decompress(p.read_bytes()) if name.endswith('.gz') else p.read_bytes()
                        if entry.get('sha256') and hashlib.sha256(content).hexdigest() != entry['sha256']:
                            raise ValueError('Original source hash mismatch: ' + name)
                        files[name] = p
                        if entry.get('query_file'):
                            query_name = relative_path(entry['query_file'])
                            files[query_name] = source_root / query_name
                payload = {'schema_version': 1, 'project_id': 'long_active_life', 'research_release': RELEASE,
                           'statistical_as_of': STATISTICAL_AS_OF, 'config': config, 'snapshot': snapshot,
                           'metadata_source': meta_path.relative_to(source_root).as_posix(), 'observations': observations,
                           'evidence_files': [{'archive_path': 'source/' + name, 'sha256': sha256(path), 'bytes': path.stat().st_size} for name, path in files.items()]}
                make_bundle(root / DOWNLOADS / 'emiss_inputs' / (sid + '.zip'), payload, files)
                contracts.append(config)
                payloads.append(payload)
        db.close()
        config = {'schema_version': 1, 'project_id': 'long_active_life', 'base_url': 'https://www.fedstat.ru',
                  'allowed_hosts': ['www.fedstat.ru', 'fedstat.ru'], 'max_cells': 300000,
                  'timeout_seconds': 25, 'retries': 1, 'min_interval_seconds': 1.0,
                  'min_download_interval_seconds': 45, 'export_retry_delay_seconds': 15,
                  'failure_circuit_breaker': 3, 'sources': contracts,
                  'unmapped_indicators': [{'indicator_code': r['indicator_code'], 'title': r['indicator_name']} for r in registry if not r['source_ids']]}
        atomic(root / 'scripts/longlife_emiss_sources.json', config)
    else:
        config = load(root / 'scripts/longlife_emiss_sources.json')
        for contract in config['sources']:
            with zipfile.ZipFile(root / DOWNLOADS / 'emiss_inputs' / (contract['indicator_id'] + '.zip')) as archive:
                payload = json.loads(archive.read('input.json'))
                for evidence in payload.get('evidence_files', []):
                    if hashlib.sha256(archive.read(evidence['archive_path'])).hexdigest() != evidence['sha256']:
                        raise ValueError('Replay evidence checksum mismatch: ' + evidence['archive_path'])
            if payload['config'] != contract:
                raise ValueError('Replay input differs from committed source contract')
            payloads.append(payload)

    receipts, statuses = [], []
    for payload in payloads:
        contract = payload['config']
        sid = contract['indicator_id']
        packet = normalize_payload(payload, aliases, regions)
        output = root / DATA / 'series' / (sid + '.json')
        atomic(output, packet)
        bundle = root / DOWNLOADS / 'emiss_inputs' / (sid + '.zip')
        provenance = {'schema_version': 1, 'source_id': sid, 'source_url': contract['source_url'],
                      'research_release': RELEASE, 'statistical_as_of': STATISTICAL_AS_OF,
                      'snapshot_id': packet['snapshot_id'], 'acquired_at': packet['published_at'],
                      'origin_kind': packet['origin_kind'], 'unit': contract['unit'],
                      'observations': len(packet['observations']), 'numeric': sum(r['value'] is not None for r in packet['observations']),
                      'published_sha256': sha256(output), 'input_sha256': sha256(bundle),
                      'input_bundle': f'downloads/projects/long_active_life/statistical/emiss_inputs/{sid}.zip',
                      'published_file': f'data/projects/long_active_life/series/{sid}.json',
                      'period_policy': 'Separate annual facts and operational monitoring; no unverified December equivalence. Alcohol uses overlapping twelve-month windows; original source periods are preserved.',
                      'export_format': contract.get('export_format', 'sdmx'),
                      'missing_policy': 'No imputation, no substitution by a report image or by another indicator.'}
        atomic(root / DATA / 'provenance' / (sid + '.json'), provenance)
        receipts.append(provenance)
        statuses.append({'source_id': sid, 'title': contract['title'], 'state': 'verified_source_snapshot' if packet['observations'] else 'metadata_only',
                         'checked_at': packet['published_at'] or STATISTICAL_AS_OF,
                         'last_success': packet['published_at'], 'published_at': packet['published_at'],
                         'published_file': provenance['published_file'], 'rows': provenance['observations'],
                         'message': 'Проверенный числовой срез ЕМИСС.' if packet['observations'] else 'Метаданные источника опубликованы, числовая таблица в исходной публикации отсутствует.'})
    checked = max(r['checked_at'] for r in statuses)
    atomic(root / DATA / 'refresh-status.json', {'schema_version': 1, 'project_id': 'long_active_life',
           'state': 'imported_verified_snapshot', 'checked_at': checked, 'published_at': checked,
           'statistical_as_of': STATISTICAL_AS_OF, 'last_success': checked,
           'message': 'Проверенные данные ЕМИСС по состоянию на 15.10.2026. Дата сборки платформы не является датой обновления статистики.',
           'sources': statuses, 'unmapped_indicators': config['unmapped_indicators']})
    atomic(root / DATA / 'import-validation.json', {'schema_version': 1, 'source_contracts': len(receipts),
           'numeric_sources': sum(bool(r['numeric']) for r in receipts), 'observations': sum(r['observations'] for r in receipts),
           'numeric': sum(r['numeric'] for r in receipts), 'sources': receipts,
           'replay_command': 'python scripts/import_longlife_release.py --from-inputs'})
    print(json.dumps({'sources': len(receipts), 'observations': sum(r['observations'] for r in receipts), 'numeric': sum(r['numeric'] for r in receipts)}))
    return receipts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--release', type=Path)
    parser.add_argument('--from-inputs', action='store_true')
    args = parser.parse_args()
    run(args.root, args.release, args.from_inputs)
