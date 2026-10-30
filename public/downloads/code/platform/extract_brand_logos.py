#!/usr/bin/env python3
"""Extract official page-47 logo vector paths without redrawing.

No fonts, raster images, network resources or source pages are embedded.
Every output <path> is copied unchanged from PyMuPDF's page SVG export.
"""
from pathlib import Path
import copy, hashlib, json, argparse
import fitz
from lxml import etree as ET

PROJECTS = [
 ('family','Семья','СЕМЬЯ',0,0),
 ('youth_children','Молодёжь и дети','МОЛОДЕЖЬ И ДЕТИ',2,0),
 ('long_active_life','Продолжительная и активная жизнь','АКТИВНАЯ ЖИЗНЬ',0,1),
 ('health_technologies','Новые технологии сбережения здоровья','ТЕХНОЛОГИИ ЗДОРОВЬЯ',2,1),
 ('life_infrastructure','Инфраструктура для жизни','ИНФРАСТРУКТУРА',0,2),
 ('environment','Экологическое благополучие','ЭКОЛОГИЯ',0,3),
 ('personnel','Кадры','КАДРЫ',1,4),
 ('competitive_economy','Эффективная и конкурентная экономика','ЭКОНОМИКА',2,3),
 ('data_economy','Экономика данных и цифровая трансформация государства','ЭКОНОМИКА ДАННЫХ',1,0),
 ('tourism','Туризм и гостеприимство','ТУРИЗМ',0,4),
 ('efficient_transport','Эффективная транспортная система','ТРАНСПОРТ',1,2),
 ('international_export','Международная кооперация и экспорт','ЭКСПОРТ',1,1),
]

THEME_COLORS={
 'family':'#2947A0','long_active_life':'#D9124A','youth_children':'#8265CB',
 'tourism':'#208076','personnel':'#CF4520','life_infrastructure':'#45B97C',
 'efficient_transport':'#DCAA44','environment':'#87C879','international_export':'#2B3847',
 'data_economy':'#4224FD','competitive_economy':'#D86464','health_technologies':'#0A8BBF',
}

def sha(b): return hashlib.sha256(b).hexdigest()

