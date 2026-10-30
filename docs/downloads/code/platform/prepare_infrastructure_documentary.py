#!/usr/bin/env python3
"""Prepare Infrastructure inputs from the byte-pinned shared passport corpus.

This import is optional for normal builds. The shared 98-document ZIP remains
one immutable file in the cumulative release. Every new project input names
that file, its checksum, original source URL and retrieval date explicitly.
"""
from pathlib import Path
import argparse, csv, hashlib, json, shutil, zipfile
from extract_infrastructure_passports import parse_passport

APP = Path(__file__).resolve().parents[1]
PROJECT = 'life_infrastructure'
REL = f'downloads/projects/{PROJECT}/documentary/'


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def prepare(root=APP, release=None):
    source = root/'inputs/healthtech/documentary'
    folder = root/'inputs/infrastructure/documentary'
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
                parsed = parse_passport(raw, meta)
                selected.append(parsed)
                name = f"{meta['document_id']}.html"
                dst = output/'sources'/name
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(raw)
                meta['download_path'] = REL+'sources/'+name
            manifest.append(meta)
    assert len(selected) == 13
    result = {**original, 'project_id':PROJECT,
        'archive_path':'inputs/healthtech/documentary/passports.zip',
        'shared_archive_download':'downloads/projects/health_technologies/documentary/documentary_sources.zip',
        'documents':manifest, 'selected_documents':len(selected),
        'selected_tokens':sum(d['document']['profile_token_count'] for d in selected),
        'source_archive_scope':'shared_98_document_corpus_with_all_13_infrastructure_passports',
        'author_report_expected':{'documents':98, 'projects':12, 'tokens':75539, 'infrastructure_tokens':5889},
        'retrieval_note':'Use the unchanged shared corpus whose passport bytes and individual retrieval dates were pinned in release 2.4.0-healthtech.1. No new retrieval or publication date is inferred from this import.'}
    dump(folder/'source_manifest.json', result)
    dump(output/'source_manifest.json', result)
    dump(folder/'parsed_infrastructure_passports.json', selected)
    if release:
        rows = list(csv.DictReader((release/'outputs/projects/life_infrastructure/targets.csv').open(encoding='utf-8-sig')))
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
        assert len(mappings) == 50
        dump(folder/'target_mapping.json', {'project_id':PROJECT, 'mapping':mappings, 'unmapped_cards':{'https://databudget.ru/projects/fp/262#passport-purpose-5':{'title':'Доля автомобильных дорог Минобороны России, соответствующих нормативным требованиям','reason':'The source card has no reviewed entry or EMISS identifier in the inherited 32-indicator registry.'}},
             'selection_policy':'Use national level when present, otherwise the corresponding federal card. Preserve all 51 source cards separately. Do not merge editions or sum duplicate levels.',
             'source_overrides':{'2.14.И.4':'59263'},
             'source_override_note':'Only total housing commissioning 59263 matches the passport volume target. Apartment and individual construction remain separate statistical components.'})
    parameters = json.loads((source/'text_parameters.json').read_text())
    parameters['equal_levels_formula']='normalize(0.5 * mean(normalized_national_document_vectors) + 0.5 * mean(normalized_federal_document_vectors)); no extra within-level normalization'
    parameters['author_claims'] = {'corpus_documents':98,'corpus_tokens':75539,'infrastructure_tokens':5889,'features':46519,'stemming_features':35510,'unigram_features':10329}
    dump(folder/'text_parameters.json', parameters)
    dump(folder/'budget_source.json', {
        'source_url':'https://base.garant.ru/411685865/',
        'source_input_path':'inputs/healthtech/documentary/budget_2027_2029.html',
        'source_html_download':'downloads/projects/health_technologies/documentary/budget_2027_2029.html',
        'source_html_sha256':hashlib.sha256((source/'budget_2027_2029.html').read_bytes()).hexdigest(),
        'table_label':'Таблица 4.1.4',
        'document':'Пояснительная записка к законопроекту № 615-9 о федеральном бюджете на 2027 год и плановый период 2028 и 2029 годов',
        'verification_status':'independently_parsed_legal_republication',
        'periods':{'2026':'Сводная бюджетная роспись на 01.09.2026','2027':'Внесённый законопроект','2028':'Внесённый законопроект','2029':'Внесённый законопроект'},
        'unit':'млн руб.', 'retrieval_basis':'Byte-pinned HTML already included in release 2.4.0-healthtech.1; original retrieval metadata retained.'})
    print(json.dumps({'selected_documents':len(selected),'selected_tokens':result['selected_tokens'],'shared_archive_download':result['shared_archive_download'],'target_mappings':50},ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=APP)
    parser.add_argument('--release', type=Path)
    args = parser.parse_args()
    prepare(args.root.resolve(), args.release)
