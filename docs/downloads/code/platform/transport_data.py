#!/usr/bin/env python3
"""Transport source contracts preserve original cells and distinguish stocks from flows."""
from pathlib import Path
from datetime import date
import csv, hashlib, json, math
from personnel_data import region_aliases, territory_key, merge_observations
ROOT=Path(__file__).resolve().parents[1]
PROJECT='efficient_transport'
DATA=Path('public/data/projects/efficient_transport')
DOWNLOADS=Path('public/downloads/projects/efficient_transport/statistics')
STATISTICAL_AS_OF='2026-10-15'
SOURCE_ORDER=['62841','62832','62820','62851','63269','62850','62849','62848','62847','62846','62819','62824','62823','62822','62821','62834','62831','62833','62845','62844','62878','63268']
MAPPING=dict(zip(SOURCE_ORDER,['2.14.Т.2','2.14.Т.1','2.14.Т.5','2.14.Т.4','2.14.Т.6','2.14.Т1.1','2.14.Т3.1','2.14.Т3.2','2.14.Т3.3','2.14.Т3.4','2.14.Т4.1','2.14.Т4.2','2.14.Т4.3','2.14.Т4.4','2.14.Т5.1','2.14.Т5.2','2.14.Т6.1','2.14.Т6.2','2.14.Т7.1','2.14.Т7.2','2.14.Т8.1','2.14.Т9.2']))
NOTES={
 '62841':('Мощность опорной транспортной сети','composite_capacity_index','Индекс к базовому уровню 2024 года, не доля и не физический объём перевозок. Значения выше 100 допустимы. Методика приравнивает годовое значение последнему месяцу с последующей верификацией. Снижение 103 до 102 в декабре 2025 года не доказывает утрату инфраструктуры.'),
 '62832':('Авиационная подвижность','cumulative_flow','Накопленные перевозки пассажиров российских авиакомпаний относительно населения. Методика меняла знаменатель на фиксированное население на 1 января 2023 года. Версия расчёта каждой исторической ячейки в выгрузке не установлена. Число перевозок не равно числу уникальных пассажиров.'),
 '62820':('Грузоперевозки по Севморпути','cumulative_flow','Масса грузов с начала календарного года. Январь–сентябрь сопоставляется с январём–сентябрём. Расчётный темп не продолжается линейно в прогноз полного года. Общий объём и транзит имеют разные совокупности.'),
 '62851':('Цифровая трансформация грузоперевозок','cumulative_fixed_denominator_index','Число электронных документов с начала года делится на фиксированный прогноз 5 млрд документов 2030 года. Индекс не является текущей долей цифровых перевозок. Скачок сентября 2026 года требует проверки первичного охвата и уточнений.'),
 '63269':('Доля обученных на обновлённом оборудовании','previous_annual_result_published_monthly','Месячное значение по приказу №174 принимает годовой результат предыдущего отчётного года. Числитель накапливается за период проекта, знаменатель отражает годовую занятость. Декабрьская запись не признаётся итогом обучения текущего года.'),
 '63268':('Подготовка на тренажёрах и учебных судах','previous_annual_result_published_monthly','Месячное значение по приказу №174 относится к предыдущему отчётному году. Посещение занятий не равно выпуску, подтверждённым навыкам или трудоустройству. Отдельный годовой результат в выгрузке отсутствует.'),
 '62850':('Минимальное время Москва – Санкт-Петербург','minimum_service_time','Минимальное время выбранного сообщения, минуты. Не включает подход, ожидание и пересадки и не измеряет среднее время поездки всех пассажиров. Снижение целевого времени предусмотрено к 2028 году; отсутствующие цели 2029–2030 не подменяются нулём.'),
 '62849':('Восточный полигон железных дорог','technical_capacity_stock','Расчётная годовая провозная способность. Унаследованная мощность не равна новому вводу или фактически перевезённому грузу. Повторяющиеся месячные уровни не образуют независимый ряд транспортной работы.'),
 '62848':('Железнодорожные подходы к Азово-Черноморским портам','technical_capacity_stock','Суммарная расчётная провозная способность подходов, млн т в год. Для сквозного маршрута необходима готовность смежных звеньев. Не суммируется с портовой мощностью как единый поток.'),
 '62847':('Железнодорожные подходы к Северо-Западным портам','technical_capacity_stock','Суммарная расчётная провозная способность подходов, млн т в год. Состояние инфраструктуры не измеряет её загрузку или общественный эффект.'),
 '62846':('Железнодорожный коридор Север – Юг','technical_capacity_stock','Расчётная провозная способность железнодорожного направления. Уровень выше плана не определяет дату ввода и не доказывает завершённость всех звеньев международного маршрута.'),
 '62819':('Прирост портовой мощности на Востоке','cumulative_project_capacity_stock','Прирост расчётной мощности с начала проекта. Январские уровни не обнуляются. Опубликованный нулевой прирост является числом, отсутствующая ячейка – пропуском. Не равен фактической перевалке.'),
 '62824':('Прирост портовой мощности на Северо-Западе','cumulative_project_capacity_stock','Прирост расчётной мощности с начала проекта, без ежегодного обнуления. Для оценки результата нужны фактическая перевалка и загрузка введённых объектов.'),
 '62823':('Прирост портовой мощности Север – Юг','cumulative_project_capacity_stock','Опубликованный нулевой прирост сохранён как число. Нулевая цель 2025 года допускает расчёт разности, но не процента выполнения. Мощность и поток различаются.'),
 '62822':('Прирост портовой мощности на Азово-Черноморском направлении','cumulative_project_capacity_stock','Нулевой прирост мощности сохранён. Цель 2025 года в выбранном паспорте отсутствует, поэтому нулевое наблюдение не получает условной нулевой цели.'),
 '62821':('Проход судов с осадкой 3,6 метра','infrastructure_length_share','Доля протяжённости Единой глубоководной системы с установленной осадкой. Не доля судов или груза. Требования к осадке, участкам и навигационному периоду сохраняют самостоятельный смысл.'),
 '62834':('Пригодность гидротехнических сооружений','structure_condition_share','Доля судоходных гидротехнических сооружений, пригодных к дальнейшей эксплуатации. Числитель включает сооружения с нормальным и пониженным уровнем безопасности. Доля не означает, что все включённые сооружения находятся в нормальном состоянии. Показатель состояния не заменяет анализ индивидуального риска и последствия отказа критического объекта.'),
 '62831':('Пропускная способность аэродромов','technical_capacity_stock','Расчётное число взлётов и посадок в час. Не фактическое число рейсов и не число перевезённых пассажиров. Эффект зависит от флота, маршрутов и спроса.'),
 '62833':('Расчётный пассажиропоток аэродромов','technical_capacity_stock','Расчётная пропускная способность в пассажирах в час. Не число выполненных поездок. Преобразование в годовую массу без режима работы и загрузки недопустимо.'),
 '62845':('Автомобильные пункты пропуска','technical_capacity_stock','Годовая расчётная пропускная способность в тысячах единиц. В выгрузке единица записана как тысяча единиц, годовой смысл раскрыт методикой. Не фактические пересечения границы или время ожидания.'),
 '62844':('Железнодорожные пункты пропуска','technical_capacity_stock','Годовая расчётная пропускная способность, млн т в год. Накопленный уровень инфраструктуры не равен перевезённой массе и не измеряет время контроля.'),
 '62878':('Расчётный индекс эффективности инвестиций','investment_formula_index','Нормативная расчётная формула с базой 100. Значение выше 100 допустимо. Распределение агрегированного изменения пропорционально финансированию не идентифицирует причинный эффект использования ГИС ТЭБ. Требуется согласование рублей и тысяч рублей.')}
