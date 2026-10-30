#!/usr/bin/env python3
"""Publish the complete immutable Export report and source-linked expertise pages."""
from pathlib import Path
import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from extract_export_report import math_text, math_property

APP = Path(__file__).resolve().parents[1]
PROJECT = 'international_export'
BASE = f'downloads/projects/{PROJECT}/report/'
REPORT_NAME = 'expertise_export_2026'
FORMULAS = {
    149: ('E_NNE,t = E_prom,t + E_APK,t', r'E_{\mathrm{NNE},t}=E_{\mathrm{prom},t}+E_{\mathrm{APK},t}'),
    152: ('g_t = 100 × (E_NNE,t / 148,5 − 1)', r'g_t=100\left(\frac{E_{\mathrm{NNE},t}}{148.5}-1\right)'),
    166: ('K_t = V_support,t / S_t', r'K_t=\frac{V_{\mathrm{support},t}}{S_t}'),
    173: ('C_T = (100 / 30) × ∑_{t=2025}^{T} ∑_{j=1}^{30} s_jt', r'C_T=\frac{100}{30}\sum_{t=2025}^{T}\sum_{j=1}^{30}s_{jt}'),
    274: ('r = (E_2030 / E_2025)^(1/5) − 1', r'r=\sqrt[5]{\frac{E_{2030}}{E_{2025}}}-1'),
    350: ('S(a,i) = ∑_{k=1}^{m}(w_ak w_ik) / (√∑_{k=1}^{m}w_ak² × √∑_{k=1}^{m}w_ik²)', r'S(a,i)=\frac{\sum_{k=1}^{m}w_{ak}w_{ik}}{\sqrt{\sum_{k=1}^{m}w_{ak}^{2}}\sqrt{\sum_{k=1}^{m}w_{ik}^{2}}}'),
    397: ('P_T = 100 × [∑_i min(A_{i,T}, V_i)] / [∑_i V_i]', r'P_T=100\frac{\sum_i\min(A_{i,T},V_i)}{\sum_iV_i}'),
    400: ('R_c,24 = 100 × N_c,13:24 / N_c', r'R_{c,24}=100\frac{N_{c,13:24}}{N_c}'),
    403: ('A_c,H = ∑_{h=0}^{H}(E_c,h − Ê⁰_c,h) / ∑_{h=0}^{H} B_c,h', r'A_{c,H}=\frac{\sum_{h=0}^{H}(E_{c,h}-\widehat{E}_{c,h}^{0})}{\sum_{h=0}^{H}B_{c,h}}'),
    413: ('F_c,L = 100 × N_c,L^done / N_c^start', r'F_{c,L}=100\frac{N_{c,L}^{\mathrm{done}}}{N_c^{\mathrm{start}}}'),
    422: ('τ̂ = (Ȳ_T,after − Ȳ_T,before) − (Ȳ_C,after − Ȳ_C,before)', r'\widehat{\tau}=(\overline{Y}_{T,\mathrm{after}}-\overline{Y}_{T,\mathrm{before}})-(\overline{Y}_{C,\mathrm{after}}-\overline{Y}_{C,\mathrm{before}})')
}


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def esc(value):
    return html.escape(str(value), quote=True)


