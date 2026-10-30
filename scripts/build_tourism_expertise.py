#!/usr/bin/env python3
"""Publish the complete unmodified Tourism expertise and its source-linked pages."""
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

APP = Path(__file__).resolve().parents[1]
PROJECT = 'tourism'
BASE = f'downloads/projects/{PROJECT}/report/'
REPORT_NAME = 'expertise_tourism_2026'
FORMULAS = {
    156: ('D = (Vтур / Vвсе) × 100%', r'D=\frac{V_{\text{тур}}}{V_{\text{все}}}\times100\%'),
    349: ('wₜ,d = (1 + ln fₜ,d) × [1 + ln((N + 1)/(dfₜ + 1))]', r'w_{t,d}=(1+\ln f_{t,d})\left[1+\ln\frac{N+1}{df_t+1}\right]'),
    351: ('cos(d₁, d₂) = (w₁ · w₂)/(‖w₁‖ × ‖w₂‖)', r'\cos(d_1,d_2)=\frac{w_1\cdot w_2}{\lVert w_1\rVert\lVert w_2\rVert}'),
    393: ('Z = (Rпрод / Rоткр) × 100%', r'Z=\frac{R_{\text{прод}}}{R_{\text{откр}}}\times100\%'),
    396: ('S₃ = ((N₍₁₎ + N₍₂₎ + N₍₃₎) / Nгод) × 100%', r'S_3=\frac{N_{(1)}+N_{(2)}+N_{(3)}}{N_{\text{год}}}\times100\%'),
    401: ('Bконс = Bфед + Bрег − T', r'B_{\text{конс}}=B_{\text{фед}}+B_{\text{рег}}-T'),
    419: ('τ = (Ȳ₁,после − Ȳ₁,до) − (Ȳ₀,после − Ȳ₀,до)', r'\tau=(\overline{Y}_{1,\text{после}}-\overline{Y}_{1,\text{до}})-(\overline{Y}_{0,\text{после}}-\overline{Y}_{0,\text{до}})')
}


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def esc(value):
    return html.escape(str(value), quote=True)


def mathml(xml, label):
    """Preserve fractions, subscripts and bars from the seven source equations."""
    def convert(node):
        tag = node.tag.rsplit('}', 1)[-1]
        if tag.endswith('Pr'):
            return ''
        if tag == 't':
            return '<mtext>' + esc(node.text or '') + '</mtext>'
        children = {c.tag.rsplit('}', 1)[-1]: c for c in node}
        if tag == 'f':
            return '<mfrac>' + convert(children['num']) + convert(children['den']) + '</mfrac>'
        if tag == 'sSub':
            return '<msub>' + convert(children['e']) + convert(children['sub']) + '</msub>'
        if tag == 'bar':
            return '<mover accent="true">' + convert(children['e']) + '<mo>¯</mo></mover>'
        return '<mrow>' + ''.join(convert(child) for child in node) + '</mrow>'
    return '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block" aria-label="' + esc(label) + '">' + convert(ET.fromstring(xml)) + '</math>'


