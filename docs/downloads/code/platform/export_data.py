#!/usr/bin/env python3
"""Audited Export contracts. Annual and monthly observations never share identity."""
from pathlib import Path
from datetime import date
import csv, hashlib, json, math
from personnel_data import region_aliases, territory_key, merge_observations
ROOT=Path(__file__).resolve().parents[1]
PROJECT='international_export'
DATA=Path('public/data/projects/international_export')
DOWNLOADS=Path('public/downloads/projects/international_export/statistics')
STATISTICAL_AS_OF='2026-10-15'
SOURCE_ORDER=['62713','62715','62716','62717','62718','62719','62720','62721','62723','62724','62728','62729','62730','62731','62736','62740','62742','63154']
MAPPING=dict(zip(SOURCE_ORDER,['2.14.М.1','2.14.М.2','2.14.М.3','2.14.М.4','2.14.М.5','2.14.М.6','2.14.М1.1','2.14.М1.2','2.14.М3.1','2.14.М3.2','2.14.М3.3','2.14.М3.4','2.14.М3.5','2.14.М3.6','2.14.М4.1','2.14.М4.2','2.14.М.7','2.14.М2.1']))
NOTES={
 '62713':('Прирост ННЭ к 2023 году','growth_from_fixed_base','Прирост к базе 2023 года, а не темп к предыдущему месяцу. В исходном срезе годовая запись 2025 года 10,2% и декабрьская 0,5% сохранены раздельно; декабрьская запись не заменяет самостоятельный годовой результат. Отрицательный прирост и прирост свыше 100% математически допустимы.'),
 '62715':('Несырьевой неэнергетический экспорт','cumulative_flow','Номинальная стоимость в млрд долларов США с начала календарного года. Январь–сентябрь сравнивается с январём–сентябрём. Валютная стоимость зависит от цен и состава поставок и не является индексом физического объёма.'),
 '62716':('ННЭ в дружественные страны','cumulative_flow','Номинальная стоимость с начала года. В исходном срезе годовая запись 2025 года 141,59 и декабрьская запись 141,8 млрд долларов различаются; самостоятельная годовая запись имеет приоритет для годового сопоставления. Перечень дружественных стран требует контроля редакции.'),
 '62717':('Промышленный экспорт','cumulative_flow','Номинальная стоимость экспорта товаров отраслей промышленности с начала года. Изменение долларовой выручки не отделяет цены, физические объёмы и товарную структуру. Состав продукции задаётся методикой.'),
 '62718':('Внешнеторговые сделки с инструментами РЭЦ','cumulative_flow','Стоимость внешнеторговых сделок с использованием инструментов Группы РЭЦ с начала года. Контракт, экспортная поставка, кредит, страховка и бюджетная субсидия имеют разные единицы учёта. Сумма сделок не является дополнительным причинным эффектом поддержки.'),
 '62719':('Охват опорных стран инфраструктурой','weighted_infrastructure_coverage','В исходном срезе 15.10.2026 годовое и декабрьское значения 2025 года равны нулю. Это опубликованные числа, не пропуски. Методика 2026 года учитывает взвешенные объекты в 29 странах и на африканском континенте; показатель не является простой долей стран. Исторические ячейки не пересчитаны задним числом.'),
 '62720':('Промышленный экспорт в дружественные страны','cumulative_flow','Номинальная стоимость с начала календарного года. Исходный ряд заканчивается декабрём 2025 года. Показатель зависит от товарной и географической классификации.'),
 '62721':('Высокотехнологичный экспорт','cumulative_flow','Номинальная стоимость с начала календарного года. В исходном срезе последняя запись — ноябрь 2025 года. Она не заменяет отсутствующий годовой итог и не сопоставляется с годовой целью как исполнение.'),
 '62723':('Сервисы «Одного окна»','available_service_stock','Число доступных сервисов, а не число обращений и завершённых экспортных операций. Исходный срез содержит только январь и февраль 2025 года; повторение уровня 44 не создаёт годовой результат.'),
 '62724':('Экспортёры цифровой экосистемы','registered_organization_count','Счётчик организаций в установленном методикой периметре. В исходном срезе доступны только январь и февраль 2025 года. Наличие в экосистеме не подтверждает дополнительный экспорт или отсутствие двойного учёта при других мерах.'),
 '62728':('Удовлетворённость услугами «Одного окна»','survey_score','Условная единица оценки удовлетворённости, не процент. Исходный ряд содержит только январь и февраль 2025 года. Без охвата и состава ответивших различие оценок не является достоверным изменением качества всех услуг.'),
 '62729':('Активные личные кабинеты','active_account_stock','Число активных кабинетов. Кабинет, организация, обращение и экспортная сделка не тождественны. В исходном срезе доступны только январь и февраль 2025 года.'),
 '62730':('Организации с поддержкой РЭЦ','supported_organization_count','Количество организаций, воспользовавшихся мерами поддержки, в установленном методикой периметре. В исходном срезе доступны только январь и февраль 2025 года. Не измеряет чистый прирост экспорта благодаря поддержке.'),
 '62731':('Региональный экспортный стандарт 2.0','legacy_standard_count','Источник относится к Региональному экспортному стандарту 2.0; выбранная паспортная цель относится к версии 3.0. Два значения 75 за январь–февраль 2025 года сохранены как исторический ряд, но не используются для оценки выполнения цели 3.0.'),
 '62736':('АПК в дружественные страны','cumulative_flow','Номинальная стоимость аграрного экспорта в дружественные страны с начала года. В исходном срезе 2026 год заканчивается августом; сопоставляется с январём–августом 2025 года, а не с полным годом.'),
 '62740':('Расчётная эффективность поддержки АПК','support_formula_ratio','Годовая расчётная эффективность мер поддержки. Отношение экспорта и бюджетной поддержки не является оценкой причинной отдачи расходов; согласуются период, валюта числителя и рублёвая единица знаменателя.'),
 '62742':('Экспорт продукции АПК','cumulative_flow','Номинальная стоимость аграрного экспорта с начала года. В исходном срезе последний период 2026 года — август. Территория регистрации экспортёра не равна месту выращивания, переработки и создания добавленной стоимости.'),
 '63154':('Исполнение программы зарубежной инфраструктуры','annual_program_cumulative_progress','Накопленное выполнение годовой программы. Переход со 100% в декабре 2025 года к 0% в январе 2026 года отражает смену годовой программы, а не потерю уже созданных объектов. Прокси-показатель не заменяет фактическую загрузку инфраструктуры.')}
