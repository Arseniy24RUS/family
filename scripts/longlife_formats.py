"""Verified official XLS and grid JSON formats for Long and Active Life.

Adapted from the supplied source_statistics/natprojects/{excel,grid}.py parsers.
Every selected dimension is checked; ambiguous axes and truncated data fail.
No transport fallback attempts to bypass source access restrictions.
"""
import json
import math
import re
import xlrd
from emiss_adapter.errors import EmissConnectorError
from emiss_adapter.sdmx import ParsedSdmxObservation, _number
from emiss_adapter.metadata import norm


def CollectionError(message, category):
    return EmissConnectorError(message, category=category)


def label_key(value):
    return re.sub(r'\s+', ' ', str(value).strip().casefold().replace('ё', 'е'))


def label(value):
    if isinstance(value,float) and value.is_integer():return str(int(value))
    return str(value).strip()

def axis_mapping(samples,fields,selected):
    multi=[f for f in fields if len(selected[str(f['field_id'])])>1]
    choices={}
    for f in multi:
        fid=str(f['field_id'])
        vocab={label_key(v['title']) for v in selected[fid]}
        choices[fid]=[slot for slot,values in enumerate(samples) if values and set(values)<=vocab]
        if not choices[fid]:raise CollectionError('Не распознана ось Excel: '+f['title'],'excel_axis_unresolved')
    solutions=[]
    def visit(pending,mapping,used):
        if len(solutions)>1:return
        if not pending:solutions.append(mapping);return
        fid=min(pending,key=lambda k:len(choices[k]))
        for slot in choices[fid]:
            if slot not in used:visit([k for k in pending if k!=fid],{**mapping,fid:slot},used|{slot})
    visit(list(choices),{},set())
    if len(solutions)!=1:raise CollectionError('Неоднозначные оси Excel.','excel_axis_ambiguous')
    return solutions[0]

def parse_excel(content,meta,selected):
    if not content.startswith(b'\xd0\xcf\x11\xe0'):
        raise CollectionError('Вместо официального XLS получен другой формат.','excel_not_workbook')
    book=xlrd.open_workbook(file_contents=content,formatting_info=True)
    if 'Данные' not in book.sheet_names():raise CollectionError('В XLS нет листа Данные.','excel_layout_changed')
    sheet=book.sheet_by_name('Данные')
    lines=[f for f in meta['filters'] if str(f['field_id'])!='0' and f.get('object_parameter')!='columnObjectIds']
    columns=[f for f in meta['filters'] if str(f['field_id'])!='0' and f.get('object_parameter')=='columnObjectIds']
    nleft=len(lines);nhead=len(columns);start=2+nhead
    if not columns or sheet.nrows<=start or sheet.ncols<=nleft:
        raise CollectionError('Неожиданная геометрия Excel.','excel_layout_changed')
    grid=[sheet.row_values(r) for r in range(sheet.nrows)]
    for rlo,rhi,clo,chi in sheet.merged_cells:
        value=grid[rlo][clo]
        for r in range(rlo,rhi):
            for c in range(clo,chi):grid[r][c]=value
    row_samples=[{label_key(label(grid[r][c])) for r in range(start,sheet.nrows) if label(grid[r][c])} for c in range(nleft)]
    col_samples=[{label_key(label(grid[r][c])) for c in range(nleft,sheet.ncols) if label(grid[r][c])} for r in range(2,start)]
    row_map=axis_mapping(row_samples,lines,selected)
    col_map=axis_mapping(col_samples,columns,selected)
    single={fid:str(v[0]['id']) for fid,v in selected.items() if len(v)==1}
    by_id={str(f['field_id']):f for f in meta['filters']}
    def code(fid,text):
        found=[str(v['id']) for v in selected[fid] if label_key(v['title'])==label_key(label(text))]
        if len(found)!=1:raise CollectionError('Неоднозначная подпись Excel: '+by_id[fid]['title'],'excel_label_ambiguous')
        return found[0]
    items=[];skipped_columns=0
    for c in range(nleft,sheet.ncols):
        # Excel omits the entire header for periods with no published cells.
        if any(not label(grid[r][c]) for r in range(2,start)):
            if any(sheet.cell(r,c).ctype==xlrd.XL_CELL_NUMBER for r in range(start,sheet.nrows)):
                raise CollectionError('Число Excel без заголовка периода.','excel_missing_header')
            skipped_columns+=1;continue
        cc={fid:code(fid,grid[2+slot][c]) for fid,slot in col_map.items()}
        for r in range(start,sheet.nrows):
            if any(not label(grid[r][slot]) for slot in row_map.values()):continue
            codes={**single,**cc,**{fid:code(fid,grid[r][slot]) for fid,slot in row_map.items()}}
            if set(codes)!=set(selected):raise CollectionError('Excel потерял измерение.','excel_dimension_loss')
            val=sheet.cell_value(r,c)
            if sheet.cell(r,c).ctype==xlrd.XL_CELL_ERROR:
                raise CollectionError('Ошибка ячейки в официальном XLS.','excel_cell_error')
            if isinstance(val,float) and not math.isfinite(val):raise CollectionError('Бесконечное значение XLS.','excel_cell_error')
            labels={by_id[fid]['title']:next(v['title'] for v in selected[fid] if str(v['id'])==vid) for fid,vid in codes.items()}
            yf=next((f for f in meta['filters'] if label_key(f['title'])=='год'),None)
            period=labels[yf['title']] if yf else None
            numeric,status=_number(label(val))
            items.append(ParsedSdmxObservation(value=numeric,value_status=status,period=period,dimensions=labels,dimension_codes=codes,
                attributes={'source_format':'official_excel','source_sheet':'Данные','source_cell':f'R{r+1}C{c+1}'},raw_value=label(val)))
    return items,{'source_format':'official_excel','skipped_unlabelled_empty_columns':skipped_columns,'sheet_rows':sheet.nrows,'sheet_columns':sheet.ncols}