def mathml(xml, label=None, display='block'):
    """Keep the source equation tree, including sums, roots, fences and accents."""
    def convert(node):
        tag = node.tag.rsplit('}', 1)[-1]
        if tag.endswith('Pr'):
            return ''
        children = {c.tag.rsplit('}', 1)[-1]: c for c in node}
        if tag == 't':
            return '<mtext>' + esc(node.text or '') + '</mtext>'
        wrappers = {'f':('mfrac','num','den'), 'sSub':('msub','e','sub'),
                    'sSup':('msup','e','sup'), 'limLow':('munder','e','lim')}
        if tag in wrappers:
            element, first, second = wrappers[tag]
            return f'<{element}>' + convert(children[first]) + convert(children[second]) + f'</{element}>'
        if tag == 'sSubSup':
            return '<msubsup>' + convert(children['e']) + convert(children['sub']) + convert(children['sup']) + '</msubsup>'
        if tag == 'd':
            left = math_property(node, 'dPr', 'begChr', '(')
            right = math_property(node, 'dPr', 'endChr', ')')
            return '<mrow><mo fence="true" stretchy="true">' + esc(left) + '</mo>' + convert(children['e']) + '<mo fence="true" stretchy="true">' + esc(right) + '</mo></mrow>'
        if tag == 'nary':
            symbol = '<mo largeop="true" movablelimits="false">' + esc(math_property(node, 'naryPr', 'chr', '∑')) + '</mo>'
            lower = math_text(children['sub']) and math_property(node, 'naryPr', 'subHide') != '1'
            upper = math_text(children['sup']) and math_property(node, 'naryPr', 'supHide') != '1'
            if lower and upper:
                symbol = '<munderover>' + symbol + convert(children['sub']) + convert(children['sup']) + '</munderover>'
            elif lower:
                symbol = '<munder>' + symbol + convert(children['sub']) + '</munder>'
            elif upper:
                symbol = '<mover>' + symbol + convert(children['sup']) + '</mover>'
            return '<mrow>' + symbol + convert(children['e']) + '</mrow>'
        if tag == 'rad':
            if math_property(node, 'radPr', 'degHide') == '1' or not math_text(children['deg']):
                return '<msqrt>' + convert(children['e']) + '</msqrt>'
            return '<mroot>' + convert(children['e']) + convert(children['deg']) + '</mroot>'
        if tag == 'acc':
            return '<mover accent="true">' + convert(children['e']) + '<mo>' + esc(math_property(node, 'accPr', 'chr', '̂')) + '</mo></mover>'
        if tag == 'bar':
            below = math_property(node, 'barPr', 'pos') == 'bot'
            wrapper, accent = ('munder', 'accentunder') if below else ('mover', 'accent')
            return f'<{wrapper} {accent}="true">' + convert(children['e']) + f'<mo>¯</mo></{wrapper}>'
        if tag == 'func':
            return '<mrow>' + convert(children['fName']) + '<mo>⁡</mo>' + convert(children['e']) + '</mrow>'
        return '<mrow>' + ''.join(convert(child) for child in node) + '</mrow>'
    root = ET.fromstring(xml)
    return f'<math xmlns="http://www.w3.org/1998/Math/MathML" display="{display}" aria-label="{esc(label or math_text(root))}">' + convert(root) + '</math>'


def inline_html(block, note_prefix=''):
    result = []
    for part in block.get('parts', []):
        if part['type'] == 'math':
            result.append(mathml(part['xml'], part['text'], 'inline'))
        elif part['type'] == 'footnote':
            n = part['number']
            result.append(f'<sup><a href="{note_prefix}#fn-{n}" aria-label="Сноска {n}">[{n}]</a></sup>')
        else:
            result.append(esc(part['text']).replace('\n','<br>'))
    return ''.join(result).strip()


def linkify(value):
    chunks, end = [], 0
    for match in re.finditer(r'https?://[^\s]+', value):
        url = match.group(0).rstrip('.,;')
        chunks.append(esc(value[end:match.start()]))
        chunks.append(f'<a href="{esc(url)}" rel="noopener noreferrer">{esc(url)}</a>')
        chunks.append(esc(match.group(0)[len(url):]))
        end = match.end()
    chunks.append(esc(value[end:]))
    return ''.join(chunks).replace('\n','<br>')