def render_complete_html(report, config, result, destination):
    """Render every original body block in source order, including the front matter."""
    figures = {int(f['sourceBlock'][1:]): f for f in result['figures']}
    tables = {int(t['sourceBlock'][1:]): t for t in result['tables']}
    blocks = {b['index']: b for b in report['blocks']}
    captions = {i + 1 for i in figures} | {i - 1 for i in tables}
    source_notes = {i + 2 for i in figures} | {i + 1 for i in tables}
    citations = lambda numbers: ' '.join(f'<sup><a href="#fn-{n}" aria-label="Сноска {n}">[{n}]</a></sup>' for n in numbers)
    rendered = []
    for block in report['blocks']:
        index = block['index']
        if index in captions or index in source_notes:
            # Titles and source notes are included inside the corresponding figure/table.
            continue
        attrs = f'id="b{index}" data-source-block="{index}"'
        notes = citations(block.get('footnotes', []))
        if index in tables:
            table = tables[index]
            rows = block['rows']
            header = ''.join(f'<th scope="col">{esc(c)}</th>' for c in rows[0])
            body = ''.join('<tr>' + ''.join(f'<td>{esc(c).replace(chr(10), "<br>")}</td>' for c in row) + '</tr>' for row in rows[1:])
            note = blocks.get(index + 1, {})
            rendered.append(f'<section class="report-table" {attrs}><h3 id="b{index-1}" data-source-block="{index-1}">{esc(table["title"])}</h3><div class="table-scroll" tabindex="0" role="region" aria-label="{esc(table["title"])}"><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div><p class="source-note" id="b{index+1}" data-source-block="{index+1}">{esc(table["note"])} {citations(note.get("footnotes", []))}</p>{notes}</section>')
        elif index in figures:
            figure = figures[index]
            note = blocks.get(index + 2, {})
            rendered.append(f'<figure {attrs}><img src="{esc(Path(figure["url"]).name)}" alt="{esc(figure["title"])}" loading="lazy"><figcaption><strong id="b{index+1}" data-source-block="{index+1}">{esc(figure["title"])}</strong><p class="source-note" id="b{index+2}" data-source-block="{index+2}">{esc(figure["note"])} {citations(note.get("footnotes", []))}</p></figcaption>{notes}</figure>')
        elif index in FORMULAS:
            formula = result['formula_lookup'][index]
            rendered.append(f'<div class="formula" {attrs}>{formula["mathml"]}<span class="formula-number">({formula["number"]})</span>{notes}</div>')
        else:
            text = block.get('text', '')
            if not text:
                continue
            match = re.fullmatch(r'Heading(\d)', block.get('style', ''))
            if match:
                tag = 'h' + str(min(int(match.group(1)) + 1, 4))
            else:
                tag = 'p'
            cls = ' class="source-note"' if block.get('style') == 'SourceNote' else ' class="source-front"' if index < config['first_substantive_block'] else ''
            rendered.append(f'<{tag}{cls} {attrs}>{esc(text).replace(chr(10), "<br>")} {notes}</{tag}>')
    def linkify(text):
        chunks = []
        end = 0
        for match in re.finditer(r'https?://[^\s]+', text):
            url = match.group(0).rstrip('.,;')
            chunks.append(esc(text[end:match.start()]))
            chunks.append(f'<a href="{esc(url)}" rel="noopener noreferrer">{esc(url)}</a>')
            chunks.append(esc(match.group(0)[len(url):]))
            end = match.end()
        chunks.append(esc(text[end:]))
        return ''.join(chunks).replace('\n', '<br>')
    sources = []
    for footnote in report['footnotes']:
        back = ' '.join(f'<a href="#b{i}" aria-label="Вернуться к фрагменту со сноской {footnote["id"]}">↩</a>' for i in footnote['referenced_by'])
        sources.append(f'<p id="fn-{footnote["id"]}"><strong>[{footnote["id"]}]</strong> {linkify(footnote["text"])} {back}</p>')
    navigation = ''.join(f'<a href="#b{b["index"]}">{esc(b["text"])}</a>' for b in report['blocks'] if b.get('style') == 'Heading1' and b['index'] >= config['first_substantive_block'])
    style = """@font-face{font-family:Roboto;src:url('../../../../assets/fonts/Roboto-Regular.woff') format('woff');font-weight:400;font-display:swap}@font-face{font-family:Roboto;src:url('../../../../assets/fonts/Roboto-Bold.woff') format('woff');font-weight:700;font-display:swap}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f1f7f6;color:#192d2c;font:17px/1.7 Roboto,Arial,sans-serif}main{max-width:1080px;margin:32px auto;padding:48px 60px;background:#fff;border-top:5px solid #208076}h1{font-size:38px;line-height:1.2;margin:0 0 22px}h2{font-size:28px;line-height:1.3;margin-top:48px}h3{font-size:22px;line-height:1.4;margin-top:32px}p{text-align:justify}a{color:#155c55;text-underline-offset:3px;overflow-wrap:anywhere}nav{display:flex;gap:12px 24px;flex-wrap:wrap;margin:24px 0;padding:18px 0;border-block:1px solid #cadfda}nav a{font-size:14px}figure{margin:34px 0}img{display:block;width:auto;height:auto;max-width:100%;margin:auto}figcaption{margin-top:14px;line-height:1.5}.source-note{font-size:14px;color:#4a6560}.table-scroll{overflow:auto;max-width:100%;border:1px solid #d9e2df}.table-scroll:focus{outline:2px solid #208076}table{border-collapse:collapse;width:100%;min-width:660px;font-size:14px;line-height:1.55}th,td{padding:10px 12px;border:1px solid #d9e2df;text-align:left;vertical-align:top}th{background:white;font-weight:700}.formula{display:flex;gap:14px;align-items:center;justify-content:center;margin:24px 0;padding:18px 0;overflow:auto}.formula math{font-size:19px}.formula-number{margin-left:auto;white-space:nowrap}.source-front{font-size:14px;color:#576c68;white-space:pre-line}.source-front#b8{font-size:24px;color:#192d2c;font-weight:700}.sources{font-size:14px}.sources p{padding:10px 0;border-bottom:1px solid #e4ece9;text-align:left}.skip{position:absolute;left:-9999px}.skip:focus{left:16px;top:10px;background:white;padding:8px}*[id]{scroll-margin-top:20px}@media(max-width:680px){main{margin:0;padding:26px 20px}h1{font-size:29px}h2{font-size:24px}p{text-align:left}.formula math{font-size:15px}.formula{justify-content:flex-start}figure{margin:24px 0}.sources{font-size:13px}}@media print{body{background:white}main{margin:0;border:0;padding:0;max-width:none}nav,.skip,.report-links{display:none}h2,h3{break-after:avoid}figure,.formula{break-inside:avoid}.table-scroll{overflow:visible}table{min-width:0}a{color:inherit;text-decoration:none}.sources{font-size:10pt}img{max-height:650px;object-fit:contain}}"""
    output = f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(config["title"])}</title><meta name="description" content="Полный текст авторской экспертизы национального проекта Туризм и гостеприимство по состоянию на 29 октября 2026 года"><style>{style}</style></head><body><a class="skip" href="#b70">К тексту исследования</a><main><h1>{esc(config["title"])}</h1><p class="report-links"><a href="../../../../#/projects/tourism/overview">Интерактивная экспертиза</a> · <a href="{REPORT_NAME}.docx">Отчёт DOCX</a> · <a href="{REPORT_NAME}.md">Текст Markdown</a></p><nav aria-label="Разделы полного отчёта">{navigation}<a href="#footnotes">Сноски и источники</a></nav><article>' + '\n'.join(rendered) + '</article><section class="sources" id="footnotes"><h2>Сноски и источники</h2>' + '\n'.join(sources) + '</section></main></body></html>\n'
    (destination / (REPORT_NAME + '.html')).write_text(output, encoding='utf-8')
    return output


