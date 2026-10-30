#!/usr/bin/env python3
"""Extract the unmodified Competitive Economy expertise DOCX with source block locators."""
from pathlib import Path
import argparse, hashlib, json, re, zipfile
import xml.etree.ElementTree as ET

APP = Path(__file__).resolve().parents[1]
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'm':'http://schemas.openxmlformats.org/officeDocument/2006/math'}

def text(el):
    return ''.join((n.text or '') if n.tag == f"{{{NS['w']}}}t" else '\n' if n.tag == f"{{{NS['w']}}}br" else '\t' if n.tag == f"{{{NS['w']}}}tab" else '' for n in el.iter()).strip()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docx', type=Path, default=APP/'public/downloads/projects/competitive_economy/report/expertise_competitive_2026.docx')
    parser.add_argument('--output', type=Path, default=APP/'.cache/competitive_expertise')
    args = parser.parse_args()
    src, out = args.docx.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        rels = {n.attrib['Id']:n.attrib for n in ET.fromstring(z.read('word/_rels/document.xml.rels'))}
        body = ET.fromstring(z.read('word/document.xml')).find('w:body', NS)
        blocks, tables, figures, headings = [], [], [], []
        para_index = 0
        for idx, el in enumerate(body):
            if el.tag.endswith('}p'):
                style_node = el.find('w:pPr/w:pStyle', NS)
                style = style_node.attrib.get(f"{{{NS['w']}}}val", '') if style_node is not None else ''
                images = []
                for pic in el.findall('.//a:blip', NS):
                    rid = pic.attrib.get(f"{{{NS['r']}}}embed")
                    if rid in rels:
                        target = rels[rid]['Target']
                        target = 'word/'+target if not target.startswith('/') else target[1:]
                        images.append(target)
                block = {'index':idx, 'paragraph_index':para_index, 'type':'paragraph', 'style':style, 'text':text(el), 'images':images,
                         'footnotes':[int(n.attrib[f"{{{NS['w']}}}id"]) for n in el.findall('.//w:footnoteReference', NS)],
                         'equations':[''.join(n.text or '' for n in m.findall('.//m:t', NS)) for m in el.findall('.//m:oMath', NS)]}
                para_index += 1
                if style.lower().startswith('heading') or style in ['Title','Subtitle']:headings.append(block)
                for im in images:
                    dst = out/'media'/Path(im).name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(z.read(im))
                    figures.append({'block':idx, 'path':str(dst.relative_to(out)), 'sha256':hashlib.sha256(z.read(im)).hexdigest()})
                links=[]
                for h in el.findall('w:hyperlink',NS):
                    rid=h.attrib.get(f"{{{NS['r']}}}id"); links.append({'text':text(h),'target':rels.get(rid,{}).get('Target')})
                if links:block['hyperlinks']=links
                blocks.append(block)
            elif el.tag.endswith('}tbl'):
                rows=[['\n'.join(text(p) for p in c.findall('w:p',NS)) for c in r.findall('w:tc',NS)] for r in el.findall('w:tr',NS)]
                cell_notes=[[[int(n.attrib[f"{{{NS['w']}}}id"]) for n in c.findall('.//w:footnoteReference',NS)] for c in row.findall('w:tc',NS)] for row in el.findall('w:tr',NS)]
                block={'index':idx,'type':'table','number':len(tables)+1,'rows':rows,'cell_footnotes':cell_notes,'footnotes':list(dict.fromkeys(number for row in cell_notes for cell in row for number in cell))}
                tables.append(block);blocks.append(block)
        notes=[]
        if 'word/footnotes.xml' in z.namelist():
            for n in ET.fromstring(z.read('word/footnotes.xml')):
                number=int(n.attrib[f"{{{NS['w']}}}id"])
                if number<=0:continue
                paragraphs=[text(p) for p in n.findall('w:p',NS)]
                txt='\n'.join(paragraphs).strip()
                notes.append({'id':number,'text':txt,'paragraphs':paragraphs,'urls':re.findall(r'https?://[^\s]+',re.sub('[\u200b\u2060\ufeff]', '', txt)),
                              'referenced_by':[b['index'] for b in blocks if number in b.get('footnotes',[])]})
        report={'source':src.name,'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'blocks':blocks,'headings':headings,'tables':tables,'figures':figures,'relationships':rels,'footnotes':notes}
        (out/'extraction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        md=[]
        for b in blocks:
            if b['type']=='paragraph':
                if b['text']:md.append(f"[B{b['index']}; {b['style']}] {b['text']}"+(f" [Сноски {', '.join(map(str,b['footnotes']))}]" if b['footnotes'] else ''))
                for eq in b['equations']:md.append('[FORMULA] '+eq)
                for im in b['images']:md.append('[IMAGE: '+im+']')
            else:md.append(f"[TABLE {b['number']}; B{b['index']}]\n"+'\n'.join(' | '.join(value+(' ['+', '.join(map(str,b['cell_footnotes'][ri][ci]))+']' if b['cell_footnotes'][ri][ci] else '') for ci,value in enumerate(row)) for ri,row in enumerate(b['rows'])))
        (out/'full_text.md').write_text('\n\n'.join(md)+'\n',encoding='utf-8')
        print(json.dumps({'blocks':len(blocks),'tables':len(tables),'figures':len(figures),'footnotes':len(notes),'formulas':sum(len(b.get('equations',[])) for b in blocks),'sha256':report['sha256']},ensure_ascii=False))

if __name__=='__main__':main()
