"""Loss-aware ecological statistics and independently dated EMISS contracts.

All physical source values, period labels, dimensions and missing cells survive
normalization. Annual facts, YTD observations, programme accumulation and city
indices are never silently made interchangeable.
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
PROJECT = 'environment'
DATA = Path('public/data/projects') / PROJECT
DOWNLOADS = Path('public/downloads/projects') / PROJECT / 'statistics'
STATISTICAL_AS_OF = '2026-10-15'
RELEASE = 'NationalProjects_Analytics_1.2.0'
ANNUAL_EQUIVALENCE = {}
SHORT_TITLES = {
 '62787':'Вторичные ресурсы и сырьё из отходов',
 '62863':'Остаточный индекс опасных выбросов: 29 территорий',
 '62786':'Ликвидированные опасные объекты',
 '62871':'Объём неочищенных сточных вод',
 '62854':'Остаточный индекс воздействия на Байкал',
 '62781':'Отношение лесовосстановления к выбытию лесов',
 '62777':'Посещения федеральных ООПТ',
 '62828':'Удалённое затонувшее имущество',
 '62793':'Доля ТКО, направленных на захоронение',
 '62792':'Доля ТКО, направленных на обработку',
 '62804':'Утилизация и обезвреживание отходов I–II классов',
 '62778':'Виды животных, охваченные мероприятиями',
 '62860':'Жители территорий со снижением опасных выбросов',
 '62862':'Остаточный индекс опасных выбросов: 12 городов',
 '62861':'Доступные группы экологической информации',
 '62859':'Жители вблизи восстановленных водных объектов',
 '62779':'Сокращение площади лесных пожаров: прекращённый показатель',
 '62782':'Отнесённые к лесным землям восстановленные площади',
}
LOWER = {'62863','62871','62854','62793','62862'}
SHARES = {'62792','62793','62804','62778','62861'}
YTD_FROM_MONTH_LABEL = {'62777','62792','62793'}
METHOD_REVIEW = {'62787','62804'}
PROGRAM_BASELINE = {'62782':2025}
AIR_TERRITORIES = {
 '62862': ['Братск','Красноярск','Липецк','Магнитогорск','Медногорск','Нижний Тагил','Новокузнецк','Норильск','Омск','Челябинск','Череповец','Чита'],
 '62863': ['Абакан','Ангарский район','Астрахань','Ачинск','Барнаул','Верхнебуреинский район','Зима','Иркутск','Искитим','Кабанский район','Кемерово','Комсомольск-на-Амуре','Курган','Кызыл','Лесосибирск','Махачкала','Минусинск','Новочеркасск','Петровск-Забайкальский район','Ростов-на-Дону','Свирск','Селенгинский район','Улан-Удэ','Усолье-Сибирское','Уссурийск','Черемхово','Черногорск','Шелеховский район','Южно-Сахалинск'],
}
AIR_TERRITORIES['62860'] = list(AIR_TERRITORIES['62863'])
NOTES = {
 '62787':'Индекс использования вторичных ресурсов имеет собственную методику. Сохранённый паспорт ссылается на приказ 692 от 29.11.2024; официальный указатель содержит приказ 761 от 30.12.2025. Соответствие чисел этим редакциям не установлено. Приказ 416 от 28.07.2026 меняет ответственного заместителя министра, а не формулу; сам по себе он не является статистическим разрывом. Временные разности и исполнение цели до согласования 692 и 761 не рассчитываются.',
 '62863':'Остаточный индекс опасных выбросов к 2020 году для 29 территорий проекта. 100 минус индекс характеризует относительное сокращение к базе. Простое среднее городских индексов не является сокращением общей массы выбросов или воздействием на население. В исходнике есть также региональные строки; они сохраняются отдельно.',
 '62786':'Число ликвидированных опасных объектов накопленного вреда. Счёт объектов не взвешен по опасности, массе загрязнений, площади или числу людей в зоне риска. Годовой факт и последующие накопленные срезы не суммируются.',
 '62871':'Объём неочищенных сточных вод в миллионах кубических метров. Последнее число в сохранённой выгрузке относится к февралю 2026 года. Подпись месяца не доказывает отдельный месячный поток или независимость последовательных оценок; значения не суммируются и не продолжаются на будущие месяцы.',
 '62854':'Индекс остаточного негативного воздействия на Байкальскую природную территорию. Уменьшение индекса не равно установленному улучшению каждого компонента экосистемы. Последняя месячная запись относится к февралю 2026 года; годовой итог самостоятельный.',
 '62781':'Отношение площади лесовосстановления и лесоразведения текущего года к площади вырубленных и погибших насаждений двумя годами ранее. Значения выше 100 допустимы. Показатель 2025 года использует выбытие 2023 года. При нулевых компонентах выбытия методика 238 предусматривает 0 при нулевом восстановлении и 125% при положительном; поэтому значение 125 без компонентов не доказывает обычное деление площадей. Оперативное накопление начинается с января каждого года; сентябрь не заменяет год. Географический охват определяется методикой. Отношение площадей не измеряет экологические функции восстановленного леса.',
 '62777':'Исходная единица – «миллион человек». Учёт суммирует посещения федеральных ООПТ и не доказывает число уникальных лиц. Месячная подпись относится к накопленному итогу с января; сопоставляются одинаковые месяцы. Посещаемость не является самостоятельной оценкой сохранности природного комплекса.',
 '62828':'Число удалённых единиц затонувшего имущества. Исходные подписи «январь», «январь–месяц» и год сохранены. По последовательности нельзя объявлять каждый срез отдельным месячным результатом; начало программного накопления требует проверки полной методики. Число единиц не заменяет массу и устранённый экологический риск.',
 '62793':'Отношение направленной на захоронение массы ТКО к образованной массе за период с начала года. Обработка и последующее захоронение могут относиться к одним отходам. Доли 62792 и 62793 не образуют дополняющие части 100%. Декабрь и самостоятельный годовой факт различаются.',
 '62792':'Отношение направленной на обработку массы ТКО к образованной массе за период с начала года. Обработка не тождественна утилизации. Обработанные отходы могут затем направляться на захоронение; сумму долей нельзя представлять как структуру потока. Декабрь и самостоятельный годовой факт различаются.',
 '62804':'Доля утилизированных и обезвреженных отходов I и II классов опасности. Официальный указатель содержит методику 432 от 05.08.2026, отличающуюся по дате от сохранённого паспорта. Применимость редакций к отдельным наблюдениям не установлена; временные разности и исполнение цели приостановлены до согласования. Неполный 2026 год не сравнивается с годовым 2025.',
 '62778':'Доля определённых методикой видов птиц и млекопитающих, охваченных мероприятиями. Это охват действиями, а не рост численности популяций, снижение угроз или изменение природоохранного статуса.',
 '62860':'Численность жителей 29 территорий, для которых учитывается снижение опасных выбросов, в тысячах человек. Это административно определённый контингент, а не доказанная величина индивидуального снижения экспозиции или предотвращённых заболеваний.',
 '62862':'Остаточный индекс опасных выбросов к 2017 году для 12 городов. База отличается от группы 29 территорий. Опубликованное значение РФ сопоставляется с простым средним городских индексов, без переноса на массу выбросов и населённостно-взвешенную экспозицию.',
 '62861':'Доля доступных групп экологической информации, определённых методикой. Не равна доле информированных граждан, полноте измерений на каждой территории или качеству принятого решения.',
 '62859':'Численность жителей вблизи водных объектов с созданными условиями проживания. Накопленный административный охват не подтверждает изменение индивидуального качества жизни или здоровья. Повторение уровня между годами не считается новым числом получателей.',
 '62779':'Прежний показатель сокращения площади лесных пожаров сохранён для проверки исходных наблюдений. Изменение паспортного состава и отмена методики имеют разные даты. Приказ 604 от 31.08.2026 отменяет приказы 858 и 1000. По этому ряду не оцениваются действующая цель, её исполнение или прогноз; источник не подменяется преемником.',
 '62782':'Отнесённая к лесным землям площадь накапливается с 1 января 2025 года и не обнуляется в январе 2026 года. Разность к уточнённому годовому уровню 2025 отделяется от всего накопленного объёма. Годовой факт 2025 и декабрьская оперативная запись имеют разные значения.',
}

def source_rules(sid, title, unit):
    sid = str(sid)
    domain = 'proportion_0_100' if sid in SHARES else 'nonnegative_ratio' if sid == '62781' else 'nonnegative_index' if sid in {'62787','62863','62854','62862','62779'} else 'nonnegative_volume'
    semantics = 'cumulative_ytd' if sid in YTD_FROM_MONTH_LABEL | {'62781'} else 'cumulative_since_' + str(PROGRAM_BASELINE[sid]) if sid in PROGRAM_BASELINE else 'cumulative_program_baseline_unverified' if sid in {'62828','62859','62786'} else 'residual_index_to_base' if sid in {'62863','62862','62854'} else 'methodology_break_unresolved' if sid in METHOD_REVIEW else 'operational_monitoring'
    display = {'процент':'%','миллион человек':'млн человек','тысяча человек':'тыс. человек','миллион кубических метров':'млн м³','тысяча гектаров':'тыс. га','штука':'ед.'}.get(unit,unit)
    status = 'discontinued' if sid == '62779' else 'methodology_review_required' if sid in METHOD_REVIEW else 'active'
    return {'short_title':SHORT_TITLES[sid], 'direction':'lower' if sid in LOWER else 'higher',
            'domain':domain, 'lower_bound':0, 'upper_bound':100 if sid in SHARES else None,
            'note':NOTES[sid], 'display_unit':display, 'period_semantics':semantics, 'period_note':NOTES[sid],
            'cumulative':semantics.startswith('cumulative'), 'annual_reset':semantics=='cumulative_ytd',
            'cumulative_since':PROGRAM_BASELINE.get(sid), 'baseline_year':2017 if sid=='62862' else 2020 if sid=='62863' else None,
            'annual_equivalence':None, 'proxy_only':False, 'source_status':status,
            'target_comparison_allowed':sid not in METHOD_REVIEW | {'62779'},
            'temporal_comparison_allowed':sid not in METHOD_REVIEW | {'62779'},
            'temporal_comparison_eligible':sid not in METHOD_REVIEW | {'62779'},
            'scenario_allowed':sid not in METHOD_REVIEW | {'62779'},
            'methodology_references':(['https://rosstat.gov.ru/storage/mediabank/FP1506_N.htm','https://www.consultant.ru/document/cons_doc_LAW_547263/9fbb91a978d21ed646107611b1a476471472a280/'] if sid=='62781' else ['https://rosstat.gov.ru/storage/mediabank/FP1502_N.htm','https://legalacts.ru/doc/prikaz-minprirody-rossii-ot-28072026-n-416-o-vnesenii/'] if sid in {'62787','62792','62793','62804'} else ['https://base.garant.ru/414962788/'] if sid=='62779' else []),
            'target_unit_scale':1, 'project_territories':AIR_TERRITORIES.get(sid,[]),
            'geography_contract':'separate_national_regional_and_project_territories',
            'target_comparison_note':'Только самостоятельный годовой факт, согласованная единица и датированная редакция цели. Арифметическое сопоставление не удостоверяет формальное исполнение и причинный эффект.'}

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
    year=int(year); s=re.sub(r'\s+',' ',str(label or '').casefold()).strip()
    if s=='на конец года': return 'annual',f'{year}-01-01',f'{year}-12-31','explicit_year_end_source_row'
    if re.fullmatch(r'10\s+июля',s): return 'dated_snapshot',f'{year}-07-10',f'{year}-07-10','explicit_calendar_date'
    from emiss_adapter.normalize import decode_period as shared
    typ,a,b,_=shared(year,label,annual_only=source_frequency=='annual')
    frequency={'год':'annual','месяц':'monthly','накопительно с января':'cumulative_ytd'}[typ]
    if source_frequency=='cumulative_ytd' and frequency=='monthly':
        frequency='cumulative_ytd';a=f'{year}-01-01'
    if source_frequency not in {None,'unresolved',frequency} or start and start!=a or end and end!=b:
        raise ValueError('Source dates disagree with explicit period label: '+str(label))
    return frequency,a,b,'independent_annual' if frequency=='annual' else 'explicit_source_period'

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
    dims=json.loads(row.get('dimensions_json') or '{}')
    label=dims.get('Период','')
    frequency,start,end,basis=decode_period(row['year'],label,row['period_kind'],row.get('period_start'),row.get('period_end'))
    # First validate the original dates, then disclose any semantic interpretation.
    if sid in YTD_FROM_MONTH_LABEL and frequency=='monthly':
        frequency='cumulative_ytd';start=f"{int(row['year'])}-01-01"
        basis='documented_ytd_semantics_original_month_label_retained'
    date.fromisoformat(start);date.fromisoformat(end)
    name=row['territory_name']; key=territory_key(name);code=aliases.get(key)
    national_scope='rf_source_definition' if key==territory_key('Российская Федерация') else None
    municipalities={territory_key(n) for n in source.get('project_territories',[])}
    geography='national' if national_scope else 'project_territory' if key in municipalities else 'regional' if code else 'other'
    if geography=='other' and name not in source.get('known_territories',[]):raise ValueError('Unmapped source geography: '+name)
    if geography=='project_territory':code=None
    category,geography_dims=category_dimensions(dims)
    val=row.get('value_numeric')
    if val is not None and (not isinstance(val,(int,float)) or not math.isfinite(val)):raise ValueError('Invalid numeric cell')
    flags=[]
    if val is None:flags.append(flag('source_missing','В исходной ячейке нет числа. Значение не заменяется нулём или прошлым наблюдением.',True,'info'))
    if val is not None and val<0:flags.append(flag('below_domain','Отрицательное значение выходит за предметную область определения.',True))
    if val is not None and source.get('upper_bound') is not None and val>source['upper_bound']:flags.append(flag('above_domain','Значение вне области определения доли 0–100. Исходное число сохранено.',True))
    if val is not None and end>cutoff:flags.append(flag('future_period_at_snapshot','Период ещё не завершился к дате получения источника. Число сохранено, но не используется как факт завершённого периода.',True))
    if val is not None and sid=='62781' and val>100:flags.append(flag('ratio_above_100_allowed','Отношение площадей может превышать 100%. Число сохранено без отсечения; знаменатель относится к другому году.',False,'info'))
    if sid=='62781' and val==125:flags.append(flag('value_125_requires_components','Методика предусматривает условное значение 125% при положительном восстановлении и нулевом выбытии. Без компонентов нельзя отличить это правило от обычного отношения площадей.',False,'info'))
    if sid in METHOD_REVIEW:flags.append(flag('methodology_revision_requires_alignment',source['note'],False))
    if sid=='62779':flags.append(flag('discontinued_indicator',source['note'],False))
    if sid in {'62792','62793'} and code=='79' and val==0:flags.append(flag('zero_pair_requires_review','Исходный ноль Еврейской автономной области сохранён. Для годовой пары обработка/захоронение 0/0 показана отдельная проверка чувствительности без этой территории.',False))
    if val==0:flags.append(flag('zero_preserved','Исходный ноль сохранён и отличается от отсутствующего значения.',False,'info'))
    if geography=='project_territory':flags.append(flag('project_territory_scope','Муниципальная территория проекта; не подменяет значение субъекта Российской Федерации.',False,'info'))
    excluded=any(f['exclude_from_analysis'] for f in flags)
    region=(regions or {}).get(code,{})
    semantics='independent_annual' if frequency=='annual' else source['period_semantics']
    active=source.get('source_status')!='discontinued'
    return {'id':observation_key(sid,name,frequency,start,end,category),'source_id':sid,
            'source_observation_key':row.get('observation_key'),'name':name,'code':code,'map_id':code,'geo_level':geography,
            'fd':region.get('federal_district'),'national_scope':national_scope,'period':str(row['year']) if frequency=='annual' else end if frequency=='dated_snapshot' else end[:7],
            'period_start':start,'period_end':end,'year':int(row['year']),'frequency':frequency,
            'source_frequency':row['period_kind'],'source_period_start':row.get('period_start'),'source_period_end':row.get('period_end'),
            'source_period_label':label,'original_period_label':label,'period_basis':basis,'period_semantics':semantics,
            'value':val,'raw':row.get('value_raw'),'raw_value':row.get('value_raw'),'unit':source['unit'],
            'category':category,'source_dimensions':dims,'quality_flags':flags,'excluded':excluded,
            'analytical_value':None if excluded else val,'status':'missing' if val is None else 'excluded' if excluded else 'ok',
            'source_status':source.get('source_status','active'),'geographic_comparison_eligible':geography=='regional',
            'geographic_exclusion_reason':None if geography=='regional' else 'not_a_region',
            'annual_comparison_eligible':frequency=='annual' and val is not None and not excluded and active and source['target_comparison_allowed'],
            'temporal_comparison_eligible':source['temporal_comparison_allowed'] and val is not None and not excluded,
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
def annual_equivalents(source_id,rows):return []
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
