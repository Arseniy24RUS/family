"""Read preserved NSEDС CSV + original EMISS XLS exports, cross-checking every cell.

No rows are reconstructed from a graph or from the narrative report. In
particular the absent June patient row remains absent from the raw dataset.
"""
from __future__ import annotations

import csv
import gzip
import io
import re
import zipfile
from datetime import datetime

import xlrd

from healthtech_data import clean, number


def cell_text(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_workbook(xls_zip, sid):
    if len(xls_zip) > 10_000_000:
        raise ValueError('Unexpected oversized source workbook')
    with zipfile.ZipFile(io.BytesIO(xls_zip)) as archive:
        expected = str(sid) + '.xls'
        if archive.namelist() != [expected] or archive.getinfo(expected).file_size > 20_000_000:
            raise ValueError('Unexpected source workbook archive layout')
        body = archive.read(expected)
    if not body.startswith(b'\xd0\xcf\x11\xe0'):
        raise ValueError('Export is not the preserved binary XLS format')
    book = xlrd.open_workbook(file_contents=body)
    if set(book.sheet_names()) != {'Данные','Паспорт'}:
        raise ValueError('Workbook sheets changed')
    sheet = book.sheet_by_name('Паспорт')
    fields = {clean(sheet.cell_value(r, 0)).rstrip(':').strip():str(sheet.cell_value(r, 1)).strip() for r in range(2, sheet.nrows)}
    unit = fields.get('Единицы измерения', '').strip('* ').strip()
    published = datetime.strptime(fields['Последнее обновление данных'], '%d.%m.%Y').date().isoformat()
    metadata = {'title':clean(sheet.cell_value(0, 0)), 'unit':unit,
                'periodicity':fields['Периодичность и характеристика временного ряда'],
                'methodology':fields.get('Методологические пояснения', ''),
                'effective_period':fields.get('Период действия', ''),
                'published_at':published, 'passport_fields':fields,
                'workbook_data_sheet':'Данные', 'workbook_passport_sheet':'Паспорт'}
    values = book.sheet_by_name('Данные')
    if clean(values.cell_value(0,0)) != metadata['title']:
        raise ValueError('Data and passport titles disagree')
    matrix = [[cell_text(v) for v in values.row_values(r)] for r in range(2, values.nrows)]
    if matrix[0][:3] != ['ОКАТО','Единица измерения','Период'] or not matrix[0][3:]:
        raise ValueError('Unreviewed workbook axes')
    if any(not re.fullmatch(r'20\d\d', y) for y in matrix[0][3:]):
        raise ValueError('Invalid source year columns')
    return metadata, matrix, body


def parse_export(csv_gz, xls_zip, sid):
    if len(csv_gz) > 2_000_000:
        raise ValueError('Unexpected oversized source CSV')
    decoded = gzip.decompress(csv_gz)
    if len(decoded) > 10_000_000:
        raise ValueError('Unexpected oversized decompressed source CSV')
    rows = list(csv.reader(io.StringIO(decoded.decode('utf-8-sig'))))
    meta, matrix, workbook_bytes = parse_workbook(xls_zip, sid)
    if not rows or rows[0] != matrix[0] or len(rows) != len(matrix):
        raise ValueError('CSV and original XLS geometry mismatch')
    observations = []
    for row_number, (csvrow, xlsrow) in enumerate(zip(rows[1:],matrix[1:]), start=4):
        if len(csvrow) != len(rows[0]) or len(xlsrow) != len(rows[0]) or csvrow[:3] != xlsrow[:3]:
            raise ValueError('CSV and original XLS axes disagree')
        for c, year in enumerate(rows[0][3:], start=3):
            if number(csvrow[c]) != number(xlsrow[c]):
                raise ValueError(f'CSV and original XLS values disagree at row {row_number}, column {c+1}')
            observations.append({'year':int(year),'territory_label':csvrow[0],'unit_label':csvrow[1],
                                 'period_label':csvrow[2],'value_raw':csvrow[c],
                                 'source_locator':f'Данные!{xlrd.formula.colname(c)}{row_number}',
                                 'origin_kind':'secondary_emiss_republication'})
    return meta, observations, {'cross_checked_cells':len(observations),'csv_rows':len(rows)-1,'workbook_bytes':len(workbook_bytes)}
