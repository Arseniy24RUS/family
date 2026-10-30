"""Source-backed HTTP acceptance for Health Technologies.

Browser plugin not available. The established Playwright environment is used.
Flow: a project route opens, the reader selects a source or document, and the
rendered evidence, URL and downloadable table follow the selected input.
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

PROJECT='health_technologies'
PAGES=['overview','framework','logic','audit','targets','map','regions','finance',
       'network','texts','domains','causal','proposals','projections','population',
       'structure','methods','lab','explorer','library','updates']

def rows_of_csv(data):
    return list(csv.DictReader(io.StringIO(data.decode('utf-8-sig')),delimiter=';'))

def numeric(text):
    try:return float(''.join(str(text).split()).replace(',','.'))
    except (ValueError,TypeError):return None

async def run(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[];requests=[];http_errors=[];downloads=[]
    def check(name,passed,detail=None):
        checks.append({'name':name,'passed':bool(passed),'detail':detail})
        if not passed:print('FAIL',name,detail,flush=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,executable_path=args.browser or None,args=['--no-sandbox'])
        context=await browser.new_context(viewport={'width':1440,'height':1000},locale='ru-RU',timezone_id='Europe/Moscow',accept_downloads=True)
        page=await context.new_page()
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
        page.on('request',lambda r:requests.append(r.url))
        page.on('response',lambda r:http_errors.append({'url':r.url,'status':r.status}) if r.status>=400 else None)
        async def get_json(path):
            return await published_json(context, args.base, path)
        stat=await get_json('data/projects/'+PROJECT+'/statistics.json')
        doc=await get_json('data/projects/'+PROJECT+'/documentary.json')
        report=await get_json('data/projects/'+PROJECT+'/expertise.json')
        sources={s['id']:s for s in stat['sources']}
        async def ready(name=None,state=None):
            await page.wait_for_function("document.querySelector('#main')?.dataset.ready==='true'||!!document.querySelector('.error-view')",timeout=30000)
            if await page.locator('.error-view').count():raise AssertionError(await page.locator('.error-view').inner_text())
            await page.wait_for_function('''([project,name,state])=>{
              const main=document.querySelector('#main');
              if(main?.dataset.project!==project||main.dataset.ready!=='true'||(name&&main.dataset.page!==name))return false;
              const actual=JSON.parse(document.querySelector('.healthtech-page')?.dataset.routeState||'{}');
              return !state||Object.entries(state).every(([k,v])=>String(actual[k]??'')===String(v));
            }''',arg=[PROJECT,name,state])
        async def route(name,params=None):
            await page.goto(args.base+'#/projects/'+PROJECT+'/'+name+('?' + urlencode(params) if params else ''),wait_until='domcontentloaded')
            await ready(name,params)
        async def choose(label,value,key):
            await page.get_by_label(label,exact=True).select_option(str(value))
            await ready(state={key:value})
        def panel(title):
            return page.locator('section.panel').filter(has=page.get_by_role('heading',name=title,exact=True))
        async def download(locator,kind):
            # Chromium throttles bursts of ten automatic file downloads.
            # A reader-paced interval tests the UI without that browser quota.
            await page.wait_for_timeout(1150)
            async with page.expect_download() as event:
                await locator.get_by_role('button',name=kind,exact=True).first.click()
            artifact=await event.value;dest=output/artifact.suggested_filename;await artifact.save_as(dest)
            data=dest.read_bytes();downloads.append({'name':dest.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()});return data

        for name in PAGES:
            try:
                await route(name)
                text=await page.locator('#main').inner_text()
                check('desktop_route_'+name,len(text)>350,{'title':await page.title(),'characters':len(text)})
                check('desktop_width_'+name,await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                check('no_authors_'+name,await page.locator('#sidebar a[href$="/authors"]').count()==0)
                check('no_load_error_'+name,await page.locator('.healthtech-load-error').count()==0)
                if name in ['overview','targets','finance','network','texts','population','map','projections']:
                    await page.screenshot(path=str(output/(name+'-desktop.png')))
            except Exception as e:check('desktop_route_'+name,False,str(e))
        check('twelve_project_tabs',await page.locator('.project-tab').count()==12)
        check('brand_color',await page.locator('html').evaluate("e=>e.style.getPropertyValue('--project-color')")=='#0A8BBF')
        check('corpus_not_eagerly_loaded',not any('/documentary-text/' in r or 'documentary_full.json' in r for r in requests))

        if not args.smoke_only:
            try:
                for sid,source in sources.items():
                    await route('explorer',{'source':sid})
                    visible=await page.locator('.healthtech-page>.stats .stat strong').all_text_contents()
                    expected=len(source['national'])
                    check('source_rows_'+sid,numeric(visible[0])==expected,{'expected':expected,'displayed':visible[0]})
                    check('source_usable_'+sid,numeric(visible[2])==sum(r.get('analytical_value') is not None for r in source['national']))
                    check('source_unit_'+sid,(source.get('display_unit') or source['unit']) in await page.locator('#main').inner_text() or not expected)
                    if expected:
                        data=rows_of_csv(await download(panel('Исходные наблюдения'),'CSV'))
                        check('source_csv_rows_'+sid,len(data)==expected)
                        numeric_csv=sum(numeric(r['Исходное число']) is not None for r in data)
                        check('source_csv_raw_'+sid,numeric_csv==sum(r['value'] is not None for r in source['national']))
                        excluded_csv=sum(r['Статус']=='Не используется в расчётах' for r in data)
                        check('source_csv_exclusions_'+sid,excluded_csv==sum(bool(r['excluded']) for r in source['national']))
                await route('targets',{'source':'62986'})
                annual_text=await panel('Сопоставимый годовой факт и план').inner_text()
                check('annual_fact_4_55','4,55' in annual_text and '1,5' in annual_text and '3,05' in annual_text)
                check('annual_source_not_formal_attainment','не является официальной оценкой' in await page.locator('#main').inner_text())
                await choose('Показатель','62985','source')
                check('unit_conflict_warning','противоречие' in await page.locator('#main').inner_text())
                await choose('Показатель','63059','source')
                check('methodology_break_visible','методик' in (await page.locator('#main').inner_text()).lower())
                await route('explorer',{'source':'63132'})
                await choose('Год','2026','year')
                table_data=rows_of_csv(await download(panel('Исходные наблюдения'),'CSV'))
                check('year_filter_export',bool(table_data) and all(r['Период'].startswith('2026') for r in table_data))
                before=page.url
                await choose('Периодичность','monthly','frequency')
                await page.go_back();await ready(state={'year':'2026'})
                check('back_restores_filter',page.url==before and await page.get_by_label('Год',exact=True).input_value()=='2026')
                for fp,expected in [('С',6),('С1',5),('С2',3),('С3',2),('С4',2),('С5',3)]:
                    await route('audit',{'fp':fp})
                    shown=await page.locator('.healthtech-page>.stats .stat strong').first.inner_text()
                    check('registry_filter_'+fp,numeric(shown)==expected)
                await route('audit')
                source_table=panel(next(t['title'] for t in report['tables'] if t['number']==2))
                await source_table.get_by_role('button',name='Уровень проекта',exact=True).click()
                await source_table.get_by_role('button',name='Уровень проекта ↑',exact=True).click()
                source_row=source_table.locator('tbody tr').filter(has_text='НП, код С')
                source_link=source_row.locator('td').first.locator('a[data-source-id="fn_037"]')
                sorted_source=await source_link.get_attribute('href')
                source_title=await source_link.get_attribute('title')
                source_aria=await source_link.get_attribute('aria-label')
                await source_table.get_by_label('Поиск по таблице',exact=True).fill('НП, код С')
                exported=rows_of_csv(await download(source_table,'CSV'))
                expected_url=next(s['url'] for s in report['sources'] if s['id']=='fn_037')
                check('cell_footnote_survives_sort_and_search',
                      sorted_source==expected_url and bool(source_title) and '37' in (source_aria or '')
                      and await source_table.locator('tbody tr a[data-source-id="fn_037"]').count()==1
                      and len(exported)==1 and exported[0]['Уровень проекта']=='НП, код С')
                await route('finance')
                data=rows_of_csv(await download(panel('Исходные суммы выбранного среза'),'CSV'))
                expected=next(f for f in doc['finance']['frames'] if f['id']=='passport_plan')['rows']
                check('exact_passport_amounts',len(data)==len(expected) and all(abs(numeric(r['План'])-v['value'])<1e-6 if v['value'] is not None else numeric(r['План']) is None for r,v in zip(data,expected)))
                check('finance_nulls_retained',sum(numeric(r['План']) is None for r in data)==8)
                figure=panel('Паспортное распределение').locator('.figure')
                svg_bytes=await download(figure,'SVG');png_bytes=await download(figure,'PNG')
                check('svg_export_source',b'<svg' in svg_bytes and 'млрд руб.'.encode() in svg_bytes and '#0A8BBF'.lower().encode() in svg_bytes.lower())
                check('png_export_signature',png_bytes.startswith(b'\x89PNG\r\n\x1a\n'))
                await choose('Документальная основа','budget_bill','frame')
                await choose('Год','2029','year')
                data=rows_of_csv(await download(panel('Исходные суммы выбранного среза'),'CSV'))
                check('budget_year_scope',all(r['Год']=='2029' for r in data))
                by_code={r['Строка']:r for r in data}
                check('budget_reserve_2029',numeric(by_code['Зарезервировано']['План'])==5613.6)
                check('explicit_budget_zero',numeric(by_code['С4']['План'])==0)
                check('budget_reserve_year_filter',await panel('Доля зарезервированных средств').locator('.chart-svg rect[tabindex]').count()==1)
                await page.screenshot(path=str(output/'finance-budget-desktop.png'))
                await route('network',{'layer':'weights'})
                text=await page.locator('#main').inner_text()
                check('unresolved_weight_explanation','не установлено' in text and 'Матрица подтверждённых влияний не строится' in text)
                data=rows_of_csv(await download(panel('Записи, требующие разрешения'),'CSV'))
                check('sixty_nine_unresolved_weights',len(data)==69 and all(r['Показатель']=='Получатель записи веса не установлен' for r in data))
                await route('network',{'layer':'structure'})
                data=rows_of_csv(await download(panel('Кандидаты внутри одного федерального проекта'),'CSV'))
                check('eighty_three_candidates',len(data)==83)
                check('candidate_status_honest',all(r['Основание связи']=='Общая принадлежность федеральному проекту' for r in data))

                for mode in ['themes','terms','similarity','projects','contexts','audit']:
                    await route('texts',{'textview':mode})
                    text=await page.locator('#main').inner_text()
                    check('text_mode_'+mode,len(text)>700 and await page.locator('.healthtech-load-error').count()==0)
                    check('text_independence_'+mode,'независимый расчёт платформы' in text)
                await route('texts',{'textview':'similarity'})
                cells=await page.locator('.chart-svg rect[tabindex]').count()
                check('six_by_six_similarity',cells==36,{'cells':cells})
                await route('texts',{'textview':'terms','doc':'np_33'})
                check('thirty_tfidf_terms',await page.locator('#main').get_by_text('из 30',exact=False).count()>0)
                await route('texts',{'textview':'projects'})
                await choose('Вариант расчёта','stemming','variant')
                check('stemming_selection',await page.get_by_label('Вариант расчёта',exact=True).input_value()=='stemming')
                variant_export=rows_of_csv(await download(panel('Межпроектная лексическая близость').locator('.figure'),'CSV'))
                check('text_export_identifies_variant',bool(variant_export) and all(r['variant']=='Русский стемминг' and 'Русский стемминг' in r['Название_визуализации'] for r in variant_export))
                await route('texts',{'textview':'terms','doc':'project'})
                check('aggregate_text_profile',await page.get_by_label('Документ',exact=True).input_value()=='project' and await page.locator('#main').get_by_text('из 30',exact=False).count()>0)
                for document in doc['text']['documents']:
                    did=document['document_id'];await route('texts',{'textview':'contexts','doc':did})
                    packet=await get_json(doc['text']['documentFiles'][did])
                    data=rows_of_csv(await download(panel('Контексты выбранного документа'),'CSV'))
                    check('context_document_'+did,len(data)==len(packet['kwic']))
                    check('context_provenance_'+did,all(r['source_url']==document['source_url'] and r['source_locator'] for r in data))
                await route('texts',{'textview':'contexts','doc':'np_33'})
                await choose('Тема','research','frame')
                data=rows_of_csv(await download(panel('Контексты выбранного документа'),'CSV'))
                check('keyword_theme_filter',bool(data) and all(r['frame_id']=='research' for r in data))
                await page.get_by_label('Поиск в контекстах',exact=True).fill('лекарств')
                await page.get_by_role('button',name='Найти',exact=True).click();await ready(state={'q':'лекарств'})
                data=rows_of_csv(await download(panel('Контексты выбранного документа'),'CSV'))
                check('context_query_filter',bool(data) and all('лекарств' in r['context'].lower() for r in data))
                await page.screenshot(path=str(output/'texts-context-desktop.png'))

                await route('projections',{'source':'62986'})
                await page.get_by_label('Условное целевое значение',exact=True).fill('20')
                await page.get_by_label('Год достижения',exact=True).fill('2030')
                await page.get_by_role('button',name='Рассчитать',exact=True).click();await ready(state={'goal':'20','goalYear':'2030'})
                check('conditional_goal_updates','20' in await page.locator('.healthtech-page>.stats').inner_text())
                await choose('Форма траектории','compound','curve')
                check('compound_curve_exists',await panel('Рассчитанная траектория').locator('path.data-line').count()==1)
                await route('projections',{'source':'63059'})
                check('no_ineligible_forecast',await page.get_by_label('Условное целевое значение',exact=True).count()==0)
                await route('lab',{'tool':'coverage'})
                await page.get_by_label('Получили технологию',exact=True).fill('240')
                await page.get_by_label('Имеют подтверждённые показания',exact=True).fill('1000')
                await page.get_by_role('button',name='Рассчитать',exact=True).click();await ready(state={'numerator':'240','denominator':'1000'})
                check('cohort_ratio_24',await page.locator('.healthtech-page>.stats .stat strong').first.inner_text()=='24 %')
                await route('lab',{'tool':'coverage','numerator':'1001','denominator':'1000'})
                check('impossible_cohort_rejected',await page.locator('.healthtech-page>.stats').count()==0)
                await route('lab',{'tool':'budget','patients':'100','currentCost':'1000','newCost':'1500'})
                check('conditional_budget_cost','50\u00a0000' in await page.locator('.healthtech-page>.stats').inner_text() or '50 000' in await page.locator('.healthtech-page>.stats').inner_text())
                await route('lab',{'tool':'changes','source':'63132'})
                check('matched_period_rows',await panel('Изменение при одинаковом временном окне').locator('tbody tr').count()>0)
                await route('lab',{'tool':'reconciliation'})
                reconciliation=await panel('Условная проверка денежного прокси и прироста').inner_text()
                check('commercialization_check_visible','357,28' in reconciliation and '249,59' in reconciliation and '292,615' in reconciliation)
                check('commercialization_limit_visible','не доказывает ошибку' in reconciliation)
                await route('map');check('no_invented_choropleth',await page.locator('.map-surface').count()==0)
                await route('library')
                same_origin=await page.locator('#main a[href]').evaluate_all('(xs)=>[...new Set(xs.map(x=>x.href).filter(h=>h.startsWith(location.origin)&&!h.includes("#")))]')
                for url in same_origin:
                    response=await context.request.get(url)
                    check('library_link_'+url.rsplit('/',1)[-1],response.status==200,{'status':response.status})
                await route('overview')
                await page.locator('.healthtech-report>summary').click()
                check('author_report_expands',await page.locator('.healthtech-report[open]').count()==1)
                check('report_source_identity',report['meta']['source_docx_sha256']=='49a0b61d96a414e72d22ededb26e6690fd45a5e17424135617b7bb9079fd8913')
            except Exception as e:check('interaction_flow',False,str(e))

            # Fresh page guarantees the lazy source packet is not cached.
            fault=await context.new_page();calls={'n':0}
            async def fault_once(route):
                calls['n']+=1
                if calls['n']==1:await route.fulfill(status=503,body='temporary test fault')
                else:await route.continue_()
            await fault.route('**/data/projects/health_technologies/series/62986.json*',fault_once)
            await fault.goto(args.base+'#/projects/'+PROJECT+'/explorer?source=62986&year=2025')
            await fault.locator('.healthtech-load-error').wait_for()
            check('lazy_failure_is_actionable',await fault.get_by_role('button',name='Повторить загрузку',exact=True).count()==1)
            await fault.get_by_role('button',name='Повторить загрузку',exact=True).click()
            await fault.locator('.healthtech-load-error').wait_for(state='detached')
            check('lazy_retry_preserves_filters',await fault.get_by_label('Год',exact=True).input_value()=='2025')
            check('lazy_retry_refetches',calls['n']==2)
            await fault.close()

        for width in [390,320]:
            await page.set_viewport_size({'width':width,'height':844})
            for name in PAGES:
                try:
                    await route(name)
                    check('mobile_width_'+str(width)+'_'+name,await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                    check('mobile_content_'+str(width)+'_'+name,len(await page.locator('#main').inner_text())>300)
                except Exception as e:check('mobile_'+str(width)+'_'+name,False,str(e))
            await route('overview')
            check('mobile_rail_scroll_'+str(width),await page.locator('.project-nav').evaluate('e=>e.scrollWidth>e.clientWidth'))
            await page.screenshot(path=str(output/('overview-mobile-'+str(width)+'.png')))
            await page.get_by_role('button',name='Открыть меню',exact=True).click()
            check('mobile_menu_opens_'+str(width),await page.locator('body').evaluate("e=>e.classList.contains('nav-open')"))
            await page.locator('#sidebar a[data-route="finance"]').click();await ready('finance')
            check('mobile_menu_navigates_'+str(width),not await page.locator('body').evaluate("e=>e.classList.contains('nav-open')"))
            await page.screenshot(path=str(output/('finance-mobile-'+str(width)+'.png')))

        check('no_console_errors',not errors,errors)
        check('no_unexpected_http_errors',not http_errors,http_errors)
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
