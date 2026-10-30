#!/usr/bin/env python3
"""Report the Competitive Economy attempt separately from its retained statistical release."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
status = json.loads((ROOT / 'public/data/projects/competitive_economy/refresh-status.json').read_text(encoding='utf-8'))
print('\n## Эффективная и конкурентная экономика\n')
print('Состояние последнего запуска: **' + status['state'] + '**.\n')
print('Проверка: ' + str(status.get('checked_at', 'не выполнялась')) + '. ' +
      'Последняя пригодная публикация: ' + str(status.get('published_at', 'нет')) + '.\n')
print(status.get('message', '') + '\n')
print('| Источник | Состояние | Последние проверенные числа |')
print('|---|---|---|')
for source in status['sources']:
    print('| ' + str(source['source_id']) + ' | ' + source['state'] + ' | ' + str(source.get('published_at', 'нет чисел')) + ' |')
print('\nПериоды наблюдений, редакции паспортных целей и дата сетевой проверки учитываются отдельно. Ошибка доступа сохраняет предыдущую пригодную публикацию.\n')
