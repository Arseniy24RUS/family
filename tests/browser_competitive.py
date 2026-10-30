"""HTTP acceptance for the Effective and Competitive Economy project.

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

PROJECT = 'competitive_economy'
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
                if(main?.dataset.project!==project||main.dataset.ready!=='true'||main.hasAttribute('aria-busy')||(name&&main.dataset.page!==name))return false;
                const actual=JSON.parse(document.querySelector('.competitive-page')?.dataset.routeState||'{}');
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
                check('no_lazy_error_' + name, await page.locator('.competitive-load-error').count() == 0)
                if name in ['overview', 'targets', 'finance', 'network', 'texts', 'population', 'map', 'regions']:
                    await page.screenshot(path=str(output / (name + '-desktop.png')))
            except Exception as error:
                check('desktop_route_' + name, False, str(error))
        check('twelve_project_tabs', await page.locator('.project-tab').count() == 12)
        check('official_economy_theme', await page.locator('html').evaluate("e=>e.style.getPropertyValue('--project-color')") == '#D86464')
        check('full_text_not_eager', not any('/documentary-text/' in path or '/documentary_full.json' in path for path in requests))

        if not args.smoke_only:
            async def statistics_flow():
                for sid, source in sources.items():
                    await route('explorer', {'source': sid})
                    values = await page.locator('.competitive-page>.stats .stat strong').all_text_contents()
                    expected = len(source.get('national', []))
                    check('source_rows_' + sid, number(values[0]) == expected)
                    check('source_analytical_' + sid, number(values[1]) == sum(analytical(r) is not None for r in source.get('national', [])))
                    check('source_zeroes_' + sid, number(values[2]) == sum(r.get('value') == 0 for r in source.get('national', [])))
                    if sid in ['62709','62712','62979','62962','62960','62961','63088','63165'] and expected:
                        data = csv_rows(await download(panel('Все наблюдения выбранного среза')))
                        check('source_csv_rows_' + sid, len(data) == expected)
                        check('source_csv_raw_' + sid, sum(number(r['Исходное число']) is not None for r in data) == sum(r.get('value') is not None for r in source.get('national', [])))
                        check('source_csv_excluded_' + sid, sum(r['Статус ячейки'] == 'Не используется в расчётах' for r in data) == sum(bool(r.get('excluded')) for r in source.get('national', [])))
                        check('source_csv_original_' + sid, all(r['Исходная запись'] != '' for r in data if number(r['Исходное число']) is not None))
                        full_source=(await get_json(source['downloads']['observations']))['observations']
                        by_id={r.get('source_observation_key') or r['id']:r for r in full_source}
                        check('source_csv_original_time_'+sid,all((r['Начало исходного окна'] or None)==by_id[r['Ключ наблюдения']].get('source_period_start',by_id[r['Ключ наблюдения']].get('period_start')) for r in data))
                for missing_id,missing_source in sources.items():
                    if missing_source.get('available'):continue
                    await route('targets',{'source':missing_id})
                    check('metadata_targets_identity_'+missing_id,await page.get_by_label('Показатель',exact=True).input_value()==missing_id)
                    check('metadata_targets_empty_'+missing_id,'Числовая публикация не получена' in await page.locator('#main').inner_text() and number((await page.locator('.competitive-page>.stats .stat strong').all_text_contents())[0])==0)
                    await choose('Показатель','62979','source')
                    await choose('Показатель',missing_id,'source')
                    check('metadata_targets_selection_'+missing_id,await page.get_by_label('Показатель',exact=True).input_value()==missing_id and await panel('Проверенные сопоставления с планом').count()==0)
                await route('explorer', {'source': '62979'})
                await choose('Территориальный уровень', 'regional', 'geography')
                await choose('Год', '2025', 'year')
                await choose('Периодичность', 'annual', 'frequency')
                values = await page.locator('.competitive-page>.stats .stat strong').all_text_contents()
                check('SME_84_annual_regions', number(values[0]) == 84 and number(values[1]) == 84)
                data = csv_rows(await download(panel('Все наблюдения выбранного среза')))
                check('SME_csv_values_below_base', sum(number(r['Для анализа']) < 100 for r in data) == 7)
                await choose('Территория', '01', 'r')
                check('SME_single_region_filter', number((await page.locator('.competitive-page>.stats .stat strong').all_text_contents())[0]) == 1)
                for sid in ['62709','62712','62979']:
                    await route('targets', {'source': sid,'frequency':'monthly'})
                    commands = await page.locator('path.data-line').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("d"))')
                    check('no_artificial_monthly_trend_' + sid, all('L' not in d for d in commands))
                    await route('lab', {'tool':'changes','source':sid})
                    check('blocked_annual_republication_change_' + sid, 'Сопоставимых пар нет' in await page.locator('#main').inner_text())
                await route('targets', {'source':'62979'})
                data = csv_rows(await download(panel('Проверенные сопоставления с планом')))
                check('SME_annual_target_comparison', len(data)==1 and number(data[0]['Факт'])==106.8 and number(data[0]['План'])==107.9 and number(data[0]['Разность'])==-1.1)
                check('SME_income_not_salary', 'заработ' in (await page.locator('#main').inner_text()).lower())
                await route('explorer', {'source':'63088','year':'2026','frequency':'quarterly'})
                data = csv_rows(await download(panel('Все наблюдения выбранного среза')))
                check('revenue_2026Q3_export', any(r['Период']=='2026-Q3' and number(r['Для анализа'])==1444772.16 for r in data))
            await group('statistics_flow', statistics_flow)

            async def geography_flow():
                await route('map', {'source':'62979'})
                check('SME_map_renders', await page.locator('.map-surface').count()>0)
                selected_slice=await page.get_by_label('Срез наблюдений',exact=True).input_value()
                check('SME_map_annual_default', selected_slice.startswith('annual|2025-12-31|'))
                await choose('Шкала карты','quartiles','scale')
                check('quartile_explanation','Границы квартилей' in await page.locator('#main').inner_text())
                await choose('Регион','01','r')
                check('region_readout',await page.locator('.region-reading').count()==1)
                await choose('Сравнить с регионом','02','compare')
                check('regional_difference',await page.locator('.comparison-reading').count()==1)
                await page.locator('.map-surface').scroll_into_view_if_needed()
                await page.screenshot(path=str(output/'map-detail-desktop.png'))
                await route('regions', {'source':'62979'})
                values=await page.locator('.competitive-page>.stats .stat strong').all_text_contents()
                check('SME_profile_84',number(values[0])==84)
                check('SME_profile_median',number(values[1])==105.4)
                data=csv_rows(await download(panel('Шесть самостоятельных региональных профилей')))
                check('six_profiles_own_periods',len(data)==6 and len(set(r['Период'] for r in data))==2)
                svg=await download(panel('Распределение выбранного показателя'),'SVG')
                check('SVG_project_source_title',b'<svg' in svg and 'Эффективная и конкурентная экономика'.encode() in svg and 'ЕМИСС'.encode() in svg)
                check('no_efficiency_ranking','рейтинг экономической эффективности' in await page.locator('#main').inner_text())
                for sid in ['62962','62991','62960','62961']:
                    await route('population',{'source':sid})
                    data=csv_rows(await download(panel('Региональные записи')))
                    check('social_regional_export_'+sid,len(data)==len(sources[sid]['regional_latest']))
                    check('social_quality_caveat_'+sid,'качество' in (await page.locator('#main').inner_text()).lower())
                await route('population',{'source':'62962'})
                check('medical_median_exact',number((await page.locator('.competitive-page>.stats .stat strong').all_text_contents())[1])==25.345)
                await page.screenshot(path=str(output/'services-desktop.png'))
            await group('geography_flow',geography_flow)

            async def finance_flow():
                for frame in ['passport_plan','budget_bill']:
                    await route('finance',{'frame':frame})
                    data=csv_rows(await download(panel('Исходные финансовые строки')))
                    expected=next(f['rows'] for f in documentary['finance']['frames'] if f['id']==frame)
                    check('finance_export_count_'+frame,len(data)==len(expected))
                    check('finance_export_sum_'+frame,abs(sum(number(r['Сумма']) or 0 for r in data)-sum(r['value'] or 0 for r in expected))<.001)
                    check('finance_export_unit_'+frame,all(r['Единица']==('тыс. руб.' if frame=='passport_plan' else 'млн руб.') for r in data))
                    await choose('Год','2027','year')
                    await choose('Федеральный проект','Э3','fp')
                    rows=csv_rows(await download(panel('Исходные финансовые строки')))
                    check('investment_financial_filter_'+frame,len(rows)>=1 and all(r['Код']=='Э3' and r['Год']=='2027' for r in rows))
                    check('finance_plan_not_execution_'+frame,'кассов' in await page.locator('#main').inner_text())
                await route('finance',{'frame':'passport_plan'})
                data=csv_rows(await download(panel('Сверка национального и федеральных паспортов')))
                check('reconciliation_2026_2007_5_thousand',any(r['Год']=='2026' and abs(number(r['НП − сумма ФП'])-.0020075)<.00000051 for r in data))
                check('reconciliation_other_years_zero',all(abs(number(r['НП − сумма ФП']))<1e-8 for r in data if r['Год']!='2026'))
                await choose('Источник средств','extra_budget','finSource')
                rows=csv_rows(await download(panel('Исходные финансовые строки')))
                check('extrabudget_filter',rows and all(r['Источник средств'] in {r['source_name'] for r in documentary['finance']['sourceYears'] if r['source_code']=='extra_budget'} for r in rows))
                for fp in ['Э5','Э7']:
                    await route('finance',{'frame':'passport_plan','fp':fp})
                    rows=csv_rows(await download(panel('Исходные финансовые строки')))
                    check('undisclosed_not_zero_'+fp,all(number(r['Сумма']) is None for r in rows))
                    check('undisclosed_label_'+fp,'Нет раскрытых сумм' in await page.locator('#main').inner_text())
            await group('finance_flow',finance_flow)

            async def documentary_flow():
                for layer in ['shared','same_project','weights','semantic']:
                    await route('network',{'layer':layer})
                    check('network_rows_'+layer,await page.locator('.data-table tbody tr').count()>0)
                    await choose('Федеральный проект','Э6','fp')
                    check('network_FP_filter_'+layer,'Э6' in await page.locator('#main').inner_text())
                await route('network',{'layer':'semantic'})
                edges=csv_rows(await download(panel('Все связи выбранного слоя')))
                check('cross_document_links_keep_both_sources',sum(r['Источник результата']!=r['Источник показателя'] for r in edges)==54)
                check('indicator_links_have_own_FP',all(r['ФП показателя'] and r['Источник показателя'] for r in edges))
                for view in ['themes','terms','similarity','projects','audit']:
                    await route('texts',{'textview':view})
                    check('text_view_'+view,await page.locator('.data-table tbody tr').count()>0)
                    check('author_and_platform_variants_distinguished_'+view,'четырёх дополнительных проверках' in await page.locator('#main').inner_text())
                audit_rows=csv_rows(await download(panel('Независимая проверка')))
                check('audit_metric_ids_and_order_preserved',[r['metric_id'] for r in audit_rows]==[r['metric'] for r in documentary['text']['replicationAudit']])
                check('audit_project_labels_are_russian',all(r['Параметр'].startswith('Близость с проектом «') for r in audit_rows if r['metric_id'].startswith(('project_cosine_','stemmed_cosine_'))))
                for variant,key in [('base','cosine'),('stemming','stemmed_cosine'),('unigrams','unigram_cosine'),('equal_levels','equal_levels_cosine'),('federal_only','federal_only_cosine'),('national_only','national_only_cosine')]:
                    await route('texts',{'textview':'projects','variant':variant})
                    data=csv_rows(await download(panel('Межпроектная лексическая близость')))
                    expected=[r for r in documentary['text']['projectSimilarity'] if r.get('project_a')==PROJECT or r.get('project_b')==PROJECT or r.get('project_id')]
                    check('similarity_count_'+variant,len(data)==len(expected))
                    check('similarity_descending_'+variant,all(number(a['value'])>=number(b['value']) for a,b in zip(data,data[1:]) if number(a['value']) is not None and number(b['value']) is not None))
                    expected_values=sorted((r[key] for r in expected if r.get(key) is not None),reverse=True)
                    check('similarity_values_'+variant,all(abs(number(r['value'])-v)<1e-10 for r,v in zip(data,expected_values)))
                await route('texts',{'textview':'terms','doc':'project'})
                check('aggregate_eight_passports','восьми паспортов' in await page.locator('#main').inner_text())
                for document in documentary['text']['documents']:
                    await route('texts',{'textview':'contexts','doc':document['document_id']})
                    check('context_load_'+document['document_id'],await page.locator('.competitive-load-error').count()==0)
                await route('texts',{'textview':'contexts','doc':'np_21'})
                await page.get_by_label('Поиск в контекстах',exact=True).fill('предпри')
                await page.get_by_role('button',name='Найти',exact=True).click()
                await ready(state={'q':'предпри'})
                data=csv_rows(await download(panel('Контексты выбранного документа')))
                check('context_query_export',data and all('предпри' in r['context'].lower() for r in data))
                await panel('Контексты выбранного документа').scroll_into_view_if_needed()
                await page.screenshot(path=str(output/'contexts-desktop.png'))
                await route('overview')
                await page.locator('.competitive-report>summary').click()
                check('original_report_expands',await page.locator('.competitive-report[open]').count()==1)
                original_text=await page.locator('#main').inner_text()
                check('original_report_not_rewritten',any(b.get('text','')[:100] in original_text for b in report['pages']['overview']['blocks'] if b.get('type')=='paragraph' and b.get('text')))
                await route('methods')
                data=csv_rows(await download(panel('Применимость методов')))
                check('all39_methods_present',len(data)==39)
                check('all_method_statuses_visible',all(r['Статус'] for r in data))
            await group('documentary_flow',documentary_flow)

            async def calculators_flow():
                await route('lab',{'tool':'deflator'})
                await page.locator('input[name="nominalIndex"]').fill('105')
                await page.locator('input[name="priceIndex"]').fill('108')
                await page.get_by_role('button',name='Рассчитать',exact=True).click()
                await ready(state={'nominalIndex':'105','priceIndex':'108'})
                vals=await page.locator('.competitive-page>.stats .stat strong').all_text_contents()
                check('nominal5_realnegative',number(vals[0])==5 and abs(number(vals[3])+2.7778)<.0001)
                await page.locator('input[name=priceIndex]').fill('')
                await page.get_by_role('button',name='Рассчитать',exact=True).click()
                await ready(state={'priceIndex':' '})
                check('blank_price_not_replaced_with_default',await page.locator('input[name=priceIndex]').input_value()=='' and await page.locator('.competitive-page>.stats').count()==0)
                await route('lab',{'tool':'deflator','nominalIndex':'100','priceIndex':'0'})
                check('zero_price_base_rejected',await page.locator('.competitive-page>.stats').count()==0)
                await route('lab',{'tool':'income','incomeBefore':'100','incomeAfter':'100','workersBefore':'100','workersAfter':'80','priceIndex':'100'})
                vals=await page.locator('.competitive-page>.stats .stat strong').all_text_contents()
                check('income_shrinking_denominator',number(vals[0])==0 and number(vals[1])==-20 and number(vals[3])==125)
                async with page.expect_download() as event:
                    await page.get_by_role('button',name='Скачать расчёт CSV',exact=True).click()
                file=await event.value
                destination=output/file.suggested_filename
                await file.save_as(destination)
                data=csv_rows(destination.read_bytes())
                check('income_calculation_csv',len(data)==1 and number(data[0]['realPerWorkerIndex'])==125)
                await route('lab',{'tool':'cost','directCost':'1000000','adminCost':'50000','expectedLoss':'100000','capitalCost':'50000','additionalResult':'10'})
                vals=await page.locator('.competitive-page>.stats .stat strong').all_text_contents()
                check('full_cost_calculator',number(vals[0])==1200000 and number(vals[2])==120000)
                await route('lab',{'tool':'cost','additionalResult':'0'})
                check('cost_zero_outcome_rejected',await page.locator('.competitive-page>.stats').count()==0)
                await route('lab',{'tool':'did','treatedBefore':'-5','treatedAfter':'0','comparisonBefore':'2','comparisonAfter':'3'})
                vals=await page.locator('.competitive-page>.stats .stat strong').all_text_contents()
                check('DID_signed_outcomes',number(vals[2])==4)
                check('DID_assumption_caveat','параллельных траекторий' in await page.locator('#main').inner_text())
                await route('projections',{'source':'62710','goal':'40','goalYear':'2030'})
                check('annual_scenario_chart',await panel('Условный путь от факта к цели').locator('.chart-svg').count()==1)
                check('scenario_no_probability','вероятность достижения не оценивается' in await page.locator('#main').inner_text())
                await route('projections',{'source':'62979','goal':'120','goalYear':'2030'})
                check('SME_annual_scenario_allowed',await panel('Условный путь от факта к цели').locator('.chart-svg').count()==1)
                for sid in ['62709','62712','63165','63089','63088']:
                    await route('projections',{'source':sid,'goal':'100','goalYear':'2030'})
                    check('scenario_guard_'+sid,await panel('Условный путь от факта к цели').count()==0 and 'не строится' in await page.locator('#main').inner_text())
            await group('calculators_flow',calculators_flow)

            async def library_flow():
                await route('library')
                urls=await page.locator('#main a[href]').evaluate_all('(xs)=>[...new Set(xs.map(x=>x.href).filter(h=>h.startsWith(location.origin)&&!h.includes("#")))]')
                for url in urls:
                    response=await context.request.get(url)
                    check('library_'+url.rsplit('/',1)[-1],response.status==200,{'status':response.status})
            await group('library_flow',library_flow)
            fault=await context.new_page()
            calls={'n':0}
            async def fail_once(route):
                calls['n']+=1
                if calls['n']==1:await route.fulfill(status=503,body='temporary test fault')
                else:await route.continue_()
            path=sources['62979']['downloads']['observations'].lstrip('./')
            await fault.route('**/'+path+'*',fail_once)
            await fault.goto(args.base+'#/projects/'+PROJECT+'/explorer?source=62979&year=2025')
            await fault.locator('.competitive-load-error').wait_for()
            check('lazy_retry_available',await fault.get_by_role('button',name='Повторить загрузку',exact=True).count()==1)
            await fault.get_by_role('button',name='Повторить загрузку',exact=True).click()
            await fault.locator('.competitive-load-error').wait_for(state='detached')
            check('lazy_retry_preserves_year',await fault.get_by_label('Год',exact=True).input_value()=='2025')
            check('lazy_retry_refetches',calls['n']==2)
            await fault.close()

        for width in [390,320]:
            await page.set_viewport_size({'width':width,'height':844})
            for name in PAGES:
                try:
                    await route(name)
                    check(f'mobile_width_{width}_{name}',await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                    check(f'mobile_content_{width}_{name}',len(await page.locator('#main').inner_text())>300)
                except Exception as error:check(f'mobile_{width}_{name}',False,str(error))
            await route('overview')
            check('mobile_project_rail_'+str(width),await page.locator('.project-nav').evaluate('e=>e.scrollWidth>e.clientWidth'))
            await page.screenshot(path=str(output/f'overview-mobile-{width}.png'))
            await page.get_by_role('button',name='Открыть меню',exact=True).click()
            check('mobile_menu_'+str(width),await page.locator('body').evaluate("e=>e.classList.contains('nav-open')"))
            await page.locator('#sidebar a[data-route="finance"]').click()
            await ready('finance')
            check('mobile_menu_navigation_'+str(width),not await page.locator('body').evaluate("e=>e.classList.contains('nav-open')"))
            await page.wait_for_function("document.querySelector('#sidebar').getBoundingClientRect().right<=1")
            await page.screenshot(path=str(output/f'finance-mobile-{width}.png'))
            await route('texts',{'textview':'contexts','doc':'np_21'})
            await panel('Контексты выбранного документа').scroll_into_view_if_needed()
            check('mobile_context_width_'+str(width),await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
            context_scroll=panel('Контексты выбранного документа').locator('.table-scroll')
            check('mobile_context_table_scroll_'+str(width),await context_scroll.evaluate('e=>e.scrollWidth>e.clientWidth'))
            await context_scroll.evaluate('e=>e.scrollLeft=e.scrollWidth')
            check('mobile_context_last_columns_reachable_'+str(width),await context_scroll.evaluate('e=>e.scrollLeft>0'))
            await context_scroll.evaluate('e=>e.scrollLeft=0')
            await page.screenshot(path=str(output/f'contexts-mobile-{width}.png'))
            await route('regions',{'source':'62979'})
            chart=page.locator('.competitive-wide-chart').first
            check('mobile_chart_scroll_'+str(width),await chart.evaluate('e=>e.scrollWidth>e.clientWidth'))
            await chart.evaluate('e=>e.scrollLeft=e.scrollWidth')
            check('mobile_chart_scroll_works_'+str(width),await chart.evaluate('e=>e.scrollLeft>0'))
            await page.screenshot(path=str(output/f'regions-mobile-{width}.png'))
            await route('lab',{'tool':'income','incomeBefore':'100','incomeAfter':'100','workersBefore':'100','workersAfter':'80','priceIndex':'100'})
            check('mobile_income_inputs_'+str(width),await page.locator('input[name="workersAfter"]').input_value()=='80')
            check('mobile_lab_width_'+str(width),await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
            await page.screenshot(path=str(output/f'income-mobile-{width}.png'))

        check('no_console_errors',not errors,errors)
        check('no_http_errors',not http_errors,http_errors)
        result={'project_id':PROJECT,'base':args.base,'browser_plugin':'not_available','fallback':'Playwright','viewports':[[1440,1000],[390,844],[320,844]],'checks':checks,'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'errors':errors,'http_errors':http_errors,'downloads':downloads,'screenshots':[p.name for p in output.glob('*.png')]}
        (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        await browser.close()
        print(json.dumps({'passed':result['passed'],'failed':result['failed'],'output':str(output)},ensure_ascii=False),flush=True)
        if result['failed']:raise SystemExit(1)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--browser')
    parser.add_argument('--smoke-only',action='store_true')
    asyncio.run(run(parser.parse_args()))

if __name__=='__main__':main()
