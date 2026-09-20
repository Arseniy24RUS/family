"""Strict, loss-aware conversion of labelled SDMX to the browser data contract."""
from __future__ import annotations
import calendar,hashlib,json,math,re
from datetime import date
from .errors import EmissConnectorError
from .metadata import norm

MONTHS=['январь','февраль','март','апрель','май','июнь','июль','август','сентябрь','октябрь','ноябрь','декабрь']
COLS=['id','r','territory','type','year','start','end','label','value','raw','flag','dimensions','fetched_at']

def territory_key(text):
    s=norm(str(text)).replace('–','-').replace('—','-')
    s=re.sub(r'^(?:г\.?|город)\s+','',s)
    return re.sub(r'\s*-\s*','-',s)

def decode_period(year,label=None,iso=None,annual_only=False):
    if not 1900<=int(year)<=2199:raise EmissConnectorError('Недопустимый год.',category='invalid_period')
    year=int(year);s=norm(label or '')
    s=re.sub(r'\s*[-–—]\s*','-',s)
    found=[(m+1,s.find(name)) for m,name in enumerate(MONTHS) if name in s]
    if not found and (s in {'всего за год','за год','annual','год','годовое значение'} or 'значение показателя за год' in s):
        return 'год',f'{year}-01-01',f'{year}-12-31','значение показателя за год'
    if len(found)==2 and found[0][0]==1:
        month=found[-1][0];return 'накопительно с января',f'{year}-01-01',f'{year}-{month:02d}-{calendar.monthrange(year,month)[1]}','январь-'+MONTHS[month-1]
    if len(found)==1:
        month=found[0][0];return 'месяц',f'{year}-{month:02d}-01',f'{year}-{month:02d}-{calendar.monthrange(year,month)[1]}',MONTHS[month-1]
    if re.fullmatch(r'0?[1-9]|1[012]',s):
        month=int(s);return 'месяц',f'{year}-{month:02d}-01',f'{year}-{month:02d}-{calendar.monthrange(year,month)[1]}',MONTHS[month-1]
    match=re.match(r'^\d{4}[-/]([01]?\d)(?:[-/]\d\d)?$',iso or '') or re.match(r'^\d{4}-?M(\d{1,2})$',iso or '',re.I)
    if match and not s:
        month=int(match.group(1))
        if 1<=month<=12:return 'месяц',f'{year}-{month:02d}-01',f'{year}-{month:02d}-{calendar.monthrange(year,month)[1]}',MONTHS[month-1]
    if annual_only and not s:return 'год',f'{year}-01-01',f'{year}-12-31','значение показателя за год'
    raise EmissConnectorError('SDMX не содержит однозначного типа/месяца периода; порядок наблюдений не используется для угадывания.',category='ambiguous_period')

def values_for_field(item,fid,meta,selected):
    if not fid:return None
    field=next(f for f in meta['filters'] if str(f['field_id'])==fid)
    raw=item.dimension_codes.get(fid)
    if raw is not None:
        return next((v['title'] for v in field['values'] if str(v['id'])==str(raw)),str(raw))
    aliases={norm(field['title']),fid}
    for k,v in item.dimensions.items():
        if norm(k) in aliases:return v
    # A single explicitly requested value may be restored; ordering never may.
    if len(selected.get(fid,[]))==1:return selected[fid][0]['title']
    return None

