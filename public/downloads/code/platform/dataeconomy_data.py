"""Loss-aware digital-economy statistics and independently dated EMISS contracts.

All physical source values, period labels, dimensions and missing cells survive
normalization. Annual facts, YTD observations, quarterly revenue and monthly
publication labels are never silently made interchangeable.
"""
from __future__ import annotations
import calendar
import csv
import gzip
import hashlib
import io
import json
import math
import re
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'data_economy'
DATA = Path('public/data/projects') / PROJECT
DOWNLOADS = Path('public/downloads/projects') / PROJECT / 'statistics'
STATISTICAL_AS_OF = '2026-10-15'
RELEASE = 'NationalProjects_Analytics_1.2.0'
# All published source cells remain in their original frequency fields.
# December equivalence is a separate, explicitly qualified reference, never a new row.
ANNUAL_EQUIVALENCE = {'62765':'report_reviewed_december_rule','62767':'report_reviewed_december_rule','62815':'report_reviewed_december_rule'}
REPEATED_ANNUAL = {'62814','62816','62883'}
YTD_FROM_MONTH_LABEL = {'62751','62760','62810'}
QUANTUM_REVIEW = {'62889','62830'}
RULES_PATH = Path(__file__).with_name('dataeconomy_source_semantics.json')

def source_rules(sid,title,unit):
    rules=json.loads(RULES_PATH.read_text(encoding='utf-8'))[str(sid)]
    display={'процент':'%','миллиард рублей':'млрд руб.','человек':'чел.','тысяча человек':'тыс. чел.','единица':'ед.','штука':'ед.','час':'ч','километр (тысяча метров)':'км'}.get(unit,unit)
    return {'lower_bound':0,'upper_bound':None,'direction':'higher','display_unit':display,
        'note':rules['note'],'period_note':rules['note'],'source_status':'active',
        'annual_equivalence':ANNUAL_EQUIVALENCE.get(str(sid)),'annual_reset':False,'cumulative':False,
        'baseline_year':None,'proxy_only':False,'proxy_for_source_id':None,'reference_lag_months':0,
        'nominal_growth_criterion':False,'real_growth':False,
        'target_comparison_allowed':True,'temporal_comparison_allowed':True,'temporal_comparison_eligible':True,
        'scenario_allowed':str(sid) in ANNUAL_EQUIVALENCE,'target_unit_scale':1,'project_territories':[],
        'methodology_references':[f'https://www.fedstat.ru/indicator/{sid}'],
        'geography_contract':'separate_national_regional_and_other_scopes',
        'target_comparison_note':'Месячная публикация, накопленный итог и самостоятельный годовой факт различаются. Декабрьское правило применяется только к явно указанным источникам с отдельным основанием. Сопоставление с редакцией цели 16.10.2026 не устанавливает исполнение первоначальных обязательств.',
        **rules}
def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def encode(value, compact=False):
    return (json.dumps(value,ensure_ascii=False,allow_nan=False,**({'separators':(',',':')} if compact else {'indent':2}))+'\n').encode()
def atomic(path,value,compact=False):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as f:
            temporary=Path(f.name); f.write(value if isinstance(value,bytes) else encode(value,compact))
        temporary.replace(path)
    finally:
        if temporary: temporary.unlink(missing_ok=True)
def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()
def territory_key(name):
    s=re.sub(r'\s+',' ',str(name).casefold().replace('ё','е')).strip().replace('–','-').replace('—','-')
    s=re.sub(r'^(?:г\.?|город)\s+','',s)
    return re.sub(r'\s*-\s*','-',s)
def region_aliases(root=ROOT):
    from longlife_data import region_aliases as shared
    aliases=shared(root)
    catalog=load(Path(root)/'public/data/catalog.json')['regions']
    for region in catalog:
        name=region['name']; code=str(region['id'])
        variants={name.replace('область','обл.').replace('Республика','Респ.').replace('автономный округ','АО')}
        if name.startswith('Республика '):variants.add('Респ. '+name[len('Республика '):])
        for v in variants:aliases[territory_key(v)]=code
    extra={'Кемеровская обл.':'42','Ханты-Мансийский АО':'86','Чувашская Респ.':'21','Еврейская АО':'79',
           'Архангельская область (без АО)':'29','Тюменская область (без АО)':'72'}
    ids={int(r['id']):str(r['id']) for r in catalog if str(r['id']).isdigit()}
    aliases.update({territory_key(k):ids[int(v)] for k,v in extra.items()})
    return aliases
def observation_key(source_id,name,frequency,start,end,category):
    return str(source_id)+':'+hashlib.sha256('|'.join([str(source_id),territory_key(name),frequency,start,end,json.dumps(category,ensure_ascii=False,sort_keys=True)]).encode()).hexdigest()[:24]