def render_complete_html(report, config, result, destination):
    """Every original body block appears once in source order, including front matter."""
    figures = {int(f['sourceBlock'][1:]):f for f in result['figures']}
    rendered = []
    for block in report['blocks']:
        i = block['index']
        attrs = f'id="b{i}" data-source-block="{i}"'
        if block['type'] == 'table':
            def cell(ri, ci, value):
                tag = 'th' if ri == 0 else 'td'
                notes = ''.join(f'<sup><a href="#fn-{n}" aria-label="Сноска {n}">[{n}]</a></sup>' for n in block['cell_footnotes'][ri][ci])
                return f'<{tag}' + (' scope="col"' if ri == 0 else '') + '>' + esc(value).replace('\n','<br>') + notes + f'</{tag}>'
            rows = ['<tr>' + ''.join(cell(ri,ci,value) for ci,value in enumerate(row)) + '</tr>' for ri,row in enumerate(block['rows'])]
            title = next(t['title'] for t in result['tables'] if t['sourceBlock'] == f'b{i}')
            rendered.append(f'<div class="table-scroll" {attrs} role="region" tabindex="0" aria-label="{esc(title)}"><table><thead>{rows[0]}</thead><tbody>{"".join(rows[1:])}</tbody></table></div>')
        elif i in figures:
            figure = figures[i]
            rendered.append(f'<figure {attrs}><img src="{esc(Path(figure["url"]).name)}" alt="{esc(figure["title"])}" loading="lazy"></figure>')
        elif i in FORMULAS:
            formula = result['formula_lookup'][i]
            rendered.append(f'<div class="formula" {attrs}>{formula["mathml"]}<span class="formula-number">({formula["number"]})</span></div>')
        elif block.get('text'):
            level = re.fullmatch(r'Heading(\d)', block.get('style',''))
            tag = 'h' + str(min(int(level.group(1))+1,4)) if level else 'p'
            style = block.get('style')
            cls = 'source-note' if style == 'SourceNote' else 'caption' if style == 'ReportCaption' else 'bibliography' if style == 'Bibliography' else 'source-front' if i < config['first_substantive_block'] else ''
            content = inline_html(block) if style != 'Bibliography' else linkify(block['text'])
            rendered.append(f'<{tag} class="{cls}" {attrs}>{content}</{tag}>')
    notes = []
    for note in report['footnotes']:
        back = ' '.join(f'<a href="#b{i}" aria-label="Вернуться к фрагменту со сноской {note["id"]}">↩</a>' for i in note['referenced_by'])
        notes.append(f'<p id="fn-{note["id"]}"><strong>[{note["id"]}]</strong> {linkify(note["text"])} {back}</p>')
    nav = ''.join(f'<a href="#b{b["index"]}">{esc(b["text"])}</a>' for b in report['blocks'] if b.get('style') == 'Heading1' and b['index'] >= config['first_substantive_block'])
    css = """@font-face{font-family:Roboto;src:url('../../../../assets/fonts/Roboto-Regular.woff') format('woff');font-weight:400;font-display:swap}@font-face{font-family:Roboto;src:url('../../../../assets/fonts/Roboto-Bold.woff') format('woff');font-weight:700;font-display:swap}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f5f7f9;color:#2B3847;font:17px/1.7 Roboto,Arial,sans-serif}main{max-width:1080px;margin:32px auto;padding:48px 60px;background:#fff;border-top:5px solid #2B3847}h1{font-size:38px;line-height:1.2;margin:0 0 22px}h2{font-size:28px;line-height:1.3;margin-top:48px}h3{font-size:22px;line-height:1.4;margin-top:32px}p{text-align:justify}a{color:#2B3847;text-underline-offset:3px;overflow-wrap:anywhere}nav{display:flex;gap:12px 24px;flex-wrap:wrap;margin:24px 0;padding:18px 0;border-block:1px solid #dce2e8}nav a{font-size:14px}figure{margin:34px 0 16px}img{display:block;width:auto;height:auto;max-width:100%;margin:auto}.caption{font-weight:700;text-align:left;margin:22px 0 12px}.source-note{font-size:14px;color:#53616f}.table-scroll{overflow:auto;max-width:100%;border:1px solid #dce2e8}.table-scroll:focus{outline:2px solid #2B3847}table{border-collapse:collapse;width:100%;min-width:660px;font-size:14px;line-height:1.55}th,td{padding:10px 12px;border:1px solid #dce2e8;text-align:left;vertical-align:top}th{background:#fff;font-weight:700}.formula{display:flex;align-items:center;justify-content:center;margin:24px 0;padding:18px 0;overflow:auto}.formula math{font-size:19px;flex:none}.formula-number{margin-left:28px;white-space:nowrap;font-size:15px}math[display=inline]{font-size:1em}.source-front{font-size:14px;color:#53616f;white-space:pre-line}.source-front#b8{font-size:24px;color:#2B3847;font-weight:700}.sources,.bibliography{font-size:14px}.sources p{padding:10px 0;border-bottom:1px solid #e6ebef;text-align:left}.skip{position:absolute;left:-9999px}.skip:focus{left:16px;top:10px;background:white;padding:8px}*[id]{scroll-margin-top:20px}@media(max-width:680px){main{margin:0;padding:26px 20px}h1{font-size:29px}h2{font-size:24px}p{text-align:left}.formula math{font-size:15px}.formula{justify-content:flex-start}.sources{font-size:13px}}@media print{body{background:white}main{margin:0;border:0;padding:0;max-width:none}nav,.skip,.report-links{display:none}h2,h3,.caption{break-after:avoid}figure,.formula{break-inside:avoid}.table-scroll{overflow:visible}table{min-width:0}a{color:inherit;text-decoration:none}.sources{font-size:10pt}img{max-height:650px;object-fit:contain}}"""
    output = f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(config["title"])}</title><meta name="description" content="Полный текст авторской экспертизы национального проекта Международная кооперация и экспорт по состоянию на 29 октября 2026 года"><style>{css}</style></head><body><a class="skip" href="#b64">К тексту исследования</a><main><h1>{esc(config["title"])}</h1><p class="report-links"><a href="../../../../#/projects/international_export/overview">Интерактивная экспертиза</a> · <a href="{REPORT_NAME}.docx">Отчёт DOCX</a> · <a href="{REPORT_NAME}.md">Текст Markdown</a></p><nav aria-label="Разделы полного отчёта">{nav}<a href="#footnotes">Сноски и источники</a></nav><article>' + '\n'.join(rendered) + '</article><section class="sources" id="footnotes"><h2>Сноски и источники</h2>' + '\n'.join(notes) + '</section></main></body></html>\n'
    (destination / (REPORT_NAME + '.html')).write_text(output, encoding='utf-8')
    return output


