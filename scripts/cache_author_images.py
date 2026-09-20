#!/usr/bin/env python3
"""Cache portraits referenced by the official ISD pages. Retain valid local files on error.
No face matching or generated portrait substitutes. Source URLs are preserved.
"""
import json,hashlib,sys
from pathlib import Path
from datetime import datetime,timezone
from demography.repository_inputs import get_bytes
from build_indicator_forecasts import write
ROOT=Path(__file__).resolve().parents[1]
ALLOWED=('https://cloud.idrras.ru/','https://xn--h1aauh.xn--p1ai/')
def run(root=ROOT):
    p=root/'public/data/authors.json';data=json.loads(p.read_text());results=[]
    authors=data['authors'] if isinstance(data,dict) else data
    for a in authors:
        try:
            url=a['photo_url']
            if not url.startswith(ALLOWED):raise ValueError('Источник изображения не входит в перечень официальных сайтов')
            body=get_bytes(url,5_000_000)
            ext='jpg' if body.startswith(b'\xff\xd8\xff') else 'png' if body.startswith(b'\x89PNG\r\n\x1a\n') else None
            if not ext:raise ValueError('Вместо фотографии получен неподдерживаемый файл')
            rel=f'assets/authors/{a["id"]}.{ext}';target=root/'public'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
            a['local_photo']=rel;a['photo_sha256']=hashlib.sha256(body).hexdigest();results.append({'id':a['id'],'state':'cached','bytes':len(body)})
        except Exception as exc:results.append({'id':a['id'],'state':'retained' if a.get('local_photo') else 'external_only','message':str(exc)})
    write(p,data);write(root/'public/data/author_images_status.json',{'checked_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'images':results})
    print('Фотографии: '+str(sum(r['state']=='cached' for r in results))+' сохранено; при недоступности используются инициалы и ссылка на официальный профиль.')
    return results
if __name__=='__main__':run()
