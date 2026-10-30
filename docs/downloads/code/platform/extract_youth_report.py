from pathlib import Path
import zipfile, json, re, hashlib, argparse
import xml.etree.ElementTree as ET

APP=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--docx',type=Path,default=APP/'public/downloads/projects/youth_children/report/expertise_youth_children_2026.docx');ap.add_argument('--output',type=Path,default=APP/'.cache/youth_expertise');args=ap.parse_args()
ROOT=args.output.resolve();ROOT.mkdir(parents=True,exist_ok=True);SRC=args.docx.resolve()
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing','p':'http://schemas.openxmlformats.org/package/2006/relationships','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}

def text(el):
    return ''.join(x.text or '' for x in el.iter() if x.tag==f"{{{NS['w']}}}t")

with zipfile.ZipFile(SRC) as z:
    rels={n.attrib['Id']:n.attrib for n in ET.fromstring(z.read('word/_rels/document.xml.rels'))}
    body=ET.fromstring(z.read('word/document.xml')).find('w:body',NS)
    blocks=[]; tables=[]; figures=[]; headings=[]
    for idx,el in enumerate(body):
        tag=el.tag.split('}')[-1]
        if tag=='p':
            ps=el.find('w:pPr/w:pStyle',NS); style=ps.attrib.get(f"{{{NS['w']}}}val",'') if ps is not None else ''
            txt=text(el)
            images=[]
            for pic in el.findall('.//a:blip',NS):
                rid=pic.attrib.get(f"{{{NS['r']}}}embed")
                if rid and rid in rels:
                    target=rels[rid]['Target']; target='word/'+target if not target.startswith('/') else target[1:]
                    images.append(target)
            block={'index':idx,'type':'paragraph','style':style,'text':txt,'images':images}
            block['footnotes']=[int(x.attrib[f"{{{NS['w']}}}id"]) for x in el.findall('.//w:footnoteReference',NS)]
            block['equations']=[''.join(x.text or '' for x in m.findall('.//m:t',NS)) for m in el.findall('.//m:oMath',NS)]
            if style.lower().startswith('heading') or style in ['1','2','3','4','Title','Subtitle']:
                headings.append(block)
            for im in images:
                imout=ROOT/'media'/Path(im).name; imout.parent.mkdir(parents=True,exist_ok=True); imout.write_bytes(z.read(im))
                figures.append({'block':idx,'path':str(imout.relative_to(ROOT)), 'sha256':hashlib.sha256(z.read(im)).hexdigest()})
            hyperlinks=[]
            for h in el.findall('w:hyperlink',NS):
                rid=h.attrib.get(f"{{{NS['r']}}}id"); hyperlinks.append({'text':text(h),'target':rels.get(rid,{}).get('Target')})
            if hyperlinks:block['hyperlinks']=hyperlinks
            blocks.append(block)
        elif tag=='tbl':
            rows=[[text(c) for c in r.findall('w:tc',NS)] for r in el.findall('w:tr',NS)]
            block={'index':idx,'type':'table','number':len(tables)+1,'rows':rows};tables.append(block);blocks.append(block)
    extras={}
    for name in ['word/footnotes.xml','word/endnotes.xml','word/comments.xml','docProps/core.xml','docProps/app.xml']:
        if name in z.namelist():extras[name]=z.read(name).decode()
    footnotes=[]
    for el in ET.fromstring(z.read('word/footnotes.xml')):
        number=int(el.attrib[f"{{{NS['w']}}}id"])
        if number>0:
            txt=text(el)
            footnotes.append({'id':number,'text':txt.strip(),'urls':re.findall(r'https?://[^\s]+',txt),'paragraphs':[text(p) for p in el.findall('w:p',NS)],'referenced_by':[b['index'] for b in blocks if number in b.get('footnotes',[])]})
    report={'source':SRC.name,'sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'blocks':blocks,'headings':headings,'tables':tables,'figures':figures,'relationships':rels,'footnotes':footnotes,'extras':extras}
    (ROOT/'extraction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    md=[]
    for b in blocks:
        if b['type']=='paragraph':
            if b['text']:md.append(f"[B{b['index']}; {b['style']}] {b['text']}"+(f" [Сноски {', '.join(map(str,b['footnotes']))}]" if b['footnotes'] else ''))
            for eq in b['equations']:md.append('[FORMULA] '+eq)
            for im in b['images']:md.append(f"[IMAGE: {im}]")
        else:
            md.append(f"[TABLE {b['number']}; B{b['index']}]\n"+'\n'.join(' | '.join(r) for r in b['rows']))
    (ROOT/'full_text.md').write_text('\n\n'.join(md))
    (ROOT/'headings.json').write_text(json.dumps(headings,ensure_ascii=False,indent=2))
    (ROOT/'footnotes.json').write_text(json.dumps(footnotes,ensure_ascii=False,indent=2))
    print(json.dumps({'blocks':len(blocks),'paragraphs':sum(b['type']=='paragraph' for b in blocks),'tables':len(tables),'figures':len(figures),'headings':len(headings),'characters':sum(len(b.get('text','')) for b in blocks),'words':sum(len(b.get('text','').split()) for b in blocks),'heading_list':[(h['index'],h['style'],h['text']) for h in headings]},ensure_ascii=False,indent=2))
