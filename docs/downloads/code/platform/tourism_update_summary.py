#!/usr/bin/env python3
"""Report the Tourism refresh attempt separately from its retained observations."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]

def summary(root=ROOT):
 status=json.loads((Path(root)/'public/data/projects/tourism/refresh-status.json').read_text(encoding='utf-8'))
 lines=['','## Туризм и гостеприимство','','Состояние последнего запуска: **'+status['state']+'**.','',
  'Проверка: '+str(status.get('checked_at','не выполнялась'))+'. Последняя пригодная публикация: '+str(status.get('published_at','нет'))+'.','',status.get('message',''),'']
 lines+=['| Источник | Состояние | Последние проверенные числа |','|---|---|---|']
 for source in status.get('sources',[]):
  lines.append('| '+str(source['source_id'])+' | '+str(source['state'])+' | '+str(source.get('published_at','нет чисел'))+' |')
 lines+=['','Денежный экспорт 62902 и физический показатель иностранных размещений 63347 учитываются отдельно. Периоды наблюдений, редакции целей и дата сетевой проверки имеют самостоятельные статусы. Ошибка доступа сохраняет предыдущие проверенные значения.','']
 return '\n'.join(lines)

if __name__=='__main__':print(summary())
