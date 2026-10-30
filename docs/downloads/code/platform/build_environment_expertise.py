#!/usr/bin/env python3
"""Publish the complete, unchanged Environment author report with source locators."""
from pathlib import Path
import argparse, csv, json, re, shutil, subprocess, sys

APP = Path(__file__).resolve().parents[1]
PROJECT = 'environment'
BASE = f'downloads/projects/{PROJECT}/report/'
REPORT_NAME = 'expertise_environment_2026'


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def norm(text):
    return re.sub(r'\W+', '', text.lower().replace('ё', 'е'))


FORMULAS = {
    211: ('wₜd = (1 + ln fₜd) × [ln((N + 1)/(dfₜ + 1)) + 1] при fₜd > 0, иначе 0', r'w_{td}=\begin{cases}(1+\ln f_{td})\left[\ln\frac{N+1}{df_t+1}+1\right],&f_{td}>0\\0,&f_{td}=0\end{cases}'),
    213: ('cos(a, b) = Σₜ aₜbₜ / (√Σₜ aₜ² × √Σₜ bₜ²)', r'\cos(a,b)=\frac{\sum_t a_tb_t}{\sqrt{\sum_t a_t^2}\sqrt{\sum_t b_t^2}}'),
    271: ('C̅ₚ = Σᵢ NᵢCᵢₚ / Σᵢ Nᵢ', r'\overline{C}_p=\frac{\sum_i N_i C_{ip}}{\sum_i N_i}'),
}


