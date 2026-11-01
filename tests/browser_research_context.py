"""HTTP acceptance of the shared research context across independent projects.

The expected windows below describe the published observations explicitly. They
are not derived with the application's context adapter. Values are read from the
published source files, including the verified gzip transport used on Pages.
"""
import argparse
import asyncio
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlencode, urlsplit

from playwright.async_api import async_playwright, expect
from browser_json import get_json as published_json


CONTEXT_KEYS = ['ctx_region', 'ctx_start', 'ctx_end', 'ctx_kind', 'ctx_frequency']
TOURISM = {'ctx_region': '77', 'ctx_start': '2026-01-01', 'ctx_end': '2026-09-30',
           'ctx_kind': 'cumulative_ytd', 'ctx_frequency': 'monthly'}
FAMILY = {'ctx_region': '77', 'ctx_start': '2026-09-01', 'ctx_end': '2026-09-30',
          'ctx_kind': 'monthly', 'ctx_frequency': 'monthly'}
HEALTH = {'ctx_region': '77', 'ctx_start': '2026-07-31', 'ctx_end': '2026-07-31',
          'ctx_kind': 'stock_at_period_end', 'ctx_frequency': 'monthly'}
PERSONNEL = {'ctx_region': '77', 'ctx_start': '2024-01-01', 'ctx_end': '2024-12-31',
             'ctx_kind': 'annual', 'ctx_frequency': 'annual'}


def query(url):
    return {key: values[-1] for key, values in
            parse_qs(urlsplit(url).fragment.partition('?')[2], keep_blank_values=True).items()}


def carried_context(url):
    state = query(url)
    return {key: state[key] for key in CONTEXT_KEYS if key in state}


def numeric_text(text):
    return float(re.sub(r'[^\d,.−-]', '', text).replace('−', '-').replace(',', '.'))


def one(rows, **fields):
    matches = [row for row in rows if all(str(row.get(key, '')) == str(value)
                                         for key, value in fields.items())]
    assert len(matches) == 1, {'source_selection': fields, 'matches': len(matches)}
    return matches[0]