def decode_period(year,label,source_frequency=None,start=None,end=None):
    year=int(year); value=re.sub(r'\s+',' ',str(label or '').casefold()).strip()
    if value in {'ежегодно','значение показателя за год','на конец года'}:
        frequency,a,b,basis='annual',f'{year}-01-01',f'{year}-12-31','independent_annual'
    elif value in {'i квартал','ii квартал','iii квартал','iv квартал'}:
        quarter={'i квартал':1,'ii квартал':2,'iii квартал':3,'iv квартал':4}[value]; month=quarter*3
        frequency,a,b,basis='quarterly',f'{year}-{month-2:02d}-01',f'{year}-{month:02d}-{calendar.monthrange(year,month)[1]:02d}','explicit_quarter_source_label'
    else:
        from emiss_adapter.normalize import decode_period as shared
        typ,a,b,_=shared(year,label,annual_only=source_frequency=='annual')
        frequency={'год':'annual','месяц':'monthly','накопительно с января':'cumulative_ytd'}[typ]
        if source_frequency=='cumulative_ytd' and frequency=='monthly':frequency='cumulative_ytd';a=f'{year}-01-01'
        basis='independent_annual' if frequency=='annual' else 'explicit_source_period'
    if source_frequency not in {None,'unresolved',frequency} or start and start!=a or end and end!=b:
        raise ValueError('Source dates disagree with explicit period label: '+str(label))
    return frequency,a,b,basis

def category_dimensions(dimensions):
    category={};geography={}
    for key,value in dimensions.items():
        k=re.sub(r'\s+',' ',key).strip()
        if any(term in k.casefold() for term in ['окато','октмо','оксм','территори','регионы российской']):
            geography[key]=value;continue
        if k in {'Показатель','Год','Период','Единица измерения'}:continue
        if k in category and category[k]!=value:raise ValueError('Conflicting duplicate dimension labels')
        category[k]=value
    return category,geography

def flag(code,message,exclude=False,severity='warning'):
    return {'code':code,'message':message,'severity':severity,'exclude_from_analysis':exclude}

