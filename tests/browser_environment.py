"""HTTP acceptance for the Environmental Wellbeing project.

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

PROJECT = 'environment'
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
                const actual=JSON.parse(document.querySelector('.environment-page')?.dataset.routeState||'{}');
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
                check('no_lazy_error_' + name, await page.locator('.environment-load-error').count() == 0)
                if name in ['overview', 'targets', 'finance', 'network', 'texts', 'population', 'map', 'regions']:
                    await page.screenshot(path=str(output / (name + '-desktop.png')))
            except Exception as error:
                check('desktop_route_' + name, False, str(error))
        check('twelve_project_tabs', await page.locator('.project-tab').count() == 12)
        check('official_green_theme', await page.locator('html').evaluate("e=>e.style.getPropertyValue('--project-color')") == '#87C879')
        check('full_text_not_eager', not any('/documentary-text/' in path or '/documentary_full.json' in path for path in requests))

        if not args.smoke_only:

            async def statistics_flow():
                for sid, source in sources.items():
                    await route('explorer', {'source': sid})
                    values = await page.locator('.environment-page>.stats .stat strong').all_text_contents()
                    expected = len(source.get('national', []))
                    check('source_rows_' + sid, number(values[0]) == expected, {'expected': expected, 'actual': values[0]})
                    check('source_analytical_' + sid, number(values[1]) == sum(analytical(r) is not None for r in source.get('national', [])))
                    check('source_zeroes_' + sid, number(values[2]) == sum(analytical(r) == 0 for r in source.get('national', [])))
                    if sid in ['62792', '62793', '62781', '62787', '62862', '62863', '62779', '62777'] and expected:
                        data = csv_rows(await download(panel('Все наблюдения выбранного среза')))
                        check('source_csv_rows_' + sid, len(data) == expected)
                        check('source_csv_raw_' + sid, sum(number(r['Исходное число']) is not None for r in data) == sum(r.get('value') is not None for r in source.get('national', [])))
                        check('source_csv_excluded_' + sid, sum(r['Статус ячейки'] == 'Не используется в расчётах' for r in data) == sum(bool(r.get('excluded')) for r in source.get('national', [])))
                        check('source_csv_original_not_blank_' + sid, all(r['Исходная запись'] != '' for r in data if number(r['Исходное число']) is not None))
                await route('explorer', {'source': '62792'})
                await choose('Территориальный уровень', 'regional', 'geography')
                await choose('Год', '2025', 'year')
                await choose('Периодичность', 'annual', 'frequency')
                check('regional_explorer_has_85_annual_rows', number((await page.locator('.environment-page>.stats .stat strong').all_text_contents())[0]) == 85)
                await choose('Территория', '79', 'r')
                check('EAO_original_zero_retained', number((await page.locator('.environment-page>.stats .stat strong').all_text_contents())[2]) == 1)
                await route('explorer', {'source': '62793', 'geography': 'regional'})
                full = (await get_json(sources['62793']['downloads']['observations']))['observations']
                expected = [r for r in full if r['geo_level'] == 'regional']
                data = csv_rows(await download(panel('Все наблюдения выбранного среза')))
                check('regional_TKO_all_rows_preserved', len(data) == len(expected))
                check('regional_TKO_excluded_raw_values_preserved', sum(r['Статус ячейки'] == 'Не используется в расчётах' for r in data) == sum(bool(r.get('excluded')) for r in expected))
                check('regional_TKO_flags_exported', all(r['Проверка качества'] for r in data if r['Статус ячейки'] == 'Не используется в расчётах'))
                for sid, count in [('62862', 12), ('62863', 29)]:
                    await route('explorer', {'source': sid, 'geography': 'project_territory', 'year': '2025', 'frequency': 'annual'})
                    values = await page.locator('.environment-page>.stats .stat strong').all_text_contents()
                    check('air_annual_participant_count_' + sid, number(values[0]) == count and number(values[1]) == count)
                    data = csv_rows(await download(panel('Все наблюдения выбранного среза')))
                    check('air_export_separate_geolevel_' + sid, len(data) == count and all(r['Уровень'] == 'project_territory' for r in data))
                for sid in ['62787', '62804']:
                    await route('targets', {'source': sid})
                    line_commands = await page.locator('path.data-line').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("d"))')
                    check('methodology_break_not_joined_' + sid, all('L' not in d for d in line_commands))
                    await route('lab', {'tool': 'changes', 'source': sid})
                    check('methodology_break_blocks_changes_' + sid, 'Сопоставимых пар нет' in await page.locator('#main').inner_text())
                await route('targets', {'source': '62779'})
                check('retired_status_visible', 'Исполнение показателя прекращено' in await page.locator('#main').inner_text())
                check('retired_no_target_attainment', await panel('Проверенные сопоставления с планом').count() == 0)
                await route('targets', {'source': '62781'})
                data = csv_rows(await download(panel('Исходные и аналитические значения')))
                check('forest_ratio_above_100_not_clamped', any(number(r['Для анализа']) is not None and number(r['Для анализа']) > 100 for r in data))
                await route('explorer', {'source': '62782'})
                check('program_accumulation_label', 'Накопление программы с 2025 года' in await page.locator('#main').inner_text())
            await group('statistics_flow', statistics_flow)


            async def geography_flow():
                await route('map', {'source': '62792'})
                check('map_renders', await page.locator('.map-surface').count() > 0)
                await page.locator('.map-surface').scroll_into_view_if_needed()
                await page.screenshot(path=str(output / 'map-detail-desktop.png'))
                selected_slice = await page.get_by_label('Срез наблюдений', exact=True).input_value()
                check('map_defaults_independent_annual_2025', selected_slice.startswith('annual|2025-12-31|'))
                await choose('Шкала карты', 'quartiles', 'scale')
                check('quartile_explanation', 'Границы квартилей' in await page.locator('#main').inner_text())
                options = await page.get_by_label('Регион', exact=True).locator('option').evaluate_all('(xs)=>xs.filter(x=>x.value).map(x=>x.value)')
                if options:
                    await choose('Регион', options[0], 'r')
                    check('map_region_readout', await page.locator('.region-reading').count() == 1)
                await route('regions', {'source': '62792'})
                matrix = analytics['correlations']
                target = panel('Обработка и захоронение ТКО: проверка чувствительности')
                values = await target.locator('.stats .stat strong').all_text_contents()
                check('waste_correlation_main_85', number(values[0]) == matrix['n'])
                check('waste_correlation_main_rho', abs(number(values[1]) - matrix['matrix'][0][1]) < .0001)
                data = csv_rows(await download(target.locator('.data-table').first))
                check('waste_main_csv_all_pairs', len(data) == 85)
                check('waste_main_csv_EAO_zero', any('Еврейская' in r['Регион'] and number(r['Обработка, %']) == 0 and number(r['Захоронение, %']) == 0 for r in data))
                await target.scroll_into_view_if_needed()
                await page.screenshot(path=str(output / 'waste-scatter-desktop.png'))
                await choose('Состав проверки', 'sensitivity', 'correlationScope')
                values = await target.locator('.stats .stat strong').all_text_contents()
                check('waste_sensitivity_84', number(values[0]) == 84)
                check('waste_sensitivity_rho', abs(number(values[1]) - matrix['sensitivity']['matrix'][0][1]) < .0001)
                data = csv_rows(await download(target.locator('.data-table').first))
                check('waste_sensitivity_only_EAO_excluded', len(data) == 84 and not any('Еврейская' in r['Регион'] for r in data))
                svg = await download(panel('Распределение выбранного показателя'), 'SVG')
                check('svg_source_and_title', b'<svg' in svg and 'Экологическое благополучие'.encode() in svg and 'ЕМИСС'.encode() in svg)
                check('waste_not_complement_explanation', 'дополнениями до 100%' in await page.locator('#main').inner_text())
                for group in analytics['air_groups']:
                    sid = group['source_id']
                    await route('population', {'airSource': sid, 'airPeriod': 'annual'})
                    values = await page.locator('.environment-page>.stats .stat strong').all_text_contents()
                    check('air_own_baseline_' + sid, str(group['baseline_year']) in await page.locator('#main').inner_text())
                    check('air_published_national_' + sid, abs(number(values[1]) - group['annual']['national_value']) < .0001)
                    check('air_unweighted_mean_' + sid, abs(number(values[2]) - group['annual']['unweighted_mean']) < .000001)
                    data = csv_rows(await download(panel('Проектные территории и исходные значения')))
                    check('air_participant_csv_' + sid, len(data) == group['expected_territories'])
                    check('air_reduction_identity_' + sid, all(abs(number(r['Остаточный индекс, %']) + number(r['Сокращение к своей базе, %']) - 100) < .0001 for r in data))
                    await panel(group['title']).scroll_into_view_if_needed()
                    await page.screenshot(path=str(output / ('air-' + sid + '-desktop.png')))
                    await choose('Чтение шкалы', 'reduction', 'airMeasure')
                    check('air_reduction_chart_' + sid, await panel(group['title']).locator('.chart-svg').count() == 1)
                    await choose('Период сравнения', 'latest', 'airPeriod')
                    values = await page.locator('.environment-page>.stats .stat strong').all_text_contents()
                    check('air_latest_no_carried_values_' + sid, values[0].startswith('0 /'))
                    check('air_latest_national_preserved_' + sid, abs(number(values[1]) - group['latest']['national_value']) < .0001)
                    check('air_latest_empty_chart_' + sid, await panel(group['title']).locator('.chart-svg').count() == 0)
                    data = csv_rows(await download(panel('Проектные территории и исходные значения')))
                    check('air_latest_csv_missing_' + sid, len(data) == group['expected_territories'] and all(number(r['Остаточный индекс, %']) is None for r in data))
            await group('geography_flow', geography_flow)


            async def finance_flow():
                for frame in ['passport_plan', 'budget_bill']:
                    await route('finance', {'frame': frame})
                    data = csv_rows(await download(panel('Исходные финансовые строки')))
                    expected = next(f['rows'] for f in documentary['finance']['frames'] if f['id'] == frame)
                    check('financial_export_count_' + frame, len(data) == len(expected))
                    check('financial_export_sum_' + frame, abs(sum(number(r['Сумма']) or 0 for r in data) - sum(r['value'] or 0 for r in expected)) < .001)
                    check('financial_export_unit_' + frame, all(r['Единица'] == ('тыс. руб.' if frame == 'passport_plan' else 'млн руб.') for r in data))
                    await choose('Год', '2027', 'year')
                    await choose('Федеральный проект', 'Ч2', 'fp')
                    rows = csv_rows(await download(panel('Исходные финансовые строки')))
                    check('financial_filter_' + frame, len(rows) >= 1 and all(r['Код'] == 'Ч2' and r['Год'] == '2027' for r in rows))
                    check('financial_not_execution_' + frame, 'кассов' in await page.locator('#main').inner_text())
                    if frame == 'budget_bill':
                        check('budget_direction_shares_filter', await panel('Отдельные направления внутри федерального финансирования').locator('tbody tr').count() == 1)
                await route('finance', {'frame': 'passport_plan'})
                data = csv_rows(await download(panel('Сверка национального и федеральных паспортов')))
                check('national_FP_reconciliation_2025', any(r['Год'] == '2025' and abs(number(r['НП − сумма ФП']) - .24781204) < .000001 for r in data))
                check('national_FP_reconciliation_later_zero', all(number(r['НП − сумма ФП']) == 0 for r in data if r['Год'] != '2025'))
                await choose('Источник средств', 'regional', 'finSource')
                rows = csv_rows(await download(panel('Исходные финансовые строки')))
                check('source_filter_only_regional', rows and all(r['Источник средств'] in {r['source_name'] for r in documentary['finance']['sourceYears'] if r['source_code'] == 'regional'} for r in rows))
                check('source_filter_has_numeric', await panel('Паспортное финансирование направлений').locator('rect[tabindex="0"]').count() > 0)
            await group('finance_flow', finance_flow)


            async def documentary_flow():
                for layer in ['shared', 'same_project', 'weights', 'semantic']:
                    await route('network', {'layer': layer})
                    check('network_layer_' + layer, await page.locator('.data-table tbody tr').count() > 0)
                    await choose('Федеральный проект', 'Ч2', 'fp')
                    check('network_filter_' + layer, 'Ч2' in await page.locator('#main').inner_text())
                for view in ['themes', 'terms', 'similarity', 'projects', 'audit']:
                    await route('texts', {'textview': view})
                    check('text_view_' + view, await page.locator('.data-table tbody tr').count() > 0)
                for variant in ['base', 'stemming', 'unigrams', 'equal_levels', 'federal_only', 'national_only']:
                    await route('texts', {'textview': 'projects', 'variant': variant})
                    check('text_variant_' + variant, await page.locator('.chart-svg').count() > 0)
                    data = csv_rows(await download(panel('Межпроектная лексическая близость')))
                    check('text_variant_corpus_11_' + variant, len(data) == 11)
                    check('text_variant_nearest_infrastructure_' + variant, data[0]['name'] == 'Инфраструктура для жизни')
                await route('texts', {'textview': 'terms', 'doc': 'project'})
                check('aggregate_profile_seven_passports', 'семи паспортов' in await page.locator('#main').inner_text())
                for document in documentary.get('text', {}).get('documents', []):
                    doc_id = document['document_id']
                    await route('texts', {'textview': 'contexts', 'doc': doc_id})
                    check('document_context_load_' + doc_id, await page.locator('.environment-load-error').count() == 0)
                    check('document_context_source_' + doc_id, bool(await page.locator('.source-foot a').count()))
                await route('texts', {'textview': 'contexts', 'doc': 'np_25'})
                await panel('Контексты выбранного документа').scroll_into_view_if_needed()
                await page.screenshot(path=str(output / 'contexts-desktop.png'))
                await page.get_by_label('Поиск в контекстах', exact=True).fill('эколог')
                await page.get_by_role('button', name='Найти', exact=True).click()
                await ready(state={'q': 'эколог'})
                data = csv_rows(await download(panel('Контексты выбранного документа')))
                check('context_query_matches_export', all('эколог' in r['context'].lower() for r in data))
                await route('proposals')
                check('proposal_source_sequence_present', 'Последовательность' in await page.locator('#main').inner_text())
                await route('overview')
                await page.locator('.environment-report>summary').click()
                check('original_report_expands', await page.locator('.environment-report[open]').count() == 1)
                await route('methods')
                data = csv_rows(await download(panel('Применимость методов')))
                check('method_catalogue_all39', len(data) == 39)
                check('method_current_labels_present', all(r['Статус'] for r in data))
            await group('documentary_flow', documentary_flow)


            async def calculators_flow():
                await route('lab', {'tool': 'waste'})
                for key, value in {'received':'100','treated':'80','secondary_used':'25','landfilled':'65','other_output':'5','stock_start':'0','stock_end':'5'}.items():
                    await page.locator('input[name="' + key + '"]').fill(value)
                await page.get_by_role('button', name='Рассчитать', exact=True).click()
                await ready(state={'received':'100','treated':'80'})
                vals = await page.locator('.environment-page>.stats .stat strong').all_text_contents()
                check('waste_balance_zero', number(vals[0]) == 0)
                check('waste_processing_not_additive', vals[1] == 'Согласован' and number(vals[2]) == 80 and number(vals[3]) == 65)
                await route('lab', {'tool':'emission','emissionBase':'100','emissionCurrent':'120'})
                vals = await page.locator('.environment-page>.stats .stat strong').all_text_contents()
                check('emission_index_allows_above100', number(vals[0]) == 120)
                check('emission_growth_negative_reduction', number(vals[1]) == -20)
                await route('lab', {'tool':'emission','emissionBase':'0','emissionCurrent':'1'})
                check('emission_zero_base_rejected', await page.locator('.environment-page>.stats').count() == 0)
                await route('lab', {'tool':'exposure'})
                text = 'А;1000;5;9\nБ;3000;15;1'
                await page.get_by_label('Ячейка; население; концентрация; площадь', exact=True).fill(text)
                await page.get_by_role('button', name='Рассчитать', exact=True).click()
                await ready(state={'exposureRows':text})
                vals = await page.locator('.environment-page>.stats .stat strong').all_text_contents()
                check('exposure_population_weighted', number(vals[0]) == 12.5)
                check('exposure_complete_coverage', number(vals[1]) == 100)
                check('exposure_multiline_input_retained', await page.get_by_label('Ячейка; население; концентрация; площадь', exact=True).input_value() == text)
                await page.screenshot(path=str(output / 'exposure-desktop.png'))
                missing = 'А;1000;5;9\nБ;3000;;1'
                await page.get_by_label('Ячейка; население; концентрация; площадь', exact=True).fill(missing)
                await page.get_by_role('button', name='Рассчитать', exact=True).click()
                await ready(state={'exposureRows':missing})
                vals = await page.locator('.environment-page>.stats .stat strong').all_text_contents()
                check('exposure_missing_not_zero', number(vals[0]) == 5 and number(vals[1]) == 25)
                check('exposure_missing_limitation_visible', 'только к ячейкам с известной концентрацией' in await page.locator('#main').inner_text())
                await route('lab', {'tool':'changes','source':'62777'})
                data = csv_rows(await download(panel('Сопоставление одинаковых периодов')))
                aug = next(r for r in data if r['Период'] == '2026-08')
                check('YTD_visits_same_window', number(aug['Предыдущее значение']) == 16.2 and number(aug['Текущее значение']) == 14.7296)
                await route('projections', {'source': '62792', 'goal': '100', 'goalYear': '2030'})
                check('scenario_renders', await panel('Условный путь от факта к цели').locator('.chart-svg').count() == 1)
                check('scenario_no_forecast_claim', 'вероятность достижения не оценивается' in await page.locator('#main').inner_text())
                await route('projections', {'source':'62781','goal':'200','goalYear':'2030'})
                check('forest_scenario_not_capped_100', await panel('Условный путь от факта к цели').locator('.chart-svg').count() == 1)
                await route('projections', {'source':'62861'})
                check('published_zero_target_not_automatic_goal', await page.locator('input[name=goal]').input_value() == '' and 'исходный ноль' in await page.locator('#main').inner_text())
                for sid in ['62779','62787','62804','62871']:
                    await route('projections', {'source':sid,'goal':'100','goalYear':'2030'})
                    check('scenario_source_restriction_' + sid, await panel('Условный путь от факта к цели').count() == 0 and 'не строится' in await page.locator('#main').inner_text())
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
            path = sources['62792']['downloads']['observations'].lstrip('./')
            await fault.route('**/' + path + '*', fail_once)
            await fault.goto(args.base + '#/projects/' + PROJECT + '/explorer?source=62792&year=2025')
            await fault.locator('.environment-load-error').wait_for()
            check('lazy_failure_retry_available', await fault.get_by_role('button', name='Повторить загрузку', exact=True).count() == 1)
            await fault.get_by_role('button', name='Повторить загрузку', exact=True).click()
            await fault.locator('.environment-load-error').wait_for(state='detached')
            check('lazy_retry_preserves_year', await fault.get_by_label('Год', exact=True).input_value() == '2025')
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
            await route('texts', {'textview': 'contexts', 'doc': 'np_25'})
            await panel('Контексты выбранного документа').scroll_into_view_if_needed()
            check('mobile_context_width_' + str(width), await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
            await page.screenshot(path=str(output / f'contexts-mobile-{width}.png'))

            await route('regions', {'source':'62792'})
            check('mobile_chart_scroll_' + str(width), await page.locator('.environment-wide-chart').first.evaluate('e=>e.scrollWidth>e.clientWidth'))
            chart = page.locator('.environment-wide-chart').first
            await chart.evaluate('e=>e.scrollLeft=e.scrollWidth')
            check('mobile_chart_scroll_works_' + str(width), await chart.evaluate('e=>e.scrollLeft>0'))
            await panel('Обработка и захоронение ТКО: проверка чувствительности').scroll_into_view_if_needed()
            await page.screenshot(path=str(output / f'waste-mobile-{width}.png'))
            await route('population', {'airSource':'62863','airPeriod':'annual'})
            await panel('Остаточный индекс опасных выбросов: 29 территорий').scroll_into_view_if_needed()
            check('mobile_air_width_' + str(width), await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
            await page.screenshot(path=str(output / f'air-mobile-{width}.png'))
            text = 'А;1000;5;9\nБ;3000;15;1'
            await route('lab', {'tool':'exposure','exposureRows':text})
            check('mobile_textarea_retained_' + str(width), await page.get_by_label('Ячейка; население; концентрация; площадь', exact=True).input_value() == text)
            check('mobile_exposure_width_' + str(width), await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
            await page.screenshot(path=str(output / f'exposure-mobile-{width}.png'))

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
