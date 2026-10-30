"""HTTP smoke acceptance for Tourism, including the /family/ Pages subpath.

Run by tests/run_browser.py in CI with Playwright / Chromium. This suite covers
all research routes and a small set of real user interactions. Series are read
through the application, so both the full site and the gzip publication view
exercise the same UI contract.
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


PROJECT = 'tourism'
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
