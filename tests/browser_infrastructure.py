"""HTTP acceptance for the Infrastructure for Life project.

Browser plugin not available. Existing Playwright / Chromium is used.
Flow: project route -> source, period or documentary selection -> source-backed
content, chart, route state and matching download; desktop and mobile widths.
"""
import argparse
import asyncio
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlencode, urljoin

from playwright.async_api import async_playwright
from browser_json import get_json as published_json

PROJECT = 'life_infrastructure'
PAGES = ['overview', 'framework', 'logic', 'audit', 'targets', 'map', 'regions',
         'finance', 'network', 'texts', 'domains', 'causal', 'proposals',
         'projections', 'population', 'structure', 'methods', 'lab',
         'explorer', 'library', 'updates']

def csv_rows(data):
    return list(csv.DictReader(io.StringIO(data.decode('utf-8-sig')), delimiter=';'))

def number(value):
    try:
        cleaned = ''.join(str(value).split()).replace(',', '.').replace('%', '')
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None

def analytical(row):
    return row.get('analytical_value') if 'analytical_value' in row else None if row.get('excluded') else row.get('value')

async def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, requests, http_errors, downloads = [], [], [], [], []
    def check(name, ok, detail=None):
        checks.append({'name': name, 'passed': bool(ok), 'detail': detail})
        if not ok:
            print('FAIL', name, detail, flush=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=args.browser or None, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000}, locale='ru-RU', timezone_id='Europe/Moscow', accept_downloads=True)
        page = await context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        page.on('request', lambda r: requests.append(r.url))
        page.on('response', lambda r: http_errors.append({'url': r.url, 'status': r.status}) if r.status >= 400 else None)
        async def get_json(path):
            return await published_json(context, args.base, path)
        stat = await get_json('data/projects/' + PROJECT + '/statistics.json')
        documentary = await get_json('data/projects/' + PROJECT + '/documentary.json')
        report = await get_json('data/projects/' + PROJECT + '/expertise.json')
        analytics = await get_json('data/projects/' + PROJECT + '/analytics.json')
        sources = {str(s['id']): s for s in stat['sources']}
        async def ready(name=None, state=None):
            await page.wait_for_function("document.querySelector('#main')?.dataset.ready==='true'||!!document.querySelector('.error-view')", timeout=45000)
            if await page.locator('.error-view').count():
                raise AssertionError(await page.locator('.error-view').inner_text())
            await page.wait_for_function('''([project,name,state])=>{
                const main=document.querySelector('#main');
                if(main?.dataset.project!==project||main.dataset.ready!=='true'||(name&&main.dataset.page!==name))return false;
                const actual=JSON.parse(document.querySelector('.infrastructure-page')?.dataset.routeState||'{}');
                return !state||Object.entries(state).every(([k,v])=>String(actual[k]??'')===String(v));
            }''', arg=[PROJECT, name, state])
        async def route(name, params=None):
            await page.goto(args.base + '#/projects/' + PROJECT + '/' + name + ('?' + urlencode(params) if params else ''), wait_until='domcontentloaded')
            await ready(name, params)
        async def choose(label, value, key):
            await page.get_by_label(label, exact=True).select_option(str(value))
            await ready(state={key: value})
        def panel(title):
            return page.locator('section.panel').filter(has=page.get_by_role('heading', name=title, exact=True))
        async def download(locator, kind='CSV'):
            await page.wait_for_timeout(1100)
            async with page.expect_download() as event:
                await locator.get_by_role('button', name=kind, exact=True).first.click()
            artifact = await event.value
            destination = output / artifact.suggested_filename
            await artifact.save_as(destination)
            data = destination.read_bytes()
            downloads.append({'name': destination.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            return data
        async def group(name, fn):
            try:
                await fn()
            except Exception as error:
                check(name, False, str(error))
        for name in PAGES:
            try:
                await route(name)
                text = await page.locator('#main').inner_text()
                check('desktop_content_' + name, len(text) > 350, {'characters': len(text), 'title': await page.title()})
                check('desktop_width_' + name, await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                check('no_authors_' + name, await page.locator('#sidebar a[href$="/authors"]').count() == 0)
                check('no_lazy_error_' + name, await page.locator('.infrastructure-load-error').count() == 0)
                if name in ['overview', 'targets', 'finance', 'network', 'texts', 'population', 'map', 'regions']:
                    await page.screenshot(path=str(output / (name + '-desktop.png')))
            except Exception as error:
                check('desktop_route_' + name, False, str(error))
        check('twelve_project_tabs', await page.locator('.project-tab').count() == 12)
        check('official_green_theme', await page.locator('html').evaluate("e=>e.style.getPropertyValue('--project-color')") == '#45B97C')
        check('full_text_not_eager', not any('/documentary-text/' in path or '/documentary_full.json' in path for path in requests))

        if not args.smoke_only:
            async def statistics_flow():
                for sid, source in sources.items():
                    await route('explorer', {'source': sid})
                    values = await page.locator('.infrastructure-page>.stats .stat strong').all_text_contents()
                    expected = len(source.get('national', []))
                    check('source_rows_' + sid, number(values[0]) == expected, {'expected': expected, 'actual': values[0]})
                    check('source_analytical_' + sid, number(values[1]) == sum(analytical(r) is not None for r in source.get('national', [])))
                    check('source_zeroes_' + sid, number(values[2]) == sum(analytical(r) == 0 for r in source.get('national', [])))
                    if sid in ['40466', '59263', '62882', '62872', '61608', '63457'] and expected:
                        data = csv_rows(await download(panel('Все наблюдения выбранного среза')))
                        check('source_csv_rows_' + sid, len(data) == expected)
                        check('source_csv_raw_' + sid, sum(number(r['Исходное число']) is not None for r in data) == sum(r.get('value') is not None for r in source.get('national', [])))
                        check('source_csv_excluded_' + sid, sum(r['Статус'] == 'Не используется в расчётах' for r in data) == sum(bool(r.get('excluded')) for r in source.get('national', [])))
                await route('explorer', {'source': '40466'})
                await choose('Территориальный уровень', 'regional', 'geography')
                await choose('Год', '2024', 'year')
                check('regional_explorer_has_rows', number((await page.locator('.infrastructure-page>.stats .stat strong').all_text_contents())[0]) > 0)
                territories = await page.get_by_label('Территория', exact=True).locator('option').evaluate_all('(xs)=>xs.filter(x=>x.value).map(x=>x.value)')
                if territories:
                    await choose('Территория', territories[0], 'r')
                    check('chosen_region_series', await page.locator('.chart-svg').count() > 0)
                await route('targets', {'source': '62872'})
                paths = await page.locator('path.data-line').get_attribute('d') if await page.locator('path.data-line').count() == 1 else None
                line_commands = await page.locator('path.data-line').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("d"))')
                check('methodology_break_not_joined', all('L' not in d for d in line_commands))
                await route('lab', {'tool': 'changes', 'source': '62872'})
                check('methodology_break_blocks_changes', 'Сопоставимых пар нет' in await page.locator('#main').inner_text())
            await group('statistics_flow', statistics_flow)

            async def geography_flow():
                await route('map', {'source': '40466'})
                check('map_renders', await page.locator('.map-surface').count() > 0)
                await page.locator('.map-surface').scroll_into_view_if_needed()
                await page.screenshot(path=str(output / 'map-detail-desktop.png'))
                await choose('Шкала карты', 'quartiles', 'scale')
                check('quartile_explanation', 'Границы квартилей' in await page.locator('#main').inner_text())
                options = await page.get_by_label('Регион', exact=True).locator('option').evaluate_all('(xs)=>xs.filter(x=>x.value).map(x=>x.value)')
                if options:
                    await choose('Регион', options[0], 'r')
                    check('map_region_readout', await page.locator('.region-reading').count() == 1)
                await route('regions', {'source': '40466'})
                matrix = analytics.get('correlations', {})
                if matrix.get('strict'):
                    check('strict_correlation_count', str(matrix['strict']['n']) in await panel('Многомерные территориальные связи').inner_text())
                    await choose('Совокупность корреляционной матрицы', 'author', 'correlationScope')
                    check('author_correlation_count', str(matrix['n']) in await panel('Многомерные территориальные связи').inner_text())
                data = await download(panel('Распределение выбранного показателя'), 'SVG')
                check('svg_source_and_title', b'<svg' in data and 'Инфраструктура для жизни'.encode() in data and 'ЕМИСС'.encode() in data)
            await group('geography_flow', geography_flow)

            async def finance_flow():
                for frame in ['passport_plan', 'budget_bill']:
                    await route('finance', {'frame': frame})
                    check('financial_rows_' + frame, await panel('Исходные финансовые строки').locator('tbody tr').count() > 0)
                    data = csv_rows(await download(panel('Исходные финансовые строки')))
                    check('financial_export_' + frame, len(data) > 10)
                    await choose('Год', '2027', 'year')
                    await choose('Федеральный проект', 'И7', 'fp')
                    rows = csv_rows(await download(panel('Исходные финансовые строки')))
                    check('financial_filter_' + frame, len(rows) >= 1 and all(r['Код'] == 'И7' and r['Год'] == '2027' for r in rows))
                    check('financial_not_execution_' + frame, 'кассов' in await page.locator('#main').inner_text())
                await route('finance', {'frame': 'passport_plan'})
                await choose('Источник средств', 'regional', 'finSource')
                check('source_filter_preserves_sums', 'Бюджеты регионов' in await page.locator('#main').inner_text())
                check('source_filter_has_numeric', await panel('Паспортное финансирование направлений').locator('rect[tabindex="0"]').count() > 0)
            await group('finance_flow', finance_flow)

            async def documentary_flow():
                for layer in ['shared', 'same_project', 'weights', 'semantic']:
                    await route('network', {'layer': layer})
                    check('network_layer_' + layer, await page.locator('.data-table tbody tr').count() > 0)
                    await choose('Федеральный проект', 'И2', 'fp')
                    check('network_filter_' + layer, 'И2' in await page.locator('#main').inner_text())
                for view in ['themes', 'terms', 'similarity', 'projects', 'audit']:
                    await route('texts', {'textview': view})
                    check('text_view_' + view, await page.locator('.data-table tbody tr').count() > 0)
                for variant in ['base', 'stemming', 'unigrams', 'equal_levels', 'federal_only', 'national_only']:
                    await route('texts', {'textview': 'projects', 'variant': variant})
                    check('text_variant_' + variant, await page.locator('.chart-svg').count() > 0)
                for document in documentary.get('text', {}).get('documents', []):
                    doc_id = document['document_id']
                    await route('texts', {'textview': 'contexts', 'doc': doc_id})
                    check('document_context_load_' + doc_id, await page.locator('.infrastructure-load-error').count() == 0)
                    check('document_context_source_' + doc_id, bool(await page.locator('.source-foot a').count()))
                await route('texts', {'textview': 'contexts', 'doc': 'np_18'})
                await panel('Контексты выбранного документа').scroll_into_view_if_needed()
                await page.screenshot(path=str(output / 'contexts-desktop.png'))
                await route('proposals')
                await choose('Этап рекомендаций', '0', 'stage')
                check('proposal_stage_filters', await panel('Последовательность внедрения').locator('tbody tr').count() == 1)
                await route('overview')
                await page.locator('.infrastructure-report>summary').click()
                check('original_report_expands', await page.locator('.infrastructure-report[open]').count() == 1)
            await group('documentary_flow', documentary_flow)

            async def calculators_flow():
                await route('lab', {'tool': 'housing'})
                for label, value in [('Площадь фонда до, млн м²', '100'), ('Население до, млн человек', '4'), ('Площадь фонда после, млн м²', '110'), ('Население после, млн человек', '3.5')]:
                    await page.get_by_label(label, exact=True).fill(value)
                await page.get_by_role('button', name='Рассчитать', exact=True).click()
                await ready(state={'stockBefore': '100', 'stockAfter': '110'})
                vals = await page.locator('.infrastructure-page>.stats .stat strong').all_text_contents()
                check('housing_ratio_before', number(vals[0]) == 25)
                check('housing_ratio_after', abs(number(vals[1]) - 110 / 3.5) < .0001)
                await route('lab', {'tool': 'accessibility'})
                await page.get_by_label('Порог времени, минут', exact=True).fill('30')
                await page.get_by_label('Территория; жителей; время пути, минут', exact=True).fill('А;100;10\nБ;900;31')
                await page.get_by_role('button', name='Рассчитать', exact=True).click()
                await ready(state={'threshold': '30'})
                check('accessibility_weighted_10', number(await page.locator('.infrastructure-page>.stats .stat strong').first.inner_text()) == 10)
                await route('lab', {'tool': 'lcc', 'initial': '100', 'annualOperating': '10', 'horizon': '2', 'discountPercent': '10', 'residual': '20', 'repairText': '1;10'})
                value = number(await page.locator('.infrastructure-page>.stats .stat strong').first.inner_text())
                check('lcc_discounted_cost', abs(value - (100 + 20 / 1.1 - 10 / 1.21)) < .0001)
                await route('lab', {'tool': 'lcc', 'initial': '100', 'annualOperating': '10', 'horizon': '0', 'discountPercent': '10', 'residual': '20'})
                check('invalid_lcc_rejected', await page.locator('.infrastructure-page>.stats').count() == 0)
                await route('projections', {'source': '40466', 'goal': '33', 'goalYear': '2030'})
                check('scenario_renders', await panel('Условный путь от факта к цели').locator('.chart-svg').count() == 1)
                check('scenario_no_forecast_claim', 'вероятность достижения не оценивается' in await page.locator('#main').inner_text())
            await group('calculators_flow', calculators_flow)

            async def library_flow():
                await route('library')
                urls = await page.locator('#main a[href]').evaluate_all('(xs)=>[...new Set(xs.map(x=>x.href).filter(h=>h.startsWith(location.origin)&&!h.includes("#")))]')
                for url in urls:
                    response = await context.request.get(url)
                    check('library_' + url.rsplit('/', 1)[-1], response.status == 200, {'status': response.status})
            await group('library_flow', library_flow)

            fault = await context.new_page()
            calls = {'n': 0}
            async def fail_once(route):
                calls['n'] += 1
                if calls['n'] == 1:
                    await route.fulfill(status=503, body='temporary test fault')
                else:
                    await route.continue_()
            path = sources['40466']['downloads']['observations'].lstrip('./')
            await fault.route('**/' + path + '*', fail_once)
            await fault.goto(args.base + '#/projects/' + PROJECT + '/explorer?source=40466&year=2024')
            await fault.locator('.infrastructure-load-error').wait_for()
            check('lazy_failure_retry_available', await fault.get_by_role('button', name='Повторить загрузку', exact=True).count() == 1)
            await fault.get_by_role('button', name='Повторить загрузку', exact=True).click()
            await fault.locator('.infrastructure-load-error').wait_for(state='detached')
            check('lazy_retry_preserves_year', await fault.get_by_label('Год', exact=True).input_value() == '2024')
            check('lazy_retry_refetches', calls['n'] == 2)
            await fault.close()

        for width in [390, 320]:
            await page.set_viewport_size({'width': width, 'height': 844})
            for name in PAGES:
                try:
                    await route(name)
                    check(f'mobile_width_{width}_{name}', await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                    check(f'mobile_content_{width}_{name}', len(await page.locator('#main').inner_text()) > 300)
                except Exception as error:
                    check(f'mobile_{width}_{name}', False, str(error))
            await route('overview')
            check('mobile_project_rail_' + str(width), await page.locator('.project-nav').evaluate('e=>e.scrollWidth>e.clientWidth'))
            await page.screenshot(path=str(output / f'overview-mobile-{width}.png'))
            await page.get_by_role('button', name='Открыть меню', exact=True).click()
            check('mobile_menu_' + str(width), await page.locator('body').evaluate("e=>e.classList.contains('nav-open')"))
            await page.locator('#sidebar a[data-route="finance"]').click()
            await ready('finance')
            check('mobile_menu_navigation_' + str(width), not await page.locator('body').evaluate("e=>e.classList.contains('nav-open')"))
            await page.wait_for_function("document.querySelector('#sidebar').getBoundingClientRect().right<=1")
            await page.screenshot(path=str(output / f'finance-mobile-{width}.png'))
            await route('texts', {'textview': 'contexts', 'doc': 'np_18'})
            await panel('Контексты выбранного документа').scroll_into_view_if_needed()
            check('mobile_context_width_' + str(width), await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
            await page.screenshot(path=str(output / f'contexts-mobile-{width}.png'))
        check('no_console_errors', not errors, errors)
        check('no_http_errors', not http_errors, http_errors)
        result = {'project_id': PROJECT, 'base': args.base, 'browser_plugin': 'not_available', 'fallback': 'Playwright', 'viewports': [[1440, 1000], [390, 844], [320, 844]], 'checks': checks, 'passed': sum(c['passed'] for c in checks), 'failed': sum(not c['passed'] for c in checks), 'errors': errors, 'http_errors': http_errors, 'downloads': downloads, 'screenshots': [p.name for p in output.glob('*.png')]}
        (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        await browser.close()
        print(json.dumps({'passed': result['passed'], 'failed': result['failed'], 'output': str(output)}, ensure_ascii=False), flush=True)
        if result['failed']:
            raise SystemExit(1)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser')
    parser.add_argument('--smoke-only', action='store_true')
    asyncio.run(run(parser.parse_args()))

if __name__ == '__main__':
    main()