def build(app, source):
    config = json.loads((app / 'inputs/international_export/report/editorial_config.json').read_text(encoding='utf-8'))
    cache = app / '.cache/export_expertise'
    subprocess.run([sys.executable,str(app/'scripts/extract_export_report.py'),'--docx',str(source),'--output',str(cache)],check=True,stdout=subprocess.DEVNULL)
    report = json.loads((cache/'extraction.json').read_text(encoding='utf-8'))
    assert report['sha256'] == config['source_sha256'], 'Editorial mapping belongs to another DOCX edition'
    # A caller may supply the uploaded filename once. The published identity is
    # canonical so later offline rebuilds produce the same extraction bytes.
    report['source'] = REPORT_NAME + '.docx'
    dump(cache/'extraction.json', report)
    blocks = {b['index']:b for b in report['blocks']}
    destination = app/'public'/BASE
    destination.mkdir(parents=True,exist_ok=True)
    sources = [{'id':'report','title':config['title']+', 2026','text':'Авторская экспертиза по состоянию на 29 октября 2026 года. Паспортное сопоставление использует представления с меткой обновления 16 октября 2026 года. Статистическая выгрузка получена 15 октября 2026 года. Периоды наблюдений и стадии уточнения сохраняются раздельно.','url':BASE+REPORT_NAME+'.docx','kind':'author_report','sha256':report['sha256']}]
    for note in report['footnotes']:
        urls = [url.rstrip('.,;') for url in note['urls']]
        sources.append({'id':f'fn_{note["id"]:03d}','title':note['paragraphs'][0].strip(),'text':note['text'],'url':urls[0] if urls else sources[0]['url'],'urls':urls,'paragraphs':note['paragraphs'],'note_number':note['id'],'kind':'source_note','source_blocks':[f'b{i}' for i in note['referenced_by']]})
    def source_ids(first,last):
        return list(dict.fromkeys(['report']+[f'fn_{n:03d}' for i in range(first,last+1) for n in blocks.get(i,{}).get('footnotes',[])]))
    tables = []
    for raw in report['tables']:
        i,n = raw['index'],raw['number']
        assert blocks[i-1]['style']=='ReportCaption'
        following_note = blocks.get(i+1, {})
        assert following_note.get('style') == 'SourceNote' or i == 447
        tables.append({'id':f'table_{n:02d}','number':n,'type':'table','sourceBlock':f'b{i}','title':blocks[i-1]['text'],'columns':[{'key':f'c{ci}','label':v,'title':v}for ci,v in enumerate(raw['rows'][0])],'rows':[{f'c{ci}':v for ci,v in enumerate(row)}for row in raw['rows'][1:]],'note':following_note.get('text',''),'sourceIds':source_ids(i-2,i+1),'headerSourceIds':[[f'fn_{x:03d}'for x in cell]for cell in raw['cell_footnotes'][0]],'cellSourceIds':[[[f'fn_{x:03d}'for x in cell]for cell in row]for row in raw['cell_footnotes'][1:]],'page':None,'csv_url':BASE+f'table_{n:02d}.csv'})
    table_map = {int(t['sourceBlock'][1:]):t for t in tables}
    figures = []
    for n,raw in enumerate(report['figures'],1):
        i = raw['block']
        assert blocks[i+1]['style']=='ReportCaption' and blocks[i+2]['style']=='SourceNote'
        filename = f'figure_{n:02d}'+Path(raw['path']).suffix
        shutil.copy2(cache/raw['path'],destination/filename)
        figures.append({'id':f'figure_{n:02d}','number':n,'title':blocks[i+1]['text'],'caption':blocks[i+1]['text'],'note':blocks[i+2]['text'],'url':BASE+filename,'sourceBlock':f'b{i}','page':None,'sourceIds':source_ids(i-1,i+2),'implementation':config['figureImplementations'][n-1],'original_sha256':raw['sha256'],'role':'faithful_source_illustration','interactive_data':'documentary.json or analytics.json; the report illustration preserves its original edition'})
    figure_map = {int(f['sourceBlock'][1:]):f for f in figures}
    formula_lookup = {}
    for number,(i,(plain,latex))in enumerate(FORMULAS.items(),1):
        raw = blocks[i]
        assert len(raw['equations'])==1 and raw['text_without_math'].strip() == f'({number})', i
        formula_lookup[i] = {'id':f'b{i}','sourceBlock':i,'sourceIds':source_ids(i,min(i+1,447)),'type':'formula','text':plain,'latex':latex,'number':number,'original_equation_text':raw['equations'],'original_equation_xml':raw['equations_xml'][0],'mathml':mathml(raw['equations_xml'][0],plain),'page':None,'page_verification':'original_ooxml_equation_structure'}
    def convert(i):
        raw = blocks[i]
        common = {'id':f'b{i}','sourceBlock':i,'sourceIds':source_ids(i,i),'page':None}
        if i in table_map:
            table=table_map[i]
            return {**table,**common,'id':table['id'],'sourceIds':table['sourceIds']}
        if i in figure_map:
            figure=figure_map[i]
            return {**common,'type':'figure_ref','figureId':figure['id'],'title':figure['title'],'note':figure['note'],'url':figure['url'],'sourceIds':figure['sourceIds']}
        if i in formula_lookup:
            return formula_lookup[i]
        value=raw.get('text','')
        if not value or raw.get('images') or raw.get('style')=='ReportCaption':
            return None
        if raw.get('style')=='SourceNote' and(i-1 in table_map or i-2 in figure_map):
            return None
        level=re.fullmatch(r'Heading(\d)',raw.get('style',''))
        if level:
            return {**common,'type':'heading','level':min(int(level.group(1))+1,4),'text':value}
        item={**common,'type':'paragraph','text':value}
        if raw.get('equations'):
            item['rich_html']=inline_html(raw,BASE+REPORT_NAME+'.html')
            item['inline_formulas']=[{'text':part['text'],'mathml':mathml(part['xml'],part['text'],'inline'),'original_equation_xml':part['xml']}for part in raw['parts']if part['type']=='math']
        return item
    mapping={route:[i for a,b in ranges for i in range(a,b+1)]for route,ranges in config['blockRanges'].items()}
    assigned=[i for ids in mapping.values()for i in ids]
    assert len(assigned)==len(set(assigned)),'Duplicate source block assignment'
    pages={}
    for route,ids in mapping.items():
        content=[item for i in ids if(item:=convert(i))]
        for n,value in enumerate(config['extra'].get(route,[]),1):
            content.append({'id':f'{route}_explanation_{n}','type':'paragraph','text':value,'sourceIds':['report'],'origin':'platform_explanation_based_on_report'})
        pages[route]={'id':route,'title':config['titles'][route],'summary':config['summaries'][route],'blocks':content,'sources':list(dict.fromkeys(s for b in content for s in b['sourceIds']))or['report'],'source_blocks':ids}
    federal=[]
    for raw in config['federalProjects']:
        ids=raw['sourceBlocks']
        federal.append({k:v for k,v in raw.items()if k!='sourceBlocks'}|{'mechanismBlocks':[f'b{i}'for i in ids],'proposalBlocks':[],'sourceIds':list(dict.fromkeys(s for i in ids for s in source_ids(i,i)))})
    math_count=sum(len(b.get('equations',[]))for b in report['blocks'])
    meta={'project_id':PROJECT,'title':config['title'],'edition_date':config['edition_date'],'statistical_snapshot':config['statistical_snapshot'],'documentary_snapshot':config['documentary_snapshot'],'source_docx_sha256':report['sha256'],'source_pages':None,'report_url':BASE+REPORT_NAME+'.docx','download_url':BASE+REPORT_NAME+'.docx','html_url':BASE+REPORT_NAME+'.html','markdown_url':BASE+REPORT_NAME+'.md','extract_url':BASE+'report_extraction.json','coverage_url':BASE+'coverage_manifest.json','content_policy':'author_report_preserved; current_statistical_panels_update_separately','tables':len(tables),'figures':len(figures),'footnotes':len(report['footnotes']),'formulas':len(FORMULAS),'inline_formula_nodes':math_count-len(FORMULAS),'total_math_nodes':math_count,'bibliography_entries':sum(b.get('style')=='Bibliography'for b in report['blocks']),'report_sources_are_not_automatically_revised':True,'source_clarifications':config['sourceClarifications']}
    result={'meta':meta,'pages':pages,'tables':tables,'figures':figures,'sources':sources,'derived':{'federalProjects':federal,'populationGroups':config['populationGroups'],'proposalStages':config['proposalStages'],'limits':config['limits']}}
    dump(app/'public/data/projects/international_export/expertise.json',result)
    if source.resolve()!=(destination/(REPORT_NAME+'.docx')).resolve():
        shutil.copy2(source,destination/(REPORT_NAME+'.docx'))
    assert hashlib.sha256((destination/(REPORT_NAME+'.docx')).read_bytes()).hexdigest()==report['sha256']
    shutil.copy2(cache/'extraction.json',destination/'report_extraction.json')
    markdown=[]
    for raw in report['blocks']:
        i=raw['index']
        if i in FORMULAS:
            plain,latex=FORMULAS[i]
            markdown.append(f'[B{i}; формула ({formula_lookup[i]["number"]})] {plain}\n\n$$\n{latex}\n$$')
        elif i in figure_map:
            figure=figure_map[i]
            markdown.append(f'[B{i}] ![{figure["title"]}]({Path(figure["url"]).name})')
        elif raw['type']=='table':
            rows=[]
            for ri,row in enumerate(raw['rows']):
                cells=[]
                for ci,value in enumerate(row):
                    notes=' ['+', '.join(map(str,raw['cell_footnotes'][ri][ci]))+']'if raw['cell_footnotes'][ri][ci]else''
                    cells.append(value.replace('|','\\|').replace('\n','<br>')+notes)
                rows.append('| '+' | '.join(cells)+' |')
                if ri==0:
                    rows.append('| '+' | '.join('---'for _ in row)+' |')
            markdown.append(f'[B{i}; таблица {raw["number"]}]\n\n'+'\n'.join(rows))
        elif raw.get('text'):
            notes=' '.join(f'[{n}]'for n in raw['footnotes'])
            level=re.fullmatch(r'Heading(\d)',raw.get('style',''))
            prefix='#'*(min(int(level.group(1))+1,4))+' 'if level else '# 'if raw.get('style')=='Title' else ''
            markdown.append(prefix+f'[B{i}; {raw["style"]}] '+raw['text']+(' '+notes if notes else''))
    markdown.append('# Сноски и источники\n\n'+'\n\n'.join(f'[{n["id"]}] {n["text"]}'for n in report['footnotes']))
    (destination/(REPORT_NAME+'.md')).write_text('\n\n'.join(markdown)+'\n',encoding='utf-8')
    for table in tables:
        with(destination/(table['id']+'.csv')).open('w',encoding='utf-8-sig',newline='')as f:
            writer=csv.writer(f);writer.writerow([c['label']for c in table['columns']]);writer.writerows([[row[c['key']]for c in table['columns']]for row in table['rows']])
    html_text=render_complete_html(report,config,{**result,'formula_lookup':formula_lookup},destination)
    first=config['first_substantive_block']
    substantive=[b['index']for b in report['blocks']if b['index']>=first and(b.get('text')or b.get('images')or b.get('equations')or b['type']=='table')]
    missing=sorted(set(substantive)-set(assigned))
    assert not missing,missing
    assert(len(pages),len(tables),len(figures),len(report['footnotes']),math_count)==(21,16,15,115,11)
    html_indices=list(map(int,re.findall(r'data-source-block="(\d+)"',html_text)))
    expected_indices=[b['index']for b in report['blocks']if b.get('text')or b.get('images')or b.get('equations')or b['type']=='table']
    assert html_indices==expected_indices,'Full HTML must preserve every nonempty block in source order'
    assert all(f'id="fn-{n["id"]}"'in html_text for n in report['footnotes'])
    assert html_text.count('<math ')==11,'All inline and display mathematics must be preserved'
    summary={'report_pages':None,'routes':len(pages),'source_body_blocks':len(report['blocks']),'substantive_blocks':len(substantive),'assigned_blocks':len(assigned),'unmapped_substantive_blocks':missing,'duplicate_assignments':[],'tables':len(tables),'figures':len(figures),'footnotes':len(report['footnotes']),'formulas':len(FORMULAS),'inline_formula_nodes':math_count-len(FORMULAS),'total_math_nodes':math_count,'bibliography_entries':meta['bibliography_entries'],'verified_page_locators':0,'original_docx_sha256_preserved':True,'full_html_order':'original_body_block_order','full_html_nonempty_blocks':len(html_indices),'full_html_substantive_block_coverage':True,'all_inline_math_in_original_positions':True,'blocks_by_page':{k:len(v['blocks'])for k,v in pages.items()}}
    coverage=[]
    for raw in report['blocks']:
        i=raw['index'];item={'sourceBlock':i,'sourceType':raw['type'],'sourceStyle':raw.get('style'),'route':next((route for route,ids in mapping.items()if i in ids),None)}
        if i<first:
            item.update(status='full_report_only',reason='Front matter preserved in unchanged DOCX and complete HTML/Markdown.')
        elif converted:=convert(i):
            item.update(status='rendered_block',target=converted['id'])
        elif raw.get('style')=='ReportCaption':
            parent=table_map.get(i+1)or figure_map.get(i-1);assert parent,i
            item.update(status='embedded_in_rendered_block',target=parent['id'],field='title')
        elif i-1 in table_map:
            item.update(status='embedded_in_rendered_block',target=table_map[i-1]['id'],field='note')
        elif i-2 in figure_map:
            item.update(status='embedded_in_rendered_block',target=figure_map[i-2]['id'],field='note')
        else:
            item.update(status='original_docx_only',reason='Blank formatting paragraph.')
        coverage.append(item)
    dump(destination/'coverage_manifest.json',{'meta':meta,'summary':summary,'blocks':coverage})
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=APP)
    parser.add_argument('--docx',type=Path)
    args=parser.parse_args();root=args.root.resolve()
    build(root,(args.docx or root/'public'/BASE/(REPORT_NAME+'.docx')).resolve())