def build(app, source, render=None):
    config = json.loads((app / 'inputs/environment/report/editorial_config.json').read_text())
    cache = app / '.cache/environment_expertise'
    subprocess.run([sys.executable, str(app / 'scripts/extract_environment_report.py'), '--docx', str(source), '--output', str(cache)], check=True, stdout=subprocess.DEVNULL)
    report = json.loads((cache / 'extraction.json').read_text())
    assert report['sha256'] == config['source_sha256'], 'Editorial map belongs to another DOCX edition'
    blocks = {b['index']: b for b in report['blocks']}
    by_paragraph = {b['paragraph_index']: b for b in report['blocks'] if 'paragraph_index' in b}
    destination = app / 'public' / BASE
    destination.mkdir(parents=True, exist_ok=True)
    locator_path = app / 'inputs/environment/report/report_page_locations.json'
    locators = json.loads(locator_path.read_text()) if locator_path.exists() else {}
    if locators.get('source_docx_sha256') != report['sha256']:
        locators = {}
    page_text = []
    if render:
        import fitz
        with fitz.open(next(render.glob('*.pdf'))) as pdf:
            page_text = [norm(page.get_text()) for page in pdf]

    def locate(text):
        query = norm(text)[:95]
        if len(query) < 15:
            return None
        if page_text:
            return next((i + 1 for i, page in enumerate(page_text) if i >= 2 and query in page), None)
        return locators.get('locations', {}).get(norm(text))

    sources = [{'id': 'report', 'title': config['title'] + ', 2026', 'text': 'Предоставленный авторский отчёт по состоянию на 28 октября 2026 года. Паспортные редакции опубликованы 16 октября 2026 года. Статистические выводы отчёта основаны на сохранённых выгрузках от 15 октября 2026 года. Обновляемые панели платформы имеют отдельные даты источников и проверки.', 'url': BASE + REPORT_NAME + '.docx', 'kind': 'author_report', 'sha256': report['sha256']}]
    for footnote in report['footnotes']:
        urls = [url.rstrip('.,;') for url in footnote['urls']]
        sources.append({'id': f"fn_{footnote['id']:03d}", 'title': footnote['paragraphs'][0].strip(), 'text': footnote['text'], 'url': urls[0] if urls else sources[0]['url'], 'urls': urls, 'paragraphs': footnote['paragraphs'], 'note_number': footnote['id'], 'kind': 'source_note', 'source_blocks': [f'b{i}' for i in footnote['referenced_by']]})

    def source_ids(first, last):
        return list(dict.fromkeys(['report'] + [f'fn_{number:03d}' for i in range(first, last + 1) for number in blocks.get(i, {}).get('footnotes', [])]))

    tables = []
    for raw in report['tables']:
        index, number = raw['index'], raw['number']
        title = blocks[index - 1]['text']
        note = blocks.get(index + 1, {}).get('text', '')
        if blocks.get(index + 1, {}).get('style') != 'SourceNote' and not note.startswith('Примечание.'):
            note = ''
        tables.append({'id': f'table_{number:02d}', 'number': number, 'type': 'table', 'sourceBlock': f'b{index}', 'title': title, 'columns': [{'key': f'c{i}', 'label': label, 'title': label} for i, label in enumerate(raw['rows'][0])], 'rows': [{f'c{i}': text for i, text in enumerate(row)} for row in raw['rows'][1:]], 'note': note, 'sourceIds': source_ids(index - 2, index + 1), 'headerSourceIds': [[f'fn_{n:03d}' for n in cell] for cell in raw.get('cell_footnotes',[[]])[0]], 'cellSourceIds': [[[f'fn_{n:03d}' for n in cell] for cell in row] for row in raw.get('cell_footnotes',[])[1:]], 'page': locate(title)})
    table_map = {t['sourceBlock']: t for t in tables}
    figures = []
    for number, raw in enumerate(report['figures'], 1):
        index = raw['block']
        title = blocks[index + 1]['text']
        note = blocks[index + 2].get('text', '')
        filename = f'figure_{number:02d}' + Path(raw['path']).suffix
        shutil.copy2(cache / raw['path'], destination / filename)
        figures.append({'id': f'figure_{number:02d}', 'number': number, 'title': title, 'caption': title, 'note': note, 'url': BASE + filename, 'sourceBlock': f'b{index}', 'page': locate(title), 'sourceIds': source_ids(index - 1, index + 2), 'implementation': config['figureImplementations'][number - 1], 'original_sha256': raw['sha256'], 'role': 'faithful_source_illustration', 'interactive_data': 'documentary.json or analytics.json; source illustrations do not replace numerical inputs'})
    figure_map = {f['sourceBlock']: f for f in figures}

    def convert(index):
        block = blocks[index]
        common = {'id': f'b{index}', 'sourceBlock': index, 'sourceIds': source_ids(index, index), 'page': locate(block.get('text', ''))}
        if f'b{index}' in table_map:
            table = table_map[f'b{index}']
            return {**table, **common, 'id': table['id'], 'sourceIds': table['sourceIds'], 'page': table['page']}
        if f'b{index}' in figure_map:
            fig = figure_map[f'b{index}']
            return {**common, 'type': 'figure_ref', 'figureId': fig['id'], 'title': fig['title'], 'note': fig['note'], 'url': fig['url'], 'page': fig['page'], 'sourceIds': fig['sourceIds']}
        paragraph = block.get('paragraph_index')
        if paragraph in FORMULAS:
            plain, latex = FORMULAS[paragraph]
            return {**common, 'type': 'formula', 'text': plain, 'latex': latex, 'number': int(re.sub(r'\D', '', block['text'])), 'original_equation_text': block.get('equations'), 'page': config.get('verifiedFormulaPages', {}).get(str(paragraph)), 'page_verification': 'rendered_source_formula_visually_checked'}
        text = block.get('text', '')
        if not text or block.get('images') or block.get('style') == 'Caption':
            return None
        if (f'b{index-1}' in table_map or f'b{index-2}' in figure_map) and (text.startswith('Примечание.') or block.get('style') == 'SourceNote'):
            return None
        level = re.search(r'Heading(\d)', block.get('style', ''))
        return {**common, 'type': 'heading', 'level': min(int(level.group(1)) + 1, 4), 'text': text} if level else {**common, 'type': 'paragraph', 'text': text}

    paragraph_route = {p: route for route, paragraphs in config['routes'].items() for p in paragraphs}
    assert len(paragraph_route) == sum(len(v) for v in config['routes'].values()), 'Duplicate paragraph assignment'
    mapping = {route: [] for route in config['routes']}
    for block in report['blocks']:
        paragraph = block.get('paragraph_index')
        if block['type'] == 'table':
            paragraph = blocks[block['index'] - 1].get('paragraph_index')
        if paragraph in paragraph_route:
            mapping[paragraph_route[paragraph]].append(block['index'])
    pages = {}
    for route, indices in mapping.items():
        content = [item for i in indices if (item := convert(i))]
        for number, text in enumerate(config['extra'].get(route, []), 1):
            content.append({'id': f'{route}_explanation_{number}', 'type': 'paragraph', 'text': text, 'sourceIds': ['report'], 'origin': 'platform_explanation_based_on_report'})
        pages[route] = {'id': route, 'title': config['titles'][route], 'summary': config['summaries'][route], 'blocks': content, 'sources': list(dict.fromkeys(s for b in content for s in b['sourceIds'])) or ['report'], 'source_blocks': indices}
    federal = []
    for raw in config['federalProjects']:
        indices = [by_paragraph[p]['index'] for p in raw['paragraphs']]
        exact_sources = list(dict.fromkeys(s for i in indices for s in source_ids(i, i)))
        federal.append({k: v for k, v in raw.items() if k != 'paragraphs'} | {'mechanismBlocks': [f'b{i}' for i in indices], 'proposalBlocks': [], 'sourceIds': exact_sources})
    derived = {'federalProjects': federal, 'populationGroups': config['populationGroups'], 'proposalStages': config['proposalStages'], 'limits': config['limits']}
    meta = {'project_id': PROJECT, 'title': config['title'], 'edition_date': config['edition_date'], 'statistical_snapshot': config['statistical_snapshot'], 'documentary_snapshot': config['documentary_snapshot'], 'source_docx_sha256': report['sha256'], 'source_pages': len(page_text) or locators.get('source_pages'), 'report_url': BASE + REPORT_NAME + '.docx', 'download_url': BASE + REPORT_NAME + '.docx', 'markdown_url': BASE + REPORT_NAME + '.md', 'extract_url': BASE + 'report_extraction.json', 'coverage_url': BASE + 'coverage_manifest.json', 'content_policy': 'author_report_preserved; current_statistical_panels_update_separately', 'tables': len(tables), 'figures': len(figures), 'footnotes': len(report['footnotes']), 'formulas': len(FORMULAS), 'report_sources_are_not_automatically_revised': True}
    result = {'meta': meta, 'pages': pages, 'tables': tables, 'figures': figures, 'sources': sources, 'derived': derived}
    meta['source_clarifications'] = config.get('sourceClarifications', [])
    dump(app / f'public/data/projects/{PROJECT}/expertise.json', result)
    if source.resolve() != (destination / (REPORT_NAME + '.docx')).resolve():
        shutil.copy2(source, destination / (REPORT_NAME + '.docx'))
    shutil.copy2(cache / 'extraction.json', destination / 'report_extraction.json')
    markdown = (cache / 'full_text.md').read_text()
    for paragraph, (plain, latex) in FORMULAS.items():
        for raw_formula in by_paragraph[paragraph]['equations']:
            markdown = markdown.replace('[FORMULA] ' + raw_formula, '[Формула] ' + plain + '\n\n$$\n' + latex + '\n$$')
    for raw, figure in zip(report['figures'], figures):
        original_image = blocks[raw['block']]['images'][0]
        markdown = markdown.replace('[IMAGE: ' + original_image + ']', '![' + figure['title'] + '](' + Path(figure['url']).name + ')')
    (destination / (REPORT_NAME + '.md')).write_text(markdown + '\n# Сноски и источники\n\n' + '\n\n'.join(f"[{f['id']}] {f['text']}" for f in report['footnotes']) + '\n', encoding='utf-8')
    for table in tables:
        with (destination / (table['id'] + '.csv')).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow([c['label'] for c in table['columns']])
            writer.writerows([[row[column['key']] for column in table['columns']] for row in table['rows']])
    first = config['first_substantive_paragraph']
    assigned = [i for indices in mapping.values() for i in indices]
    substantive = [b['index'] for b in report['blocks'] if b['index'] >= by_paragraph[first]['index'] and (b.get('text') or b.get('images') or b['type'] == 'table')]
    missing = sorted(set(substantive) - set(assigned))
    duplicates = [i for i in set(assigned) if assigned.count(i) > 1]
    assert not missing and not duplicates, (missing, duplicates)
    assert (len(pages), len(tables), len(figures), len(report['footnotes']), sum(len(b.get('equations', [])) for b in report['blocks'])) == (21, 10, 12, 112, 3)
    summary = {'report_pages': meta['source_pages'], 'routes': len(pages), 'substantive_blocks': len(substantive), 'assigned_blocks': len(assigned), 'unmapped_substantive_blocks': missing, 'duplicate_assignments': duplicates, 'tables': len(tables), 'figures': len(figures), 'footnotes': len(report['footnotes']), 'formulas': len(FORMULAS), 'verified_page_locators': sum(b.get('page') is not None for p in pages.values() for b in p['blocks']), 'blocks_by_page': {k: len(v['blocks']) for k, v in pages.items()}}
    coverage = []
    for block in report['blocks']:
        index = block['index']
        item = {'sourceBlock': index, 'sourceType': block['type'], 'sourceStyle': block.get('style'), 'route': next((route for route, ids in mapping.items() if index in ids), None)}
        if index < by_paragraph[first]['index']:
            item.update(status='original_docx_only', reason='Title, approval template and table of contents remain in the unchanged original DOCX and Markdown.')
        elif converted := convert(index):
            item.update(status='rendered_block', target=converted['id'])
        elif block.get('style') == 'Caption':
            parent = table_map.get(f'b{index+1}') or figure_map.get(f'b{index-1}')
            assert parent, index
            item.update(status='embedded_in_rendered_block', target=parent['id'], field='title')
        elif f'b{index-1}' in table_map:
            item.update(status='embedded_in_rendered_block', target=table_map[f'b{index-1}']['id'], field='note')
        elif f'b{index-2}' in figure_map:
            item.update(status='embedded_in_rendered_block', target=figure_map[f'b{index-2}']['id'], field='note')
        else:
            item.update(status='original_docx_only', reason='Blank formatting paragraph.')
        coverage.append(item)
    dump(destination / 'coverage_manifest.json', {'meta': meta, 'summary': summary, 'blocks': coverage})
    if page_text:
        dump(locator_path, {'source_docx_sha256': report['sha256'], 'source_pages': len(page_text), 'locations': {norm(b.get('text', '')): locate(b.get('text', '')) for b in report['blocks'] if locate(b.get('text', '')) is not None}})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=APP)
    parser.add_argument('--docx', type=Path)
    parser.add_argument('--render-dir', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    build(root, (args.docx or root / 'public' / BASE / (REPORT_NAME + '.docx')).resolve(), args.render_dir)
