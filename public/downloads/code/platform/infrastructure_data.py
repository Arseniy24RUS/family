"""Loss-aware Infrastructure for Life source contracts.

Year-end source rows, independent annual observations, calendar accumulation,
monthly records and explicitly dated snapshots remain identifiable. No gap is
filled. Original source dimensions, values and period labels are retained.
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
PROJECT = 'life_infrastructure'
DATA = Path('public/data/projects') / PROJECT
DOWNLOADS = Path('public/downloads/projects') / PROJECT / 'statistics'
STATISTICAL_AS_OF = '2026-10-15'
RELEASE = 'NationalProjects_Analytics_1.2.0'
ANNUAL_EQUIVALENCE = {}

SHORT_TITLES = {
 '62872':'Качество среды в опорных населённых пунктах', '62876':'Обновление жилищного фонда',
 '40466':'Жилая площадь на человека', '59262':'Ввод жилья в многоквартирных домах',
 '59263':'Общий ввод жилья', '59993':'Ввод жилья населением',
 '62882':'Жители с улучшением коммунальных услуг', '62881':'Объекты питьевого водоснабжения',
 '62893':'Благоустроенные общественные территории', '62892':'Реализованные проекты конкурса среды',
 '62879':'Длительность строительного цикла', '63457':'Погибшие в ДТП на 10 тыс. транспортных средств',
 '63456':'Оперативный расчёт погибших в ДТП', '61608':'Выданные ипотечные кредиты',
 '62795':'Нормативные дороги агломераций', '62794':'Нормативные региональные дороги',
 '62801':'Нормативные дороги опорной сети', '62798':'Нормативные федеральные дороги',
 '62887':'Нормативный возраст общественного транспорта', '62890':'Переселение из непригодного жилья',
 '62875':'Повышение доступности первичного жилья', '63028':'Прокси: индекс доступности жилья',
 '62944':'ИЖС с использованием счетов эскроу', '63052':'Социальная газификация домовладений',
 '63460':'Земля для индивидуального строительства', '63181':'Пригородные поезда внутри агломераций',
 '63122':'Нормативная инфраструктура электротранспорта', '62797':'Обходы на федеральных дорогах',
 '62800':'Обходы на региональных и местных дорогах', '62799':'Удовлетворённость автомобильными дорогами',
 '62796':'Зрелость интеллектуальных транспортных систем', '63152':'Индекс энергосбережения в строительстве',
 '59319':'Ставка по ипотечному кредиту', '62993':'Пассажиропоток центрального транспортного узла',
}
LOWER = {'62879','63457','63456','59319'}
NOTES = {
 '62872':'Составной показатель для опорных населённых пунктов. Сохранённый паспорт ЕМИСС ссылается на приказ 446/пр от 25.07.2025, авторская экспертиза – на действующую редакцию 363/пр от 09.06.2026 с 16 компонентами. Сопоставимость методических редакций не подтверждена. Перенос компонентов и территориальные замены не раскрыты на уровне каждой ячейки. Временные разности, прогноз и исполнение плана по этому ряду заблокированы.',
 '62876':'Доля фонда, обновлённого после 2019 года. Собственный годовой факт не означает доступность нового жилья для каждого домохозяйства.',
 '40466':'Площадь на одного жителя. Категории «Всего», город и село сохраняются раздельно. Среднее по регионам не заменяет опубликованное значение РФ. Ряд характеризует обеспеченность площадью, без учёта цены, состояния и распределения между домохозяйствами.',
 '59263':'Общий ввод жилья включает многоквартирное строительство и строительство населением. В источнике отдельно представлены год, месяц и январь–месяц. С 2023 года географический охват ряда определяется источником без четырёх новых субъектов. Сумма округлённых компонентов может отличаться от общего значения.',
 '59262':'Компонент общего ввода – многоквартирные дома. Не сопоставляется с паспортной целью общего ввода жилья. Месяцы и накопленные итоги не суммируются совместно.',
 '59993':'Компонент общего ввода – жильё, построенное населением. Не сопоставляется с целью общего ввода. Изменение регистрации, площади и доступности жилья требует раздельного анализа.',
 '62882':'Численность накоплена с 2025 года. После положительного июня 2026 года в июле–сентябре 2026 опубликованы нули для страны и всех территорий. Такие ячейки сохранены, но исключены из аналитики до проверки учёта. Последнее пригодное значение не переносится на последующие периоды.',
 '62881':'Число объектов накоплено с 2019 года. Не равно числу объектов текущего проекта или людей с подтверждённым улучшением водоснабжения.',
 '62893':'Количество общественных территорий нарастает с 2025 года. Не измеряет площадь, состояние после ввода или распределение выгод среди жителей.',
 '62892':'Реализованные проекты конкурса нарастают с 2025 года. Не складываются с числом территорий без пообъектной проверки пересечений.',
 '62879':'Административный показатель длительности инвестиционно-строительного цикла. Снижение не удостоверяет качество объекта или готовность эксплуатации.',
 '63457':'Годовой показатель – погибшие в ДТП на 10 тыс. зарегистрированных транспортных средств. Единица в исходнике «человек», знаменатель указан в названии и методике. Не равен смертности на 100 тыс. жителей.',
 '63456':'Оперативный показатель накоплен с начала года. Сравнение с самостоятельным годовым рядом 63457 требует одинакового горизонта и проверки методики. Из неполного года не выводится годовое исполнение.',
 '61608':'Объём выдачи нарастает с января. Валюты сохраняются отдельными категориями. Методика предусматривает годовую сумму 12 месяцев. При отсутствии самостоятельного годового значения январь–декабрь может быть отдельным годовым ориентиром с явной маркировкой. Ревизии годовой записи и декабрьского накопления могут расходиться.',
 '62794':'Отдельная исходная строка «на конец года» отличается от декабря. Обе записи сохранены. Доля нормативных дорог не измеряет время поездки или доступность услуг.',
 '62801':'Опорная сеть и региональная сеть имеют различный состав. Отдельная строка «на конец года» используется для годового сравнения, декабрь остаётся оперативным срезом.',
 '62795':'Нормативность сети крупнейших агломераций. Территориальный охват показателя отличается от всей дорожной сети субъекта.',
 '62798':'Федеральные дороги. Отдельная годовая строка и декабрьский мониторинг не взаимозаменяемы.',
 '62887':'Доля парка в пределах нормативного возраста. Пропуск не означает отсутствие транспорта. Нормативный возраст не измеряет частоту, вместимость, маршрутную доступность и состояние каждого транспортного средства.',
 '62890':'Число переселённых накоплено с 2019 года. Отдельный годовой и месячные срезы не суммируются. Результат включает период до начала национального проекта.',
 '62875':'Показатель повышения доступности первичного жилья имеет собственную методику. Прокси 63028 не подменяет этот годовой показатель.',
 '63028':'Прокси-показатель по собственной методике. Не подставляется в паспортную цель повышения доступности жилья 62875.',
 '62944':'Доля ИЖС по договорам подряда с эскроу. Относится к определённой форме строительства, а не ко всему индивидуальному жилищному фонду.',
 '63052':'Подключённые домовладения накоплены программой социальной газификации. Количество домовладений не равно числу жителей.',
 '63460':'Выявленная земельная площадь не равна введённому жилью или участкам с готовой инфраструктурой. Отдельная запись «10 июля» сохранена как датированный срез 10.07.2026, отдельно от июльского месяца.',
 '63181':'Размер движения измеряется парами поездов. Число пар не равно пассажиропотоку и не охватывает все виды повседневных поездок.',
 '63122':'Доля нормативной контактной сети и путей электротранспорта. Состояние инфраструктуры не заменяет оценку маршрутов, частоты и доступности.',
 '62797':'Накопленное число построенных обходов федеральных дорог. Количество объектов не равно протяжённости и общественному эффекту.',
 '62800':'Накопленное число обходов региональных и местных дорог. Не складывается с федеральными без проверки непересечения объектов.',
 '62799':'Доля опрошенных, отметивших улучшение. Для переноса на всё население необходимы дизайн опроса и оценка неопределённости.',
 '62796':'Доля городов установленной совокупности, достигших уровня зрелости ИТС. Ограничения по населению и исключённым территориям заданы методикой.',
 '63152':'Составной индекс энергосбережения в строительстве. Административный индекс не равен измеренному сокращению расходов домохозяйств.',
 '59319':'Средняя ставка опубликованного кредитного контингента. Среднее по субъектам без кредитных весов не заменяет показатель РФ. Годовой показатель не подменяется ставкой декабря.',
 '62993':'Пассажиропоток центрального транспортного узла. Исходная единица «пассажиропоток» сохранена. Масштаб и способ учёта требуют проверки, произвольного перевода в пассажиров или миллионы нет.',
}
SHARES = {'62876','62795','62794','62801','62798','62887','62944','63122','62799','62796','63152'}
CUMULATIVE_SINCE = {'62882':2025,'62881':2019,'62893':2025,'62892':2025,'62890':2019}
UNVERIFIED_CUMULATIVE_BASELINE = {'63052','62797','62800'}

def source_rules(sid, title, unit):
    sid = str(sid)
    domain = 'proportion_0_100' if sid in SHARES else 'nonnegative_index' if sid in {'62872','62875','63028'} else 'nonnegative_volume'
    semantics = 'mixed_annual_monthly_ytd' if sid in {'59262','59263','59993'} else 'cumulative_ytd' if sid in {'61608','63456'} else 'cumulative_since_'+str(CUMULATIVE_SINCE[sid]) if sid in CUMULATIVE_SINCE else 'cumulative_program_baseline_unverified' if sid in UNVERIFIED_CUMULATIVE_BASELINE else 'methodology_break_unresolved' if sid=='62872' else 'stock_at_period_end' if sid in {'62795','62794','62801','62798','62887','63460'} else 'operational_monitoring'
    display = {'процент':'%','миллион квадратных метров общей площади':'млн м²','квадратный метр':'м²/чел.','миллион человек':'млн чел.','тысяча человек':'тыс. чел.','триллион рублей':'трлн руб.','процент годовых':'% годовых','пара (2 шт.)':'пар поездов','миллион единиц':'млн ед.','гектар':'га'}.get(unit,unit)
    if sid in {'63457','63456'}: display='чел. на 10 тыс. транспортных средств'
    note = NOTES[sid]
    if sid in UNVERIFIED_CUMULATIVE_BASELINE:
        note+=' Точный базовый год накопления не подтверждён сохранённым описанием методики. Произвольная дата начала накопления не назначается.'
    return {'short_title':SHORT_TITLES[sid], 'direction':'lower' if sid in LOWER else 'higher', 'domain':domain,
            'lower_bound':0, 'upper_bound':100 if sid in SHARES else None, 'note':note, 'display_unit':display,
            'period_semantics':semantics, 'period_note':note, 'cumulative':semantics.startswith('cumulative'),
            'annual_reset':semantics=='cumulative_ytd', 'annual_equivalence':None,
            'target_comparison_allowed':sid not in {'62872','62882','59262','59993','63028','63456','62993'},
            'proxy_only':sid=='63028', 'temporal_comparison_allowed':sid not in {'62872'},
            'temporal_comparison_eligible':sid not in {'62872'},
            'target_unit_scale':1000 if sid=='63460' else 1,
            'target_comparison_note':'Сопоставление выполняется по явной редакции и единице, самостоятельному годовому значению или отдельному документированному полному годовому накоплению.'}

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
    additions={
      'Архангельская область (без а/о)':'29','Архангельская область (без АО)':'29',
      'Тюменская область (без а/о)':'72','Тюменская область (без АО)':'72',
      'Архангельская область без данных по Ненецкому автономному округу':'29',
      'Тюменская область без данных по Ханты-Мансийскому автономному округу - Югре и Ямало-Ненецкому автономному округу':'72',
      'в том числе Ненецкий автономный округ':'83','в том числе Ханты-Мансийский автономный округ - Югра':'86',
      'в том числе Ямало-Ненецкий автономный округ':'89','Чувашская Республика':'21',
      'Забайкальский край\\':'75','Республика Бурятия\\':'03','Республика Крым\\':'91','г. Севастополь\\':'92',
    }
    aliases.update({territory_key(k):v for k,v in additions.items()})
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
    date.fromisoformat(start);date.fromisoformat(end)
    name=row['territory_name'];code=aliases.get(territory_key(name))
    national_scope='rf_without_new_subjects_from_2023' if sid in {'59262','59263','59993'} and name=='Российская Федерация без учета новых субъектов (с 01.01.2023)' else 'rf_source_definition' if territory_key(name)==territory_key('Российская Федерация') else None
    geography='national' if national_scope else 'regional' if code else 'other'
    if geography=='other' and name not in source.get('known_territories',[]):
        raise ValueError('Unmapped source geography: '+name)
    category,geography_dims=category_dimensions(dims)
    val=row.get('value_numeric')
    if val is not None and (not isinstance(val,(int,float)) or not math.isfinite(val)):raise ValueError('Invalid numeric cell')
    flags=[]
    if val is None:flags.append(flag('source_missing','В исходной ячейке нет числа. Значение не заменяется нулём или прошлым наблюдением.',True,'info'))
    if val is not None and val<0:flags.append(flag('below_domain','Отрицательное значение выходит за предметную область определения.',True))
    if val is not None and source.get('upper_bound') is not None and val>source['upper_bound']:flags.append(flag('above_domain','Значение вне области определения доли 0–100. Исходное число сохранено.',True))
    if val is not None and end>cutoff:flags.append(flag('future_period_at_snapshot','Период ещё не завершился к дате получения источника. Число сохранено, но не используется как факт завершённого периода.',True))
    if sid=='62872':flags.append(flag('methodology_break_unresolved','Редакции методики и обновление компонентов не согласованы. Временные изменения и исполнение плана не рассчитываются.',False))
    if sid=='62882' and val==0 and '2026-07-01'<=start<='2026-09-30':flags.append(flag('synchronized_zero_after_positive','Общий сброс накопленного показателя после положительного июня2026. До сверки источник сохранён без аналитического использования этих нулей.',True))
    if sid=='62993':flags.append(flag('unit_scale_unresolved','Масштаб исходной единицы «пассажиропоток» не уточнён. Пересчёт единицы и сравнение с планом заблокированы.',False))
    if national_scope=='rf_without_new_subjects_from_2023':flags.append(flag('national_geographic_scope','Российская Федерация без учёта новых субъектов с01.01.2023 в определении источника. Сравнение через изменение охвата2022/2023 не выполняется.',False,'info'))
    if val==0:flags.append(flag('zero_preserved','Исходный ноль сохранён и отличается от отсутствующего значения.',False,'info'))
    if basis=='explicit_year_end_source_row':flags.append(flag('explicit_year_end','Годовая строка явно подписана «на конец года». Не выведена из декабрьского значения.',False,'info'))
    excluded=any(f['exclude_from_analysis'] for f in flags)
    region=(regions or {}).get(code,{})
    ambiguous=code in {'29','72'} and not any(x in name.casefold() for x in ['кроме','без'])
    semantics='year_end_stock' if basis=='explicit_year_end_source_row' else 'independent_annual' if frequency=='annual' else source['period_semantics']
    return {'id':observation_key(sid,name,frequency,start,end,category),'source_id':sid,
            'source_observation_key':row.get('observation_key'),'name':name,'code':code,'map_id':code,'geo_level':geography,
            'fd':region.get('federal_district'),'national_scope':national_scope,'period':str(row['year']) if frequency=='annual' else end if frequency=='dated_snapshot' else end[:7],
            'period_start':start,'period_end':end,'year':int(row['year']),'frequency':frequency,
            'source_frequency':row['period_kind'],'source_period_start':row.get('period_start'),'source_period_end':row.get('period_end'),
            'source_period_label':label,'original_period_label':label,'period_basis':basis,'period_semantics':semantics,
            'value':val,'raw':row.get('value_raw'),'raw_value':row.get('value_raw'),'unit':source['unit'],
            'category':category,'source_dimensions':dims,'quality_flags':flags,'excluded':excluded,
            'analytical_value':None if excluded else val,'status':'missing' if val is None else 'excluded' if excluded else 'ok',
            'geographic_comparison_eligible':not ambiguous,'geographic_exclusion_reason':'unclear_autonomous_okrug_scope' if ambiguous else None,
            'annual_comparison_eligible':frequency=='annual' and val is not None and not excluded,
            'temporal_comparison_eligible':sid!='62872' and val is not None and not excluded,
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
