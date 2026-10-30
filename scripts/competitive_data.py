"""Loss-aware economic statistics and independently dated EMISS contracts.

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
PROJECT = 'competitive_economy'
DATA = Path('public/data/projects') / PROJECT
DOWNLOADS = Path('public/downloads/projects') / PROJECT / 'statistics'
STATISTICAL_AS_OF = '2026-10-15'
RELEASE = 'NationalProjects_Analytics_1.2.0'
ANNUAL_EQUIVALENCE = {}
SHORT_TITLES = {
 '62709':'Производительность экономики к 2023 году', '62710':'Охват предприятий несырьевых отраслей',
 '62711':'Охват организаций социальной сферы', '62979':'Реальный доход МСП на работника к 2023 году',
 '62978':'Прирост инвестиций к 2020 году', '63088':'Выручка малых технологических компаний',
 '63093':'Капитализация рынка акций к ВВП', '63094':'Доля долгосрочных сбережений',
 '62992':'Программы климатической адаптации', '63089':'Система мониторинга климатически активных веществ',
 '62981':'Переход МСП в более крупные категории', '63165':'Налоги МСП на работника: оперативный прокси',
 '62712':'Предприятия с номинальным приростом производительности 5%', '62829':'Занимающиеся спортом на работника отрасли',
 '63196':'Обучающиеся СПО на работника', '63195':'Обучающиеся школ и детсадов на работника',
 '63197':'Охват образовательных организаций', '62962':'Охват медицинских организаций',
 '62961':'Индекс диспансерного наблюдения на врачебную должность', '62960':'Индекс оборота койки',
 '63473':'Охват социального обслуживания и медико-социальной экспертизы', '63381':'Обучающиеся вуза на работника',
 '63234':'Обучающиеся на административного и вспомогательного работника вуза', '63232':'Охват организаций высшего образования',
 '62991':'Охват организаций культуры', '62990':'Индекс посещений организаций культуры на работника',
 '63121':'Охват организаций спорта', '63126':'Публичные размещения государственных компаний',
 '63128':'Средства в долгосрочных финансовых продуктах', '63127':'Публичные размещения акций компаний',
 '63129':'Доля средств граждан в ПИФ и доверительном управлении', '63136':'Технологические компании в реестровом показателе кооперации',
 '63222':'Технологические компании с размещением ценных бумаг', '63362':'Университетские стартапы со статусом МТК',
 '63176':'Система развития конкуренции', '63175':'Рост удовлетворённости участников рынка',
 '63177':'Товары для национальных ценовых индикаторов',
}
SHARES = {'62710','62711','63094','62981','62712','63197','62962','63473','63232','62991','63121','63129'}
INDEXES = {'62709','62979','63165','62961','62960','62990','63175'}
REPEATED_ANNUAL = {'62709','62979','62712'}
QUARTERLY_LABELS = {'63088','62992','63222'}
YTD_FROM_MONTH_LABEL = {'62960','62961'}
NOTES = {
 '62709':'Макроэкономический индекс к 2023 году имеет годовой экономический смысл. Месячная строка показывает публикацию или повтор последнего расчёта. Нули среди положительных индексов сохранены и исключены из аналитики до разъяснения статуса. Декабрьская запись не становится самостоятельным годовым фактом. Изменение всей экономики не идентифицирует эффект адресной поддержки.',
 '62710':'Накопленный охват предприятий, соответствующих критериям участия. Доля охвата не измеряет реальный прирост добавленной стоимости и не позволяет суммировать последовательные месячные уровни. Годовая запись учитывается отдельно от декабрьской.',
 '62711':'Охват государственных и муниципальных организаций социальной сферы. Межотраслевые различия совокупностей и знаменателей сохраняются. Участие в проекте не удостоверяет улучшение качества услуг.',
 '62979':'Доход субъекта МСП на одного учитываемого работника, дефлированный и сопоставленный с 2023 годом. Показатель не является заработной платой или доходом домохозяйства. Месячные строки повторяют последнюю годовую оценку. Для годового сравнения используется только самостоятельная годовая запись. Состав предприятий, доход и знаменатель занятости могут меняться одновременно.',
 '62978':'Прирост объёма инвестиций к 2020 году выражен в процентах прироста, поэтому 34,7 означает индекс 134,7. Подписи марта, июня, сентября и декабря сохранены как исходные месячные метки квартального мониторинга. Суммирование уровней и подмена годового факта декабрём не допускаются. Номинальный объём инвестиций и индекс физического объёма различаются.',
 '63088':'Совокупная выручка компаний со статусом МТК на конец периода. Методика предусматривает накопление с начала года. Квартальные записи сохраняют отдельную частоту и начало периода 1 января. Динамика зависит от состава реестра и уточнений годовой отчётности. Кварталы не суммируются, IV квартал не подменяет самостоятельный годовой факт. Резкий переход между годами требует сверки состава и периода выручки.',
 '63093':'Отношение капитализации рынка акций к ВВП. Может превышать 100% и не является ограниченной долей. Рыночная переоценка и изменение номинального ВВП воздействуют на отношение. Капитализация не равна новым средствам, полученным предприятиями от размещений. Для длинного ряда необходимо согласование расчётного охвата.',
 '63094':'Доля долгосрочных финансовых продуктов в объёме сбережений. Месячная декабрьская запись не является самостоятельным годовым итогом. Показатель не характеризует долю граждан с достаточным резервом и фактический срок удержания вложений.',
 '62992':'Число утверждённых и реализованных программ адаптации. Квартальная подпись сохранена. Счёт документов не измеряет снижение климатического ущерба, затраты адаптации и её воздействие на уязвимые группы. Квартальные уровни не суммируются.',
 '63089':'Годовой индикатор создания системы мониторинга. Явная исходная подпись «ежегодно» разрешена как годовой факт с сохранением оригинала. Нулевой факт при нулевом плане означает арифметическое равенство. Оно не доказывает создание системы. Статус принимает 0 или 1; промежуточная дробная система не рассчитывается.',
 '62981':'Доля МСП, превысивших пороги своей категории по реестровым критериям. Переход не удостоверяет сохранение нового масштаба в последующие годы. Динамика зависит от порогов, цен, реестрового состава и занятости.',
 '63165':'Налоговый показатель является оперативным прокси дохода МСП. Отчётный месяц отражает состояние на конец предшествующего месяца. Налоговые ставки, режимы, сроки платежей и зачётов меняют величину независимо от реального дохода. Подмена ряда 62979 этим рядом и совместное обучение прогноза запрещены.',
 '62712':'Доля предприятий, достигших ежегодного прироста производительности на 5%. Методика предусматривает номинальную добавленную стоимость на работника. Выполнение критерия не подтверждает реальный прирост 5%. Месячные публикации повторяют последний годовой расчёт и не образуют независимую месячную историю.',
 '62829':'Число систематически занимающихся спортом в расчёте на работника отрасли. Отношение может расти при сокращении числа работников. Требуются отдельные сведения о качестве, доступности занятий и нагрузке персонала.',
 '63196':'Обучающиеся профессиональных образовательных организаций на работника. Учитываются состав персонала, контингент и качество обучения. Высокое отношение не является самостоятельным доказательством экономической эффективности.',
 '63195':'Обучающиеся дошкольных и общеобразовательных организаций на работника. Изменение знаменателя и структуры учреждений влияет на отношение. Доступность образования, размер групп и качество услуг оцениваются отдельно.',
 '63197':'Охват образовательных организаций мероприятиями повышения производительности. Участие учреждения и качество образовательного результата требуют разных подтверждений.',
 '62962':'Доля медицинских организаций, охваченных мероприятиями. Для сентября 2026 года доступны 88 региональных чисел. Доля не является клиническим исходом, охватом пациентов или приростом производительности.',
 '62961':'Индекс случаев диспансерного наблюдения на занятую врачебную должность относительно базы. Методика использует накопленные с начала года компоненты. Сравниваются одинаковые календарные горизонты. Исходный ноль базового индекса требует разъяснения и исключается из аналитики. Качество наблюдения и нагрузка врача оцениваются отдельно.',
 '62960':'Индекс оборота койки к базе 2023 года использует накопленные с начала года компоненты. Число оборотов не равно качеству лечения. Сравниваются одинаковые календарные горизонты. Нулевой индекс сохранён с исключением из аналитики до разъяснения статуса.',
 '63473':'Охват организаций социального обслуживания и медико-социальной экспертизы. Участие в мероприятиях не характеризует качество и доступность помощи. Самостоятельный годовой факт сохраняется отдельно.',
 '63381':'Обучающиеся на одного работника вуза. Изменение числителя, состава работников и продолжительности обучения требует самостоятельной проверки. Более высокая величина не означает автоматически лучшее качество образования.',
 '63234':'Обучающиеся на работника административной и вспомогательной категории вуза. Знаменатель отличается от полного состава работников. Показатель нельзя соединять с 63381 в одну временную серию.',
 '63232':'Охват организаций высшего образования. Накопленный охват и самостоятельная годовая запись разделены. Выполнение плановой доли не измеряет результат обучения.',
 '62991':'Накопленный охват организаций культуры. Исходный тип периода cumulative_ytd сохраняется. Сравниваются одинаковые месяцы. Исходные нули охвата допустимы и не заменяются пропусками. Доля участия не измеряет посещения или качество услуги.',
 '62990':'Годовой индекс посещений организаций культуры на работника. Значение выше 100 допустимо. Индекс не тождественен числу уникальных посетителей, качеству культурной услуги или благополучию работников.',
 '63121':'Охват организаций спорта мероприятиями повышения производительности. Содержание знаменателя и качество услуг оцениваются отдельно от доли участия.',
 '63126':'Объём публичных размещений государственных компаний в триллионах рублей. В сохранённом источнике доступна методика без числовой таблицы. Отсутствие чисел не означает нулевой объём.',
 '63128':'Средства в программе долгосрочных сбережений, ИИС и долевом страховании жизни в триллионах рублей. В источнике доступны только метаданные. Пополнения, переводы накоплений и государственное софинансирование требуют раздельного учёта.',
 '63127':'Объём публичных размещений акций в триллионах рублей. Числовая таблица отсутствует в сохранённом источнике. Объём размещений, капитализация рынка и бюджетные расходы имеют разные определения.',
 '63129':'Доля средств физических лиц в ПИФ и доверительном управлении. Сохранены метаданные без числовой таблицы. Отсутствие ряда не интерпретируется как отсутствие средств.',
 '63136':'Реестровый показатель технологических компаний, которые могут участвовать либо участвуют в проектах и кооперационных цепочках. Число не подтверждает исполненные контракты и фактические поставки. Для результата нужны даты и объёмы договоров.',
 '63222':'Число технологических компаний с внебиржевым или биржевым размещением ценных бумаг. Квартальные уровни сохраняются отдельно. Повторение значения не считается новым размещением и не суммируется.',
 '63362':'Университетские стартапы, получившие статус малой технологической компании. Статус и включение в реестр не доказывают устойчивые коммерческие продажи. Отдельно проверяются выживаемость, состав когорты и выручка от независимых заказчиков.',
 '63176':'Создание системы развития конкуренции характеризует правовые и организационные условия. Метаданные доступны, числовой таблицы нет. Индикатор не измеряет рыночную власть на конкретном товарном рынке. Статус принимает 0 или 1; плавная интерполяция этапа не выполняется.',
 '63175':'Рост совокупной удовлетворённости участников рынка. Числовая таблица отсутствует. Необходимы состав выборки, сопоставимость вопросов, охват групп и правила агрегирования.',
 '63177':'Расширение перечня товаров для национальных ценовых индикаторов. Числовая таблица отсутствует. Количество позиций не характеризует качество каждого ценового ориентира и интенсивность конкуренции.',
}

def source_rules(sid, title, unit):
    sid=str(sid)
    semantics=('annual_estimate_republished_monthly' if sid in REPEATED_ANNUAL else
       'cumulative_ytd_quarterly' if sid=='63088' else 'cumulative_ytd' if sid in YTD_FROM_MONTH_LABEL|{'62991'} else
       'cumulative_participation' if sid in {'62710','62711','63232'} else
       'lagged_tax_proxy' if sid=='63165' else 'quarter_end_monitoring_to_base_2020' if sid=='62978' else
       'quarterly_level' if sid in QUARTERLY_LABELS else 'operational_monitoring')
    display={'процент':'%','миллион рублей':'млн руб.','триллион рублей':'трлн руб.','человек':'чел.','единица':'ед.','штука':'ед.'}.get(unit,unit)
    return {'short_title':SHORT_TITLES[sid],'direction':'higher','domain':'binary_status' if sid in {'63089','63176'} else 'proportion_0_100' if sid in SHARES else 'nonnegative_index' if sid in INDEXES else 'growth_percent' if sid=='62978' else 'nonnegative_ratio' if sid=='63093' else 'nonnegative_volume',
       'lower_bound':-100 if sid=='62978' else 0,'upper_bound':1 if sid in {'63089','63176'} else 100 if sid in SHARES else None,
       'display_unit':display,'note':NOTES[sid],'period_note':NOTES[sid],'period_semantics':semantics,
       'cumulative':semantics.startswith('cumulative'),'annual_reset':semantics in {'cumulative_ytd','cumulative_ytd_quarterly'},
       'annual_equivalence':None,'baseline_year':2023 if sid in {'62709','62979','62960','62961'} else 2020 if sid=='62978' else None,
       'proxy_only':sid=='63165','proxy_for_source_id':'62979' if sid=='63165' else None,'reference_lag_months':1 if sid=='63165' else 0,
       'nominal_growth_criterion':sid=='62712','real_growth':sid in {'62709','62979'},
       'source_status':'active','target_comparison_allowed':sid!='63165','temporal_comparison_allowed':sid not in {'62709','62712'},
       'temporal_comparison_eligible':sid not in {'62709','62712'},'scenario_allowed':sid not in {'62709','62712','63165','63089','63176'},
       'methodology_references':[f'https://www.fedstat.ru/indicator/{sid}'],'target_unit_scale':1,'project_territories':[],
       'geography_contract':'separate_national_regional_and_other_scopes',
       'target_comparison_note':'Сопоставление допустимо только для самостоятельного годового факта, согласованной единицы и датированной редакции цели. Арифметическая разность не удостоверяет исполнение всего проекта или причинный эффект.'}
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
    if sid=='63088' and frequency=='quarterly':
        start=f"{int(row['year'])}-01-01";basis='explicit_quarter_documented_ytd_components'
    date.fromisoformat(start);date.fromisoformat(end)
    name=row['territory_name'];key=territory_key(name);code=aliases.get(key)
    national_scope='rf_source_definition' if key==territory_key('Российская Федерация') else None
    geography='national' if national_scope else 'regional' if code else 'other'
    if geography=='other' and name not in source.get('known_territories',[]):raise ValueError('Unmapped source geography: '+name)
    category,geography_dims=category_dimensions(dims);val=row.get('value_numeric')
    if val is not None and (isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val)):raise ValueError('Invalid numeric cell')
    flags=[]
    if val is None:flags.append(flag('source_missing','В исходной ячейке нет числа. Значение сохраняется как пропуск.',True,'info'))
    if val is not None and val<source.get('lower_bound',0):flags.append(flag('below_domain','Значение ниже области определения. Исходное число сохранено.',True))
    if val is not None and source.get('upper_bound') is not None and val>source['upper_bound']:flags.append(flag('above_domain','Значение превышает верхнюю границу определения показателя. Исходное число сохранено.',True))
    if val is not None and source['domain']=='binary_status' and val not in {0,1}:flags.append(flag('outside_binary_status','Индикатор состояния допускает только 0 или 1. Дробный статус не интерпретируется как частично созданная система.',True))
    if val is not None and end>cutoff:flags.append(flag('future_period_at_snapshot','Период ещё не завершился к дате получения источника. Число сохранено отдельно от фактов завершённого периода.',True))
    if val==0:
        flags.append(flag('zero_preserved','Исходный ноль сохранён и отличается от отсутствующего значения.',False,'info'))
        if sid in INDEXES:flags.append(flag('zero_base_index_requires_review','Нулевой индекс с положительной базой требует разъяснения статуса. Запись сохранена и исключена из аналитических разностей, карт и сценариев.',True))
    if sid in REPEATED_ANNUAL and frequency!='annual':flags.append(flag('annual_estimate_republished','Месячная публикация последней годовой оценки не является независимым месячным наблюдением.',False,'info'))
    if sid=='62712':flags.append(flag('nominal_growth_criterion','Критерий 5% относится к номинальному росту. Реальный прирост данным показателем не установлен.',False,'info'))
    if sid=='63165':flags.append(flag('lagged_proxy_not_target_fact','Налоговый прокси с месячным сдвигом не заменяет годовой доход МСП.',False,'info'))
    if sid=='63088':flags.append(flag('registry_composition_and_reporting_period','Накопленная выручка зависит от состава реестра и периода бухгалтерской отчётности. Суммирование квартальных уровней не допускается.',False,'info'))
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