YTD={'62820','62832','62851'}
STAFF={'63268','63269'}
SHARES={'63269','62821','62834'}

def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def atomic(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(path)
def csv_write(path,rows,columns=None):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);keys=columns or list(dict.fromkeys(k for r in rows for k in r))
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
  for r in rows:w.writerow({k:json.dumps(r.get(k),ensure_ascii=False) if isinstance(r.get(k),(dict,list)) else r.get(k) for k in keys})

def normalize_record(row,source,aliases=None,regions=None):
 sid=str(row['source_id']);assert sid==str(source['indicator_id'])
 if row['unit'].strip().casefold()!=source['unit'].strip().casefold():raise ValueError('Unit mismatch '+sid)
 original_start,original_end=row['period_start'],row['period_end'];date.fromisoformat(original_start);date.fromisoformat(original_end)
 if original_start>original_end:raise ValueError('Reversed period')
 year=int(row['year']);source_frequency=row['period_kind']
 if source_frequency not in ('monthly','cumulative_ytd','quarterly','annual'):raise ValueError('Unrecognised source frequency')
 frequency='cumulative_ytd' if sid in YTD and source_frequency!='annual' else 'monthly' if source_frequency=='cumulative_ytd' else source_frequency
 start=f'{year}-01-01' if frequency=='cumulative_ytd' else original_start
 name=row['territory_name']
 if territory_key(name)!=territory_key('Российская Федерация'):raise ValueError('Unreviewed geographic scope '+name)
 rawval=row.get('value_numeric');value=None if rawval in (None,'') else float(rawval)
 if value is not None and not math.isfinite(value):raise ValueError('Nonfinite value')
 flags=[]
 if value is None:flags.append({'code':'missing','exclude_from_analysis':True,'message':'Числовое значение отсутствует в источнике. Пропуск не заменён нулём.'})
 if value is not None and (value<0 or sid in SHARES and value>100):flags.append({'code':'domain_violation','exclude_from_analysis':True,'message':'Значение вне области определения показателя.'})
 flags.append({'code':NOTES[sid][1],'exclude_from_analysis':False,'message':NOTES[sid][2]})
 dimensions=row.get('dimensions_json') or '{}';dimensions=json.loads(dimensions) if isinstance(dimensions,str) else dimensions
 category={k:v for k,v in dimensions.items() if k not in {'Показатель','Год','Период','Единица измерения','ОКАТО','ОКТМО','ОКСМ'}}
 excluded=any(f['exclude_from_analysis'] for f in flags);period=original_end[:7] if source_frequency!='annual' else str(year)
 key=hashlib.sha256(json.dumps([sid,territory_key(name),frequency,start,original_end,category],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 return {'id':key,'source_id':sid,'source_observation_key':row.get('observation_key'),'indicator_code':MAPPING[sid],'catalog_indicator_code':row.get('indicator_code'),'name':name,'code':None,'map_id':None,'geo_level':'national','fd':None,'territory_code_source':row.get('territory_code'),'period':period,'year':year,'period_start':start,'period_end':original_end,'frequency':frequency,'source_frequency':source_frequency,'source_period_start':original_start,'source_period_end':original_end,'source_period_label':dimensions.get('Период'),'period_semantics':NOTES[sid][1],'value':value,'raw':row.get('value_raw') or '' if value is None else str(row.get('value_raw',value)),'unit':source['unit'],'category':category,'quality_flags':flags,'excluded':excluded,'analytical_value':None if excluded else value,'status':row.get('value_status','ok'),'annual_comparison_eligible':source_frequency=='annual' and not excluded,'annual_equivalent_eligible':period.endswith('-12') and not excluded and sid not in STAFF,'geographic_comparison_eligible':False,'methodology_version':'not_determined_for_individual_historical_cell','acquired_at':row.get('acquired_at'),'snapshot_id':row.get('snapshot_id'),'origin_kind':row.get('origin_kind','live_emiss'),'source_url':source['source_url'],'source_cell_attributes':json.loads(row.get('attributes_json') or '{}')}
