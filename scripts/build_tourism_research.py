#!/usr/bin/env python3
"""Build the lossless observation packet used by the v3 tourism pilot."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def build(root=ROOT):
    root=Path(root)
    directory=root/'public/data/projects/tourism'
    source_path=directory/'series/62900.json'
    raw=source_path.read_bytes()
    source=json.loads(raw)
    observations=source['observations']
    common={key:val for key,val in observations[0].items()
            if all(key in row and row[key]==val for row in observations)}
    compact=[{key:val for key,val in row.items() if key not in common}
             for row in observations]
    assert [{**common,**row} for row in compact]==observations
    statistics=json.loads((directory/'statistics.json').read_text(encoding='utf-8'))
    exclusions=[]
    for path in sorted((directory/'series').glob('*.json')):
        dataset=json.loads(path.read_text(encoding='utf-8'))
        for row in dataset.get('observations',[]):
            if any(flag.get('exclude_from_analysis') for flag in row.get('quality_flags',[])):
                exclusions.append({**row,'source_id':dataset['source_id'],'source_title':dataset['title']})
    packet={key:value for key,value in source.items() if key!='observations'}
    packet.update({
        'schema':'national-projects.tourism-research/1',
        'release_version':json.loads((root/'package.json').read_text())['version'],
        'source_path':'data/projects/tourism/series/62900.json',
        'source_sha256':hashlib.sha256(raw).hexdigest(),
        'observation_defaults':common,
        'observations':compact,
        'coverage':statistics['coverage'],
        'exclusions':exclusions,
        'comparison_status':'requires_edition_review',
        'methodology_review':{
            'checked_on':'2026-10-31',
            'status':'requires_edition_review',
            'url':'https://rosstat.gov.ru/storage/mediabank/NP10_N.htm',
            'note':'В официальном перечне Росстата для поездок указан приказ Минэкономразвития России от 30.09.2026 № 684. Редакция методики и статус первой либо уточнённой оценки каждой сохранённой ячейки ещё не установлены. Дата приказа сама по себе не определяет момент разрыва ряда.'
        }
    })
    output=directory/'research.json'
    output.write_text(json.dumps(packet,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print(f'Tourism v3: {len(observations)} observations, {len(exclusions)} exclusions; {output.stat().st_size:,} bytes; lossless expansion verified.')
    return packet

if __name__=='__main__':
    build()
