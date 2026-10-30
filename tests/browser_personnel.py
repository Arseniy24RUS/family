"""HTTP acceptance tests for the completed Personnel project and shared navigation.

Uses ordinary Playwright: Browser plugin not available in the implementation session.
Screenshots and exported QA files are written outside the repository.
"""
import csv
import io
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
PAGES=['overview','framework','logic','audit','targets','map','regions','finance','network','texts','domains','causal','proposals','lab','explorer','library','updates','projections','population','structure','methods']

async def run(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    results=[];errors=[];http_errors=[];downloads=[];requests=[]
    def check(name,condition,detail=None):
        results.append({'name':name,'passed':bool(condition),'detail':detail})
        if not condition:print('FAIL:',name,detail,flush=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,executable_path=args.browser or None,args=['--no-sandbox'])
        context=await browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True,locale='ru-RU',timezone_id='Europe/Moscow')
        page=await context.new_page()
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.on('console',lambda msg:errors.append(msg.text) if msg.type=='error' else None)
        page.on('response',lambda resp:http_errors.append({'url':resp.url,'status':resp.status}) if resp.status>=400 else None)
        page.on('request',lambda req:requests.append(req.url))
        async def ready():
            await page.wait_for_function("document.querySelector('#main')?.dataset.ready==='true'||!!document.querySelector('.error-view')",timeout=30000)
            if await page.locator('.error-view').count():raise AssertionError(await page.locator('.error-view').inner_text())
        async def route(name,query='',project='personnel'):
            target='#/'+name if project=='family' else '#/projects/'+project+'/'+name
            await page.goto(args.base+target+query,wait_until='domcontentloaded')
            await ready()
            await page.wait_for_function('([p,s])=>document.querySelector("#main")?.dataset.project===p&&document.querySelector("#main")?.dataset.page===s',arg=[project,name])
        async def select(label,val):
            await page.get_by_label(label,exact=True).select_option(val)
            await ready()
            await page.wait_for_function('([label,value])=>document.querySelector(`select[aria-label="${label}"]`)?.value===value',arg=[label,val])
        async def closed_mobile_navigation(width):
            # Resizing across the mobile breakpoint starts the sidebar's CSS
            # transition. Main content readiness alone does not end that motion.
            await page.wait_for_function('''() => {
                const sidebar=document.querySelector('#sidebar');
                return !document.body.classList.contains('nav-open') && sidebar?.inert
                    && sidebar.getBoundingClientRect().right<=0
                    && sidebar.getAnimations().every(a=>a.playState!=='running');
            }''')
            state=await page.locator('#sidebar').evaluate('''sidebar => ({
                right:sidebar.getBoundingClientRect().right,
                inert:sidebar.inert,
                navOpen:document.body.classList.contains('nav-open'),
                runningAnimations:sidebar.getAnimations().filter(a=>a.playState==='running').length
            })''')
            check('mobile_navigation_closed_'+str(width),state['right']<=0 and state['inert']
                and not state['navOpen'] and state['runningAnimations']==0,state)
        for name in PAGES:
            try:
                await route(name)
                content=await page.locator('#main').inner_text()
                check('desktop_route_'+name,len(content)>350,{'characters':len(content),'title':await page.title()})
                check('desktop_width_'+name,await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                check('no_authors_'+name,await page.locator('#sidebar a[href$="/authors"]').count()==0)
                if name in ['overview','map','finance','network','texts','projections']:
                    await page.screenshot(path=str(output/(name+'-desktop.png')),full_page=False)
            except Exception as exc:
                check('desktop_route_'+name,False,str(exc))
        # Ordinary route loading must not fetch the full text corpus.
        check('corpus_is_lazy',not any('/text/' in u or 'documentary_full.json' in u for u in requests))
        if not args.smoke_only:

            def panel(title):
                return page.locator('section.panel').filter(has=page.get_by_role('heading',name=title,exact=True))
            async def download_from(locator,ext):
                async with page.expect_download() as waiting:
                    await locator.get_by_role('button',name=ext,exact=True).click()
                download=await waiting.value;dest=output/download.suggested_filename;await download.save_as(dest)
                body=dest.read_bytes();downloads.append({'name':dest.name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
                return body
            await route('explorer','?source=62907')
            await select('Периодичность','annual')
            observed=panel('Наблюдения и исходные значения')
            text=await observed.inner_text()
            check('annual_fact_is_not_december','81,3' in text and '80,2' not in text)
            check('annual_filter_has_one_record',await observed.locator('tbody tr').count()==1)
            bookmark=page.url
            await page.reload();await ready()
            check('filters_survive_reload',await page.get_by_label('Периодичность',exact=True).input_value()=='annual' and page.url==bookmark)
            await select('Показатель','63238')
            await select('Год','2026')
            text=await panel('Наблюдения и исходные значения').inner_text()
            check('survey_periods_are_quarterly','Квартал' in text and 'Месяц' in text)
            check('quarterly_source_period_preserved','Исходный период' in text)
            await route('targets','?source=63038')
            annual=panel('Основание годового сопоставления')
            check('ratio_above_100_retained','112,89' in await annual.inner_text())
            check('annual_equivalent_explained','Годовой эквивалент по методике' in await annual.inner_text())
            check('all_eleven_targets',await page.get_by_label('Паспортный показатель',exact=True).locator('option').count()==11)
            await select('Паспортный показатель','2.14.Л1.1')
            check('ambiguous_zero_qualified','Паспортный нуль требует интерпретации' in await panel('Целевая траектория 2025–2030').inner_text())
            check('missing_plan_not_zero','Плановое значение не опубликовано' in await panel('Целевая траектория 2025–2030').inner_text())
            await select('Паспортный показатель','2.14.Л1.2')
            check('conditional_mapping_qualified','условный статус' in await page.locator('#main').inner_text())
            await route('map')
            check('map_is_preproject_context','до начала проекта' in await page.locator('#main').inner_text())
            await select('Регион','77')
            await select('Сравнить с регионом','78')
            check('regional_comparison','compare=78' in page.url and 'Разность' in await page.locator('.comparison-reading').inner_text())
            check('context_national_is_source_value','2,5%' in await page.locator('.atlas-aside').inner_text())
            await select('Федеральный округ','Центральный федеральный округ')
            check('district_filter_updates_count',await page.get_by_label('Регион',exact=True).locator('option').count()==19)
            body=await download_from(page.locator('.figure').first,'CSV')
            rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig')),delimiter=';'))
            check('map_csv_respects_district',len(rows)==18 and all(r['Год']=='2024' and r['Роль']=='Исходный контекст' for r in rows))
            await select('Шкала карты','continuous')
            check('continuous_map_scale','scale=continuous' in page.url and await page.locator('.map-legend').count()==1)
            await page.get_by_role('button',name='Плиточная карта',exact=True).click();await ready()
            check('tile_map','view=tile' in page.url)
            await route('regions','?r=77')
            check('regional_profile_uses_2024','2024' in await panel('г. Москва').inner_text())
            await route('finance')
            before=await page.locator('.figure svg').first.text_content()
            await select('Год финансового плана','2030')
            after=await page.locator('.figure svg').first.text_content()
            check('finance_year_changes_chart',before!=after and 'finyear=2030' in page.url)
            await select('Единица суммы','million')
            check('finance_units','money=million' in page.url and 'млн' in await page.locator('.figure svg').first.text_content())
            check('finance_horizons_separated','2031–2036' in await panel('Общий и полный горизонты паспортов').inner_text())
            for ext in ['SVG','PNG','CSV']:
                body=await download_from(page.locator('.figure').first,ext)
                check('export_'+ext,len(body)>100)
                if ext=='SVG':
                    text=body.decode('utf-8');check('svg_has_embedded_fonts',text.count('data:font/woff;base64,')==3)
                    check('svg_personnel_identity','Кадры' in text and '#cf4520' in text.lower())
                    check('svg_finance_unit_and_period','млн руб.' in text and '2030' in text)
                if ext=='CSV':
                    rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig')),delimiter=';'))
                    check('finance_csv_unit_period',len(rows)==4 and all(r['unit']=='млн руб.' and r['period']=='2030' for r in rows))
            await route('projections','?source=62907')
            step=page.get_by_label('Ежегодное абсолютное изменение',exact=True)
            await step.fill('2');await step.press('Tab');await ready()
            await page.wait_for_function("new URLSearchParams(location.hash.split('?')[1]).get('step')==='2'")
            check('scenario_parameter_changes_result','91,3' in await page.locator('#main').inner_text() and 'step=2' in page.url)
            await page.reload();await ready();check('scenario_parameter_bookmark',await step.input_value()=='2')
            await route('projections','?source=63038&step=0')
            text=await page.locator('#main').inner_text()
            check('over100_scenario_is_valid','112,89' in text and 'выводит траекторию за область' not in text)
            check('attained_target_not_recommended_to_decrease','сохраняет достигнутый уровень' in text)
            await route('projections','?source=63363&step=50')
            text=await page.locator('#main').inner_text()
            check('bounded_share_scenario_warns','выводит траекторию за область' in text and '250,1766' in text)
            await route('lab','?calc=distribution')
            check('lab_context_median','2,4' in await page.locator('.stats .stat').nth(2).inner_text())
            await select('Расчёт','annual')
            check('lab_five_annual_comparisons',await panel('Самостоятельный расчёт разности').locator('tbody tr').count()==5)
            await route('network')
            check('network_weights_have_source_meaning','Паспортный вес' in await page.locator('#main').inner_text())
            await select('Основание связи','shared')
            check('network_layer_filter','layer=shared' in page.url)
            check('network_all_67_shared_links','из67' in (await panel('Все связи выбранного слоя').inner_text()).replace(' ',''))
            await route('texts')
            await select('Представление','similarity')
            check('text_six_passport_pairs',await panel('6 пар документов').locator('tbody tr').count()==6)
            await select('Представление','contexts')
            await ready()
            check('text_context_lazy_request',any('/data/projects/personnel/text/' in u for u in requests))
            check('text_context_rows',await panel('Ключевое слово в контексте').locator('tbody tr').count()>0)
            check('no_full_corpus_request',not any('documentary_full.json' in u for u in requests))
            await route('audit')
            await select('Доступность','no_table_link')
            check('audit_unmapped_count',await panel('Реестр показателей').locator('tbody tr').count()==2)
            await route('library')
            local_links=await page.locator('#main a[download]').evaluate_all('(els)=>els.map(e=>e.href)')
            for url in local_links:
                response=await context.request.get(url)
                check('library_link_'+url.split('/')[-1],response.status==200)
            await route('map','?r=77')
            await page.locator('.project-tab[data-project="youth_children"]').click();await ready()
            check('switch_to_youth_preserves_map_clears_filters',page.url.endswith('#/projects/youth_children/map'))
            await page.go_back();await ready();check('browser_back_restores_personnel','personnel/map' in page.url and 'r=77' in page.url)
            await page.locator('.project-tab[data-project="family"]').click();await ready()
            check('switch_to_family_preserves_map_clears_filters',page.url.endswith('#/map'))
        await page.set_viewport_size({'width':390,'height':844})
        await closed_mobile_navigation(390)
        for name in PAGES:
            try:
                await route(name)
                check('mobile_route_'+name,len(await page.locator('#main').inner_text())>350)
                check('mobile_width_'+name,await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                if name in ['overview','map','finance','network','texts']:
                    await page.screenshot(path=str(output/(name+'-mobile.png')),full_page=False)
            except Exception as exc:check('mobile_route_'+name,False,str(exc))
        await route('overview')
        await page.get_by_role('button',name='Открыть меню',exact=True).click()
        check('mobile_navigation_open',await page.locator('.workspace').evaluate('(e)=>e.inert'))
        check('mobile_menu_focused',await page.evaluate('document.querySelector("#sidebar").contains(document.activeElement)'))
        await page.keyboard.press('Escape')
        check('mobile_navigation_escape',await page.get_by_role('button',name='Открыть меню',exact=True).evaluate('(e)=>e===document.activeElement') and not await page.locator('.workspace').evaluate('(e)=>e.inert'))
        await page.get_by_role('button',name='Следующие нацпроекты',exact=True).click()
        await page.wait_for_function('document.querySelector(".project-nav").scrollLeft>0')
        check('mobile_project_scroll',True)
        await page.set_viewport_size({'width':320,'height':740})
        await closed_mobile_navigation(320)
        for name in ['overview','network','finance','projections']:
            await route(name);check('small_mobile_width_'+name,await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
        await page.screenshot(path=str(output/'projections-320.png'))
        # All generated text pages load independently without JavaScript modules.
        for name in PAGES:
            filename='index.html' if name=='overview' else name+'.html'
            response=await context.request.get(args.base+'research/projects/personnel/'+filename)
            text=await response.text()
            check('static_'+name,response.status==200 and '<h1>' in text and 'Кадры' in text)
        for project in ['long_active_life','tourism','youth_children','life_infrastructure','efficient_transport','environment','international_export','data_economy','competitive_economy']:
            await route('overview',project=project);check('other_project_'+project,await page.locator('#main h1').count()==1)
        # Sources offered by the Personnel library must exist under a project subpath.
        manifest=json.loads((ROOT/'docs/downloads/index.json').read_text(encoding='utf-8'))
        for item in manifest['files']:
            if not item['path'].startswith('projects/personnel/'):continue
            response=await context.request.get(args.base+'downloads/'+item['path'])
            body=await response.body()
            check('download_'+item['path'],response.status==200 and hashlib.sha256(body).hexdigest()==item['sha256'])
        check('no_javascript_errors',not errors,errors)
        check('no_http_errors',not http_errors,http_errors)
        await browser.close()
    report={'base':args.base,'browser_path':'Playwright; Browser plugin not available','checks':results,'errors':errors,'http_errors':http_errors,'downloads':downloads,'passed':all(r['passed'] for r in results)}
    (output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':len(results),'failed':sum(not r['passed'] for r in results)},ensure_ascii=False),flush=True)
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',required=True)
    parser.add_argument('--browser')
    parser.add_argument('--output',type=Path,default=Path('/tmp/personnel-browser-qa'))
    parser.add_argument('--smoke-only',action='store_true')
    asyncio.run(run(parser.parse_args()))
