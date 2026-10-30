#!/usr/bin/env python3
"""Rebuild the distinct CBR services context from unchanged official workbooks."""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from xml.etree import ElementTree as ET
import csv, hashlib, io, json, os, re, zipfile
ROOT=Path(__file__).resolve().parents[1]
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
ALIASES={
 'Город Москва столица Российской Федерации город федерального значения':'77',
 'Город Санкт-Петербург город федерального значения':'78',
 'Город федерального значения Севастополь':'92',
 'Чувашская Республика - Чувашия':'21',
 'Ханты-Мансийский автономный округ':'86',
 'Тюменская область без данных по Ханты-Мансийскому автономному округу -Югре и Ямало-Ненецкому автономному округу':'72',
 'Архангельская область без данных по Ненецкому автономному округу':'29',
}
MAIN_COMPONENTS={'transport':'K','travel':'P','ict':'AY','insurance':'BD','finance':'BI','intellectual_property':'BN','business':'BS','personal_cultural':'BX','government':'CC','other':'CH'}

def normalized(name):
 name=re.sub(r'^\d+\s+','',name.strip()).replace('ё','е').lower()
 return re.sub(r'[^а-яa-z0-9]','',re.sub(r'\([^)]*\)','',name))

def workbook_cells(path):
 with zipfile.ZipFile(path) as z:
  strings=[''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml'))]
  cells={}
  for row in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//m:row',NS):
   for cell in row:
    v=cell.find('m:v',NS)
    value=v.text if v is not None else ''
    if cell.get('t')=='s' and value:value=strings[int(value)]
    if value:cells[cell.get('r')]=value
 return cells

def published_number(raw):
 # Official legends distinguish an absent phenomenon from missing information.
 if raw.strip()=='-':return Decimal('0')
 if raw.strip() in {'','...','…'}:return None
 return Decimal(raw).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)

