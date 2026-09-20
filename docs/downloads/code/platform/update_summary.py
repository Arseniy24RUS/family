#!/usr/bin/env python3
"""Markdown summary of the refresh, including per-source failures and preserved data."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'public/data/latest/manifest.json').read_text(encoding='utf-8'))
def safe(value):return str(value or '—').replace('|','/').replace('\n',' ').replace('<','&lt;').replace('>','&gt;')
print('# Проверка ЕМИСС\n')
print('Состояние: **'+safe(manifest['state'])+'**. '+safe(manifest.get('message'))+'\n')
print('Последняя попытка: '+safe(manifest.get('checked_at'))+'\n')
print('| Источник | Статус | Новые строки | Пересмотры | Диагностика |\n|---|---|---:|---:|---|')
for s in manifest.get('sources',[]):
    print('| '+' | '.join(safe(s.get(k)) for k in ['source_id','state','new_rows','revisions','message'])+' |')
print('\nОшибка загрузки не удаляет последний проверенный набор. Архив экспертизы не изменяется.')

for rel,title in [('indicators','Прогнозы СКР/СКР3+'),('population','Передвижка возрастов')]:
    p=root/f'public/data/projections/{rel}/manifest.json'
    if p.exists():
        m=json.loads(p.read_text());print('\n## '+title+'\n');print('Рассчитано: '+safe(m.get('ready'))+'. Проверка: '+safe(m.get('checked_at'))+'.')
        if rel=='population':print('Сохранено: '+safe(m.get('retained'))+'. Без полных входов: '+safe(m.get('unavailable'))+'. '+safe(m.get('source',{}).get('message')))
print('\nПрогнозные значения и авторские сценарии не маркируются как наблюдения; исходная экспертиза остаётся неизменной.')
