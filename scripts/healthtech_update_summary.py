#!/usr/bin/env python3
"""Show the health-technology source attempt independently of site publication."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    status = json.loads((ROOT / 'public/data/projects/health_technologies/refresh-status.json').read_text(encoding='utf-8'))
    print('\n## Новые технологии сбережения здоровья\n')
    print('Состояние последнего запуска: **' + status['state'] + '**.\n')
    print('Проверка: ' + str(status.get('checked_at') or 'не выполнялась') + '. ' +
          'Последняя пригодная публикация: ' + str(status.get('published_at') or 'нет') + '.\n')
    print(status.get('message', '') + '\n')
    print('| Источник | Состояние | Последняя пригодная публикация |')
    print('|---|---|---|')
    for source in status.get('sources', []):
        print('| ' + str(source['source_id']) + ' | ' + source['state'] + ' | ' +
              str(source.get('published_at') or 'нет чисел') + ' |')
    print('\nДата получения файла, обновление исходной публикации и периоды наблюдений учитываются раздельно. Ошибка доступа сохраняет пригодные значения и их происхождение.\n')


if __name__ == '__main__':
    main()
