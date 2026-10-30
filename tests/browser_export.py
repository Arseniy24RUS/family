"""Export research acceptance on the full or compact Pages publication.

Run in CI through tests/run_browser.py with Playwright / Chromium. The suite
waits for the application render-ready state before testing the selected source,
period, frequency and downloaded rows. Source series use the application's data
transport, including gzip publication manifests under /family/.
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


PROJECT = 'international_export'
PAGES = ['overview', 'framework', 'logic', 'audit', 'targets', 'map', 'regions',
         'finance', 'network', 'texts', 'domains', 'causal', 'proposals',
         'projections', 'population', 'structure', 'methods', 'lab',
         'explorer', 'library', 'updates']
SOURCE_IDS = {str(x) for x in [62713, 62715, 62716, 62717, 62718, 62719, 62720,
                             62721, 62723, 62724, 62728, 62729, 62730, 62731,
                             62736, 62740, 62742, 63154]}


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
                const root = main?.querySelector('.international_export-page');
                if (!root || main.dataset.project !== 'international_export' ||
                    main.dataset.ready !== 'true' || main.hasAttribute('aria-busy') ||
                    (name && main.dataset.page !== name)) return false;
                const actual = JSON.parse(root.dataset.routeState || '{}');
                const query = Object.fromEntries(new URLSearchParams(location.hash.split('?')[1] || ''));
                const keys = new Set([...Object.keys(query), ...Object.keys(actual).filter(
                    key => !['nationalProject', 'page', 'mode'].includes(key))]);
                if ([...keys].some(key => String(actual[key] ?? '') !== String(query[key] ?? ''))) return false;
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

        async def csv_rows(container, key):
            async with page.expect_download() as event:
                await container.get_by_role('button', name='CSV', exact=True).first.click()
            artifact = await event.value
            destination = output / (key + '-' + Path(artifact.suggested_filename).name)
            await artifact.save_as(destination)
            payload = destination.read_bytes()
            rows = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig')), delimiter=';'))
            check('download_' + key, bool(rows) and destination.suffix.lower() == '.csv')
            downloads.append({'name': destination.name, 'bytes': len(payload),
                              'sha256': hashlib.sha256(payload).hexdigest(), 'rows': len(rows)})
            return rows

        for name in PAGES:
            async def route_check(name=name):
                await route(name)
                main = page.locator('main[data-ready="true"][data-project="international_export"]')
                check('route_' + name, await main.get_attribute('data-page') == name)
                check('heading_' + name, await main.locator('.page-heading h1').is_visible())
                check('content_' + name, await main.locator('.panel, .project-card, .note').count() > 0)
                check('title_' + name, 'Международная кооперация и экспорт' in await page.title())
                check('no_authors_' + name, await page.locator('#sidebar a[data-route="authors"]').count() == 0)
            await group('load_' + name, route_check)

        async def source_targets():
            statistics = await published_json(context, base, 'data/projects/international_export/statistics.json')
            source_ids = {str(source.get('source_id', source.get('id')))
                          for source in statistics['sources']}
            check('eighteen_source_contract', source_ids == SOURCE_IDS, sorted(source_ids))
            for source_id in sorted(SOURCE_IDS):
                await route('targets', {'source': source_id})
                picker = page.get_by_label('Показатель', exact=True)
                check('source_selected_' + source_id, await picker.input_value() == source_id)
                check('source_chart_' + source_id, await panel('Опубликованные значения').locator('svg.chart-svg').count() == 1)
                check('source_history_' + source_id, await panel('Исходные наблюдения').locator('tbody tr').count() > 0)
                check('source_link_' + source_id,
                      await page.locator('.international_export-source-note').get_by_role(
                          'link', name='ЕМИСС ' + source_id, exact=True).count() == 1)
            await page.screenshot(path=str(output / 'targets-desktop.png'))
        await group('source_targets', source_targets)

        async def frequency_and_export():
            await route('explorer')
            check('default_source_62715', await page.get_by_label('Показатель', exact=True).input_value() == '62715')
            rows = await csv_rows(panel('Наблюдения'), 'default-62715')
            check('default_source_csv_21', len(rows) == 21)
            check('pagination_twelve', await panel('Наблюдения').locator('tbody tr').count() == 12)
            await route('targets', {'source': '62713'})
            check('annual_preferred', await page.get_by_label('Режим статистического ряда').input_value() == 'annual')
            rows = await csv_rows(panel('Исходные наблюдения'), '62713-annual')
            check('annual_10_2', len(rows) == 1 and float(rows[0]['Значение']) == 10.2)
            await page.get_by_label('Режим статистического ряда').select_option('monthly')
            await ready('targets', {'source': '62713', 'series_basis': 'monthly'})
            rows = await csv_rows(panel('Исходные наблюдения'), '62713-december')
            check('december_0_5', len(rows) == 1 and float(rows[0]['Значение']) == 0.5)
            check('monthly_csv_label', all(r['Режим публикации'].startswith('Месячная') for r in rows))
            await page.go_back()
            await ready('targets', {'source': '62713', 'series_basis': ''})
            check('back_restores_annual', await page.get_by_label('Режим статистического ряда').input_value() == 'annual')
            await route('explorer', {'source': '62716', 'series_basis': 'monthly', 'period': '2025-12'})
            rows = await csv_rows(panel('Наблюдения'), '62716-monthly-period')
            check('period_frequency_filter_csv', len(rows) == 1 and float(rows[0]['Значение']) == 141.8)
            await route('explorer', {'source': '62716', 'series_basis': 'annual'})
            rows = await csv_rows(panel('Наблюдения'), '62716-annual')
            check('annual_friendly_141_59', len(rows) == 1 and float(rows[0]['Значение']) == 141.59)
        await group('frequency_and_export', frequency_and_export)

        async def geography_controls():
            await route('map', {'context': 'services', 'year': '2025', 'measure': 'share'})
            check('all_89_map_territories', await panel('Территориальное распределение').locator('.region').count() == 89)
            check('four_missing_territories', await panel('Территориальное распределение').locator('.region[aria-label$="нет данных"]').count() == 4)
            rows = await csv_rows(panel('Территориальное распределение'), 'services-share')
            check('services_85_rows', len(rows) == 85)
            check('selected_share_exported', all(r['measure'] == 'share' and r['unit'] == '% национального итога' for r in rows))
            moscow = next(r for r in rows if r['territory'] in ('Москва', 'г. Москва'))
            check('moscow_national_share', abs(float(moscow['value']) - 45.9146) < .0001)
            await page.get_by_label('Представление', exact=True).select_option('tiles')
            await ready('map', {'view': 'tiles'})
            await panel('Территориальное распределение').locator('.region[data-region="90"]').click()
            await ready('map', {'region': '90'})
            check('missing_profile_explicit', 'нет наблюдения' in await panel('Профиль территории').inner_text())
            check('missing_profile_not_substituted', await panel('Профиль территории').locator('.stat').count() == 0)
            await page.get_by_label('Показатель', exact=True).select_option('growth')
            await ready('map', {'measure': 'growth'})
            rows = await csv_rows(panel('Территориальное распределение'), 'services-growth')
            check('growth_uses_same_85_regions', len(rows) == 85 and all(r['measure'] == 'growth' for r in rows))
            await page.screenshot(path=str(output / 'geography-desktop.png'))
        await group('geography_controls', geography_controls)

        async def network_and_text():
            await route('network', {'evidence': 'lexical', 'threshold': '0.05', 'network_view': 'matrix'})
            rows = await csv_rows(panel('Связи результатов и показателей'), 'lexical-threshold-005')
            check('threshold_005_computed_28', len(rows) == 28)
            check('matrix_47_by_18', await panel('Матрица выбранных связей').locator('svg rect[tabindex]').count() == 846)
            check('author_difference_visible', 'в докладе – 26' in await page.locator('main').inner_text())
            await route('texts')
            query = page.get_by_label('Поиск по документам', exact=True)
            await query.fill('___NO_MATCH___')
            check('no_match_search', 'Фрагментов: 0' in await page.locator('.international_export-text-results').inner_text())
            await query.fill('экспорт')
            check('search_real_profiles', await page.locator('.international_export-text-fragment').count() > 0)
            await page.get_by_label('Строки лексической матрицы').select_option('М3')
            await ready('texts', {'matrix_fp': 'М3'})
            check('matrix_fp_filter', await panel('Лексическая матрица результатов и показателей').locator('svg rect[tabindex]').count() == 23 * 18)
            check('federal_similarity_4_by_4', await panel('Близость четырёх федеральных направлений').locator('svg rect[tabindex]').count() == 16)
        await group('network_and_text', network_and_text)

        async def calculator_flow():
            for kind, values, expected in [('paid_shipments', [100, 200, 100, 0, 0, 0], 50),
                                           ('additional_export', [80, 100, 10], -2),
                                           ('did', [10, 15, 8, 10], 3)]:
                await route('lab', {'calculator': kind})
                calculator = page.locator('.international_export-calculator')
                fields = calculator.locator('input')
                result = calculator.locator('.international_export-calculation-output strong')
                check('calculator_blank_' + kind, await result.count() == 0)
                for i, value in enumerate(values):
                    await fields.nth(i).fill(str(value))
                rendered = (await result.inner_text()).split(' ', 1)[0].replace(',', '.')
                check('calculator_value_' + kind, abs(float(rendered) - expected) < 1e-8)
                await fields.nth(0).fill('')
                check('calculator_missing_' + kind, await result.count() == 0)
                if kind == 'additional_export':
                    await fields.nth(0).fill('80')
                    await fields.nth(1).fill('')
                    check('counterfactual_required', await result.count() == 0)
        await group('calculator_flow', calculator_flow)

        for width in [390, 320]:
            async def mobile_navigation(width=width):
                await page.set_viewport_size({'width': width, 'height': 844})
                await route('overview')
                rail = page.locator('.project-nav')
                check('mobile_rail_overflows_' + str(width), await rail.evaluate('e => e.scrollWidth > e.clientWidth'))
                await rail.evaluate('e => { e.scrollLeft = e.scrollWidth; }')
                check('mobile_rail_scrolls_' + str(width), await rail.evaluate('e => e.scrollLeft > 0'))
                check('mobile_active_project_' + str(width),
                      await rail.locator('.project-tab[data-project="international_export"]').get_attribute('aria-current') == 'true')
                check('mobile_page_width_' + str(width), await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'))
                menu = page.get_by_role('button', name='Открыть меню', exact=True)
                await menu.click()
                check('mobile_menu_opens_' + str(width), await menu.get_attribute('aria-expanded') == 'true')
                await page.locator('#sidebar a[data-route="map"]').click()
                await ready('map')
                check('mobile_menu_closes_' + str(width), await menu.get_attribute('aria-expanded') == 'false')
                check('mobile_map_width_' + str(width), await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'))
                await page.screenshot(path=str(output / ('map-mobile-' + str(width) + '.png')))
            await group('mobile_navigation_' + str(width), mobile_navigation)

        check('no_page_errors', not page_errors, page_errors)
        check('no_console_errors', not console_errors, console_errors)
        check('no_http_errors', not http_errors, http_errors)
        result = {'project_id': PROJECT, 'base': base, 'runner': 'Playwright Chromium',
                  'scope': 'all_routes_and_sources_with_frequency_geography_export_interactions',
                  'viewports': [[1440, 1000], [390, 844], [320, 844]],
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
                        help='Accepted for CLI parity; Export always runs this bounded smoke suite.')
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
