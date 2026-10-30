"""HTTP acceptance for the Data Economy project.

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
from browser_json import get_json as published_json, fulfill_json

PROJECT = 'data_economy'
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
                const actual=JSON.parse(document.querySelector('.dataeconomy-page')?.dataset.routeState||'{}');
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
        async def download(locator, kind='CSV', last=False):
            await page.wait_for_timeout(1100)
            async with page.expect_download() as event:
                buttons=locator.get_by_role('button',name=kind,exact=True)
                await (buttons.last if last else buttons.first).click()
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
                check('no_lazy_error_' + name, await page.locator('.dataeconomy-load-error').count() == 0)
                if name in ['overview', 'targets', 'finance', 'network', 'texts', 'population', 'map', 'regions']:
                    await page.screenshot(path=str(output / (name + '-desktop.png')))
            except Exception as error:
                check('desktop_route_' + name, False, str(error))
        check('twelve_project_tabs', await page.locator('.project-tab').count() == 12)
        check('official_economy_theme', await page.locator('html').evaluate("e=>e.style.getPropertyValue('--project-color')") == '#4224FD')
        check('full_text_not_eager', not any('/documentary-text/' in path or '/documentary_full.json' in path for path in requests))
        check('result_finance_not_eager', not any('/documentary-finance/' in path for path in requests))


        if not args.smoke_only:
            async def values():
                return [number(v) for v in await page.locator('.dataeconomy-page .stats').first.locator('.stat strong').all_text_contents()]
            async def button_download(label):
                async with page.expect_download() as event:
                    await page.get_by_role('button',name=label,exact=True).click()
                artifact=await event.value
                destination=output/artifact.suggested_filename
                await artifact.save_as(destination)
                data=destination.read_bytes()
                downloads.append({'name':destination.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
                return csv_rows(data)

            async def statistics_flow():
                for sid,source in sources.items():
                    await route('explorer',{'source':sid})
                    nums=await values();expected=source.get('national',[])
                    check('source_rows_'+sid,nums[0]==len(expected))
                    check('source_analytical_'+sid,nums[1]==sum(analytical(r)is not None for r in expected))
                    check('source_zeroes_'+sid,nums[2]==sum(r.get('value')==0 for r in expected))
                    check('source_selection_'+sid,await page.get_by_label('Показатель',exact=True).input_value()==sid)
                    if sid in ['62751','62857','62889','62830','63143','62766','62815','62809','62868']:
                        data=csv_rows(await download(panel('Все наблюдения выбранного среза')))
                        check('source_csv_rows_'+sid,len(data)==len(expected))
                        check('source_csv_raw_'+sid,sum(number(r['Исходное число'])is not None for r in data)==sum(r.get('value')is not None for r in expected))
                        check('source_csv_exclusions_'+sid,sum(r['Статус ячейки']=='Не используется в расчётах' for r in data)==sum(bool(r.get('excluded')) for r in expected))
                        if sid=='63143':check('excluded_rf_scope_kept',all('без' in r['Территория'].lower() or 'without' in r['Территориальный охват'] or 'excluding' in r['Территориальный охват'] for r in data))
                        if sid in ['62751','62857']:check('indices_above100_not_removed_'+sid,any(number(r['Для анализа'])is not None and number(r['Для анализа'])>100 for r in data))
                for sid in ['62765','62767','62815','62751','62809','62868']:
                    await route('targets',{'source':sid})
                    check('target_source_identity_'+sid,await page.get_by_label('Показатель',exact=True).input_value()==sid)
                    check('targets_no_official_attainment_'+sid,'Официальная оценка' in await page.locator('#main').inner_text() or await panel('Проверенные сопоставления с планом').count()==0)
                await route('targets',{'indicator':'2.14.Ц4.6'})
                check('unmapped_registry_target_identity',await page.get_by_label('Показатель',exact=True).input_value()=='registry-2.14.Ц4.6')
                check('unmapped_registry_has_no_observations',(await values())[0]==0 and 'Числовой источник не установлен' in await page.locator('#main').inner_text())
                target_data=csv_rows(await download(panel('Паспортные ориентиры')))
                check('unmapped_registry_own_goals',len(target_data)==6 and all(r['Код']=='2.14.Ц4.6'for r in target_data))
                await choose('Показатель','62766','source');await choose('Показатель','registry-2.14.Ц4.6','source')
                check('unmapped_registry_selection_preserved',(await values())[0]==0 and await page.get_by_label('Показатель',exact=True).input_value()=='registry-2.14.Ц4.6')
                await route('explorer',{'source':'62815','geography':'regional','year':'2026','frequency':'monthly'})
                candidates=await page.get_by_label('Территория',exact=True).locator('option').evaluate_all('(xs)=>xs.map(x=>x.value).filter(Boolean)')
                await choose('Территория',candidates[0],'r')
                data=csv_rows(await download(panel('Все наблюдения выбранного среза')))
                check('single_region_filter',len(set(r['Территория']for r in data))==1)
                check('year_frequency_filters',all(r['Период'].startswith('2026')and r['Периодичность источника']=='monthly' for r in data))
            await group('statistics_flow',statistics_flow)

            async def geography_flow():
                for sid,source in sources.items():
                    if not source.get('regional_latest'):continue
                    await route('map',{'source':sid})
                    check('map_renders_'+sid,await page.locator('.map-surface').count()>0)
                    check('map_period_'+sid,(await page.get_by_label('Срез наблюдений',exact=True).input_value()).startswith('monthly|')or(await page.get_by_label('Срез наблюдений',exact=True).input_value()).startswith('cumulative_ytd|'))
                    await choose('Шкала карты','quartiles','scale')
                    check('map_quartile_note_'+sid,'Границы квартилей' in await page.locator('#main').inner_text())
                await route('map',{'source':'62766'})
                candidates=await page.get_by_label('Регион',exact=True).locator('option').evaluate_all('(xs)=>xs.map(x=>x.value).filter(Boolean)')
                await choose('Регион',candidates[0],'r')
                check('map_selected_region',await page.locator('.region-reading').count()==1)
                await page.get_by_role('button',name='Плиточная карта',exact=True).click()
                await ready(state={'view':'tile'})
                check('map_tile_switch',await page.locator('.map-surface').count()>0)
                await page.locator('.map-surface').scroll_into_view_if_needed()
                await page.screenshot(path=str(output/'map-detail-desktop.png'))
                await route('regions',{'source':'62766'})
                profile=csv_rows(await download(panel('Самостоятельные региональные профили')))
                check('seven_regional_profiles',len(profile)==7)
                check('national_benchmark_not_comparable',all(r['Сопоставимость с РФ']=='false' for r in profile))
                for sid in [r['source_id']for r in analytics['digital']['regional_profiles']]:
                    await route('regions',{'source':sid})
                    distribution=panel('Распределение выбранного показателя')
                    check('no_RF_reference_line_'+sid,not any(t.startswith('РФ ')for t in await distribution.locator('svg text').all_text_contents()))
                    check('national_separate_observation_'+sid,'без опорной линии'in await page.locator('#main').inner_text())
                await route('regions',{'source':'62766'})
                await choose('Второй показатель','62815','otherSource')
                check('pairwise_matched_period',await panel('Парное региональное сопоставление').locator('.chart-svg').count()==1)
                check('regional_no_ranking','не формируют шкалу' in await page.locator('#main').inner_text())
            await group('geography_flow',geography_flow)

            async def multivariate_flow():
                model=analytics['multivariate'];summary=model['summary']
                await route('regions',{'regionview':'pca'})
                nums=await values()
                check('pca_sample_size',nums[0]==summary['regions']==85)
                check('pca_feature_count',nums[1]==summary['features']==5)
                check('pca_imputation_count',nums[3]==summary['imputed_cells']==1)
                check('pca_explained_share',abs(nums[2]-summary['pc12_variance']*100)<.006)
                data=csv_rows(await download(panel('Координаты и базовые группы')))
                check('pca_rowcount',len(data)==85)
                check('cluster_labels_not_shifted',set(r['Базовое разбиение']for r in data)=={'Группа 1','Группа 2'})
                check('pca_imputed_row_visible',sum(r['Расчётная матрица']=='Есть заполненная ячейка'for r in data)==1)
                await panel('Первые две главные компоненты').scroll_into_view_if_needed()
                await page.screenshot(path=str(output/'pca-desktop.png'))
                await choose('Представление регионов','matrix','regionview')
                matrix=csv_rows(await download(panel('Наблюдения и расчётная матрица')))
                check('matrix425_cells',len(matrix)==425)
                filled=[r for r in matrix if r['Основание']=='Заполнена медианой']
                check('matrix_preserves_missing_vs_imputation',len(filled)==1 and number(filled[0]['Исходное значение'])is None and number(filled[0]['В матрице модели'])is not None)
                await choose('Представление регионов','stability','regionview')
                seeds=csv_rows(await download(panel('Начальное состояние алгоритма')))
                check('seed_runs_all_visible',len(seeds)==7)
                check('seed_eligibility_qualified',sum(r['Результат']=='Допустимо'for r in seeds)==1)
                omitted=csv_rows(await download(panel('Поочерёдное исключение признаков')))
                check('feature_sensitivity_all_visible',len(omitted)==5)
                check('feature_eligibility_qualified',sum(r['Результат']=='Допустимо'for r in omitted)==1)
                check('temporal_no_admissible_previous','Нет допустимого разбиения' in await panel('Соседние месяцы на общей панели').inner_text())
                await page.screenshot(path=str(output/'stability-desktop.png'))
                await choose('Представление регионов','outliers','regionview')
                flags=csv_rows(await download(panel('Повторяемость алгоритмической отметки')))
                check('outlier85_rows',len(flags)==85)
                check('outlier_counts_and_fraction',all(number(r['Всего запусков'])==7 and abs(number(r['Доля запусков с отметкой'])-number(r['Запусков с отметкой'])/7)<1e-10 for r in flags))
                await choose('Состав таблицы','flagged','flagScope')
                flags=csv_rows(await download(panel('Повторяемость алгоритмической отметки')))
                check('outlier_flag_filter',all(number(r['Запусков с отметкой'])>0 for r in flags))
                check('outlier_no_probability_claim','не является вероятностью' in await page.locator('#main').inner_text())
            await group('multivariate_flow',multivariate_flow)

            async def finance_flow():
                for frame in ['passport_plan','budget_bill']:
                    await route('finance',{'frame':frame})
                    data=csv_rows(await download(panel('Исходные финансовые строки')))
                    expected=next(f['rows']for f in documentary['finance']['frames']if f['id']==frame)
                    check('finance_export_count_'+frame,len(data)==len(expected))
                    check('finance_export_sum_'+frame,abs(sum(number(r['Сумма'])or 0 for r in data)-sum(r['value']or 0 for r in expected))<.001)
                    check('finance_source_units_'+frame,all(r['Единица']==('тыс. руб.'if frame=='passport_plan'else'млн руб.')for r in data))
                    await choose('Год','2027','year');await choose('Федеральный проект','Ц4','fp')
                    data=csv_rows(await download(panel('Исходные финансовые строки')))
                    check('finance_selection_'+frame,bool(data)and all(r['Код']=='Ц4'and r['Год']=='2027'for r in data))
                    check('finance_no_execution_substitution_'+frame,'кассов' in await page.locator('#main').inner_text())
                await route('finance',{'frame':'passport_plan'})
                nums=await values();check('national_comparable_plan',abs(nums[0]-1212.74911229)<.0001)
                data=csv_rows(await download(panel('Сверка национального и федеральных паспортов')))
                check('national_federal_reconciliation_zero',len(data)==6 and all(abs(number(r['НП − сумма ФП']))<1e-8 for r in data))
                await route('finance',{'fp':'Ц1','year':'2030'})
                data=csv_rows(await download(panel('Исходные финансовые строки')))
                check('C1_2030_not_zero',all(number(r['Сумма'])is None for r in data)and'не раскрыта'in await page.locator('#main').inner_text())
                await route('finance',{'frame':'budget_bill','fp':'Ц1'})
                check('C1_budget_absent_not_zero','отдельная именованная строка Ц1 отсутствует'in await page.locator('#main').inner_text())
                for budget_year in ['2028','2029']:
                    await route('finance',{'frame':'budget_bill','year':budget_year})
                    check('missing_budget_row_count_'+budget_year,(await values())[2]==1)
                    missing=csv_rows(await download(panel('Не выделенные в бюджетной таблице направления')))
                    check('missing_C1_budget_year_'+budget_year,len(missing)==1 and missing[0]['ФП']=='Ц1' and missing[0]['Год']==budget_year and number(missing[0]['Раскрытая сумма, млн руб.'])is None)
                await route('finance',{'frame':'budget_bill'})
                data=csv_rows(await download(panel('Изменение назначения между 2026 и 2027 годами'),last=True))
                by_name={r['Состав назначения']:r for r in data}
                check('budget_total_delta',abs(number(by_name['Все федеральные назначения']['Изменение'])+22.2963)<1e-8)
                check('budget_named_delta',abs(number(by_name['Именные федеральные проекты']['Изменение'])-10.5578)<1e-8)
                check('budget_other_delta',abs(number(by_name['Другие структурные элементы']['Изменение'])+32.8543)<1e-8)
                check('budget_reserve_and_rounding_preserved',{'Резерв','Остаток округления'}.issubset(by_name))
                await choose('Единица диаграммы','million','money')
                scaled=csv_rows(await download(panel('Изменение назначения между 2026 и 2027 годами'),last=True))
                check('budget_units_scaling',all(abs(number(a['Изменение'])*1000-number(b['Изменение']))<1e-6 for a,b in zip(data,scaled)))
                await page.screenshot(path=str(output/'budget-breakdown-desktop.png'))

                await route('finance',{'frame':'passport_plan','financeview':'results'})
                check('result_finance_loaded_lazily',any('/documentary-finance/results.json'in path for path in requests))
                result_packet=await get_json(documentary['finance']['resultsFile'])
                data=csv_rows(await download(panel('Раскрытые средства по результатам')))
                check('finance90_result_cards',len(data)==90)
                check('result_null_is_not_zero',sum(number(r['Сумма известных родительских строк'])is None for r in data)==1)
                expected=sum(r['amount_thousand_rub']or 0 for r in result_packet['resultYears']if 2025<=r['year']<=2030 and not r.get('is_subcomponent')and r.get('included_in_additive_total')is not False)
                check('result_parent_sum_only',abs(sum(number(r['Сумма известных родительских строк'])or 0 for r in data)-expected/1000000)<1e-8)
                check('result_cost_completeness_qualified',all(r['Статус']=='Полнота стоимости не установлена'for r in data))
                orphans=csv_rows(await download(panel('Подстроки без раскрытой родительской суммы')))
                check('orphan12_components_visible',len(orphans)==12)
                raw=csv_rows(await download(panel('Исходные строки финансирования результатов')))
                check('result480_selected_source_cells',len(raw)==480)
                check('result486_all_source_cells_preserved',len(result_packet['resultYears'])==486 and sum(r['year']>2030 for r in result_packet['resultYears'])==6)
                check('result_full_source_download_available',await page.get_by_role('link',name='Полные исходные строки, включая последующий горизонт (JSON)',exact=True).count()==1)
                await choose('Год','2027','year');await choose('Федеральный проект','Ц4','fp')
                raw=csv_rows(await download(panel('Исходные строки финансирования результатов')))
                check('result_finance_year_FP_filter',bool(raw)and all(r['Год']=='2027'and r['ФП']=='Ц4'for r in raw))
                await choose('Источник средств','federal','finSource')
                raw=csv_rows(await download(panel('Исходные строки финансирования результатов')))
                check('result_finance_parent_source_filter',bool(raw)and all(r['Источник средств']=='Федеральный бюджет'for r in raw))
                await page.screenshot(path=str(output/'finance-results-desktop.png'))

            await group('finance_flow',finance_flow)

            async def documentary_flow():
                for layer in ['shared','same_project','weights','semantic']:
                    await route('network',{'layer':layer})
                    check('network_rows_'+layer,await page.locator('.data-table tbody tr').count()>0)
                    await choose('Федеральный проект','Ц5','fp')
                    check('network_FP_filter_'+layer,'Ц5'in await page.locator('#main').inner_text())
                await route('network',{'layer':'semantic'})
                data=csv_rows(await download(panel('Все связи выбранного слоя')))
                check('semantic150_candidates',len(data)==150)
                check('semantic_both_card_sources',all(r['Источник результата']and r['Источник показателя']and r['ФП показателя']for r in data))
                for view in ['themes','terms','similarity','projects','audit']:
                    await route('texts',{'textview':view})
                    check('text_view_'+view,await page.locator('.data-table tbody tr').count()>0)
                data=csv_rows(await download(panel('Независимая проверка')))
                check('audit_order_preserved',[r['metric_id']for r in data]==[r['metric']for r in documentary['text']['replicationAudit']])
                check('audit_project_labels_russian',all(r['Параметр'].startswith('Близость с проектом «')for r in data if r['metric_id'].startswith(('project_cosine_','stemmed_cosine_'))))
                for variant,key in [('base','cosine'),('stemming','stemmed_cosine'),('unigrams','unigram_cosine'),('equal_levels','equal_levels_cosine'),('federal_only','federal_only_cosine'),('national_only','national_only_cosine')]:
                    await route('texts',{'textview':'projects','variant':variant})
                    data=csv_rows(await download(panel('Межпроектная лексическая близость')))
                    expected=[r for r in documentary['text']['projectSimilarity']if r.get('project_a')==PROJECT or r.get('project_b')==PROJECT or r.get('project_id')]
                    expected_values=sorted((r[key]for r in expected if r.get(key)is not None),reverse=True)
                    check('project_similarity_count_'+variant,len(data)==len(expected_values))
                    check('project_similarity_values_'+variant,all(abs(number(r['value'])-v)<1e-10 for r,v in zip(data,expected_values)))
                await route('texts',{'textview':'terms','doc':'project'})
                check('aggregate_ten_passports','десяти паспортов'in await page.locator('#main').inner_text())
                for document in documentary['text']['documents']:
                    await route('texts',{'textview':'contexts','doc':document['document_id']})
                    check('context_lazy_load_'+document['document_id'],await page.locator('.dataeconomy-load-error').count()==0)
                await route('texts',{'textview':'contexts','doc':'np_23'})
                await page.get_by_label('Поиск в контекстах',exact=True).fill('данн');await page.get_by_role('button',name='Найти',exact=True).click();await ready(state={'q':'данн'})
                data=csv_rows(await download(panel('Контексты выбранного документа')))
                check('context_search_csv',bool(data)and all('данн'in r['context'].lower()for r in data))
                await route('overview');await page.locator('.dataeconomy-report>summary').click()
                check('original_report_expands',await page.locator('.dataeconomy-report[open]').count()==1)
                text=await page.locator('#main').inner_text()
                check('original_report_wording',any(b.get('text','')[:100]in text for b in report['pages']['overview']['blocks']if b.get('type')=='paragraph'and b.get('text')))
                await route('methods');data=csv_rows(await download(panel('Применимость методов')))
                check('all39_methods_present',len(data)==39)
                check('all_method_statuses_present',all(r['Статус']for r in data))
            await group('documentary_flow',documentary_flow)

            async def calculators_flow():
                await route('lab',{'tool':'cascade'})
                for key,val in [('eligible','1000'),('accessible','800'),('started','500'),('completed','400')]:await page.locator('input[name="'+key+'"]').fill(val)
                await page.get_by_role('button',name='Рассчитать',exact=True).click();await ready(state={'completed':'400'})
                nums=await values();check('cascade_denominators',nums==[80,62.5,80,40])
                data=await button_download('Скачать расчёт CSV');check('cascade_export',number(data[0]['populationCompletionPercent'])==40)
                await page.locator('input[name=eligible]').fill('');await page.get_by_role('button',name='Рассчитать',exact=True).click();await ready(state={'eligible':' '})
                check('blank_input_not_defaulted',await page.locator('input[name=eligible]').input_value()==''and await page.get_by_role('button',name='Скачать расчёт CSV',exact=True).count()==0)
                await route('lab',{'tool':'cascade','eligible':'1000','accessible':'0','started':'0','completed':'0'})
                data=await button_download('Скачать расчёт CSV');check('cascade_zero_denominators',number(data[0]['startPercent'])is None and number(data[0]['populationCompletionPercent'])==0)
                await route('lab',{'tool':'cost'});data=await button_download('Скачать расчёт CSV');check('completed_service_cost',number(data[0]['unitCost'])==1250)
                await route('lab',{'tool':'cost','completedServices':'0'});check('zero_completed_cost_rejected',await page.get_by_role('button',name='Скачать расчёт CSV',exact=True).count()==0)
                await route('lab',{'tool':'lifecycle'});data=await button_download('Скачать расчёт CSV');check('lifecycle_cost',number(data[0]['totalCost'])==21000000 and number(data[0]['unitCost'])==42)
                check('lifecycle_no_hidden_discount',data[0]['discounting']=='not_applied')
                await route('lab',{'tool':'did','treatedBefore':'-5','treatedAfter':'0','comparisonBefore':'2','comparisonAfter':'3'});data=await button_download('Скачать расчёт CSV');check('DID_signed',number(data[0]['difference'])==4)
                await route('projections',{'source':'62751'});check('unverified_baseline_empty',await page.locator('input[name=baseValue]').input_value()==''and await panel('Условный путь к цели').count()==0)
                await page.locator('input[name=baseValue]').fill('150');await page.locator('input[name=goal]').fill('180');await page.get_by_role('button',name='Рассчитать',exact=True).click();await ready(state={'baseValue':'150','goal':'180'})
                check('index_above100_scenario',await panel('Условный путь к цели').locator('.chart-svg').count()==1)
                data=csv_rows(await download(panel('Условный путь к цели')));check('scenario_user_basis',data[0]['baseline_kind']=='user_assumption'and number(data[0]['value'])==150 and number(data[-1]['value'])==180)
                await page.locator('input[name=baseValue]').fill('');await page.get_by_role('button',name='Рассчитать',exact=True).click();await ready(state={'baseValue':' '})
                check('blank_scenario_baseline_not_replaced',await page.locator('input[name=baseValue]').input_value()==''and await panel('Условный путь к цели').count()==0)
                for sid in ['62809','62868']:
                    await route('projections',{'source':sid});check('unresolved_unit_no_goal_'+sid,await page.locator('input[name=goal]').input_value()=='')
                for sid in ['62814','62816','62761','62815','63145']:
                    await route('projections',{'source':sid,'baseValue':'50','goal':'150','baseYear':'2025','goalYear':'2030'})
                    check('bounded_scenario_rejects150_'+sid,await panel('Условный путь к цели').count()==0 and await page.locator('input[name=goal]').get_attribute('max')=='100')
            await group('calculators_flow',calculators_flow)

            async def library_flow():
                await route('library')
                urls=await page.locator('#main a[href]').evaluate_all('(xs)=>[...new Set(xs.map(x=>x.href).filter(h=>h.startsWith(location.origin)&&!h.includes("#")))]')
                for url in urls:
                    response=await context.request.get(url);check('library_'+url.rsplit('/',1)[-1],response.status==200,{'status':response.status})
            await group('library_flow',library_flow)
            fault=await context.new_page();calls={'n':0}
            async def fail_once(route):
                calls['n']+=1
                if calls['n']==1:await route.fulfill(status=503,body='temporary test fault')
                else:await route.continue_()
            path=sources['62766']['downloads']['observations'].lstrip('./')
            await fault.route('**/'+path+'*',fail_once)
            await fault.goto(args.base+'#/projects/'+PROJECT+'/explorer?source=62766&year=2025')
            await fault.locator('.dataeconomy-load-error').wait_for()
            check('lazy_retry_available',await fault.get_by_role('button',name='Повторить загрузку',exact=True).count()==1)
            await fault.get_by_role('button',name='Повторить загрузку',exact=True).click();await fault.locator('.dataeconomy-load-error').wait_for(state='detached')
            check('lazy_retry_preserves_filter',await fault.get_by_label('Год',exact=True).input_value()=='2025')
            check('lazy_retry_refetches',calls['n']==2);await fault.close()

            for state,phrase in [('no_common_publication_period','нет общего периода'),('insufficient_observed_matrix','недостаточно наблюдаемых'),('constant_feature','не различается'),('no_earlier_complete_panel','Нет сопоставимой общей панели предыдущего периода')]:
                unavailable=await context.new_page()
                packet=json.loads(json.dumps(analytics))
                if state=='no_earlier_complete_panel':packet['multivariate']['temporal']={'status':state}
                else:packet['multivariate']={'status':state}
                async def replace_analytics(route):await fulfill_json(route,packet)
                await unavailable.route('**/data/projects/data_economy/analytics.json*',replace_analytics)
                await unavailable.goto(args.base+'#/projects/'+PROJECT+'/regions?regionview=stability')
                await unavailable.wait_for_function("document.querySelector('#main')?.dataset.ready==='true'&&!!document.querySelector('.dataeconomy-page')")
                text=await unavailable.locator('#main').inner_text()
                check('multivariate_unavailable_reason_'+state,phrase in text)
                check('multivariate_unavailable_not_false_clustering_'+state,'Нет допустимого разбиения'not in text)
                if state=='no_earlier_complete_panel':
                    check('temporal_absence_keeps_other_checks',await unavailable.get_by_role('heading',name='Начальное состояние алгоритма',exact=True).count()==1 and await unavailable.get_by_role('heading',name='Поочерёдное исключение признаков',exact=True).count()==1)
                    check('temporal_absence_has_no_numeric_export',await unavailable.get_by_role('button',name='Скачать временную проверку CSV',exact=True).count()==0)
                await unavailable.close()

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
            await route('texts',{'textview':'contexts','doc':'np_23'})
            await panel('Контексты выбранного документа').scroll_into_view_if_needed()
            check('mobile_context_width_'+str(width),await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
            context_scroll=panel('Контексты выбранного документа').locator('.table-scroll')
            check('mobile_context_table_scroll_'+str(width),await context_scroll.evaluate('e=>e.scrollWidth>e.clientWidth'))
            await context_scroll.evaluate('e=>e.scrollLeft=e.scrollWidth')
            check('mobile_context_last_columns_reachable_'+str(width),await context_scroll.evaluate('e=>e.scrollLeft>0'))
            await context_scroll.evaluate('e=>e.scrollLeft=0')
            await page.screenshot(path=str(output/f'contexts-mobile-{width}.png'))
            await route('regions',{'source':'62766'})
            chart=page.locator('.dataeconomy-wide-chart').first
            check('mobile_chart_scroll_'+str(width),await chart.evaluate('e=>e.scrollWidth>e.clientWidth'))
            await chart.evaluate('e=>e.scrollLeft=e.scrollWidth')
            check('mobile_chart_scroll_works_'+str(width),await chart.evaluate('e=>e.scrollLeft>0'))
            await page.screenshot(path=str(output/f'regions-mobile-{width}.png'))
            await route('lab',{'tool':'lifecycle'})
            check('mobile_lifecycle_inputs_'+str(width),await page.locator('input[name="annualServices"]').input_value()=='100000')
            check('mobile_lab_width_'+str(width),await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
            await page.screenshot(path=str(output/f'lifecycle-mobile-{width}.png'))
            for view in ['pca','matrix','stability','outliers']:
                await route('regions',{'regionview':view})
                check('mobile_multivariate_'+view+'_'+str(width),await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                await page.screenshot(path=str(output/f'{view}-mobile-{width}.png'))


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
