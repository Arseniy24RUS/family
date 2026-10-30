#!/usr/bin/env python3
"""Tourism observation contracts. Original source cells are never overwritten by inference."""
from pathlib import Path
from datetime import date
import csv, hashlib, json, math, re
from personnel_data import region_aliases, territory_key, convert_live, merge_observations

ROOT=Path(__file__).resolve().parents[1]
DATA=Path('public/data/projects/tourism')
DOWNLOADS=Path('public/downloads/projects/tourism/statistics')
STATISTICAL_AS_OF='2026-10-15'
SOURCE_ORDER=['62900','62159','62903','62902','63347','62780']
MAPPING={'62900':'2.14.П.2','62159':'2.14.П1.1','62903':'2.14.П.3','62902':'2.14.П.1','63347':'2.14.П3.1','62780':'2.14.П5.1'}
NOTES={
 '62900':('Туристические поездки','cumulative_flow','Месячные колонки содержат накопленные оценки с начала года. Разности соседних оценок не публикуются как месячный поток без проверки единой редакции. Поездки не равны уникальным людям.'),
 '62159':('Классифицированный номерной фонд','administrative_stock','Запас зарегистрированных номеров на дату наблюдения. Изменение реестра не тождественно строительному вводу. Ранние накопительные подписи источника сохранены.'),
 '62903':('Доля туристской отрасли','annual_estimate_repeated_monthly','Годовая величина опубликована в месячных колонках. Первая годовая оценка может приниматься равной плану. Знаменатель по методике – ВДС всех отраслей в основных ценах. Исторические ячейки не заменены более поздним сообщением Росстата.'),
 '62902':('Экспорт туристских услуг','quarterly_cumulative_publication','Денежная оценка, млрд долларов США. Повторные месячные публикации не являются независимыми месячными потоками. Стадия уточнения сохранённой декабрьской оценки не установлена.'),
 '63347':('Иностранные размещения','cumulative_flow','Физическая величина, млн размещённых иностранных граждан. Отдельный показатель и прокси экспорта. Не переводится в доллары и не интерпретируется как число уникальных иностранцев.'),
 '62780':('Отечественная продукция для туризма','reported_share_with_carryforward','Опубликованная доля. Повторение значения не удостоверяет независимые результаты за каждый месяц. Исходные числитель и знаменатель в выбранной выгрузке не раскрыты.')}

def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def atomic(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(path)
def csv_write(path,rows,columns=None):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 keys=columns or list(dict.fromkeys(k for r in rows for k in r))
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
  for r in rows:w.writerow({k:json.dumps(r.get(k),ensure_ascii=False) if isinstance(r.get(k),(dict,list)) else r.get(k) for k in keys})

def normalize_record(row,source,aliases,regions=None):
 sid=str(row['source_id']);assert sid==str(source['indicator_id'])
 if row['unit'].strip().casefold()!=source['unit'].strip().casefold():raise ValueError('Unit mismatch '+sid)
 original_start,original_end=row['period_start'],row['period_end'];date.fromisoformat(original_start);date.fromisoformat(original_end)
 if original_start>original_end:raise ValueError('Reversed period')
 year=int(row['year']);frequency=row['period_kind'];start=original_start
 if frequency not in ('monthly','cumulative_ytd','quarterly','annual'):raise ValueError('Unrecognised source frequency')
 if sid in ('62900','63347') and frequency=='monthly':frequency='cumulative_ytd';start=f'{year}-01-01'
 name=row['territory_name'];code=aliases.get(territory_key(name));geo='national' if territory_key(name)==territory_key('Российская Федерация') else 'regional' if code else 'other'
 rawval=row.get('value_numeric');value=None if rawval in (None,'') else float(rawval)
 if value is not None and not math.isfinite(value):raise ValueError('Nonfinite value')
 flags=[]
 if value is None:flags.append({'code':'missing','exclude_from_analysis':True,'message':'Числовое значение отсутствует в источнике.'})
 if value is not None and (value<0 or source['unit'].casefold()=='процент' and value>100):flags.append({'code':'domain_violation','exclude_from_analysis':True,'message':'Значение вне области определения.'})
 if value==0 and sid in ('62902','62903','62780'):
  flags.append({'code':'zero_status_unresolved','exclude_from_analysis':True,'message':'Исходный ноль сохранён. Он не интерпретируется как отсутствие экономической деятельности, поскольку статус и компоненты оценки не установлены.'})
 flags.append({'code':NOTES[sid][1],'exclude_from_analysis':False,'message':NOTES[sid][2]})
 dimensions=row.get('dimensions_json') or '{}';dimensions=json.loads(dimensions) if isinstance(dimensions,str) else dimensions
 category={k:v for k,v in dimensions.items() if k not in {'Показатель','Год','Период','Единица измерения','ОКАТО','ОКТМО','ОКСМ'}}
 excluded=any(f['exclude_from_analysis'] for f in flags)
 period=original_end[:7] if row['period_kind']!='annual' else str(year)
 key=hashlib.sha256(json.dumps([sid,territory_key(name),frequency,start,original_end,category],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 return {'id':key,'source_id':sid,'source_observation_key':row.get('observation_key'),'indicator_code':MAPPING[sid],'catalog_indicator_code':row.get('indicator_code'),
  'name':name,'code':code,'map_id':code,'geo_level':geo,'fd':(regions or {}).get(code,{}).get('federal_district'),
  'territory_code_source':row.get('territory_code'),'period':period,'year':year,'period_start':start,'period_end':original_end,
  'frequency':frequency,'source_frequency':row['period_kind'],'source_period_start':original_start,'source_period_end':original_end,
  'source_period_label':dimensions.get('Период'),'period_semantics':NOTES[sid][1],
  'value':value,'raw':row.get('value_raw'),'unit':source['unit'],'category':category,'quality_flags':flags,
  'excluded':excluded,'analytical_value':None if excluded else value,'status':row.get('value_status','ok'),
  'annual_comparison_eligible':False,'annual_equivalent_eligible':period.endswith('-12') and not excluded,
  'geographic_comparison_eligible':geo=='regional' and not excluded,'acquired_at':row.get('acquired_at'),
  'snapshot_id':row.get('snapshot_id'),'origin_kind':row.get('origin_kind','live_emiss'),
  'source_url':source['source_url'],'source_cell_attributes':json.loads(row.get('attributes_json') or '{}')}
