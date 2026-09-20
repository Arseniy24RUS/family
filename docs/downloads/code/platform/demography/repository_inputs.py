"""Read the author's documented XLSX/CSV contract, retaining observation status.
Binary XLSX is read using Python's standard XML/ZIP libraries. No office application
or runtime dependency on a spreadsheet engine is required. Unsupported schemas fail
closed. Projections in a status sheet are NEVER accepted as observed base stocks.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, re, time, urllib.request, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from .cohort import fertility_profile, migration_profile, validate_input
REPO='Arseniy24RUS/Population-Forecast-Dashboard-of-Russia-2100'
FILES=['POP_wide_female_noMIG.xlsx','POP_wide_male_noMIG.xlsx','LE_Russia_subjects_forecast_2100_long.csv','MIG_cyclic_tidy.csv','TFR_Russia_subjects_ML_GP_UCM_tidy.csv']
S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

def norm(v): return re.sub(r'[^a-zа-я0-9]', '',str(v or '').lower().replace('ё','е'))
def number(v):
    if isinstance(v,bool) or v is None: raise ValueError('Пропуск числовой ячейки')
    z=float(str(v).replace('\u00a0','').replace(' ','').replace(',','.'))
    if not math.isfinite(z):raise ValueError('Неконечное значение')
    return z

def get_bytes(url, limit=32_000_000):
    last=None
    for attempt in range(2):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Semya-research-platform/1.1 (+academic reproducibility)','Accept':'*/*'})
            with urllib.request.urlopen(req,timeout=25) as r:
                if r.status!=200:raise ValueError('HTTP '+str(r.status))
                data=r.read(limit+1)
                if len(data)>limit:raise ValueError('Источник превышает установленный предел размера')
                return data
        except Exception as exc:
            last=exc
            if attempt==0:time.sleep(.5)
    raise RuntimeError(f'Не получен {url}: {last}')

def xlsx_sheets(path):
    """Return sheet-name -> worksheet path; reject ZIP bombs before parsing."""
    z=zipfile.ZipFile(path)
    if sum(i.file_size for i in z.infolist())>350_000_000:raise ValueError('Слишком большой распакованный XLSX')
    rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'));targets={r.attrib['Id']:r.attrib['Target'] for r in rels}
    sheets={}
    for e in ET.fromstring(z.read('xl/workbook.xml')).iter(S+'sheet'):
        target=targets[e.attrib[REL+'id']].replace('\\','/')
        dest=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        if '..' in PurePosixPath(dest).parts:raise ValueError('Некорректный путь XLSX')
        sheets[e.attrib['name']]=dest
    return z,sheets

def xlsx_rows(path,sheet):
    z,sheets=xlsx_sheets(path)
    try:
        if sheet not in sheets:raise ValueError(f'В книге отсутствует обязательный лист {sheet}. Доступны: {list(sheets)}')
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            for event,e in ET.iterparse(z.open('xl/sharedStrings.xml'),events=('end',)):
                if e.tag==S+'si': strings.append(''.join(t.text or '' for t in e.iter(S+'t')));e.clear()
        for event,row in ET.iterparse(z.open(sheets[sheet]),events=('end',)):
            if row.tag!=S+'row':continue
            values=[]
            for cell in row:
                if cell.tag!=S+'c':continue
                letters=re.match(r'[A-Z]+',cell.attrib.get('r','A1'))[0];idx=0
                for c in letters:idx=idx*26+ord(c)-64
                while len(values)<idx:values.append(None)
                typ=cell.attrib.get('t');v=cell.find(S+'v')
                if typ=='inlineStr': val=''.join(t.text or '' for t in cell.iter(S+'t'))
                elif v is None:val=None
                elif typ=='s':val=strings[int(v.text)]
                elif typ in ('str','e','b'):val=v.text
                else:
                    try:val=float(v.text);val=int(val) if val.is_integer() else val
                    except (TypeError,ValueError):val=v.text
                values[idx-1]=val
            yield values;row.clear()
    finally:z.close()

def tabular_sheet(path,sheet):
    it=iter(xlsx_rows(path,sheet));header=next(it,[])
    if not header:raise ValueError('Пустой лист '+sheet)
    # First column can be an exported dataframe index. Retain blank headers by position.
    return header,[dict(zip([str(k) if k is not None else f'_blank_{i}' for i,k in enumerate(header)],row)) for row in it if any(v is not None for v in row)]

def identify(headers,candidates):
    keys=[str(h) for h in headers if norm(h) in candidates]
    if len(keys)!=1:raise ValueError('Неоднозначная колонка: '+str(candidates)+' в '+str(headers[:8]))
    return keys[0]

def status_lookup(path):
    header,rows=tabular_sheet(path,'status');yearkey=identify(header,{'год','year'});out={}
    terr=[str(h) for h in header if norm(h) in {'территория','субъект','регион','territory','region'}]
    stat=[str(h) for h in header if norm(h) in {'статус','status'}]
    if terr and stat:
        for row in rows:
            if row.get(yearkey) is None:continue
            key=(norm(row.get(terr[0])),int(number(row[yearkey])))
            if key in out and out[key]!=row.get(stat[0]):raise ValueError('Противоречивые статусы')
            out[key]=row.get(stat[0])
    else:
        for row in rows:
            if row.get(yearkey) is None:continue
            year=int(number(row[yearkey]))
            for h in header:
                if h is not None and str(h)!=yearkey:out[(norm(h),year)]=row.get(str(h))
    return out

def observed_stocks(path):
    status=status_lookup(path);header,rows=tabular_sheet(path,'by_age')
    rk=identify(header,{'территория','субъект','регион','territory','region'});yk=identify(header,{'год','year'})
    ages={}
    for h in header:
        s=str(h).strip()
        if re.fullmatch(r'\d+(?:\.0)?',s):age=int(float(s))
        elif re.fullmatch(r'100\+|100\s*и\s*(?:более|старше)',s,re.I):age=100
        else:continue
        if 0<=age<=100:
            if age in ages:raise ValueError('Дублирование возраста '+str(age))
            ages[age]=str(h)
    if set(ages)!=set(range(101)):raise ValueError('Для by_age нужны отдельные возраста 0–99 и 100+. Найдено: '+str(len(ages)))
    out={}
    for row in rows:
        name=row.get(rk)
        if name is None or row.get(yk) is None:continue
        year=int(number(row[yk]));key=(norm(name),year)
        # Explicitly observed rows only, never blank/estimated/projected statuses.
        if norm(status.get(key)) not in {'наблюдение','наблюдения','факт','observed','observation','actual'}:continue
        pop=[number(row.get(ages[a])) for a in range(101)]
        if min(pop)<0 or sum(pop)<=0:raise ValueError('Недопустимая базовая численность '+str(name))
        if key in out and out[key]['population']!=pop:raise ValueError('Дубли наблюдаемой базы '+str(key))
        out[key]={'name':str(name),'year':year,'population':pop}
    if not out:raise ValueError('Нет подтверждённых наблюдений в by_age/status')
    return out

def csv_rows(path):
    text=Path(path).read_text(encoding='utf-8-sig');sep=';' if text.splitlines()[0].count(';')>text.splitlines()[0].count(',') else ','
    return list(csv.DictReader(io.StringIO(text),delimiter=sep))

def aliases_for(catalog,root):
    aliases={norm(r['name']):r['id'] for r in catalog['regions']}
    aliases.update({norm('Российская Федерация'):'RU',norm('Россия'):'RU'})
    for sid in ['data_21','data_22']:
        packet=json.loads((root/f'public/data/baseline/{sid}.json').read_text())
        for r in (dict(zip(packet['columns'],x)) for x in packet['rows']):
            rid=r.get('r')
            if rid:aliases[norm(r['territory'])]=rid
            elif re.match('Российская Федерация',r['territory']):aliases[norm(r['territory'])]='RU'
    # Exact documented aliases only; not fuzzy matching.
    aliases.update({norm('г. Москва'):'77',norm('г. Санкт-Петербург'):'78',norm('г. Севастополь'):'92',norm('Кемеровская область'):'42',norm('Республика Северная Осетия – Алания'):'15',norm('Чувашская Республика'):'21',norm('Ханты-Мансийский автономный округ'):'86'})
    return aliases

def resolve_name(name,aliases):
    return aliases.get(norm(name))

def annual_components(rows,aliases,value_candidates,sexed=True):
    if not rows:raise ValueError('Пустой CSV компонент')
    header=list(rows[0]);rk=identify(header,{'территория','регион','субъект','territory','region'});yk=identify(header,{'год','year'});vk=identify(header,value_candidates)
    sk=identify(header,{'пол','sex'}) if sexed else None
    staged={}
    for row in rows:
        rid=resolve_name(row[rk],aliases)
        if not rid:continue
        s=norm(row[sk]) if sk else 'all';sex='male' if s in {'мужчины','мужской','муж','male','m','м','мужскойпол','1'} else 'female' if s in {'женщины','женский','жен','female','f','ж','женскийпол','2'} else None
        if sexed and sex is None:continue
        year=int(number(row[yk]))
        if year>2030:continue
        v=number(row[vk]);key=(rid,sex or 'all',year)
        staged.setdefault(key,[]).append((str(row[rk]),v,row.get('Статус') or row.get('status')))
    out={}
    for (rid,sex,year),group in staged.items():
        parts=[r for r in group if re.search(r'кроме|без.*автоном',r[0],re.I)];pool=parts or group
        if len({p[1] for p in pool})!=1:raise ValueError(f'Несогласованные компоненты: {rid}, {sex}, {year}')
        out.setdefault((rid,sex),{})[str(year)]={'value':pool[0][1],'status':pool[0][2],'territory':pool[0][0]}
    return out

def fetch_repository(cache):
    cache.mkdir(parents=True,exist_ok=True);now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    old=json.loads((cache/'manifest.json').read_text()) if (cache/'manifest.json').exists() else {};report={'checked_at':now,'repository':REPO,'files':[]}
    try:
        info=json.loads(get_bytes(f'https://api.github.com/repos/{REPO}/commits/main',1_500_000));sha=info['sha']
        if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('Не получена SHA ревизии')
        report['commit']=sha
    except Exception as exc:
        # Cached inputs are legitimate dated sources, never falsely labelled freshly retrieved.
        report.update(state='retained' if all((cache/f).exists() for f in FILES) else 'unavailable',message=str(exc),commit=old.get('commit'),last_success=old.get('last_success'))
        report['files']=old.get('files',[]);return report
    staged={}
    try:
        for filename in FILES:
            url=f'https://raw.githubusercontent.com/{REPO}/{sha}/{filename}';data=get_bytes(url)
            temp=cache/(filename+'.incoming');temp.write_bytes(data)
            if filename.endswith('.xlsx'):observed_stocks(temp)
            else:
                rows=csv_rows(temp)
                if not rows:raise ValueError('Пустой CSV')
            staged[filename]=temp
            report['files'].append({'name':filename,'url':url,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
        for filename,temp in staged.items():temp.replace(cache/filename)
        report.update(state='fetched',last_success=now)
    except Exception as exc:
        for p in cache.glob('*.incoming'):p.unlink()
        report.update(state='retained' if all((cache/f).exists() for f in FILES) else 'unavailable',message=str(exc),commit=old.get('commit'),last_success=old.get('last_success'),files=old.get('files',[]))
    return report

def build_inputs(root,cache):
    catalog=json.loads((root/'public/data/catalog.json').read_text());aliases=aliases_for(catalog,root)
    stocks={s:observed_stocks(cache/f'POP_wide_{s}_noMIG.xlsx') for s in ['male','female']}
    grouped={}
    for sex in stocks:
        for (raw,year),item in stocks[sex].items():
            rid=resolve_name(item['name'],aliases)
            if rid:grouped.setdefault((rid,year,sex),[]).append(item)
    chosen={}
    for key,group in grouped.items():
        parts=[g for g in group if re.search('кроме|без.*автоном',g['name'],re.I)];pool=parts or group
        if len({tuple(g['population']) for g in pool})>1:continue  # Ambiguity is unavailable, not an arbitrary average.
        chosen[key]=pool[0]
    e0=annual_components(csv_rows(cache/'LE_Russia_subjects_forecast_2100_long.csv'),aliases,{'e0','опж'})
    mig=annual_components(csv_rows(cache/'MIG_cyclic_tidy.csv'),aliases,{'сальдо','net','netmigration'})
    tfr=annual_components(csv_rows(cache/'TFR_Russia_subjects_ML_GP_UCM_tidy.csv'),aliases,{'median','tfr','скр'},False)
    source_manifest=json.loads((cache/'manifest.json').read_text()) if (cache/'manifest.json').exists() else {'state':'local','files':[{'name':f,'sha256':hashlib.sha256((cache/f).read_bytes()).hexdigest()} for f in FILES]}
    result=[];unavailable=[]
    for rid,name in [('RU','Российская Федерация')]+[(r['id'],r['name']) for r in catalog['regions']]:
        try:
            common=[y for r,y,s in chosen if r==rid and s=='male' and (rid,y,'female') in chosen and 2000<=y<=2030]
            if not common:raise ValueError('Нет общего наблюдаемого базового года с 101 возрастом для обоих полов.')
            base=max(common)
            for sex in ['male','female']:
                if (rid,sex) not in e0 or (rid,sex) not in mig:raise ValueError('Отсутствует компонент ОПЖ или миграции для '+sex)
            if (rid,'all') not in tfr:raise ValueError('Отсутствует стартовая траектория СКР')
            indpath=root/f'public/data/projections/indicators/data_21/{rid}.json';model=json.loads(indpath.read_text()) if indpath.exists() else None
            monthly={r['date'][:7]:r['value'] for r in model['observations']+model['forecast']} if model else {}
            # Annual national-project observations override the older project's annual driver only on their exact years.
            tf={y:v['value'] for y,v in tfr[(rid,'all')].items()}
            latest=json.loads((root/'public/data/latest/manifest.json').read_text());source=next((s for s in latest.get('sources',[]) if s['source_id']=='data_21'),{})
            packet=json.loads((root/'public'/(source.get('published_file') or 'data/baseline/data_21.json')).read_text())
            annual_groups={}
            for rr in (dict(zip(packet['columns'],x)) for x in packet['rows']):
                rrid=rr.get('r') or ('RU' if re.match('Российская Федерация',rr['territory']) else None)
                if rrid==rid and rr['type']=='год':annual_groups.setdefault(str(rr['year']),[]).append(rr)
            for year,group in annual_groups.items():
                scoped=[r for r in group if re.search(r'кроме|без.*автоном',r['territory'],re.I)];pool=scoped or group
                vals={r['value'] for r in pool if isinstance(r.get('value'),(int,float)) and not isinstance(r.get('value'),bool) and math.isfinite(r['value'])}
                if len(vals)>1:raise ValueError('Противоречие территориального охвата годового СКР '+year)
                if len(vals)==1:tf[year]=next(iter(vals))
            obj={'schema':'semya.cohort-input/1','region_id':rid,'region_name':name,'base_date':f'{base}-01-01','population':{s:chosen[(rid,base,s)]['population'] for s in ['male','female']},'sex_ratio':105.6,'fertility':{'annual_tfr':tf,'monthly_tfr':monthly,'weights':fertility_profile()},'mortality':{s:{'annual_e0':{y:v['value'] for y,v in e0[(rid,s)].items()}} for s in ['male','female']},'migration':{s:{'annual_net':{y:v['value'] for y,v in mig[(rid,s)].items()},'weights':migration_profile()} for s in ['male','female']},'provenance':[{'role':'observed age-sex baseline','repository':REPO,'year':base,'territories':{s:chosen[(rid,base,s)]['name'] for s in ['male','female']},'commit':source_manifest.get('commit'),'files':source_manifest.get('files',[])},{'role':'fertility monthly driver','model_version':model.get('model_version') if model else None,'input_sha256':model.get('input_sha256') if model else None,'as_of':model.get('source_as_of') if model else None},{'role':'mortality and migration drivers','source':'Авторский репозиторий, наблюдения и явно помеченные прогнозные траектории','mortality':{s:e0[(rid,s)] for s in ['male','female']},'migration':{s:mig[(rid,s)] for s in ['male','female']}}],'assumptions':['Базовая численность: только наблюдения из листов by_age/status; общий год для обоих полов.','Однолетние возраста разделены на 12 равных месячных подкогорт. Внутригодовое распределение — модельное предположение.','Месячный СКР используется как годовая интенсивность; число рождений определяется женской экспозицией и возрастным профилем.','Возрастная форма рождаемости — фиксированный гладкий профиль (центр 28 лет, sd 6), не наблюдаемые региональные ASFR.','Возрастная смертность — модельная таблица, калиброванная к ОПЖ. ОПЖ сама по себе не определяет фактическую возрастную смертность.','ОПЖ и годовое миграционное сальдо — входные траектории из авторского репозитория, включая его прогнозные годы; обновление файла не превращает прогноз в наблюдение.','Годовая миграция делится равномерно по месяцам и распределяется по объявленному гладкому возрастному профилю.','Месяцы без нового значения годовой компоненты используют последнее значение данного региона и пола; межрегиональное заполнение не применяется.','Российская серия рассчитывается независимо, не как сумма региональных коэффициентов; общий итог регионов может отличаться из-за охвата и несогласованных предпосылок.']}
            validate_input(obj);result.append(obj)
        except Exception as exc:unavailable.append({'region_id':rid,'region_name':name,'message':str(exc)})
    return result,unavailable