def write_json(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 temp=path.with_name(path.name+'.tmp')
 temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');os.replace(temp,path)

def build(root=ROOT):
 root=Path(root);inp=root/'inputs/international_export/context';out=root/'public/data/projects/international_export'
 cat=json.loads((root/'public/data/catalog.json').read_text(encoding='utf-8'))['regions']
 by_id={r['id']:r for r in cat};mapping={normalized(r['name']):r['id'] for r in cat}
 mapping.update({normalized(n):rid for n,rid in ALIASES.items()})
 expected=json.loads((inp/'sources.json').read_text(encoding='utf-8'))
 records=[];national=[];unallocated=[];concentration=[];sources=[];reconciliation=[];excluded=[]
 for year in [2024,2025]:
  filename=f'cbr_services_regions_{year}.xlsx';source=next(s for s in expected['sources'] if s['name']==filename)
  path=inp/filename;raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
  if sha!=source['sha256']:raise ValueError('Source workbook checksum changed: '+filename)
  cells=workbook_cells(path)
  if cells.get('F7','').strip()!=f'{year} г.':raise ValueError('Unexpected annual column')
  if 'млн долларов США' not in cells.values():raise ValueError('Unexpected workbook unit')
  seen=set();region_decimals=[]
  for rownum in range(8,106):
   label=cells.get(f'A{rownum}','');raw_value=cells.get(f'F{rownum}','')
   if not label or not raw_value:continue
   value=published_number(raw_value)
   item={'year':year,'value':float(value) if value is not None else None,'raw_value':raw_value,'source_cell':f'F{rownum}','source_url':source['url']}
   if label=='ВСЕГО':national.append(item);continue
   if label.startswith('Не распределено'):unallocated.append(item);continue
   if 'ФЕДЕРАЛЬНЫЙ ОКРУГ' in label:
    excluded.append({'year':year,'name':label,'source_cell':f'F{rownum}','reason':'district_aggregate'});continue
   if normalized(label) in {normalized('Архангельская область'),normalized('Тюменская область')}:
    excluded.append({'year':year,'name':label,'source_cell':f'F{rownum}','reason':'aggregate_includes_autonomous_okrugs'});continue
   rid=mapping.get(normalized(label))
   if not rid or rid in seen:raise ValueError('Unmatched or duplicate territory: '+label)
   seen.add(rid)
   if value is None:raise ValueError('Unexpected missing annual total: '+label)
   region_decimals.append(value)
   components={key:(float(v) if v is not None else None) for key,col in MAIN_COMPONENTS.items() if (v:=published_number(cells.get(f'{col}{rownum}',''))) is not None}
   # Keep missing component cells explicit instead of making them zero.
   for key in MAIN_COMPONENTS:components.setdefault(key,None)
   records.append({**item,'map_id':rid,'name':by_id[rid]['name'],'source_name':label,'components':components,'component_cells':{key:f'{col}{rownum}' for key,col in MAIN_COMPONENTS.items()}})
  if len(seen)!=85:raise ValueError('Expected 85 mutually exclusive territories')
  total=published_number(cells['F8']);unalloc=published_number(cells['F105']);assigned=sum(region_decimals)
  residual=assigned+unalloc-total
  rounding_bound=Decimal(len(region_decimals)+2)*Decimal('.005')
  if abs(residual)>rounding_bound:raise ValueError('Regional reconciliation outside the cumulative rounding bound')
  sorted_values=sorted(region_decimals,reverse=True);top10=sum(sorted_values[:10])
  current=[r for r in records if r['year']==year];moscow=next(r['value'] for r in current if r['map_id']=='77')
  concentration.append({'year':year,'n_regions':85,'allocated_million_usd':float(assigned),'hhi_allocated':float(sum((v/assigned)**2 for v in region_decimals)),'top10_share_national_pct':float(top10/total*100),'top10_share_allocated_pct':float(top10/assigned*100),'moscow_share_national_pct':float(Decimal(str(moscow))/total*100)})
  reconciliation.append({'year':year,'regional_sum':float(assigned),'unallocated':float(unalloc),'national':float(total),'residual':float(residual),'tolerance':float(rounding_bound),'unit':'млн долларов США','note':'Расхождение суммы опубликованных округлённых ячеек и национального итога сохраняется. Верхняя граница округления: (85 субъектов + нераспределённая сумма + национальный итог) × 0,005 млн долларов США.'})
  local='downloads/projects/international_export/context/'+filename
  dest=root/'public'/local;dest.parent.mkdir(parents=True,exist_ok=True)
  if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest()!=sha:
   temp=dest.with_name(dest.name+'.tmp');temp.write_bytes(raw);os.replace(temp,dest)
  sources.append({'year':year,'url':source['url'],'local_file':local,'sha256':sha,'bytes':len(raw),'source_updated':cells['A114'],'retrieved_at':expected['retrieved_at']})
 r24={r['map_id']:r['value'] for r in records if r['year']==2024};r25={r['map_id']:r['value'] for r in records if r['year']==2025}
 growth={'increased':sum(r25[k]>r24[k] for k in r24),'decreased':sum(r25[k]<r24[k] for k in r24),'unchanged':sum(r25[k]==r24[k] for k in r24),'comparable_regions':len(r24)}
 result={'schema':'national-projects.export-regional-context/1','project_id':'international_export','services':{
  'rows':records,'national':national,'unallocated':unallocated,'years':[2024,2025],'unit':'млн долларов США','source_url':sources[-1]['url'],'sources':sources,'concentration':concentration,'growth_summary':growth,'reconciliation':reconciliation,'excluded_aggregates':excluded,'missing_map_ids':sorted(set(by_id)-set(r25)),
  'notes':['Отдельный источник Банка России. Региональные значения не включаются в число рядов ЕМИСС национального проекта.','Архангельская и Тюменская области представлены без автономных округов. Самостоятельные округа учитываются отдельными строками.','Доля региона в национальном итоге и доля в распределённой сумме используют разные знаменатели. Нераспределённые операции показаны отдельно.','Территория учёта экспортной операции может отличаться от места производства, занятости и получения дохода. Для индивидуальных предпринимателей источник использует территорию филиала банка.','Пустые категории и знак многоточия обозначают отсутствие данных. Знак дефиса обозначает отсутствие явления по легенде источника. Годовые значения сохраняют точность опубликованной таблицы до 0,01 млн долларов США.'],
  'note':'Экспорт услуг по данным Банка России. Представлены 85 сопоставимых территорий за 2024 и 2025 годы. Нераспределённая часть сохраняется отдельно.'}}
 write_json(out/'regional-context.json',result)
 download=root/'public/downloads/projects/international_export/context/cbr_services_regions_2024_2025.csv'
 stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(['region_id','region_name','source_name','year','million_usd','source_cell','source_url'])
 for r in records:writer.writerow([r['map_id'],r['name'],r['source_name'],r['year'],r['value'],r['source_cell'],r['source_url']])
 temp=download.with_name(download.name+'.tmp');temp.write_text('\ufeff'+stream.getvalue(),encoding='utf-8');os.replace(temp,download)
 result['services']['download_csv']='downloads/projects/international_export/context/'+download.name
 write_json(out/'regional-context.json',result)
 audit={'project_id':'international_export','sources':sources,'regional_rows':len(records),'regions':85,'excluded_aggregate_rows':len(excluded),'reconciliation':reconciliation,'concentration':concentration,'growth_summary':growth,'status':'passed'}
 write_json(root/'documentation/EXPORT_REGIONAL_CONTEXT_AUDIT.json',audit)
 return result

if __name__=='__main__':
 d=build()['services'];print(json.dumps({'regions':85,'observations':len(d['rows']),'concentration':d['concentration'],'growth':d['growth_summary'],'reconciliation':d['reconciliation']},ensure_ascii=False))