def convert(items,meta,roles,selected,source,aliases,fetched_at):
    out=[]
    for item in items:
        if item.value_status=='invalid' or item.value is not None and not math.isfinite(item.value):
            raise EmissConnectorError('В SDMX есть нечисловое или бесконечное значение.',category='invalid_numeric')
        territory=values_for_field(item,roles.get('territory'),meta,selected)
        if not territory:
            if source.get('min_regional_count',0):raise EmissConnectorError('Не удаётся однозначно восстановить территорию.',category='ambiguous_territory')
            territory='Российская Федерация'
        year=values_for_field(item,roles.get('year'),meta,selected)
        if year is None:
            match=re.search(r'(?:19|20|21)\d{2}',item.period or '')
            year=match.group(0) if match else None
        if year is None:raise EmissConnectorError('Не определён год наблюдения.',category='ambiguous_period')
        period=values_for_field(item,roles.get('month'),meta,selected)
        typ,start,end,label=decode_period(year,period,item.period,annual_only='month' not in roles)
        if typ not in source['expected_period_types']:
            raise EmissConnectorError('Новый тип периода требует проверки: '+typ,category='period_schema_changed')
        dimensions={}
        for f in meta['filters']:
            fid=str(f['field_id'])
            if fid=='0' or fid in roles.values():continue
            val=values_for_field(item,fid,meta,selected)
            if val is None:raise EmissConnectorError('Потеряно дополнительное измерение: '+f['title'],category='ambiguous_dimension')
            dimensions[f['title']]=val
            if any(s in norm(f['title']) for s in ['единиц','ед. измер']):
                unit=norm(val);expected=norm(source['unit'])
                aliases_unit={'единица':{'единица','единиц','единицы','ед.','ед'},'процент':{'процент','процентов','%','проценты'},'промилле (0,1 процента)':{'промилле (0,1 процента)','промилле','‰','на 1000 родившихся живыми','на 1 тыс. родившихся живыми'}}
                if unit not in aliases_unit.get(expected,{expected}):raise EmissConnectorError('Изменилась единица измерения.',category='unit_mismatch')
        value=item.value;flag=''
        if value is None:flag='missing'
        elif value<0:flag='negative'
        elif value>100 and source['unit']=='процент' and source['source_id']!='data_35':flag='outside_0_100'
        rid=aliases.get(territory_key(territory))
        if rid is None and not any(t in norm(territory) for t in ['российская федерация', 'федеральный округ', 'в том числе', 'всего']):
            raise EmissConnectorError('Неизвестная территория: '+str(territory),category='territory_requires_mapping')
        natural='|'.join([source['source_id'],territory_key(territory),typ,start,end])
        oid='emiss_'+hashlib.sha256(natural.encode()).hexdigest()[:18]
        out.append(dict(zip(COLS,[oid,rid,territory,typ,int(year),start,end,label,value,item.raw_value,flag,dimensions,fetched_at])))
    seen={}
    for row in out:
        key=(territory_key(row['territory']),row['type'],row['start'],row['end'])
        if key in seen and (seen[key]['value']!=row['value'] or seen[key]['dimensions']!=row['dimensions']):
            raise EmissConnectorError('Несколько значений/измерений для одного ключа; агрегирование запрещено.',category='conflicting_duplicates')
        seen[key]=row
    regional={row['r'] for row in out if row['r'] and row['value'] is not None}
    if len(regional)<source.get('min_regional_count',0):
        raise EmissConnectorError('Территориальное покрытие выгрузки существенно ниже исходного; требуется проверка.',category='coverage_drop')
    if not seen:raise EmissConnectorError('Нет нормализованных наблюдений.',category='empty_export')
    return list(seen.values())

def unpack(packet):return [dict(zip(packet['columns'],row)) for row in packet['rows']]
def merge(previous,incoming):
    def key(r):return(territory_key(r['territory']),r['type'],r['start'],r['end'])
    lookup={key(r):i for i,r in enumerate(previous)};out=[dict(r) for r in previous];new_rows=0;revisions=[]
    for row in incoming:
        k=key(row)
        if k not in lookup:
            lookup[k]=len(out);out.append(row);new_rows+=1
        else:
            index=lookup[k];old=out[index]
            if old.get('dimensions') and row.get('dimensions') != old['dimensions']:
                raise EmissConnectorError('Изменилось дополнительное измерение существующего ряда; требуется отдельный контракт.',category='historical_dimension_changed')
            # A missing new cell must not silently delete a last known number.
            if row['value'] is None and old.get('value') is not None:continue
            if old.get('value')!=row['value']:
                revisions.append({'territory':row['territory'],'type':row['type'],'start':row['start'],'end':row['end'],'old_value':old.get('value'),'new_value':row['value']})
            out[index]={**old,**row}
    return out,new_rows,revisions
