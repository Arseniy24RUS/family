#!/usr/bin/env python3
"""Prepare Environment inputs from the byte-pinned shared passport corpus.

This import is optional for normal builds. The shared 98-document ZIP remains
one immutable file in the cumulative release. Every new project input names
that file, its checksum, original source URL and retrieval date explicitly.
"""
from pathlib import Path
import argparse, csv, hashlib, json, shutil, zipfile
from extract_environment_passports import parse_passport

APP = Path(__file__).resolve().parents[1]
PROJECT = 'environment'
REL = f'downloads/projects/{PROJECT}/documentary/'


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def prepare(root=APP, release=None):
    source = root/'inputs/healthtech/documentary'
    folder = root/'inputs/environment/documentary'
    output = root/'public'/REL
    folder.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    original = json.loads((source/'source_manifest.json').read_text())
    archive = source/'passports.zip'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == original['archive_sha256']
    selected = []
    manifest = []
    with zipfile.ZipFile(archive) as shared:
        for item in original['documents']:
            meta = dict(item)
            if meta['project_id'] == PROJECT:
                raw = shared.read(meta['archive_entry'])
                assert hashlib.sha256(raw).hexdigest() == meta['sha256']
                name = f"{meta['document_id']}.html"
                dst = output/'sources'/name
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(raw)
                meta['download_path'] = REL+'sources/'+name
                parsed = parse_passport(raw, meta)
                selected.append(parsed)
            manifest.append(meta)
    assert len(selected) == 7
    result = {**original, 'project_id':PROJECT,
        'archive_path':'inputs/healthtech/documentary/passports.zip',
        'shared_archive_download':'downloads/projects/health_technologies/documentary/documentary_sources.zip',
        'documents':manifest, 'selected_documents':len(selected),
        'selected_tokens':sum(d['document']['profile_token_count'] for d in selected),
        'source_archive_scope':'shared_98_document_corpus_with_all_7_environment_passports',
        'author_report_expected':{'documents':98, 'projects':12, 'tokens':75539, 'environment_tokens':6110},
        'retrieval_note':'Use the unchanged shared corpus whose passport bytes and individual retrieval dates were pinned in release 2.4.0-healthtech.1. No new retrieval or publication date is inferred from this import.'}
    dump(folder/'source_manifest.json', result)
    dump(output/'source_manifest.json', result)
    dump(folder/'parsed_environment_passports.json', selected)
    if release:
        rows = list(csv.DictReader((release/'outputs/projects/environment/targets.csv').open(encoding='utf-8-sig')))
        mappings = {}
        for item in rows:
            if not item['source_url'].startswith('https://databudget.ru/'):
                continue
            key = item['source_url']+'#'+item['source_locator']
            if key in mappings:
                assert mappings[key]['indicator_code'] == item['indicator_code']
            mappings[key] = {'indicator_code':item['indicator_code'], 'source_sha256':item['source_sha256'],
                'title':item['target_indicator_name'], 'unit':item['unit'], 'mapping_status':item['mapping_status'],
                'mapping_id':item['mapping_id'], 'target_is_proxy':item['target_is_proxy']=='1',
                'origin':'reviewed_mapping_from_NationalProjects_Analytics_1.2.0'}
        assert len(mappings) == 24
        fire=next(t for d in selected for t in d['targets'] if t['document_id']=='fp_247' and t['card_id']=='passport-purpose-1')
        mappings[fire['source_url']+'#'+fire['card_id']] = {
            'indicator_code':'2.14.Ч6.1','source_sha256':fire['source_sha256'],
            'title':fire['title'],'unit':fire['unit'],'mapping_status':'discontinued_source_card_exact_title',
            'mapping_id':'environment-fire-card-source-review-2026-10-29','target_is_proxy':False,
            'origin':'independent_exact_title_and_registry_identifier_review',
            'note':'The source card states cessation on 21.05.2026. Retain the published 2025 target and all subsequent missing cells without inferring a current target.'}
        dump(folder/'target_mapping.json', {'project_id':PROJECT, 'mapping':mappings, 'unmapped_cards':{},
             'selection_policy':'Use national level when present, otherwise the corresponding federal card. Preserve all 25 source cards separately, including the discontinued fire card. Do not merge editions or sum duplicate levels.',
             'source_overrides':{}})
    parameters = json.loads((source/'text_parameters.json').read_text())
    parameters['equal_levels_formula']='normalize(0.5 * mean(normalized_national_document_vectors) + 0.5 * mean(normalized_federal_document_vectors)); no extra within-level normalization'
    parameters['author_claims'] = {'corpus_documents':98,'corpus_tokens':75539,'environment_tokens':6110,'features':46519,'stemming_features':35510,'unigram_features':10329}
    parameters['author_sensitivity'] = {
        'base':1.000,'stemming':0.982,'unigrams':1.000,
        'equal_levels':0.636,'federal_only':0.991,'national_only':0.300}
    parameters['author_nearest_project_all_variants'] = 'life_infrastructure'
    parameters['author_sensitivity_source'] = {'report':'expertise_environment_2026.docx','table':8,'source_block':266,'precision_decimals':3}
    parameters['stopword_source'] = 'Existing pinned research text_analysis.py; list length matches the author-described 120 words. Identity with the unstated author list is not independently established.'
    dump(folder/'text_parameters.json', parameters)
    budget_original=json.loads((source/'budget_source_verification.json').read_text())
    dump(folder/'budget_source.json', {
        'source_url':'https://base.garant.ru/411685865/',
        'source_input_path':'inputs/healthtech/documentary/budget_2027_2029.html',
        'source_html_download':'downloads/projects/health_technologies/documentary/budget_2027_2029.html',
        'source_html_sha256':hashlib.sha256((source/'budget_2027_2029.html').read_bytes()).hexdigest(),
        'retrieved_at':budget_original['retrieved_at'],
        'source_metadata_path':'inputs/healthtech/documentary/budget_source_verification.json',
        'table_label':'Таблица 4.1.6',
        'document':'Пояснительная записка к законопроекту № 615-9 о федеральном бюджете на 2027 год и плановый период 2028 и 2029 годов',
        'verification_status':'independently_parsed_legal_republication',
        'periods':{'2026':'Сводная бюджетная роспись на 01.09.2026','2027':'Внесённый законопроект','2028':'Внесённый законопроект','2029':'Внесённый законопроект'},
        'unit':'млн руб.', 'retrieval_basis':'Byte-pinned HTML already included in release 2.4.0-healthtech.1; original retrieval metadata retained.'})
    print(json.dumps({'selected_documents':len(selected),'selected_tokens':result['selected_tokens'],'shared_archive_download':result['shared_archive_download'],'target_mappings':25},ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=APP)
    parser.add_argument('--release', type=Path)
    args = parser.parse_args()
    prepare(args.root.resolve(), args.release)
