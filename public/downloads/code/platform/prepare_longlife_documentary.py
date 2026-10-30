#!/usr/bin/env python3
"""Import compact Longlife documentary inputs from the pinned research release.

Normal platform builds need only the bundled inputs and original documents.
The full research database is neither required nor copied into the platform.
"""
from pathlib import Path
import argparse, csv, gzip, hashlib, json, shutil, zipfile

APP = Path(__file__).resolve().parents[1]
PROJECT = 'long_active_life'
BASE = f'downloads/projects/{PROJECT}/documentary/'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def rows(path):
    with (gzip.open(path, 'rt', encoding='utf-8-sig') if path.suffix == '.gz' else path.open(encoding='utf-8-sig', newline='')) as stream:
        return list(csv.DictReader(stream))


def prepare(release, root=APP):
    output = root / 'public' / BASE
    output.mkdir(parents=True, exist_ok=True)
    input_dir = root / 'inputs/longlife/documentary'
    text_dir = release / 'outputs/research/text/tables'
    documents = [r for r in rows(text_dir / 'documents.csv') if r['project_id'] == PROJECT]
    assert len(documents) == 15
    ids = {d['document_id'] for d in documents}
    tables, provenance = {}, []
    names = ['documents', 'document_projects', 'frame_scores', 'project_frame_scores', 'tfidf_top_terms', 'document_similarity', 'project_similarity', 'stemming_project_sensitivity', 'nodes', 'edges', 'link_coverage', 'result_indicator_shared_task', 'semantic_candidates', 'network_node_metrics', 'network_summary', 'link_claims', 'indicator_registry_links', 'domain_evidence', 'lexical_frequencies', 'formal_text_features', 'concept_cooccurrence', 'kwic', 'units']
    for name in names:
        path = text_dir / (name + '.csv')
        if not path.exists():
            path = text_dir / (name + '.csv.gz')
        selected = [r for r in rows(path) if r.get('project_id') == PROJECT or r.get('project_a') == PROJECT or r.get('project_b') == PROJECT or r.get('document_id') in ids]
        tables[name] = selected
        provenance.append({'path': path.relative_to(release).as_posix(), 'sha256': sha(path), 'size_bytes': path.stat().st_size, 'selected_rows': len(selected)})
    for name in ['f_cashflows', 'f_documents', 'f_federal_shares', 'f_concentration', 'f_project_year', 'f_source_reconciliation']:
        path = release / 'outputs/research/finance' / (name + '.csv')
        selected = [r for r in rows(path) if r.get('project_id') == PROJECT]
        tables[name] = selected
        provenance.append({'path': path.relative_to(release).as_posix(), 'sha256': sha(path), 'size_bytes': path.stat().st_size, 'selected_rows': len(selected)})
    path = release / 'outputs/tables/targets.csv'
    tables['targets'] = [r for r in rows(path) if r.get('project_id') == PROJECT]
    provenance.append({'path': path.relative_to(release).as_posix(), 'sha256': sha(path), 'size_bytes': path.stat().st_size, 'selected_rows': len(tables['targets'])})
    shared = root / 'public/downloads/projects/youth_children/documentary/documentary_inputs.json.gz'
    with gzip.open(shared, 'rt', encoding='utf-8') as stream:
        profiles = json.load(stream)['profiles']
    assert len(profiles['documents']) == 137
    for profile in profiles['documents']:
        assert hashlib.sha256(profile['text'].encode()).hexdigest() == profile['profile_text_sha256']
    manual = input_dir / 'manual_direct_links.csv'
    manual_provenance = json.loads((input_dir / 'manual_review_provenance.json').read_text())
    assert sha(manual) == manual_provenance['sha256']
    manual_rows = rows(manual)
    assert len(manual_rows) == 24
    for number in range(1, 7):
        assert sum(int(r['documentary_weight_percent']) for r in manual_rows if int(r['indicator_number']) == number) == 100
    source_documents = []
    for document in documents:
        source = release / document['local_file']
        assert sha(source) == document['local_file_sha256'] == document['source_sha256']
        target = output / 'sources' / (document['source_sha256'] + source.suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_documents.append({**document, 'archive_entry': 'sources/' + target.name, 'download_path': BASE + 'sources/' + target.name, 'sha256': sha(source), 'size_bytes': source.stat().st_size})
    demographic = json.loads((input_dir / 'rosstat_life_expectancy_2023_source.json').read_text())
    for record in demographic['files']:
        assert sha(input_dir / record['name']) == record['sha256']
    demographic_2024 = json.loads((input_dir / 'rosstat_life_expectancy_2024_source.json').read_text())
    assert sha(input_dir / demographic_2024['source_excerpt']) == demographic_2024['excerpt_sha256']
    assert demographic_2024['geography'] == 'Российская Федерация'
    assert demographic_2024['downloaded_original_pdf'] is False
    supplemental_files = ['manual_direct_links.csv', 'manual_review_provenance.json', 'rosstat_life_expectancy_2023.csv', 'rosstat_life_expectancy_2023_source.txt', 'rosstat_life_expectancy_2023_source.json', 'rosstat_life_expectancy_2024_source.txt', 'rosstat_life_expectancy_2024_source.json']
    for name in supplemental_files:
        shutil.copy2(input_dir / name, output / name)
    inputs = {'schema_version': 1, 'project_id': PROJECT, 'source_release': 'NationalProjects_Analytics_1.2.0', 'source_release_sha256': '4efffb01a65c67d6ed7a07dc4a16b4c6ed7d08226dd887a36721c6f9d72eca86', 'documentary_snapshot': '2026-10-19', 'tables': tables, 'profiles': profiles, 'source_provenance': provenance, 'source_documents': source_documents, 'manual_reviewed_links': manual_rows, 'manual_review_provenance': manual_provenance, 'demographic_context': {'rows': rows(input_dir / 'rosstat_life_expectancy_2023.csv'), 'provenance': demographic}, 'profile_replication_basis': {'source': 'Previously verified fixed 137-document research profiles', 'input_sha256': sha(shared)}, 'normalization': 'Amounts retain decimal strings. Source editions, annual periods and documentary weights are not collapsed.', 'limits': ['Passport plans do not establish expenditure execution.', 'Documentary weights do not estimate causal effects.', 'Target editions remain separate.', 'Published finance horizons differ between federal projects.']}
    inputs['demographic_context']['provenance_2024'] = demographic_2024
    data = gzip.compress((json.dumps(inputs, ensure_ascii=False, allow_nan=False) + '\n').encode(), mtime=0)
    for target in [root / 'inputs/longlife/documentary_inputs.json.gz', output / 'documentary_inputs.json.gz']:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    dump(output / 'source_manifest.json', {'project_id': PROJECT, 'documents': source_documents, 'input_provenance': provenance, 'manual_review': manual_provenance, 'demographic_context': demographic, 'demographic_context_2024': demographic_2024})
    shutil.copy2(release / 'outputs/research/text/METHODS_RU.md', output / 'text_methods.md')
    shutil.copy2(release / 'outputs/research/finance/METHODS_RU.md', output / 'finance_methods.md')
    code = output / 'original_code'
    code.mkdir(exist_ok=True)
    for name in ['text_analysis.py', 'validate_text_analysis.py', 'finance_analysis.py', 'verify_finance.py', 'requirements-tested.txt']:
        shutil.copy2(release / 'research' / name, code / name)
    with zipfile.ZipFile(output / 'documentary_sources.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in ['source_manifest.json', *supplemental_files]:
            archive.write(output / name, name)
        for document in source_documents:
            archive.write(root / 'public' / document['download_path'], document['archive_entry'])
    print(json.dumps({'documents': len(source_documents), 'input_gzip_bytes': len(data), 'tables': {k: len(v) for k, v in tables.items()}, 'manual_direct_links': len(manual_rows)}, ensure_ascii=False, indent=2))
    return inputs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=APP)
    args = parser.parse_args()
    prepare(args.release.resolve(), args.root.resolve())