def build(app, source):
    config = json.loads((app / 'inputs/tourism/report/editorial_config.json').read_text(encoding='utf-8'))
    cache = app / '.cache/tourism_expertise'
    subprocess.run([sys.executable, str(app / 'scripts/extract_tourism_report.py'), '--docx', str(source), '--output', str(cache)], check=True, stdout=subprocess.DEVNULL)
    report = json.loads((cache / 'extraction.json').read_text(encoding='utf-8'))
    assert report['sha256'] == config['source_sha256'], 'Editorial map belongs to another DOCX edition'
    blocks = {b['index']: b for b in report['blocks']}
    destination = app / 'public' / BASE
    destination.mkdir(parents=True, exist_ok=True)
    sources = [{'id':'report', 'title':config['title'] + ', 2026', 'text':'Авторская экспертиза по состоянию на 29 октября 2026 года. Паспортные редакции опубликованы 16 октября 2026 года. Статистическая выгрузка получена 15 октября 2026 года. Периоды отдельных наблюдений и статусы оценок раскрыты в тексте.', 'url':BASE + REPORT_NAME + '.docx', 'kind':'author_report', 'sha256':report['sha256']}]
    for note in report['footnotes']:
        urls = [url.rstrip('.,;') for url in note['urls']]
        sources.append({'id':f'fn_{note["id"]:03d}', 'title':note['paragraphs'][0].strip(), 'text':note['text'], 'url':urls[0] if urls else sources[0]['url'], 'urls':urls, 'paragraphs':note['paragraphs'], 'note_number':note['id'], 'kind':'source_note', 'source_blocks':[f'b{i}' for i in note['referenced_by']]})

    def source_ids(first, last):
        return list(dict.fromkeys(['report'] + [f'fn_{number:03d}' for i in range(first, last + 1) for number in blocks.get(i, {}).get('footnotes', [])]))

    tables = []
    for raw in report['tables']:
        index, number = raw['index'], raw['number']
        title = blocks[index - 1]['text']
        note = blocks[index + 1]['text']
        assert blocks[index - 1]['style'] == 'Caption' and blocks[index + 1]['style'] == 'SourceNote'
        tables.append({'id':f'table_{number:02d}', 'number':number, 'type':'table', 'sourceBlock':f'b{index}', 'title':title, 'columns':[{'key':f'c{i}', 'label':label, 'title':label} for i, label in enumerate(raw['rows'][0])], 'rows':[{f'c{i}':text for i, text in enumerate(row)} for row in raw['rows'][1:]], 'note':note, 'sourceIds':source_ids(index - 2, index + 1), 'headerSourceIds':[[f'fn_{n:03d}' for n in cell] for cell in raw['cell_footnotes'][0]], 'cellSourceIds':[[[f'fn_{n:03d}' for n in cell] for cell in row] for row in raw['cell_footnotes'][1:]], 'page':None, 'csv_url':BASE + f'table_{number:02d}.csv'})
    table_map = {int(t['sourceBlock'][1:]):t for t in tables}
    figures = []
    for number, raw in enumerate(report['figures'], 1):
        index = raw['block']
        assert blocks[index + 1]['style'] == 'Caption' and blocks[index + 2]['style'] == 'SourceNote'
        title, note = blocks[index + 1]['text'], blocks[index + 2]['text']
        filename = f'figure_{number:02d}' + Path(raw['path']).suffix
        shutil.copy2(cache / raw['path'], destination / filename)
        figures.append({'id':f'figure_{number:02d}', 'number':number, 'title':title, 'caption':title, 'note':note, 'url':BASE + filename, 'sourceBlock':f'b{index}', 'page':None, 'sourceIds':source_ids(index - 1, index + 2), 'implementation':config['figureImplementations'][number - 1], 'original_sha256':raw['sha256'], 'role':'faithful_source_illustration', 'interactive_data':'documentary.json or analytics.json; source illustrations preserve the report edition'})
    figure_map = {int(f['sourceBlock'][1:]):f for f in figures}
    formula_lookup = {}
    for index, (plain, latex) in FORMULAS.items():
        raw = blocks[index]
        assert len(raw['equations']) == 1
        formula_lookup[index] = {'id':f'b{index}', 'sourceBlock':index, 'sourceIds':source_ids(index, index), 'type':'formula', 'text':plain, 'latex':latex, 'number':int(re.sub(r'\D', '', raw['text'])), 'original_equation_text':raw['equations'], 'original_equation_xml':raw['equations_xml'][0], 'mathml':mathml(raw['equations_xml'][0], plain), 'page':None, 'page_verification':'original_ooxml_equation_structure'}

    def convert(index):
        raw = blocks[index]
        common = {'id':f'b{index}', 'sourceBlock':index, 'sourceIds':source_ids(index, index), 'page':None}
        if index in table_map:
            table = table_map[index]
            return {**table, **common, 'id':table['id'], 'sourceIds':table['sourceIds']}
        if index in figure_map:
            figure = figure_map[index]
            return {**common, 'type':'figure_ref', 'figureId':figure['id'], 'title':figure['title'], 'note':figure['note'], 'url':figure['url'], 'sourceIds':figure['sourceIds']}
        if index in formula_lookup:
            return formula_lookup[index]
        text = raw.get('text', '')
        if not text or raw.get('images') or raw.get('style') == 'Caption':
            return None
        if raw.get('style') == 'SourceNote' and (index - 1 in table_map or index - 2 in figure_map):
            return None
        level = re.fullmatch(r'Heading(\d)', raw.get('style', ''))
        return {**common, 'type':'heading', 'level':min(int(level.group(1)) + 1, 4), 'text':text} if level else {**common, 'type':'paragraph', 'text':text}

    mapping = {route:[i for first,last in ranges for i in range(first,last + 1)] for route,ranges in config['blockRanges'].items()}
    assigned = [i for indices in mapping.values() for i in indices]
    assert len(assigned) == len(set(assigned)), 'Duplicate source block assignment'
    pages = {}
    for route, indices in mapping.items():
        content = [item for i in indices if (item := convert(i))]
        for number, text in enumerate(config['extra'].get(route, []), 1):
            content.append({'id':f'{route}_explanation_{number}', 'type':'paragraph', 'text':text, 'sourceIds':['report'], 'origin':'platform_explanation_based_on_report'})
        pages[route] = {'id':route, 'title':config['titles'][route], 'summary':config['summaries'][route], 'blocks':content, 'sources':list(dict.fromkeys(s for b in content for s in b['sourceIds'])) or ['report'], 'source_blocks':indices}
    federal = []
    for raw in config['federalProjects']:
        indices = raw['sourceBlocks']
        exact_sources = list(dict.fromkeys(s for i in indices for s in source_ids(i, i)))
        federal.append({k:v for k,v in raw.items() if k != 'sourceBlocks'} | {'mechanismBlocks':[f'b{i}' for i in indices], 'proposalBlocks':[], 'sourceIds':exact_sources})
    derived = {'federalProjects':federal, 'populationGroups':config['populationGroups'], 'proposalStages':config['proposalStages'], 'limits':config['limits']}
    meta = {'project_id':PROJECT, 'title':config['title'], 'edition_date':config['edition_date'], 'statistical_snapshot':config['statistical_snapshot'], 'documentary_snapshot':config['documentary_snapshot'], 'source_docx_sha256':report['sha256'], 'source_pages':None, 'report_url':BASE + REPORT_NAME + '.docx', 'download_url':BASE + REPORT_NAME + '.docx', 'html_url':BASE + REPORT_NAME + '.html', 'markdown_url':BASE + REPORT_NAME + '.md', 'extract_url':BASE + 'report_extraction.json', 'coverage_url':BASE + 'coverage_manifest.json', 'content_policy':'author_report_preserved; current_statistical_panels_update_separately', 'tables':len(tables), 'figures':len(figures), 'footnotes':len(report['footnotes']), 'formulas':len(FORMULAS), 'report_sources_are_not_automatically_revised':True, 'source_clarifications':config['sourceClarifications']}
    result = {'meta':meta, 'pages':pages, 'tables':tables, 'figures':figures, 'sources':sources, 'derived':derived}
    dump(app / 'public/data/projects/tourism/expertise.json', result)
    if source.resolve() != (destination / (REPORT_NAME + '.docx')).resolve():
        shutil.copy2(source, destination / (REPORT_NAME + '.docx'))
    assert hashlib.sha256((destination / (REPORT_NAME + '.docx')).read_bytes()).hexdigest() == report['sha256']
    shutil.copy2(cache / 'extraction.json', destination / 'report_extraction.json')
    markdown = (cache / 'full_text.md').read_text(encoding='utf-8')
    for index, (plain, latex) in FORMULAS.items():
        for raw_formula in blocks[index]['equations']:
            markdown = markdown.replace('[FORMULA] ' + raw_formula, '[Формула] ' + plain + '\n\n$$\n' + latex + '\n$$')
    for raw, figure in zip(report['figures'], figures):
        original_image = blocks[raw['block']]['images'][0]
        markdown = markdown.replace('[IMAGE: ' + original_image + ']', '![' + figure['title'] + '](' + Path(figure['url']).name + ')')
    (destination / (REPORT_NAME + '.md')).write_text(markdown + '\n# Сноски и источники\n\n' + '\n\n'.join(f'[{f["id"]}] {f["text"]}' for f in report['footnotes']) + '\n', encoding='utf-8')
    for table in tables:
        with (destination / (table['id'] + '.csv')).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow([c['label'] for c in table['columns']])
            writer.writerows([[row[c['key']] for c in table['columns']] for row in table['rows']])
    html_text = render_complete_html(report, config, {**result, 'formula_lookup':formula_lookup}, destination)
    first = config['first_substantive_block']
    substantive = [b['index'] for b in report['blocks'] if b['index'] >= first and (b.get('text') or b.get('images') or b['type'] == 'table')]
    missing = sorted(set(substantive) - set(assigned))
    assert not missing, missing
    assert (len(pages), len(tables), len(figures), len(report['footnotes']), sum(len(b.get('equations', [])) for b in report['blocks'])) == (21, 16, 12, 130, 7)
    assert all(f'data-source-block="{i}"' in html_text for i in substantive), 'Full HTML omitted a source block'
    assert all(f'id="fn-{n["id"]}"' in html_text for n in report['footnotes']), 'Full HTML omitted a footnote'
    summary = {'report_pages':None, 'routes':len(pages), 'substantive_blocks':len(substantive), 'assigned_blocks':len(assigned), 'unmapped_substantive_blocks':missing, 'duplicate_assignments':[], 'tables':len(tables), 'figures':len(figures), 'footnotes':len(report['footnotes']), 'formulas':len(FORMULAS), 'verified_page_locators':0, 'original_docx_sha256_preserved':True, 'full_html_order':'original_body_block_order', 'full_html_substantive_block_coverage':True, 'blocks_by_page':{k:len(v['blocks']) for k,v in pages.items()}}
    coverage = []
    for raw in report['blocks']:
        index = raw['index']
        item = {'sourceBlock':index, 'sourceType':raw['type'], 'sourceStyle':raw.get('style'), 'route':next((route for route,ids in mapping.items() if index in ids), None)}
        if index < first:
            item.update(status='full_report_only', reason='Front matter preserved in the unchanged DOCX, complete HTML and Markdown.')
        elif converted := convert(index):
            item.update(status='rendered_block', target=converted['id'])
        elif raw.get('style') == 'Caption':
            parent = table_map.get(index + 1) or figure_map.get(index - 1)
            assert parent, index
            item.update(status='embedded_in_rendered_block', target=parent['id'], field='title')
        elif index - 1 in table_map:
            item.update(status='embedded_in_rendered_block', target=table_map[index - 1]['id'], field='note')
        elif index - 2 in figure_map:
            item.update(status='embedded_in_rendered_block', target=figure_map[index - 2]['id'], field='note')
        else:
            item.update(status='original_docx_only', reason='Blank formatting paragraph.')
        coverage.append(item)
    dump(destination / 'coverage_manifest.json', {'meta':meta, 'summary':summary, 'blocks':coverage})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=APP)
    parser.add_argument('--docx', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    build(root, (args.docx or root / 'public' / BASE / (REPORT_NAME + '.docx')).resolve())