def extract(source, out, manifest_path, qa_dir=None):
 out.mkdir(parents=True, exist_ok=True)
 svgout=out
 pngout=qa_dir/'preview' if qa_dir else None
 if pngout: pngout.mkdir(parents=True,exist_ok=True)
 source_hash=sha(source.read_bytes())
 if source_hash!='eb480ed2200e61c56cdec8f98299b6594a7a0766bf6ae88c8bd864a5552e3485':
  raise ValueError('This extractor targets the verified 2025 brandbook edition; the supplied PDF checksum differs.')
 doc=fitz.open(source); page=doc[46]
 assert len(doc)==50 and '47' in page.get_text().splitlines()
 assert list(page.rect)==[0,0,1920,1080]
 root=ET.fromstring(page.get_svg_image(text_as_path=True).encode())
 # Page-47 logos are already outlines: 487 vector paths in one clipped group.
 pathgroup=root[1][0][0]
 drawings=page.get_drawings()
 assert len(pathgroup)==len(drawings)==487
 assert all(ET.QName(x).localname=='path' for x in pathgroup)
 ns='http://www.w3.org/2000/svg'
 records=[]
 for project,full,label,row,col in PROJECTS:
  selection=fitz.Rect(795+202*col,220+198*row,950+202*col,350+198*row)
  indices=[i for i,d in enumerate(drawings) if selection.contains(d['rect'])]
  assert indices
  bbox=fitz.Rect()
  for i in indices: bbox|=drawings[i]['rect']
  margin=2
  crop=fitz.Rect(bbox.x0-margin,bbox.y0-margin,bbox.x1+margin,bbox.y1+margin)
  logo=ET.Element('{%s}svg'%ns, nsmap={None:ns}, attrib={
   'viewBox':' '.join(f'{v:.8f}'.rstrip('0').rstrip('.') for v in [crop.x0,crop.y0,crop.width,crop.height]),
   'width':'134.51','height':'111.92','role':'img','aria-labelledby':'logo-title logo-desc'
  })
  ET.SubElement(logo,'{%s}title'%ns, id='logo-title').text=f'Национальный проект «{full}»'
  ET.SubElement(logo,'{%s}desc'%ns,id='logo-desc').text=f'Официальный логотип «{label}». Брендбук «Национальные проекты России», 2025, страница 47.'
  for i in indices: logo.append(copy.deepcopy(pathgroup[i]))
  content=ET.tostring(logo,xml_declaration=True,encoding='UTF-8',pretty_print=False)
  dest=svgout/f'{project}.svg';dest.write_bytes(content)
  reroot=ET.fromstring(content)
  actualpaths=reroot.findall('{%s}path'%ns)
  assert len(actualpaths)==len(indices)
  for i,originalidx in enumerate(indices): assert actualpaths[i].attrib==pathgroup[originalidx].attrib
  svgdoc=fitz.open(stream=content,filetype='svg')
  preview=svgdoc[0].get_pixmap(matrix=fitz.Matrix(3,3),alpha=False)
  if pngout: preview.save(pngout/f'{project}.png')
  sourcepix=page.get_pixmap(matrix=fitz.Matrix(3,3),clip=crop,alpha=False)
  if pngout: sourcepix.save(pngout/f'{project}-source.png')
  colors=sorted(set(x.get('fill') for x in actualpaths if x.get('fill')))
  path_digest=sha(json.dumps([dict(sorted(pathgroup[i].attrib.items())) for i in indices],ensure_ascii=False,separators=(',',':')).encode())
  records.append({'id':project,'project_id':project,'project_name':full,'brandbook_label':label,
    'file':f'{project}.svg','platform_path':f'public/assets/brand/{project}.svg','sha256':sha(content),'bytes':len(content),'path_count':len(indices),
    'source_path_attributes_sha256':path_digest,'source_crop_png_sha256':sha(sourcepix.tobytes('png')),'source_sha256':source_hash,
    'source_page':47,'geometry_unchanged':True,'brand_color':next(c.upper() for c in colors if c.lower() not in ('#ffffff','#fff')),
    'project_color':THEME_COLORS[project],
    'source_path_indices':indices,'source_bbox_points':list(bbox),'crop_points':list(crop),
    'color_values_as_exported':colors,'path_attributes_unchanged':True,
    'no_raster_images':not bool(reroot.findall('.//{%s}image'%ns)),
    'no_font_dependency':not bool(reroot.findall('.//{%s}text'%ns))})
 manifest={'schema':'national-projects.brand-logos/2','schema_version':2,'edition_date':'2026-10-30','source':{'filename':source.name,'sha256':sha(source.read_bytes()),
  'file_size_bytes':source.stat().st_size,'physical_page':47,'printed_page':47,'page_size_points':list(page.rect)},
  'method':'Select existing vector paths by bounding rectangle from PyMuPDF SVG export of page 47; copy d, transform, fill and other attributes unchanged; adjust SVG viewBox with 2-point margin. No redrawing, font substitution or rasterization of deliverable.',
  'extractor_version':fitz.VersionBind,'project_count':len(records),'logos':records}
 manifest_path.parent.mkdir(parents=True,exist_ok=True)
 manifest_json=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
 manifest_path.write_text(manifest_json)
 (out/'manifest.json').write_text(manifest_json)
 if qa_dir:
  from PIL import Image, ImageDraw, ImageFont
  # Internal visual proof: original page crop (left) beside extracted SVG (right).
  width=1500;cellw=500;cellh=340
  sheet=Image.new('RGB',(width,cellh*4),'#f4f6f8');draw=ImageDraw.Draw(sheet)
  fontpath='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
  font=ImageFont.truetype(fontpath,16);small=ImageFont.truetype(fontpath,12)
  for j,record in enumerate(records):
   x=(j%3)*cellw;y=(j//3)*cellh
   draw.text((x+18,y+10),record['project_id'],fill='#17202a',font=font)
   draw.text((x+18,y+35),'PDF, стр. 47                      Извлечённый SVG',fill='#4c5764',font=small)
   for offset,suffix in [(0,'-source'),(1,'')]:
    pic=Image.open(pngout/(record['project_id']+suffix+'.png')).convert('RGB')
    pic.thumbnail((220,220))
    sheet.paste(pic,(x+15+offset*240,y+65))
   draw.text((x+18,y+275),record['brandbook_label'],fill='#17202a',font=small)
   draw.text((x+18,y+298),f"{record['path_count']} paths | {record['bytes']:,} bytes",fill='#4c5764',font=small)
  sheet.save(qa_dir/'contact-sheet.png')
 print(json.dumps({'logos':len(records),'total_svg_bytes':sum(r['bytes'] for r in records),'manifest':str(manifest_path)},ensure_ascii=False))
 return manifest

if __name__=='__main__':
 root=Path(__file__).resolve().parents[1]
 ap=argparse.ArgumentParser(description='Extract the twelve official SVG logos from verified brandbook page 47.')
 ap.add_argument('--source',required=True,type=Path,help='Original Brendbuk_Natsproekty_Rossii_2025 PDF supplied by the user')
 ap.add_argument('--output-dir',type=Path,default=root/'public/assets/brand')
 ap.add_argument('--manifest',type=Path,default=root/'documentation/BRAND_LOGOS_PROVENANCE.json')
 ap.add_argument('--qa-dir',type=Path,help='Optional external directory for PNG comparisons; not part of the site')
 a=ap.parse_args();extract(a.source,a.output_dir,a.manifest,a.qa_dir)
