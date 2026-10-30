#!/usr/bin/env python3
"""Reproduce Data Economy plans, document structure and text diagnostics.

Inputs are byte-pinned public passport renderings and separately attributed source
transcriptions. No network request, regional imputation or causal model is run.
"""
from pathlib import Path
from decimal import Decimal
import argparse,collections,csv,gzip,hashlib,json,math,re,shutil,zipfile
from extract_dataeconomy_passports import parse_passport,decimal,norm,ws,TOKEN_RE

APP=Path(__file__).resolve().parents[1]
PROJECT='data_economy'
REL=f'downloads/projects/{PROJECT}/documentary/'
YEARS=list(range(2025,2031))
NAMES={'family':'Семья','personnel':'Кадры','youth_children':'Молодёжь и дети','long_active_life':'Продолжительная и активная жизнь','health_technologies':'Новые технологии сбережения здоровья','life_infrastructure':'Инфраструктура для жизни','environment':'Экологическое благополучие','data_economy':'Экономика данных и цифровая трансформация государства','competitive_economy':'Эффективная и конкурентная экономика','efficient_transport':'Эффективная транспортная система','international_export':'Международная кооперация и экспорт','tourism':'Туризм и гостеприимство'}
def dump(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def csv_write(p,rows,columns=None):
 p.parent.mkdir(parents=True,exist_ok=True)
 columns=columns or list(dict.fromkeys(k for row in rows for k in row))
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
  for row in rows:w.writerow({k:json.dumps(row.get(k),ensure_ascii=False) if isinstance(row.get(k),(dict,list)) else row.get(k) for k in columns})

from dataeconomy_text import build_text


def load(root):
    folder = root/'inputs/dataeconomy/documentary'
    manifest = json.loads((folder/'source_manifest.json').read_text())
    archive = root/manifest['archive_path']
    assert sha(archive) == manifest['archive_sha256']
    docs = []
    with zipfile.ZipFile(archive) as z:
        for meta in manifest['documents']:
            if meta['project_id'] != PROJECT:
                continue
            raw = z.read(meta['archive_entry'])
            assert hashlib.sha256(raw).hexdigest() == meta['sha256']
            parsed = parse_passport(raw, meta)
            assert parsed['document']['profile_token_count'] == meta['profile_token_count']
            destination = root/'public'/meta['download_path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or destination.read_bytes() != raw:
                destination.write_bytes(raw)
            docs.append(parsed)
    assert len(docs) == 10
    return folder, manifest, docs


UNIT_LABELS = {'Процент':'%', 'Единица':'ед.', 'Штука':'шт.',
    'Миллион квадратных метров общей площади':'млн м²', 'Квадратных метров на человека':'м² на человека',
    'Триллион рублей':'трлн руб.', 'Миллион человек':'млн человек', 'Тысяча человек':'тыс. человек',
    'Миллион рублей':'млн руб.', 'Миллиард рублей':'млрд руб.', 'Человек':'чел.', 'Миллион тонн':'млн т', 'Миллион единиц':'млн ед.', 'Тысяча гектаров':'тыс. га', 'Сутки':'сутки', 'Пара (2 шт.)':'пара поездов', 'Миллион кубических метров':'млн м³'}


def build_targets(folder, docs, registry):
    mapping = json.loads((folder/'target_mapping.json').read_text())
    reg = {x['indicator_code']:x for x in registry}
    cards, records = [], []
    for doc in docs:
        for t in doc['targets']:
            key = t['source_url']+'#'+t['card_id']
            match = mapping['mapping'].get(key)
            if match is None:
                assert key in mapping['unmapped_cards']
                match={'indicator_code':None,'source_sha256':t['source_sha256'],'title':t['title'],'mapping_id':None,'target_is_proxy':False}
            assert match['source_sha256'] == t['source_sha256']
            assert norm(match['title']) == norm(t['title'])
            code = match['indicator_code']
            ids = reg[code]['source_ids'] if code in reg else []
            source_id = mapping.get('source_overrides',{}).get(code) or (ids[0] if len(ids)==1 else None)
            unit = UNIT_LABELS.get(t['unit'], t['unit'])
            out = {'indicator_code':code, 'code':code, 'source_id':source_id,
                'title':t['title'], 'registry_title':reg[code]['indicator_name'] if code in reg else None, 'unit':unit,
                'passport_unit':t['unit'], 'years':{str(y):t['years'].get(str(y)) for y in YEARS},
                'source_document':t['document_id'], 'document_level':doc['document']['document_level'],
                'source_locator':t['source_locator'], 'source_url':t['source_url'], 'source_sha256':t['source_sha256'],
                'source_version':doc['document']['publisher_version'], 'publication_date':doc['document']['publication_date'],
                'source_card_id':t['card_id'], 'local_code':t['local_code'], 'base_value_raw':t['base_value_raw'],
                'base_date':t['base_date'], 'mapping_status':'reviewed_same_level_definition' if code else 'outside_inherited_registry',
                'mapping_id':match['mapping_id'], 'target_is_proxy':bool(match['target_is_proxy'] or 'прокси' in norm(t['title'])),
                'raw_years':t['raw_years'], 'origin':'independently_extracted_passport_plan',
                'source_metadata':t['metadata'], 'mapping_origin':match.get('origin'),
                'execution_status':'discontinued_in_source_card' if t['metadata'].get('Не исполняется')=='1' else 'not_marked_discontinued',
                'cessation_date':t['metadata'].get('Дата прекращения исполнения'),
                'cessation_date_basis':'passport_metadata_not_legal_order_date' if t['metadata'].get('Дата прекращения исполнения') else None,
                'target_comparison_status':'historical_card_no_current_target_conclusion' if t['metadata'].get('Не исполняется')=='1' else 'dated_republication_not_original_assignment_certificate',
                'federal_project_code':None if doc['document']['kind']=='np' else t['fp']}
            cards.append(out)
            for year, raw in t['raw_years'].items():
                records.append({'indicator_code':code, 'source_id':source_id, 'document_id':t['document_id'],
                    'card_id':t['card_id'], 'year':int(year), 'value':t['years'][year], **raw, 'unit':unit,
                    'source_url':t['source_url'], 'source_sha256':t['source_sha256'],
                    'source_version':doc['document']['publisher_version'], 'title':t['title']})
    assert len(cards)==60 and len({t['indicator_code'] for t in cards if t['indicator_code']})==49
    items=[]
    for item in registry:
        code=item['indicator_code']; alternatives=[c for c in cards if c['indicator_code']==code]
        chosen=sorted(alternatives,key=lambda x:(x['document_level']!='national',x['source_document']))[0]
        comparisons=[]
        for a in alternatives:
            if a is chosen:continue
            comparisons.append({'source_document':a['source_document'],'source_card_id':a['source_card_id'],
                'source_url':a['source_url'],'source_locator':a['source_locator'],'source_sha256':a['source_sha256'],
                'different_years':[str(y) for y in YEARS if a['years'][str(y)]!=chosen['years'][str(y)]]})
        items.append({**chosen,'alternative_cards':comparisons,'selection_reason':'national_level_preferred_when_available'})
    numeric=sum(v is not None for x in items for v in x['years'].values())
    return {'project_id':PROJECT,'documentary_snapshot':'2026-10-16','basis':'single_source_edition_per_card',
        'items':items,'allCards':cards,'target_cells':len(items)*6,'numeric_targets':numeric,
        'missing_targets':len(items)*6-numeric,'version_policy':mapping['selection_policy'],
        'extracted_records_all_years':len(records),'source_card_count':len(cards),'strategicGoals':[]}, records


SOURCES = {
    'Федеральный бюджет, всего':('federal','Федеральный бюджет'),
    'Консолидированные бюджеты субъектов Российской Федерации, всего':('regional','Бюджеты регионов, консолидированные'),
    'Внебюджетные источники, всего':('extra_budget','Внебюджетные источники')}


def decimal_sum(rows):
    return sum((Decimal(r['amount_decimal']) for r in rows if r['amount_decimal'] is not None), Decimal(0))


def amounts(value):
    return {'amount_decimal':str(value) if value is not None else None,
        'amount_thousand_rub':float(value) if value is not None else None,
        'amountThousandRub':float(value) if value is not None else None,
        'amount_billion_rub':float(value/1000000) if value is not None else None,
        'value':float(value) if value is not None else None}


from dataeconomy_budget import build_budget


def build_finance(root, folder, docs):
    labels={**SOURCES, 'из них: бюджетам субъектов Российской Федерации':('federal_transfer_component','Из федерального бюджета бюджетам субъектов'), 'в том числе: средства Фонда национального благосостояния':('fnb_component','В том числе средства ФНБ')}
    allrows=[{**r,'source_code':labels[r['source']][0],'source_name':labels[r['source']][1], 'is_subcomponent':r['source'] not in SOURCES, 'included_in_additive_total':r['source'] in SOURCES} for d in docs for r in d['finance_records']]
    for row in allrows:
        if not row['is_subcomponent']:
            continue
        parent=[candidate for candidate in allrows if candidate['document_id']==row['document_id']
            and candidate['scope']==row['scope'] and candidate.get('result_id')==row.get('result_id')
            and candidate['year']==row['year'] and candidate['source_code']=='federal'
            and candidate['amount_decimal'] is not None]
        row['parent_source_available']=bool(parent)
        row['parent_source_locators']=[candidate['source_locator'] for candidate in parent]
        row['component_status']='subcomponent_of_disclosed_parent' if parent else 'orphan_component_parent_not_disclosed'
    docrows=[r for r in allrows if r['scope']=='document' and r['included_in_additive_total']]
    national=[r for r in docrows if r['fp']=='Ц' and r['year'] in YEARS]
    federal=[r for r in docrows if r['fp']!='Ц' and r['year'] in YEARS]
    nat_total=decimal_sum(national);fp_total=decimal_sum(federal)
    assert nat_total==Decimal('1212749112.29')
    assert fp_total==nat_total
    fpyears=[];fpsource=[];projects=[]
    for d in docs:
        meta=d['document'];code=meta['code']
        if code=='Ц':continue
        name=meta['title'].split('] ',1)[-1];rows=[r for r in federal if r['document_id']==meta['document_id']]
        years=[]
        for year in YEARS:
            yr=[r for r in rows if r['year']==year];value=decimal_sum(yr) if yr else None
            base={'fp':code,'code':code,'name':name,'year':year,'unit':'тыс. руб.','kind':'passport_plan',
                'scope':'published_all_sources_federal_project_plan','source_id':meta['document_id'],
                'source_url':meta['url'],'source_sha256':meta['sha256'],'source_version':meta['publisher_version']}
            out={**base,**amounts(value),'source_code':'all','source_name':'Все опубликованные источники',
                'source_locator':None,'source_locators':[r['source_locator'] for r in yr],
                'missing_reason':None if yr else 'no_published_annual_amount_in_selected_edition',
                'component_count':len(yr),'origin':'sum_of_visible_source_rows_without_zero_imputation'}
            fpyears.append(out);years.append(out)
            for source, (source_code, source_name) in SOURCES.items():
                cells=[r for r in yr if r['source']==source];assert len(cells)<=1
                value=decimal_sum(cells) if cells else None
                fpsource.append({**base,**amounts(value),'source':source,'source_code':source_code,'source_name':source_name,
                    'source_locator':cells[0]['source_locator'] if cells else None,
                    'value_raw':cells[0]['value_raw'] if cells else None,
                    'missing_reason':None if cells else 'no_published_source_year_cell',
                    'origin':'independently_extracted_document_plan'})
        visible_total=decimal_sum(rows) if rows else None
        projects.append({'code':code,'fp':code,'name':name,'totalThousandRub':float(visible_total) if visible_total is not None else None,
            'totalDecimal':str(visible_total) if visible_total is not None else None,'years':years,
            'source_url':meta['url'],'source_sha256':meta['sha256'],'scope':'published_all_sources_2025_2030'})
    reconciliation=[]
    for year in YEARS:
        n=decimal_sum([r for r in national if r['year']==year]);f=decimal_sum([r for r in federal if r['year']==year]);diff=f-n
        reconciliation.append({'year':year,'nationalThousandRub':float(n),'federalThousandRub':float(f),'differenceThousandRub':float(diff),
            'national_thousand_rub':float(n),'federal_thousand_rub':float(f),'difference_thousand_rub':float(diff),
            'national_decimal':str(n),'federal_decimal':str(f),'difference_decimal':str(diff),
            'definition':'Сумма опубликованных строк ФП минус сумма опубликованных строк НП за тот же год и все источники.',
            'national_locators':[r['source_locator'] for r in national if r['year']==year],
            'federal_locators':[r['source_locator'] for r in federal if r['year']==year]})
    source_reconciliation=[]
    for year in YEARS:
        for source,(source_code,source_label) in SOURCES.items():
            nrows=[r for r in national if r['year']==year and r['source']==source]
            frows=[r for r in federal if r['year']==year and r['source']==source]
            nvalue=decimal_sum(nrows);fvalue=decimal_sum(frows)
            source_reconciliation.append({'year':year,'source_code':source_code,'source_name':source_label,
                'national_decimal':str(nvalue),'federal_decimal':str(fvalue),'difference_decimal':str(fvalue-nvalue),
                'unit':'тыс. руб.','national_locators':[r['source_locator'] for r in nrows],
                'federal_locators':[r['source_locator'] for r in frows],
                'missing_rows_are_not_zero_cost':True})
    assert [(r['year'],r['source_code'],Decimal(r['difference_decimal'])) for r in source_reconciliation if Decimal(r['difference_decimal'])] == []
    sources=[]
    for source,(code,label) in SOURCES.items():
        rs=[r for r in national if r['source']==source];amount=decimal_sum(rs)
        sources.append({'source_code':code,'source_name':label,'source':source,'amountThousandRub':float(amount),
            'amount_thousand_rub':float(amount),'amount_decimal':str(amount),'sharePercent':float(amount/nat_total*100),
            'years':rs,'origin':'national_passport_published_plan'})
    shares=[]
    for p in projects:
        value=Decimal(p['totalDecimal']) if p['totalDecimal'] is not None else None
        shares.append({'fp':p['code'],'code':p['code'],'name':p['name'],**amounts(value),
            'share':float(value/fp_total) if value is not None else None,
            'sharePercent':float(value/fp_total*100) if value is not None else None,
            'denominator':'sum_visible_federal_project_amounts_2025_2030'})
    horizons=[]
    for d in docs:
        for first,last in [(2025,2030),(2031,2036)]:
            rs=[r for r in docrows if r['document_id']==d['document']['document_id'] and first<=r['year']<=last]
            horizons.append({'code':d['document']['code'],'name':d['document']['title'],'horizon':f'{first}–{last}',
                'first_year':first,'last_year':last,**amounts(decimal_sum(rs) if rs else None),
                'published_cells':len(rs),'source_url':d['document']['url'],
                'included_in_national_reconciliation':first==2025})
    details=[r for r in allrows if r['scope']=='result'];result_sums=[]
    result_nodes={n['node_id']:n for d in docs for n in d['nodes'] if n['kind']=='result'}
    for rid,node in sorted(result_nodes.items()):
        rs=[r for r in details if r['result_id']==rid and r['year'] in YEARS and r['included_in_additive_total']]
        omitted=[r for r in details if r['result_id']==rid and r['year'] in YEARS
            and r.get('component_status')=='orphan_component_parent_not_disclosed']
        result_sums.append({'result_id':rid,'fp':node['fp'],'result_title':node['title'],
            **amounts(decimal_sum(rs) if rs else None),
            'unit':'тыс. руб.','scope':'sum_of_disclosed_parent_source_rows_2025_2030','source_url':node['source_url'],
            'source_locator':node['source_locator'],'source_sha256':node['source_sha256'],
            'total_is_complete':False,'coverage_status':'orphan_transfer_without_parent' if omitted else
                'visible_rows_only_completeness_not_established' if rs else 'no_published_parent_source_amount',
            'published_parent_source_cells':len(rs),
            'orphan_component_cells':len(omitted),'orphan_component_locators':[r['source_locator'] for r in omitted]})
    budget=build_budget(root,folder)
    return {'unit':'тыс. руб.','periods':YEARS,'totalThousandRub':float(nat_total),'nationalThousandRub':float(nat_total),
        'federalThousandRub':float(fp_total),'totalDecimal':str(nat_total),'nationalDecimal':str(nat_total),
        'federalDecimal':str(fp_total),'nationalMinusFederalThousandRub':float(nat_total-fp_total),
        'federalMinusNationalThousandRub':float(fp_total-nat_total),'projects':projects,'fpYears':fpyears,
        'sourceYears':fpsource,'nationalSourceYears':national,'sourceSummaries':sources,'horizonSummaries':horizons,
        'yearTotals':reconciliation,'reconciliation':reconciliation,'sourceReconciliation':source_reconciliation,'federalShares':shares,
        'hhi':sum(x['share']**2 for x in shares if x['share'] is not None),
        'resultYears':details,'resultSums':result_sums,'orphanComponents':[r for r in allrows if r.get('component_status')=='orphan_component_parent_not_disclosed'],'sources':docrows,'sourceRows':allrows,
        'frames':[{'id':'passport_plan','title':'Паспортный план всех источников на 2025–2030 годы',
            'unit':'тыс. руб.','periods':YEARS,'rows':fpsource,'totalRows':fpyears,'source_kind':'secondary_epbs_rendering',
            'edition_date':'2026-10-16','grain':'federal_project_source_year'},
            {'id':'budget_bill','title':'Федеральная роспись 2026 года и бюджетные предложения 2027–2029 годов',
            'unit':'млн руб.','periods':list(range(2026,2030)),'rows':budget['projectRows'],'totalRows':budget['totals'],
            'source_kind':'legal_republication','verification_status':budget['verification_status'],'grain':'federal_project_year'}],
        'budgetBill':budget,'notes':['Финансирование НП за 2025–2030 годы представлено по всем опубликованным источникам и текущим ценам.',
            'Годовые строки девяти ФП согласованы с НП на горизонте 2025–2030 годов. В Ц1 отдельная строка 2030 года отсутствует. Совпадение суммы не устанавливает размер нераскрытого обязательства.',
            'Ц4 содержит по 951 445,5 тыс. руб. в 2031–2036 годах. Дополнительные 5 708 673 тыс. руб. сохранены отдельно и исключены из суммы 2025–2030 годов.',
            'Отсутствующие источник и год сохраняются как пропуск. Подстрока трансферта не прибавляется повторно к раскрытой федеральной строке. На уровне результатов подстрока без родительской суммы отмечается отдельно и не подтверждает полный итог результата.',
            'Паспорт, роспись и бюджетные предложения имеют разные даты и статус. Паспортная классификация источников не является независимой консолидацией всех платежей участников.']}


def build_network(selected, candidates):
    nodes=[n for d in selected for n in d['nodes']]
    byid={n['node_id']:n for n in nodes}
    assert len(byid)==len(nodes)==194
    claims=[c for d in selected for c in d['unresolved_weight_claims']]
    for claim in claims:
        claim['causal_status']='not_identified'
        claim['target_assignment_permitted']=False
    same_project=[];shared=[];result_tasks=[]
    for d in selected:
        results=[n for n in d['nodes'] if n['kind']=='result']
        indicators=[n for n in d['nodes'] if n['kind']=='indicator']
        for r in results:
            if r.get('task_node_id'):
                task=byid[r['task_node_id']]
                result_tasks.append({'id':r['node_id']+'__'+task['node_id'],'result_node_id':r['node_id'],
                    'task_node_id':task['node_id'],'document_id':r['document_id'],'source_locator':r['source_locator'],
                    'task_locator':task['source_locator'],'source_url':r['source_url'],'membership_basis':r['task_assignment_basis']})
            for x in indicators:
                pair={'id':r['node_id']+'__'+x['node_id'],'document_id':r['document_id'],'fp':r['fp'],
                    'source_node_id':r['node_id'],'target_node_id':x['node_id'],'result_node_id':r['node_id'],
                    'indicator_node_id':x['node_id'],'result_title':r['title'],'indicator_title':x['title'],
                    'source_url':r['source_url'],'result_locator':r['source_locator'],'indicator_locator':x['source_locator'],
                    'evidence_class':'same_federal_project_candidate','causal_status':'not_identified',
                    'origin':'administrative_same_project_pair_not_causal'}
                same_project.append(pair)
                if r.get('task_node_id') and r['task_node_id']==x.get('task_node_id'):
                    task=byid[r['task_node_id']]
                    shared.append({**pair,'task_node_id':task['node_id'],'task_title':task['title'],
                        'task_locator':task['source_locator'],'result_membership_basis':r['task_assignment_basis'],
                        'indicator_membership_basis':x['task_assignment_basis'],
                        'evidence_class':'same_document_task_membership','origin':'source_addressed_task_membership_not_causal'})
    counts=collections.Counter(n['kind'] for n in nodes)
    assert dict(counts)=={'task':34,'result':90,'indicator':60,'goal':10} or counts==collections.Counter({'task':34,'result':90,'indicator':60,'goal':10})
    assert len(claims)==168 and len(shared)==632 and len(result_tasks)==90
    assert len(candidates)==150 and len({r['result_node_id'] for r in candidates})==68
    docs=[]
    for d in selected:
        m=d['document'];ns=d['nodes'];code=m['code']
        docs.append({'document_id':m['document_id'],'fp':code,'title':m['title'],
            'results':sum(n['kind']=='result' for n in ns),'indicators':sum(n['kind']=='indicator' for n in ns),
            'unresolved_weight_claims':len(d['unresolved_weight_claims']),
            'same_project_pairs':sum(x['fp']==code for x in same_project),'shared_task_pairs':sum(x['fp']==code for x in shared),
            'source_url':m['url'],'source_sha256':m['sha256']})
    return {'nodes':nodes,'unresolvedClaims':claims,'reviewedEdges':[],'directLinks':[],'edges':[],
        'sharedTaskPairs':shared,'sameProjectPairs':same_project,'semanticCandidates':candidates,
        'resultTaskLinks':result_tasks,'documents':docs,
        'summary':{'results':90,'indicators':60,'tasks':34,'goals':10,'standalone_tasks':22,'repeated_structure_tasks':12,
            'unresolved_weight_claims':168,'reviewed_direct_links':0,'shared_task_pairs':632,'result_task_links':90,
            'same_project_pairs':len(same_project),'semantic_candidates':150,'candidate_results':68,
            'results_without_candidate':22,'shared_task_density':632/(90*60)},
        'evidenceClasses':[
            {'id':'source_card','name':'Адресуемая карточка','causal_status':'not_applicable'},
            {'id':'unresolved_target_indicator','name':'Запись влияния без определённого показателя назначения','causal_status':'not_identified'},
            {'id':'same_federal_project_candidate','name':'Принадлежность одному федеральному проекту','causal_status':'not_identified'},
            {'id':'same_document_task_membership','name':'Общая адресуемая задача документа','causal_status':'not_identified'},
            {'id':'semantic_candidate','name':'Лексическая близость формулировок','causal_status':'not_identified'}],
        'notes':['Сохранены 34 записи задач: 22 самостоятельные карточки и 12 повторных представлений в национальном паспорте. Повторные записи не создают дополнительных связей.',
            '90 результатов имеют адресуемую задачу. 632 пар соединены через общую задачу внутри документа.',
            '168 записей влияния не идентифицируют показатель назначения. Указанные числовые веса не присваиваются рёбрам.',
            '150 лексических кандидатов отобраны среди всех 60 карточек показателей одного НП по правилу до трёх на результат при косинусе от 0,10. Межпроектная принадлежность ФП для них не требуется.',
            'Косинус и общая задача не измеряют дополнительный общественный и экономический эффект.']}


def build(root=APP, verify=False):
    folder,manifest,all_docs=load(root)
    selected=[d for d in all_docs if d['document']['project_id']==PROJECT]
    data_dir=root/f'public/data/projects/{PROJECT}';output=root/'public'/REL
    registry=json.loads((data_dir/'indicators.json').read_text())['items']
    output.mkdir(parents=True,exist_ok=True)
    targets,targetrecords=build_targets(folder,selected,registry)
    finance=build_finance(root,folder,selected)
    text,candidates=build_text(folder,all_docs,selected,output,data_dir)
    network=build_network(selected,candidates)
    documentary={'meta':{'project_id':PROJECT,'documentary_snapshot':'2026-10-16','prepared_at':'2026-10-29',
        'sources':10,'corpus_documents':137,'corpus_projects':11,'comparable_text_projects':10,'shared_passport_archive_documents':98,'shared_passport_archive_projects':12,'source_kind':'secondary_epbs_rendering','schema_version':1,
        'input_archive_sha256':manifest['archive_sha256'],'retrieval_policy':'Individual original retrieval dates are preserved; preparation is not a new retrieval.'},
        'finance':finance,'network':network,'text':text,'targets':targets,'sources':[d['document'] for d in selected],
        'officialUpdates':[],'downloads':{'sources':manifest['shared_archive_download'],'inputs':REL+'documentary_inputs.json.gz',
        'sources_index':REL+'source_manifest.json','full_documentary':REL+'documentary_full.json',
        'finance_years':REL+'finance_fp_years.csv','finance_sources':REL+'finance_source_rows.csv',
        'finance_results':REL+'finance_result_years.csv','finance_reconciliation':REL+'finance_reconciliation.csv',
        'budget_bill':REL+'budget_bill_rows.csv','targets_all_editions':REL+'targets_all_years.csv',
        'target_mapping':REL+'target_mapping.json','text_methods':REL+'text_methods.md','author_code':'downloads/projects/personnel/documentary/original_code/text_analysis.py','text_shared_inputs':'downloads/projects/personnel/documentary/documentary_inputs.json.gz',
        'finance_methods':REL+'finance_methods.md','code':'downloads/code/platform/build_dataeconomy_documentary.py'}}
    for name,rows in [('finance_fp_years',finance['fpYears']),('finance_source_rows',finance['sourceRows']),
        ('finance_fp_source_years',finance['sourceYears']),('finance_national_source_years',finance['nationalSourceYears']),
        ('finance_reconciliation',finance['reconciliation']),('finance_source_reconciliation',finance['sourceReconciliation']),('finance_horizons',finance['horizonSummaries']),
        ('finance_result_years',finance['resultYears']),('finance_result_sums',finance['resultSums']),
        ('budget_bill_rows',finance['budgetBill']['rows']),('budget_direction_shares',finance['budgetBill']['directionShares']),
        ('budget_reconciliation',finance['budgetBill']['reconciliation']),
        ('targets_all_years',targetrecords),('network_nodes',network['nodes']),('network_unresolved_weights',network['unresolvedClaims']),
        ('network_result_task',network['resultTaskLinks']),('network_shared_task',network['sharedTaskPairs']),('network_same_project',network['sameProjectPairs']),
        ('network_semantic_candidates',network['semanticCandidates'])]:
        csv_write(output/(name+'.csv'),rows)
    documentary['downloads'].update({name:REL+name+'.csv' for name in [
        'finance_source_reconciliation','finance_fp_source_years','finance_national_source_years','finance_horizons','finance_result_sums',
        'budget_direction_shares','budget_reconciliation','network_result_task','network_nodes','network_unresolved_weights',
        'network_shared_task','network_same_project','network_semantic_candidates','text_corpus_profiles',
        'text_units','text_kwic','frame_scores','document_similarity','project_similarity','text_sensitivity',
        'tfidf_top_terms','text_replication_audit','project_frame_scores','author_project_similarity']})
    for name in ['text_parameters.json','theme_dictionary.json','target_mapping.json','budget_source.json','author_reference_tables.json','text_methods.md','finance_methods.md']:
        shutil.copy2(folder/name,output/name)
    inp={'source_manifest':manifest,'selected_passports':selected,'text_parameters':text['method'],'theme_dictionary':text['dictionary'],
        'shared_corpus_archive':manifest['shared_archive_download'],'shared_corpus_sha256':manifest['archive_sha256']}
    (output/'documentary_inputs.json.gz').write_bytes(gzip.compress((json.dumps(inp,ensure_ascii=False,allow_nan=False)+'\n').encode(),mtime=0))
    result_file=f'data/projects/{PROJECT}/documentary-finance/results.json'
    finance['resultsFile']=result_file
    dump(root/'public'/result_file,{'project_id':PROJECT,'unit':'тыс. руб.','resultYears':finance['resultYears'],
        'resultSums':finance['resultSums'],'orphanComponents':finance['orphanComponents'],
        'note':'Годовые ячейки результата сохраняют статус источника. Подстроки не прибавляются повторно к родительским суммам. Полнота стоимости результата не установлена.'})
    dump(data_dir/'targets.json',targets)
    dump(output/'documentary_full.json',documentary)
    runtime=json.loads(json.dumps(documentary,ensure_ascii=False))
    repeated_pair_fields={'result_title','indicator_title','source_url','result_locator','indicator_locator','task_title','task_locator','indicator_source_url'}
    for field in ['sharedTaskPairs','sameProjectPairs','semanticCandidates']:
        runtime['network'][field]=[{k:v for k,v in row.items() if k not in repeated_pair_fields} for row in runtime['network'][field]]
    runtime['meta']['network_pair_text_policy']='Repeated titles and source locators are resolved from network.nodes in the interface. Full JSON and CSV retain complete rows.'
    for field in ['sourceRows','resultYears']:
        runtime['finance'].pop(field)
    runtime['finance']['budgetBill'].pop('rows')
    runtime['targets'].pop('allCards')
    runtime['meta']['runtime_omissions']={'finance.sourceRows':'finance_source_rows.csv','finance.resultYears':'finance_result_years.csv','finance.budgetBill.rows':'budget_bill_rows.csv','targets.allCards':'documentary_full.json'}
    runtime['meta']['full_export_url']=REL+'documentary_full.json'
    dump(data_dir/'documentary.json',runtime)
    dump(output/'source_manifest.json',{**manifest,'supplemental_sources':[finance['budgetBill']|{'rows':None,'projectRows':None,'totals':None}]})
    validation={'passed':True,'project_id':PROJECT,'corpus_documents':137,'corpus_projects':11,'corpus_tokens':text['corpusTokenCount'],
        'dataeconomy_tokens':text['sameGenreTokenCount'],'source_passports':10,'target_cards':targets['source_card_count'],
        'target_cells':targets['target_cells'],'numeric_targets':targets['numeric_targets'],'missing_targets':targets['missing_targets'],
        'finance_national_total_thousand_rub':finance['nationalDecimal'],'finance_federal_total_thousand_rub':finance['federalDecimal'],
        'finance_federal_minus_national_thousand_rub':finance['federalMinusNationalThousandRub'],
        'budget_source_cells':finance['budgetBill']['published_numeric_cells'],
        'unique_nodes':len(network['nodes']),**network['summary'],'thematic_cells':len(text['frameScores']),
        'context_count':text['contextCount'],'features':text['features'],'replication_audit':text['replicationAudit']}
    dump(output/'documentary_validation.json',validation)
    print(json.dumps(validation,ensure_ascii=False,indent=2))
    return documentary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=APP)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    build(args.root.resolve(),args.verify)