YTD={'62715','62716','62717','62718','62720','62721','62736','62742','63154'}
STALE={'62723','62724','62728','62729','62730','62731'}
SHARES={'62719','63154'}
FORMATS={sid:('sdmx' if sid in {'62713','62716','62718','62728'} else 'grid' if sid=='62731' else 'excel') for sid in SOURCE_ORDER}

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
 if value is None:flags.append({'code':'missing','exclude_from_analysis':True,'message':'Число отсутствует в источнике. Пропуск не заменён нулём.'})
 if value is not None and ((value<0 and sid!='62713') or sid in SHARES and value>100 or sid=='62713' and value<-100):flags.append({'code':'domain_violation','exclude_from_analysis':True,'message':'Значение вне области определения показателя.'})
 flags.append({'code':NOTES[sid][1],'exclude_from_analysis':False,'message':NOTES[sid][2]})
 dimensions=row.get('dimensions_json') or '{}';dimensions=json.loads(dimensions) if isinstance(dimensions,str) else dimensions
 category={k:v for k,v in dimensions.items() if k not in {'Показатель','Год','Период','Единица измерения','ОКАТО','ОКТМО','ОКСМ'}}
 excluded=any(f['exclude_from_analysis'] for f in flags);period=original_end[:7] if source_frequency!='annual' else str(year)
 key=hashlib.sha256(json.dumps([sid,territory_key(name),frequency,start,original_end,category],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 return {'id':key,'source_id':sid,'source_observation_key':row.get('observation_key'),'indicator_code':MAPPING[sid],'catalog_indicator_code':row.get('indicator_code'),'name':name,'code':None,'map_id':None,'geo_level':'national','fd':None,'territory_code_source':row.get('territory_code'),'period':period,'year':year,'period_start':start,'period_end':original_end,'frequency':frequency,'source_frequency':source_frequency,'source_period_start':original_start,'source_period_end':original_end,'source_period_label':dimensions.get('Период'),'period_semantics':NOTES[sid][1],'value':value,'raw':row.get('value_raw') or '' if value is None else str(row.get('value_raw',value)),'unit':source['unit'],'category':category,'quality_flags':flags,'excluded':excluded,'analytical_value':None if excluded else value,'status':row.get('value_status','ok'),'annual_comparison_eligible':source_frequency=='annual' and not excluded and sid!='62731','annual_equivalent_eligible':period.endswith('-12') and not excluded and sid not in STALE,'geographic_comparison_eligible':False,'methodology_version':'not_determined_for_individual_historical_cell','acquired_at':row.get('acquired_at'),'snapshot_id':row.get('snapshot_id'),'origin_kind':row.get('origin_kind','live_emiss'),'source_url':source['source_url'],'source_cell_attributes':json.loads(row.get('attributes_json') or '{}')}
