#!/usr/bin/env python3
"""Import the checked Health Technologies exports and retain self-contained inputs.

--from-inputs uses the acquired files under inputs/healthtech_statistics.
--from-bundles replays the published ZIPs without the research archive or inputs.
This explicit import restores the source snapshot. Routine builds do not run it.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

from healthtech_data import ROOT, PROJECT, DATA, DOWNLOADS, INPUTS, REPORT_DATE, atomic, encode, load, sha256, source_rule, observation, csv_write, CSV_FIELDS
from healthtech_formats import parse_export


def bundle_bytes(items):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name, body in sorted(items.items()):
            info = zipfile.ZipInfo(name, date_time=(2026,10,29,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info,body)
    return buffer.getvalue()


def read_bundle(path):
    with zipfile.ZipFile(path) as archive:
        if any(i.file_size > 30_000_000 for i in archive.infolist()):
            raise ValueError('Oversized input bundle')
        return {name:archive.read(name) for name in archive.namelist()}


def run(root=ROOT, from_bundles=False):
    root = Path(root)
    if from_bundles:
        global_files = read_bundle(root / DOWNLOADS / 'inputs/registry.zip')
        registry = json.loads(global_files['registry_input.json'])
        acquisition = json.loads(global_files['retrieval_manifest.json'])
    else:
        registry = load(root / INPUTS / 'registry_input.json')
        acquisition = load(root / INPUTS / 'nsedc/retrieval_manifest.json')
        global_files = {'registry_input.json':(root/INPUTS/'registry_input.json').read_bytes(),
                        'retrieval_manifest.json':(root/INPUTS/'nsedc/retrieval_manifest.json').read_bytes(),
                        'emiss_organizations_saved.html.gz':(root/INPUTS/'emiss_organizations_saved.html.gz').read_bytes()}
        atomic(root / DOWNLOADS / 'inputs/registry.zip',bundle_bytes(global_files))
    cards, contracts, statuses, all_rows = [], [], [], []
    for item in registry['indicators']:
        card = {**item,'project_id':PROJECT,'source_project_id':item['project_id'],'included':True,
                'source_catalogue_capture_date':registry['source_capture_date'],'mapping_status':'confirmed_catalogue_hierarchy' if item['source_ids'] else 'no_confirmed_source_id'}
        cards.append(card)
        for sid in item['source_ids']:
            folder = root / INPUTS / 'nsedc' / sid
            available = any(r.get('file','').endswith('.xls.zip') and r.get('status') == 200 for r in acquisition[sid])
            if available:
                if from_bundles:
                    files = read_bundle(root / DOWNLOADS / 'inputs' / (sid + '.zip'))
                else:
                    files = {name:(folder/name).read_bytes() for name in ['package.json',sid+'.csv.gz',sid+'.xls.zip']}
                    files['retrieval.json'] = encode(acquisition[sid])
                    atomic(root / DOWNLOADS / 'inputs' / (sid+'.zip'), bundle_bytes(files))
                metadata, raw, verify = parse_export(files[sid+'.csv.gz'],files[sid+'.xls.zip'],sid)
                package = json.loads(files['package.json'])['result']
                source_links = [package.get('dataset_link',''), *[r.get('url','') for r in package.get('resources',[])]]
                if package['name'] != 'emiss_' + sid or not any('/indicator/'+sid in url for url in source_links):
                    raise ValueError('Repository package identifies another source')
                for record in acquisition[sid]:
                    if record.get('status') == 200:
                        name = Path(record['file']).name
                        if name in files and hashlib.sha256(files[name]).hexdigest() != record['sha256']:
                            raise ValueError('Acquired input hash mismatch: ' + name)
                acquired_at = max(r['retrieved_at'] for r in acquisition[sid] if r.get('status') == 200)
            else:
                metadata,raw,verify,package = {},[],{},{}
                acquired_at = None
            rule = source_rule(sid)
            contract = {'source_id':sid,'indicator_id':sid,'title':metadata.get('title') or item['source_titles'][0],
                        'titles':list(dict.fromkeys([metadata.get('title') or item['source_titles'][0],*item['source_titles']])),
                        'indicator_codes':[item['indicator_code']], 'indicator_level':item['indicator_level'],
                        'federal_project_code':item['federal_project_code'],'federal_project_name':item['federal_project_name'],
                        'unit':metadata.get('unit','процент'), 'display_unit':{'процент':'%','миллион рублей':'млн руб.','единица':'ед.'}.get(metadata.get('unit','процент'),metadata.get('unit','процент')),
                        'source_url':'https://fedstat.ru/indicator/'+sid,'republisher_url':'https://repository.nsedc.ru/dataset/emiss_'+sid,
                        'first_year':2025,'field_overrides':{},'dimension_defaults':{},'min_regional_count':0,
                        'export_format':'excel','contract_status':'verified_republished_workbook' if available else 'metadata_discovery_only',
                        'methodology':metadata.get('methodology'), 'periodicity':metadata.get('periodicity'),
                        'effective_period':metadata.get('effective_period'), **rule}
            if sid == '62985':
                contract.update(display_unit='%, как опубликовано',semantic_unit='изделий на 1 млрд руб.')
            rows = [observation(sid,r,contract) for r in raw]
            keys = [r['source_observation_key'] for r in rows]
            if len(set(keys)) != len(keys):
                raise ValueError('Duplicate input observations')
            rows.sort(key=lambda r:(r['period_end'],r['frequency'],r['id']))
            packet = {'schema_version':1,'project_id':PROJECT,'source_id':sid,'title':contract['title'],'unit':contract['unit'],
                      'origin_kind':'secondary_emiss_republication' if available else 'no_numeric_publication_recovered',
                      'direct_emiss_verified':False,'published_at':metadata.get('published_at'),'acquired_at':acquired_at,
                      'snapshot_id':'nsedc:' + hashlib.sha256(files[sid+'.xls.zip']).hexdigest() if available else None,
                      'observations':rows}
            atomic(root / DATA / 'series' / (sid+'.json'),packet)
            provenance = {'schema_version':1,'project_id':PROJECT,'source_id':sid,'origin_kind':packet['origin_kind'],
                          'source_url':contract['source_url'],'republisher_url':contract['republisher_url'],
                          'license':package.get('license_title'), 'license_url':package.get('license_url'),
                          'attribution':'ЕМИСС / Минздрав России; сохранённая републикация Национального центра социально-экономических данных',
                          'direct_emiss_verified':False,'acquired_at':acquired_at,'published_at':metadata.get('published_at'),
                          'date_source':'Паспорт!B7' if available else None,
                          'repository_dataset_update':package.get('dataset_update'),'repository_metadata_modified':package.get('metadata_modified'),
                          'repository_date_caution':'Дата метаданных репозитория не заменяет дату обновления данных во встроенном паспорте XLS.',
                          'metadata':metadata,'input_files':acquisition[sid],'cross_validation':verify,
                          'source_catalogue_capture_date':registry['source_capture_date'],
                          'source_catalogue_sha256':registry['source_sha256'],'published_sha256':sha256(root/DATA/'series'/(sid+'.json'))}
            atomic(root / DATA / 'provenance' / (sid+'.json'),provenance)
            csv_write(root / DOWNLOADS / 'series' / (sid+'.csv'),rows,CSV_FIELDS)
            statuses.append({'source_id':sid,'title':contract['title'],'state':'retained_republication' if available else 'not_recovered',
                             'published_at':packet['published_at'],'last_success':None,'republisher_checked_at':acquired_at,
                             'direct_emiss_verified':False,'origin_kind':packet['origin_kind'],
                             'message':'Проверена сохранённая републикация; актуальное состояние оригинала ЕМИСС непосредственно не подтверждено.' if available else 'Числовая публикация не восстановлена. Открытая карточка не подтверждает наличие значения.'})
            contracts.append(contract)
            all_rows.extend(rows)
    config = {'schema_version':1,'project_id':PROJECT,'base_url':'https://fedstat.ru',
              'allowed_hosts':['fedstat.ru','www.fedstat.ru'],'timeout_seconds':15,'retries':1,
              'min_interval_seconds':1,'min_download_interval_seconds':2,'failure_circuit_breaker':3,
              'max_cells':10000,'sources':contracts}
    atomic(root / 'scripts/healthtech_emiss_sources.json',config)
    atomic(root / DATA / 'indicators.json',{'schema_version':1,'project_id':PROJECT,'source_catalogue':{'url':registry['source_url'],'capture_date':registry['source_capture_date'],'sha256':registry['source_sha256']},'items':cards})
    atomic(root / DATA / 'refresh-status.json',{'schema_version':1,'project_id':PROJECT,'state':'retained_republication',
           'checked_at':None,'published_at':max([s['published_at'] for s in statuses if s['published_at']],default=None),
           'last_success':None,'direct_emiss_verified':False,'message':'Исходные републикации проверены по XLS и CSV. Прямая проверка текущего состояния ЕМИСС требует отдельного успешного запроса.',
           'sources':statuses})
    csv_write(root / DOWNLOADS / 'observations.csv',all_rows,CSV_FIELDS)
    csv_write(root / DOWNLOADS / 'indicator_registry.csv',cards,['indicator_code','indicator_name','indicator_level','federal_project_code','federal_project_name','source_ids','mapping_status','source_url'])
    return {'sources':len(contracts),'available_sources':sum(bool(s['published_at']) for s in statuses),
            'observations':len(all_rows),'numeric_observations':sum(r['value'] is not None for r in all_rows),
            'missing_observations':sum(r['value'] is None for r in all_rows)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--from-inputs',action='store_true')
    group.add_argument('--from-bundles',action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.root,args.from_bundles),ensure_ascii=False))