async def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    base = args.base.rstrip('/') + '/'
    checks, errors, console_errors, http_errors = [], [], [], []

    def check(name, condition, detail=None):
        checks.append({'name': name, 'passed': bool(condition), 'detail': detail})
        if not condition:
            print('FAIL', name, detail, flush=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=args.browser or None,
                                           args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000},
                                             locale='ru-RU', timezone_id='Europe/Moscow',
                                             reduced_motion='reduce')
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: console_errors.append(message.text)
                if message.type == 'error' else None)
        page.on('response', lambda response: http_errors.append(
            {'url': response.url, 'status': response.status}) if response.status >= 400 else None)

        manifest, health, personnel, tourism = await asyncio.gather(
            published_json(context, base, 'data/latest/manifest.json'),
            published_json(context, base, 'data/projects/long_active_life/series/62971.json'),
            published_json(context, base, 'data/projects/personnel/context.json'),
            published_json(context, base, 'data/projects/tourism/series/62900.json'))
        family_path = next(source['published_file'] for source in manifest['sources']
                           if source['source_id'] == 'data_21')
        family_packet = await published_json(context, base, family_path)
        family_rows = [dict(zip(family_packet['columns'], values)) for values in family_packet['rows']]

        def shared_region():
            return page.get_by_label('Территория исследования', exact=True)

        def shared_period():
            return page.get_by_label('Доступный период исследования', exact=True)

        def panel(title):
            return page.locator('#main section.panel').filter(
                has=page.get_by_role('heading', name=title, exact=True))

        async def ready(project, route='map', status=None, expected=None, native_period=None):
            await page.wait_for_function('''([project, route, status, expected, nativePeriod]) => {
                if (document.querySelector('.error-view')) return true;
                const main = document.querySelector('#main');
                const bar = document.querySelector('.research-context');
                if (main?.dataset.ready !== 'true' || main.hasAttribute('aria-busy') ||
                    main.dataset.project !== project || main.dataset.page !== route || !bar ||
                    (status && bar.dataset.contextStatus !== status)) return false;
                const values = new URLSearchParams(location.hash.split('?')[1] || '');
                if (expected && Object.entries(expected).some(([key, value]) => values.get(key) !== value)) return false;
                return !nativePeriod || document.querySelector('[aria-label="Доступный период исследования"]')?.value === nativePeriod;
            }''', arg=[project, route, status, expected, native_period], timeout=60000)
            if await page.locator('.error-view').count():
                raise AssertionError(await page.locator('.error-view').inner_text())

        async def go(project, route='map', params=None, status=None, expected=None):
            path = '/' + route if project == 'family' else '/projects/' + project + '/' + route
            await page.goto(base + '#' + path + ('?' + urlencode(params) if params else ''),
                            wait_until='domcontentloaded')
            await ready(project, route, status, expected)

        async def group(name, action):
            try:
                await action()
            except Exception as error:
                check(name, False, str(error))
                await page.screenshot(path=str(output / (name + '-failure.png')))

        async def screenshot(name):
            await page.locator('.research-context').scroll_into_view_if_needed()
            await page.screenshot(path=str(output / name))

        async def check_context(name, expected):
            actual = carried_context(page.url)
            check(name, actual == expected and await shared_region().input_value() == expected['ctx_region'],
                  {'expected': expected, 'actual': actual, 'url': page.url})

        async def check_empty(name, heading='За выбранный период данных нет'):
            check(name, await page.get_by_role('heading', name=heading, exact=True).is_visible()
                  and await page.locator('.research-context-empty').count() == 1
                  and await page.locator('#main .map-surface, #main .region-reading').count() == 0)

        async def check_value(name, expected, table_title=None):
            shown = numeric_text(await page.locator('.region-reading strong').first.inner_text())
            mark = page.locator('.map-surface .region[data-region="' + query(page.url)['ctx_region'] + '"]')
            check(name + '_map', abs(shown - expected) < .000051 and
                  await mark.count() > 0 and await mark.first.get_attribute('fill') != 'url(#missing)',
                  {'expected': expected, 'shown': shown})
            if table_title:
                table = panel(table_title)
                await table.get_by_label('Поиск по таблице', exact=True).fill('Москва')
                await expect(table.locator('tbody tr')).to_have_count(1)
                shown = numeric_text(await table.locator('tbody tr td.num').first.inner_text())
                check(name + '_table', abs(shown - expected) < .000051,
                      {'expected': expected, 'shown': shown})

        cases = [
            ('family', 'месяц|2026-09-30', FAMILY,
             float(one(family_rows, r='77', type='месяц', end='2026-09-30')['value']),
             'Все региональные значения'),
            ('long_active_life', 'monthly|2026-07-31|', HEALTH,
             float(one(health['observations'], map_id='77', frequency='monthly', period_end='2026-07-31')['analytical_value']),
             'Наблюдения выбранных регионов'),
            ('personnel', 'annual|2024-12-31', PERSONNEL,
             float(one(personnel['regions'], map_id='77')['analytical_value']),
             'Наблюдения выбранных регионов')]
        for project, native_period, expected, value, table_title in cases:
            async def cross_project_period(project=project, native_period=native_period,
                                           expected=expected, value=value, table_title=table_title):
                await go('tourism', params={'region': '77', 'regions': '77', 'period': '2026-09-30', 'view': 'tiles'},
                         status='available', expected=TOURISM)
                if project == 'family':
                    shown = numeric_text(await page.locator('.v3-profile-metrics strong').first.inner_text())
                    original = float(one(tourism['observations'], map_id='77', period_end='2026-09-30')['value'])
                    check('tourism_original_cumulative_value', abs(shown - original) < .000051)
                await page.locator('.project-tab[data-project="' + project + '"]').click()
                await ready(project, status='unavailable', expected=TOURISM)
                await check_context(project + '_carried_window_unchanged', TOURISM)
                check(project + '_local_parameters_do_not_cross',
                      not {'source', 'period', 'edition', 'regions'}.intersection(query(page.url)))
                await check_empty(project + '_no_silent_period_substitution')
                await screenshot('context-' + project + '-unavailable.png')
                await shared_period().select_option(native_period)
                await ready(project, status='available', expected=expected, native_period=native_period)
                await check_context(project + '_explicit_period_applies', expected)
                await check_value(project + '_source_value', value, table_title)
                await screenshot('context-' + project + '-available.png')
            await group('cross_project_' + project, cross_project_period)

        async def compatible_source_keeps_the_requested_window():
            compatible = await published_json(context, base, 'data/projects/long_active_life/series/62930.json')
            original = one(compatible['observations'], map_id='77', frequency='monthly', period_end='2026-09-30')
            check('compatible_source_has_cumulative_semantics', original['period_semantics'] == 'cumulative_ytd'
                  and original['measurement_window_start'] == TOURISM['ctx_start'])
            await go('tourism', params={'region': '77', 'period': '2026-09-30'},
                     status='available', expected=TOURISM)
            await page.locator('.project-tab[data-project="long_active_life"]').click()
            await ready('long_active_life', status='unavailable', expected=TOURISM)
            await page.get_by_label('Показатель для выбранного периода', exact=True).select_option('62930')
            await ready('long_active_life', status='available', expected=TOURISM,
                        native_period='monthly|2026-09-30|')
            await check_context('source_change_keeps_the_requested_window', TOURISM)
            check('source_change_selects_requested_indicator',
                  await page.get_by_label('Показатель', exact=True).input_value() == '62930')
            await check_value('same_window_in_health', float(original['analytical_value']),
                              'Наблюдения выбранных регионов')
            await screenshot('context-compatible-health-source.png')
        await group('compatible_source_keeps_the_requested_window', compatible_source_keeps_the_requested_window)

        async def navigation_and_history():
            await go('family', params={**FAMILY, 'source': 'data_21'}, status='available', expected=FAMILY)
            await page.locator('#sidebar a[data-route="regions"]').click()
            await ready('family', 'regions', 'outside', FAMILY)
            await check_context('regional_analysis_preserves_context', FAMILY)
            scope = (await page.locator('.research-context-scope').inner_text()).lower()
            check('multiperiod_analysis_discloses_scope', 'период' in scope and 'не применяется' in scope
                  and await page.locator('.research-context-empty').count() == 0)
            await screenshot('context-regional-analysis-outside.png')
            await page.locator('#sidebar a[data-route="map"]').click()
            await ready('family', status='available', expected=FAMILY)
            await check_context('sidebar_returns_to_exact_map_window', FAMILY)
            await page.go_back()
            await ready('family', 'regions', 'outside', FAMILY)
            await page.go_back()
            await ready('family', status='available', expected=FAMILY)
            await page.reload()
            await ready('family', status='available', expected=FAMILY)
            await check_context('back_and_refresh_restore_window_and_region', FAMILY)
            await check_value('restored_family_value', float(one(family_rows, r='77', type='месяц', end='2026-09-30')['value']))
            await page.locator('.project-tab[data-project="youth_children"]').click()
            await ready('youth_children', status='outside', expected=FAMILY)
            await check_context('unsupported_project_keeps_request', FAMILY)
            check('unsupported_project_scope_is_explicit',
                  bool((await page.locator('.research-context-scope').inner_text()).strip()) and
                  await page.locator('.research-context-empty').count() == 0)
            await page.locator('.project-tab[data-project="family"]').click()
            await ready('family', status='available', expected=FAMILY)
            await check_context('supported_project_reapplies_request', FAMILY)
        await group('navigation_and_history', navigation_and_history)

        async def all_regions_survives_navigation():
            all_regions = {**FAMILY, 'ctx_region': 'all'}

            async def verify_all_regions(name):
                check(name, carried_context(page.url) == all_regions and
                      await shared_region().input_value() == '' and
                      await page.locator('#main .region-reading, #main .selected-explanation, '
                                         '#main .v3-profile, #main .v3-chip, '
                                         '#main .map-surface .region[aria-pressed="true"]').count() == 0,
                      {'context': carried_context(page.url), 'url': page.url})

            await go('family', params={**FAMILY, 'source': 'data_21'}, status='available', expected=FAMILY)
            await expect(page.locator('.region-reading')).to_have_count(1)
            await shared_region().select_option('')
            await ready('family', status='available', expected=all_regions)
            await verify_all_regions('clearing_region_removes_profile_and_selection')
            await page.locator('#sidebar a[data-route="regions"]').click()
            await ready('family', 'regions', 'outside', all_regions)
            await verify_all_regions('all_regions_survives_sidebar')
            await page.locator('.project-tab[data-project="tourism"]').click()
            await ready('tourism', 'regions', 'unavailable', all_regions)
            await verify_all_regions('all_regions_does_not_restore_tourism_defaults')
            await page.go_back()
            await ready('family', 'regions', 'outside', all_regions)
            await page.locator('#sidebar a[data-route="map"]').click()
            await ready('family', status='available', expected=all_regions)
            await verify_all_regions('all_regions_survives_back_and_return_to_map')
            await screenshot('context-all-regions-after-navigation.png')
        await group('all_regions_survives_navigation', all_regions_survives_navigation)

        async def annual_is_not_december_cumulative():
            cumulative = {**TOURISM, 'ctx_start': '2025-01-01', 'ctx_end': '2025-12-31'}
            annual = {**cumulative, 'ctx_kind': 'annual', 'ctx_frequency': 'annual'}
            await go('tourism', params={'region': '77', 'period': '2025-12-31'},
                     status='available', expected=cumulative)
            await page.locator('.project-tab[data-project="family"]').click()
            await ready('family', status='unavailable', expected=cumulative)
            await check_empty('december_cumulative_is_not_annual')
            check('annual_record_is_offered_as_distinct_choice',
                  await shared_period().locator('option[value="год|2025-12-31"]').count() == 1)
            await shared_period().select_option('год|2025-12-31')
            await ready('family', status='available', expected=annual, native_period='год|2025-12-31')
            await check_context('annual_choice_changes_semantics', annual)
            await check_value('annual_family_value', float(one(family_rows, r='77', type='год', end='2025-12-31')['value']))
            await page.locator('.project-tab[data-project="tourism"]').click()
            await ready('tourism', status='unavailable', expected=annual)
            await check_empty('annual_is_not_tourism_december_cumulative')
            await shared_period().select_option('2025-12-31')
            await ready('tourism', status='available', expected=cumulative, native_period='2025-12-31')
            await check_context('explicit_cumulative_choice_restores_tourism', cumulative)
        await group('annual_is_not_december_cumulative', annual_is_not_december_cumulative)

        async def invalid_context():
            invalid = {**FAMILY, 'ctx_start': '2026-02-30'}
            await go('family', params={**invalid, 'source': 'data_21'}, status='invalid', expected=invalid)
            await check_context('invalid_date_kept_in_request', invalid)
            await check_empty('invalid_date_does_not_render_default_map', 'Период указан некорректно')
            await screenshot('context-invalid-request.png')
            await page.reload()
            await ready('family', status='invalid', expected=invalid)
            await check_empty('invalid_request_survives_refresh_without_fallback', 'Период указан некорректно')
            await shared_period().select_option('месяц|2026-09-30')
            await ready('family', status='available', expected=FAMILY, native_period='месяц|2026-09-30')
            await check_context('explicit_period_repairs_invalid_request', FAMILY)
            await go('family', params={'r': '77', 'source': 'data_21', 'period': 'месяц|2030-01-31'}, status='unavailable')
            check('invalid_native_period_remains_requested', query(page.url).get('period') == 'месяц|2030-01-31')
            await check_empty('invalid_native_period_has_no_latest_fallback')
        await group('invalid_context', invalid_context)

        for width in [390, 320]:
            async def mobile_context(width=width):
                await page.set_viewport_size({'width': width, 'height': 844})
                await go('family', params=TOURISM, status='unavailable', expected=TOURISM)
                await screenshot('context-empty-mobile-' + str(width) + '.png')
                bar = page.locator('.research-context')
                boxes = await bar.locator('select').evaluate_all(
                    '(nodes) => nodes.map(node => ({left: node.getBoundingClientRect().left, right: node.getBoundingClientRect().right}))')
                check('context_controls_fit_' + str(width), bool(boxes) and
                      all(box['left'] >= 0 and box['right'] <= width + 1 for box in boxes), boxes)
                await shared_region().focus()
                await shared_region().select_option('23')
                carried = {**TOURISM, 'ctx_region': '23'}
                await ready('family', status='unavailable', expected=carried)
                await expect(shared_region()).to_be_focused()
                await check_context('mobile_region_focus_and_context_' + str(width), carried)
                await shared_period().focus()
                await shared_period().select_option('месяц|2026-09-30')
                selected = {**FAMILY, 'ctx_region': '23'}
                await ready('family', status='available', expected=selected, native_period='месяц|2026-09-30')
                await expect(shared_period()).to_be_focused()
                await check_context('mobile_period_focus_and_context_' + str(width), selected)
                await check_value('mobile_selected_value_' + str(width),
                                  float(one(family_rows, r='23', type='месяц', end='2026-09-30')['value']))
                check('context_page_width_' + str(width),
                      await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'))
                await screenshot('context-selected-mobile-' + str(width) + '.png')
            await group('mobile_context_' + str(width), mobile_context)

        check('no_page_errors', not errors, errors)
        check('no_console_errors', not console_errors, console_errors)
        check('no_http_errors', not http_errors, http_errors)
        result = {'suite': 'research_context', 'base': base, 'runner': 'Playwright Chromium',
                  'checks': checks, 'passed': sum(item['passed'] for item in checks),
                  'failed': sum(not item['passed'] for item in checks), 'page_errors': errors,
                  'console_errors': console_errors, 'http_errors': http_errors,
                  'screenshots': [path.name for path in output.glob('*.png')]}
        (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        await browser.close()
        print(json.dumps({'passed': result['passed'], 'failed': result['failed'], 'output': str(output)}), flush=True)
        if result['failed']:
            raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser')
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