def normalize_record(row,source,aliases,regions=None,cutoff=STATISTICAL_AS_OF):
    sid=str(source['indicator_id'])
    if str(row['source_id'])!=sid:raise ValueError('Source identity mismatch')
    if row['unit'].strip().casefold()!=source['unit'].strip().casefold():raise ValueError('Source unit mismatch')
    dims=json.loads(row.get('dimensions_json') or '{}');label=dims.get('Период','')
    frequency,start,end,basis=decode_period(row['year'],label,row['period_kind'],row.get('period_start'),row.get('period_end'))
    if sid in YTD_FROM_MONTH_LABEL and frequency=='monthly':
        frequency='cumulative_ytd';start=f"{int(row['year'])}-01-01";basis='documented_ytd_components_original_month_label_retained'
    if sid=='63144' and int(row['year'])>=2026 and frequency=='monthly':
        frequency='cumulative_ytd';start=f"{int(row['year'])}-01-01";basis='quality_standard_2026_ytd_publication_schedule'
    date.fromisoformat(start);date.fromisoformat(end)
    name=row['territory_name'];key=territory_key(name);code=aliases.get(key)
    national_scope='rf_source_definition' if key==territory_key('Российская Федерация') else 'rf_excluding_new_subjects_since_2023' if key==territory_key('Российская Федерация без учета новых субъектов (с 01.01.2023)') else None
    geography='national' if national_scope else 'regional' if code else 'other'
    if geography=='other' and name not in source.get('known_territories',[]):raise ValueError('Unmapped source geography: '+name)
    category,geography_dims=category_dimensions(dims);val=row.get('value_numeric')
    if val is not None and (isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val)):raise ValueError('Invalid numeric cell')
    flags=[]
    if val is None:flags.append(flag('source_missing','В исходной ячейке нет числа. Значение сохраняется как пропуск.',True,'info'))
    if val is not None and source.get('lower_bound') is not None and val<source['lower_bound']:flags.append(flag('below_domain','Значение ниже области определения. Исходное число сохранено.',True))
    if val is not None and source.get('upper_bound') is not None and val>source['upper_bound']:flags.append(flag('above_domain','Значение превышает верхнюю границу определения показателя. Исходное число сохранено.',True))
    if val is not None and source['domain']=='binary_status' and val not in {0,1}:flags.append(flag('outside_binary_status','Индикатор состояния допускает только 0 или 1. Дробный статус не интерпретируется как частично созданная система.',True))
    if val is not None and end>cutoff:flags.append(flag('future_period_at_snapshot','Период ещё не завершился к дате получения источника. Число сохранено отдельно от фактов завершённого периода.',True))
    if val==0:
        flags.append(flag('zero_preserved','Исходный ноль сохранён и отличается от отсутствующего значения.',False,'info'))
        if sid in QUANTUM_REVIEW and int(row['year'])>=2026:
            flags.append(flag('technology_zero_requires_review','Нулевой опубликованный результат после положительного уровня требует уточнения календаря и редакции методики. Исходный ноль сохранён, аналитическая разность и сценарий по нему не рассчитываются.',True))
    if sid in REPEATED_ANNUAL and frequency!='annual':flags.append(flag('annual_estimate_republished','Месячная публикация последней годовой оценки не является независимым месячным наблюдением.',False,'info'))
    if sid=='62751':flags.append(flag('external_consistency_unresolved','Индекс к числу предотвращённых попыток за 2024 год допускает значения выше 100. Сверка с опубликованными годовыми объёмами Банка России не завершена. Рост индекса не означает снижение ущерба.',False))
    if sid=='62760':flags.append(flag('national_regional_components_unresolved','Национальное значение нельзя восстановить как положительно взвешенное среднее опубликованной региональной панели. Требуются числители, знаменатели и состав услуг.',False))
    if sid=='62766':flags.append(flag('service_not_person_denominator','Единица счёта – вид услуги. Порог допуска: более 200 ненулевых анкет для национальной оценки и более 1 для региональной за 12 месяцев. Средняя оценка относится к отчётному месяцу.',False,'info'))
    if sid=='62815':flags.append(flag('software_composite_and_series_break','Показатель нормативно взвешивает состав ПО систем и рабочих мест. Причина разрыва ряда в августе 2025 года не установлена.',False))
    if sid in {'62868','62809'}:flags.append(flag('unit_label_unresolved','Сохранённая карточка не задаёт однозначную физическую единицу. Пересчёт в другую шкалу и сравнение с целью в иной единице не выполняются.',False))
    if sid=='63144':flags.append(flag('quality_method_revision_2026','С января 2026 года применяется новый стандарт качества и накопленное число опубликованных показателей относительно годового плана. Межгодовая разность смешивает разные методики.',False))
    if sid=='62866' and val==0:flags.append(flag('graduate_calendar_requires_review','Нулевой счётчик выпускников требует проверки учебного календаря и отчётного периода. Он не удостоверяет прекращение подготовки кадров.',False))
    excluded=any(f['exclude_from_analysis'] for f in flags);region=(regions or {}).get(code,{})
    semantics='independent_annual' if frequency=='annual' else source['period_semantics']
    period=str(row['year']) if frequency=='annual' else f"{row['year']}-Q{(int(end[5:7])-1)//3+1}" if frequency=='quarterly' else end[:7]
    temporal=source['temporal_comparison_allowed'] and not(sid in REPEATED_ANNUAL and frequency!='annual')
    return {'id':observation_key(sid,name,frequency,start,end,category),'source_id':sid,'source_observation_key':row.get('observation_key'),
      'name':name,'code':code,'map_id':code,'geo_level':geography,'fd':region.get('federal_district'),'national_scope':national_scope,
      'period':period,'period_start':start,'period_end':end,'year':int(row['year']),'frequency':frequency,
      'source_frequency':row['period_kind'],'source_period_start':row.get('period_start'),'source_period_end':row.get('period_end'),
      'source_period_label':label,'original_period_label':label,'period_basis':basis,'period_semantics':semantics,
      'value':val,'raw':row.get('value_raw'),'raw_value':row.get('value_raw'),'unit':source['unit'],'category':category,'source_dimensions':dims,
      'quality_flags':flags,'excluded':excluded,'analytical_value':None if excluded else val,'status':'missing' if val is None else 'excluded' if excluded else 'ok',
      'source_status':source.get('source_status','active'),'geographic_comparison_eligible':geography=='regional' and not excluded,
      'geographic_exclusion_reason':'excluded_numeric_or_missing' if geography=='regional' and excluded else None if geography=='regional' else 'not_a_region',
      'annual_comparison_eligible':frequency=='annual' and val is not None and not excluded and source['target_comparison_allowed'],
      'annual_equivalent_eligible':sid in ANNUAL_EQUIVALENCE and end[5:]=='12-31' and val is not None and not excluded,
      'annual_equivalent_basis':ANNUAL_EQUIVALENCE.get(sid),
      'measurement_regime':('software_pre_august_2025' if end<'2025-08-01' else 'software_since_august_2025') if sid=='62815' else ('quality_before_2026' if int(row['year'])<2026 else 'quality_standard_2026') if sid=='63144' else 'published_methodology',
      'temporal_comparison_eligible':temporal and val is not None and not excluded,
      'source_attributes':json.loads(row.get('attributes_json') or '{}'),'origin_kind':'live_emiss'}