def parse_grid(body,meta,selected):
    try:packet=json.loads(body)
    except Exception as exc:raise CollectionError('Ответ таблицы не является JSON.','grid_not_json') from exc
    lines=packet.get('results')
    if not isinstance(lines,list):raise CollectionError('В JSON таблицы нет массива results.','grid_contract_changed')
    if '__count' not in packet or int(packet['__count'])!=len(lines):
        raise CollectionError('Счётчик строк JSON не совпадает с полученным массивом.','grid_truncated')
    fields={str(f['field_id']):f for f in meta['filters']}
    column_fields=[fid for fid,f in fields.items() if f.get('object_parameter')=='columnObjectIds' and fid!='0']
    single={fid:str(v[0]['id']) for fid,v in selected.items() if len(v)==1}
    def by_label(fid,label):
        ids=[str(v['id']) for v in selected[fid] if label_key(v['title'])==label_key(label)]
        if len(ids)!=1:raise CollectionError('Неоднозначная подпись JSON: '+fields[fid]['title'],'grid_label_ambiguous')
        return ids[0]
    items=[]
    for row_no,line in enumerate(lines):
        row_codes={}
        for fid in fields:
            if 'dim'+fid in line:row_codes[fid]=by_label(fid,line['dim'+fid])
        for key,value in line.items():
            match=re.fullmatch(r'dim(.+)_d(\d+)_i(\d+)',key)
            if not match:continue
            tokens=match[1].split('_')
            if len(tokens)!=len(column_fields):raise CollectionError('Изменился состав колонок JSON.','grid_dimension_loss')
            allowed={fid:[i for i,tok in enumerate(tokens) if tok in {str(v['id']) for v in selected[fid]}] for fid in column_fields}
            solutions=[]
            def assign(pending,mapping,used):
                if len(solutions)>1:return
                if not pending:solutions.append(mapping);return
                fid=min(pending,key=lambda k:len(allowed[k]))
                for index in allowed[fid]:
                    if index not in used:assign([k for k in pending if k!=fid],{**mapping,fid:tokens[index]},used|{index})
            assign(column_fields,{},set())
            if len(solutions)!=1:raise CollectionError('Неоднозначные коды колонок JSON.','grid_axis_ambiguous')
            codes={**single,**row_codes,**solutions[0]}
            if set(codes)!=set(fields):raise CollectionError('JSON потерял многозначное измерение.','grid_dimension_loss')
            labels={fields[fid]['title']:next(v['title'] for v in selected[fid] if str(v['id'])==vid) for fid,vid in codes.items()}
            year_field=next((fid for fid,f in fields.items() if label_key(f['title'])=='год'),None)
            period=labels[fields[year_field]['title']] if year_field else None
            numeric,status=_number(None if value is None else str(value))
            items.append(ParsedSdmxObservation(value=numeric,value_status=status,period=period,dimensions=labels,dimension_codes=codes,
                attributes={'source_format':'official_grid_json','source_row':row_no,'source_data_id':match[2],'source_cell_indicator_id':match[3]},raw_value=None if value is None else str(value)))
    return items,{'source_format':'official_grid_json','returned_rows':len(lines),'observations':len(items)}
