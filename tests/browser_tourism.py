"""HTTP smoke acceptance for Tourism, including the /family/ Pages subpath.

Run by tests/run_browser.py in CI with Playwright / Chromium. This suite covers
all research routes, real user interactions and downloaded research artifacts.
Series are read through the application, so both the full site and the gzip
publication view exercise the same UI contract. The UI JSON download is replayed
by the independent Python verifier; CSV, SVG and PNG bytes are checked as well.
"""
import argparse
import asyncio
import base64
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
from urllib.parse import urlencode, urljoin
import xml.etree.ElementTree as ET

from playwright.async_api import async_playwright
from browser_json import get_json as published_json


PROJECT = 'tourism'
ROOT = Path(__file__).resolve().parents[1]
PAGES = ['overview', 'framework', 'logic', 'audit', 'targets', 'map', 'regions',
         'finance', 'network', 'texts', 'domains', 'causal', 'proposals',
         'projections', 'population', 'structure', 'methods', 'lab',
         'explorer', 'library', 'updates']
SOURCE_IDS = {'62900', '62159', '62903', '62902', '63347', '62780'}


async def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    base = args.base.rstrip('/') + '/'
    checks, page_errors, console_errors, http_errors, downloads = [], [], [], [], []

    def check(name, ok, detail=None):
        checks.append({'name': name, 'passed': bool(ok), 'detail': detail})
        if not ok:
            print('FAIL', name, detail, flush=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True, executable_path=args.browser or None, args=['--no-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1440, 'height': 1000}, locale='ru-RU',
            timezone_id='Europe/Moscow', reduced_motion='reduce', accept_downloads=True)
        page = await context.new_page()
        page.on('pageerror', lambda error: page_errors.append(str(error)))
        page.on('console', lambda message: console_errors.append(message.text)
                if message.type == 'error' else None)
        page.on('response', lambda response: http_errors.append(
            {'url': response.url, 'status': response.status}) if response.status >= 400 else None)

        async def ready(name=None, state=None):
            await page.wait_for_function('''([name, state]) => {
                if (document.querySelector('.error-view')) return true;
                const main = document.querySelector('main#main');
                const root = main?.querySelector('.tourism-page');
                if (!root || main.dataset.project !== 'tourism' ||
                    main.dataset.ready !== 'true' || main.hasAttribute('aria-busy') ||
                    (name && main.dataset.page !== name)) return false;
                const actual = JSON.parse(root.dataset.routeState || '{}');
                return !state || Object.entries(state).every(
                    ([key, value]) => String(actual[key] ?? '') === String(value));
            }''', arg=[name, state], timeout=45000)
            if await page.locator('.error-view').count():
                raise AssertionError(await page.locator('.error-view').inner_text())

        async def route(name, params=None):
            suffix = '?' + urlencode(params) if params else ''
            await page.goto(base + '#/projects/' + PROJECT + '/' + name + suffix,
                            wait_until='domcontentloaded')
            await ready(name, params)

        def panel(title):
            return page.locator('#main section.panel').filter(
                has=page.get_by_role('heading', name=title, exact=True))

        async def group(name, action):
            try:
                await action()
            except Exception as error:
                check(name, False, str(error))

        async def save_download(control, filename):
            # Exercise the user action and browser download, never the serializer directly.
            async with page.expect_download(timeout=45000) as event:
                await control.click()
            artifact = await event.value
            failure = await artifact.failure()
            if failure:
                raise AssertionError('Download failed: ' + failure)
            check('download_name_' + filename, artifact.suggested_filename == filename,
                  artifact.suggested_filename)
            destination = output / filename
            await artifact.save_as(destination)
            payload = destination.read_bytes()
            if not payload:
                raise AssertionError('Empty downloaded file: ' + filename)
            downloads.append({'name': filename, 'bytes': len(payload),
                              'sha256': hashlib.sha256(payload).hexdigest()})
            return destination, payload

        for name in PAGES:
            async def route_check(name=name):
                await route(name)
                main = page.locator('main[data-ready="true"][data-project="tourism"]')
                check('route_' + name, await main.get_attribute('data-page') == name)
                check('heading_' + name, await main.locator('.page-heading h1').is_visible())
                check('content_' + name, await main.locator('.panel, .project-card, .note').count() > 0)
                check('title_' + name, 'Туризм и гостеприимство' in await page.title())
                check('no_authors_' + name, await page.locator('#sidebar a[data-route="authors"]').count() == 0)
            await group('load_' + name, route_check)

        async def source_targets():
            statistics = await published_json(context, base, 'data/projects/tourism/statistics.json')
            source_ids = {str(source.get('source_id', source.get('id')))
                          for source in statistics['sources']}
            check('six_source_contract', source_ids == SOURCE_IDS, sorted(source_ids))
            for source_id in sorted(SOURCE_IDS):
                await route('targets', {'source': source_id})
                picker = page.get_by_label('Показатель', exact=True)
                check('source_selected_' + source_id, await picker.input_value() == source_id)
                available = set(await picker.locator('option').evaluate_all('(items) => items.map(x => x.value)'))
                check('source_options_' + source_id, available == SOURCE_IDS)
                check('source_chart_' + source_id, await panel('Опубликованные значения').locator('svg.chart-svg').count() > 0)
                check('source_history_' + source_id, await panel('Исходные наблюдения').locator('tbody tr').count() > 0)
                check('source_link_' + source_id,
                      await page.locator('.tourism-source-note').get_by_role(
                          'link', name='ЕМИСС ' + source_id, exact=True).count() == 1)
            await page.screenshot(path=str(output / 'targets-desktop.png'))
        await group('source_targets', source_targets)

        async def territory_click():
            # Equal-sized tile marks avoid tiny or multipart SVG hit areas.
            await route('map', {'view': 'tiles'})
            picker = page.get_by_label('Территория', exact=True)
            current = await picker.input_value()
            options = await picker.locator('option').evaluate_all('(items) => items.map(x => x.value)')
            marks = page.locator('.map-surface .region[data-region]')
            map_ids = set(await marks.evaluate_all('(items) => items.map(x => x.dataset.region)'))
            selected = next(region for region in options if region != current and region in map_ids)
            await page.locator('.map-surface .region[data-region="' + selected + '"]').click()
            await ready('map', {'region': selected, 'view': 'tiles'})
            check('map_click_updates_profile', await picker.input_value() == selected)
            check('map_profile_visible', await panel('Профиль территории').is_visible())
            check('map_profile_explorer_link', 'region=' + selected in
                  (await panel('Профиль территории').get_by_role(
                      'link', name='Наблюдения территории', exact=True).get_attribute('href') or ''))
            await page.screenshot(path=str(output / 'map-desktop.png'))
        await group('territory_click', territory_click)

        async def calculator_flow():
            await route('lab', {'calculator': 'occupancy'})
            calculator = page.locator('.tourism-calculator[data-calculator="occupancy"]')
            await calculator.get_by_label('Проданные номеро-сутки', exact=True).fill('30')
            denominator = calculator.get_by_label('Открытые номеро-сутки', exact=True)
            await denominator.fill('80')
            result = calculator.locator('.tourism-calculation-output strong')
            await result.wait_for(state='visible')
            rendered = (await result.inner_text()).replace('%', '').replace(',', '.')
            value = float(''.join(rendered.split()))
            check('calculator_valid_value', abs(value - 100 * 30 / 80) < 1e-8)
            await denominator.fill('0')
            check('calculator_zero_denominator', await result.count() == 0)
            await denominator.fill('')
            check('calculator_blank_denominator', await result.count() == 0)
        await group('calculator_flow', calculator_flow)

        async def csv_download():
            await route('targets', {'source': '62900'})
            async with page.expect_download() as event:
                await panel('Исходные наблюдения').get_by_role('button', name='CSV', exact=True).click()
            artifact = await event.value
            destination = output / Path(artifact.suggested_filename).name
            await artifact.save_as(destination)
            payload = destination.read_bytes()
            rows = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig')), delimiter=';'))
            check('csv_file_downloaded', destination.suffix.lower() == '.csv' and bool(payload))
            check('csv_observations_nonempty', bool(rows))
            check('csv_source_fields', bool(rows) and
                  {'Территория', 'Период', 'Значение', 'Единица', 'Примечание'}.issubset(rows[0]))
            check('csv_period_and_unit', bool(rows) and all(row['Период'] and row['Единица'] for row in rows))
            downloads.append({'name': destination.name, 'bytes': len(payload),
                              'sha256': hashlib.sha256(payload).hexdigest(), 'rows': len(rows)})
        await group('csv_download', csv_download)

        research_period = '2026-09-30'
        research_label = 'Январь–сентябрь 2026'
        research_regions = ['77', '23', '24']
        research_state = {'period': research_period, 'regions': ','.join(research_regions),
                          'region': '24'}
        research_inputs = {}
        figure_export = {}

        async def research_data():
            if not research_inputs:
                source, packet = await asyncio.gather(
                    published_json(context, base, 'data/projects/tourism/series/62900.json'),
                    published_json(context, base, 'data/projects/tourism/research.json'))
                research_inputs.update(source=source, packet=packet)
            return research_inputs['source'], research_inputs['packet']

        async def research_json_download():
            source, packet = await research_data()
            await route('regions', {**research_state, 'view': 'table'})
            destination, payload = await save_download(
                page.get_by_role('button', name='Скачать исследование', exact=True),
                'tourism-research-' + research_period + '.json')
            bundle = json.loads(payload)
            settings = bundle['settings']
            check('research_json_selected_context',
                  settings['requestedPeriod'] == research_period == settings['appliedPeriod'] and
                  settings['regions'] == research_regions and settings['view'] == 'regions/table', settings)
            check('research_json_complete_source_rows',
                  bundle['source_observations'] == source['observations'] and
                  len(bundle['source_observations']) == 1806)
            provenance = bundle['provenance']
            check('research_json_provenance',
                  provenance['source_sha256'] == packet['source_sha256'] and
                  provenance['snapshot_ids'] == [source['snapshot_id']] and
                  provenance['source_url'] == 'https://www.fedstat.ru/indicator/62900' and
                  provenance['statistical_as_of'] == packet['statistical_as_of'] and
                  provenance['code_version'] == settings['version'])
            replay_path = output / 'tourism-research-replay.json'
            replay = subprocess.run(
                [sys.executable, str(ROOT / 'scripts/reproduce_tourism_research.py'),
                 str(destination), '--output', str(replay_path)],
                cwd=ROOT, capture_output=True, text=True, timeout=30)
            receipt = json.loads(replay_path.read_text(encoding='utf-8'))
            check('research_json_independent_python_replay',
                  replay.returncode == 0 and receipt['status'] == 'PASS',
                  {'returncode': replay.returncode, 'receipt': receipt, 'stderr': replay.stderr})
            check('research_json_replay_scope',
                  (receipt.get('observations'), receipt.get('regions'), receipt.get('periods_checked'),
                   receipt.get('trajectory_points_checked'), receipt.get('mismatches')) ==
                  (1806, 85, 21, 84, 8))
        await group('research_json_download', research_json_download)

        async def research_csv_download():
            source, packet = await research_data()
            await route('regions', {**research_state, 'view': 'table'})
            table = panel('Все территории выбранного среза')
            check('research_csv_table_is_paginated', await table.locator('tbody tr').count() == 15)
            await table.get_by_label('Поиск по таблице', exact=True).fill('Красноярский')
            check('research_csv_table_is_filtered', await table.locator('tbody tr').count() == 1)
            _, payload = await save_download(
                table.get_by_role('button', name='CSV всего среза', exact=True),
                'tourism-regions-' + research_period + '.csv')
            rows = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig')), delimiter=';'))
            expected = {row['map_id']: row for row in source['observations']
                        if row['period_end'] == research_period and row['geo_level'] == 'regional'}
            check('research_csv_whole_slice_after_filter',
                  len(rows) == len(expected) == 85 and
                  {row['region_id'] for row in rows} == set(expected), {'rows': len(rows)})
            check('research_csv_period_units_provenance', bool(rows) and all(
                row['period_start'] == '2026-01-01' and row['period_end'] == research_period and
                row['unit'] == 'млн поездок' and row['temporal_type'] == 'cumulative_ytd' and
                row['source_id'] == '62900' and
                row['source_url'] == 'https://www.fedstat.ru/indicator/62900' and
                row['snapshot_id'] == source['snapshot_id'] and
                row['source_sha256'] == packet['source_sha256'] and
                row['comparison_status'] == 'requires_edition_review' and bool(row['code_version'])
                for row in rows))
            check('research_csv_exact_source_values_and_cells', all(
                row['territory'] == expected[row['region_id']]['name'] and
                Decimal(row['value']) == Decimal(str(expected[row['region_id']]['value'])) and
                row['source_cell'] == expected[row['region_id']]['source_cell_attributes']['source_cell']
                for row in rows))
            total = sum(Decimal(str(row['value'])) for row in expected.values())
            national = next(Decimal(str(row['value'])) for row in source['observations']
                            if row['period_end'] == research_period and row['geo_level'] == 'national')
            tolerance = Decimal('0.000000001')
            check('research_csv_independent_shares_and_reconciliation', all(
                abs(Decimal(row['share_of_observed_regions_pct']) - Decimal(row['value']) / total * 100) < tolerance and
                abs(Decimal(row['regional_sum']) - total) < tolerance and
                abs(Decimal(row['national_value']) - national) < tolerance and
                abs(Decimal(row['national_minus_regions']) - (national - total)) < tolerance
                for row in rows))
            check('research_csv_ranked_rows',
                  [int(row['rank']) for row in rows] == list(range(1, 86)) and
                  [Decimal(row['value']) for row in rows] ==
                  sorted((Decimal(row['value']) for row in rows), reverse=True))
            downloads[-1]['rows'] = len(rows)
        await group('research_csv_download', research_csv_download)

        async def research_svg_download():
            _, packet = await research_data()
            await route('regions', {**research_state, 'view': 'ranking'})
            _, payload = await save_download(
                panel('Распределение поездок').get_by_role('button', name='SVG', exact=True),
                'tourism-rank-' + research_period + '.svg')
            svg = ET.fromstring(payload)
            ns = '{http://www.w3.org/2000/svg}'
            check('research_svg_document', svg.tag == ns + 'svg')
            title = 'Территории по объёму поездок · ' + research_label
            source = svg.findtext(ns + 'desc', '')
            acquired_date = '.'.join(packet['statistical_as_of'][:10].split('-')[::-1])
            source_terms = ['ЕМИСС 62900', research_label, 'млн поездок', 'накопленным итогом',
                            packet['source_sha256'][:12], acquired_date]
            check('research_svg_title_period_source',
                  svg.findtext(ns + 'title') == title and all(term in source for term in source_terms))
            # Direct text nodes are the visible annotation, distinct from accessibility metadata.
            visible = ' '.join(''.join(node.itertext()) for node in svg.findall(ns + 'text'))
            check('research_svg_visible_annotations', title in visible and source.strip() in visible)
            fonts = re.findall(r'data:font/woff;base64,([A-Za-z0-9+/=]+)', payload.decode('utf-8'))
            check('research_svg_embedded_fonts',
                  len(fonts) == 3 and all(base64.b64decode(font).startswith(b'wOFF') for font in fonts))
            chart = svg.find(ns + 'svg')
            width, height = int(svg.attrib['width']), int(svg.attrib['height'])
            top, chart_height = float(chart.attrib['y']), float(chart.attrib['height'])
            check('research_svg_chart_and_bounds',
                  width > 0 and height > top + chart_height and len(chart.findall('.//' + ns + 'rect')) >= 15)
            figure_export.update(svg=payload, width=width, height=height,
                                 top=top, chart_bottom=top + chart_height)
        await group('research_svg_download', research_svg_download)

        async def research_png_download():
            await route('regions', {**research_state, 'view': 'ranking'})
            _, payload = await save_download(
                panel('Распределение поездок').get_by_role('button', name='PNG', exact=True),
                'tourism-rank-' + research_period + '.png')
            check('research_png_signature', payload[:8] == b'\x89PNG\r\n\x1a\n' and payload[12:16] == b'IHDR')
            width, height = struct.unpack('>II', payload[16:24])
            if not figure_export:
                raise AssertionError('PNG downloaded; SVG acceptance failed, so image comparison is unavailable')
            check('research_png_dimensions',
                  (width, height) == (figure_export['width'] * 2, figure_export['height'] * 2),
                  {'width': width, 'height': height})
            # Decode the downloaded bytes and compare every pixel with the separately
            # downloaded SVG whose visible title, period and provenance were checked above.
            # Also require ink in all three bands, so two blank images cannot pass.
            raster = await page.evaluate('''async ({png, svg, top, bottom}) => {
                const load = (type, data) => new Promise((resolve, reject) => {
                    const image = new Image();
                    image.onload = () => resolve(image);
                    image.onerror = () => reject(new Error('Downloaded image cannot be decoded'));
                    image.src = 'data:' + type + ';base64,' + data;
                });
                const [actual, expected] = await Promise.all([load('image/png', png), load('image/svg+xml', svg)]);
                const width = actual.naturalWidth, height = actual.naturalHeight;
                const pixels = image => {
                    const canvas = document.createElement('canvas');
                    canvas.width = width; canvas.height = height;
                    const context = canvas.getContext('2d');
                    context.drawImage(image, 0, 0, width, height);
                    return context.getImageData(0, 0, width, height).data;
                };
                const a = pixels(actual), b = pixels(expected);
                let different = 0, headerInk = 0, chartInk = 0, sourceInk = 0;
                for (let i = 0; i < a.length; i += 4) {
                    if ([0, 1, 2, 3].some(c => Math.abs(a[i + c] - b[i + c]) > 2)) different++;
                    if (a[i + 3] > 0 && Math.min(a[i], a[i + 1], a[i + 2]) < 220) {
                        const y = Math.floor(i / 4 / width);
                        if (y < top * 2) headerInk++;
                        else if (y >= bottom * 2) sourceInk++;
                        else chartInk++;
                    }
                }
                return {width, height, differentPixels: different, headerInk, chartInk, sourceInk};
            }''', {'png': base64.b64encode(payload).decode('ascii'),
                   'svg': base64.b64encode(figure_export['svg']).decode('ascii'),
                   'top': figure_export['top'], 'bottom': figure_export['chart_bottom']})
            check('research_png_decodes_with_visible_annotations',
                  (raster['width'], raster['height']) == (width, height) and
                  all(raster[key] > 100 for key in ['headerInk', 'chartInk', 'sourceInk']), raster)
            check('research_png_matches_annotated_svg', raster['differentPixels'] == 0, raster)
        await group('research_png_download', research_png_download)

        for width in [390, 320]:
            async def mobile_navigation(width=width):
                await page.set_viewport_size({'width': width, 'height': 844})
                await route('overview')
                rail = page.locator('.project-nav')
                check('mobile_rail_overflows_' + str(width),
                      await rail.evaluate('e => e.scrollWidth > e.clientWidth'))
                await rail.evaluate('e => { e.scrollLeft = e.scrollWidth; }')
                check('mobile_rail_scrolls_' + str(width), await rail.evaluate('e => e.scrollLeft > 0'))
                check('mobile_active_project_' + str(width),
                      await rail.locator('.project-tab[data-project="tourism"]').get_attribute('aria-current') == 'true')
                check('mobile_page_width_' + str(width),
                      await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'))
                menu = page.get_by_role('button', name='Открыть меню', exact=True)
                await menu.click()
                check('mobile_menu_opens_' + str(width), await menu.get_attribute('aria-expanded') == 'true')
                await page.locator('#sidebar a[data-route="finance"]').click()
                await ready('finance')
                check('mobile_menu_navigates_' + str(width), await menu.get_attribute('aria-expanded') == 'false')
                check('mobile_menu_closes_' + str(width),
                      not await page.locator('body').evaluate('e => e.classList.contains("nav-open")'))
                await page.screenshot(path=str(output / ('finance-mobile-' + str(width) + '.png')))
            await group('mobile_navigation_' + str(width), mobile_navigation)

        check('no_page_errors', not page_errors, page_errors)
        check('no_console_errors', not console_errors, console_errors)
        check('no_http_errors', not http_errors, http_errors)
        result = {'project_id': PROJECT, 'base': base, 'runner': 'Playwright Chromium',
                  'scope': 'smoke', 'viewports': [[1440, 1000], [390, 844], [320, 844]],
                  'checks': checks, 'passed': sum(c['passed'] for c in checks),
                  'failed': sum(not c['passed'] for c in checks), 'page_errors': page_errors,
                  'console_errors': console_errors, 'http_errors': http_errors,
                  'downloads': downloads, 'screenshots': [p.name for p in output.glob('*.png')]}
        (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        await browser.close()
        print(json.dumps({'passed': result['passed'], 'failed': result['failed'],
                          'output': str(output)}, ensure_ascii=False), flush=True)
        if result['failed']:
            raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser')
    parser.add_argument('--smoke-only', action='store_true',
                        help='Accepted for CLI parity; Tourism always runs this bounded smoke suite.')
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