def normalize_payload(payload,aliases,regions=None):
    snapshot=payload.get('snapshot');source=payload['config']
    if snapshot and snapshot['origin_kind']!='live_emiss':raise ValueError('Only verified original EMISS source snapshots are accepted')
    rows=[normalize_record(r,source,aliases,regions,snapshot['acquired_at'][:10] if snapshot else STATISTICAL_AS_OF) for r in payload['observations']]
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('Duplicate normalized observation identity')
    rows=series_flags(rows,source['indicator_id'])
    rows.sort(key=lambda r:(r['period_end'],r['frequency'],r['name'],r['id']))
    return {'schema_version':1,'project_id':PROJECT,'source_id':source['indicator_id'],'unit':source['unit'],'source_url':source['source_url'],
            'published_at':snapshot['acquired_at'] if snapshot else None,'published_at_semantics':'verified_source_snapshot_acquisition_time',
            'snapshot_id':snapshot['snapshot_id'] if snapshot else None,'origin_kind':'live_emiss' if snapshot else 'metadata_only',
            'direct_emiss_verified':bool(snapshot),'observations':rows}

def series_flags(rows,source_id):
    from collections import defaultdict
    groups=defaultdict(list)
    for row in rows:
        if row['geo_level']=='regional':groups[(row['code'],row['period_end'],row['frequency'],json.dumps(row['category'],sort_keys=True))].append(row)
    for group in groups.values():
        eligible=[r for r in group if r['geographic_comparison_eligible']]
        if len({r['value'] for r in eligible if r['value'] is not None})>1:
            for row in group:
                row['geographic_comparison_eligible']=False
                row['geographic_exclusion_reason']='conflicting_explicit_territorial_scopes'
                if not any(f['code']=='conflicting_explicit_territorial_scopes' for f in row['quality_flags']):
                    row['quality_flags'].append(flag('conflicting_explicit_territorial_scopes','В одном периоде опубликованы несовпадающие значения нескольких территориальных строк, сопоставленных одному субъекту. Для карты ни одна строка не выбирается произвольно. Исходные наблюдения доступны в исследователе.',False))
    return rows
def annual_equivalents(source_id,rows):
    return [{**r,'reference_observation_id':r['id'],'annual_basis':ANNUAL_EQUIVALENCE[source_id],
      'anchor_kind':'reported_december_with_reviewed_annual_rule','formal_attainment_eligible':False,
      'is_independent_annual_fact':False,'year_end_rule_verified_from_primary':False,
      'basis_source':'downloads/projects/data_economy/report/expertise_dataeconomy_2026.docx',
      'basis_locator':'Раздел 3.4–3.5, раздел 4.2 и примечание к таблице 3',
      'interpretation':'Декабрьское значение с годовым правилом, разобранным в авторской экспертизе. Исходная месячная запись сохранена. Формальное исполнение не удостоверено.'}
      for r in rows if r['geo_level']=='national' and r.get('annual_equivalent_eligible')]

def quantile(values,p):
    values=sorted(values)
    if not values:return None
    at=(len(values)-1)*p;a=math.floor(at);b=math.ceil(at)
    return values[a]+(values[b]-values[a])*(at-a)

def csv_write(path,rows,fields=None):
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    text=io.StringIO(newline='');writer=csv.DictWriter(text,fieldnames=fields,extrasaction='ignore');writer.writeheader()
    for r in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in r.items()})
    content=('\ufeff'+text.getvalue()).encode()
    # Verify row integrity before replacing any published download.
    decoded=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    if len(decoded)!=len(rows):raise ValueError('CSV roundtrip row count mismatch')
    atomic(path,gzip.compress(content,compresslevel=9,mtime=0) if str(path).endswith('.gz') else content)

def merge_observations(previous,incoming):
    out={r['id']:dict(r) for r in previous}
    if len(out)!=len(previous):raise ValueError('Duplicate existing observations')
    seen=set();added=0;revisions=[]
    for row in incoming:
        if row['id'] in seen:raise ValueError('Duplicate incoming observation')
        seen.add(row['id']);old=out.get(row['id'])
        if old is None:added+=1
        elif old['unit']!=row['unit'] or old['category']!=row['category']:raise ValueError('Historical dimension changed')
        elif row['value'] is None and old['value'] is not None:continue
        elif old['value']!=row['value']:revisions.append({'id':row['id'],'name':row['name'],'period':row['period'],'old_value':old['value'],'new_value':row['value']})
        out[row['id']]={**row,'source_observation_key':row.get('source_observation_key') or (old or {}).get('source_observation_key')}
    return sorted(out.values(),key=lambda r:(r['period_end'],r['frequency'],r['name'],r['id'])),added,revisions
