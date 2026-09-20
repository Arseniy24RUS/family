#!/usr/bin/env python3
"""Additional browser tests for v1.1. Real local modules/workers; virtual file transport optional.
Run: python tests/browser_upgrade.py --virtual --browser /usr/bin/chromium --output /tmp/semya-qa
Virtual mode is not a verification of GitHub Pages, network fetch or upstream XLSX.
"""
import argparse,asyncio,json,mimetypes,subprocess
from pathlib import Path
from urllib.parse import urlparse,unquote
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
ROUTES=['projections','projections?r=77&compare=50','projections?source=data_22&r=78&members=1','projections?tab=map','projections?source=data_22&tab=validation','projections?tab=data','projections?r=90','population','population?r=demo','population?r=demo&tab=pyramid','population?r=demo&tab=components','population?r=demo&tab=data','population?r=demo&tab=sources','population?r=demo&scenario=custom','authors']
async def execute(args):
 out=Path(args.output);out.mkdir(parents=True,exist_ok=True);checks=[];errors=[];external=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,executable_path=args.browser)
  context=await browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True,reduced_motion='reduce')
  async def serve(route):
   part=unquote(urlparse(route.request.url).path.lstrip('/'));f=(ROOT/'docs'/part).resolve()
   if (ROOT/'docs').resolve() not in f.parents or not f.is_file():await route.fulfill(status=404,body='Missing');return
   await route.fulfill(body=f.read_bytes(),content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
  if args.virtual:await context.route('https://semya.test/**',serve)
  # Explicitly test graceful portrait failure, not invent a successful remote download.
  async def portrait_failure(route):external.append(route.request.url);await route.abort()
  await context.route('https://cloud.idrras.ru/**',portrait_failure);await context.route('https://xn--h1aauh.xn--p1ai/**',portrait_failure)
  page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  if args.virtual:await page.set_content((ROOT/'docs/index.html').read_text().replace('<head>','<head><base href="https://semya.test/">'),wait_until='networkidle')
  else:await page.goto(args.base)
  await page.wait_for_selector('#main[data-ready=true]')
  async def go(route):
   print('GO',route,flush=True)
   await page.evaluate('(r)=>location.hash="#/"+r',route);await page.wait_for_timeout(180)
   await page.wait_for_function('(r)=>document.querySelector("#main").dataset.page===r && !document.querySelector("#main").hasAttribute("aria-busy")',arg=route.split('?')[0])
   assert not await page.locator('.error-view').count(),route
  assert 'Экспертиза национального проекта' in await page.title()
  assert await page.locator('.sidebar-footer').count()==0
  links=await page.locator('.institution-link').evaluate_all('(a)=>a.map(x=>[x.href,x.querySelector("img").naturalWidth])')
  await page.locator('.institution-link').last.scroll_into_view_if_needed();await page.wait_for_timeout(150)
  links=await page.locator('.institution-link').evaluate_all('(a)=>a.map(x=>[x.href,x.querySelector("img").naturalWidth])')
  assert [i[0] for i in links]==['https://new.ras.ru/','https://www.fnisc.ru/','https://isd-ras.ru/']
  assert all(i[1]>0 for i in links),links
  checks.append({'check':'identity_logo_order_all_logos_loaded_footer_removed','pass':True})
  for size in [{'width':1440,'height':1000},{'width':390,'height':844}]:
   await page.set_viewport_size(size)
   for route in ROUTES:
    await go(route)
    assert await page.locator('h1').count()==1,route
    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+2'),route+' overflow '+str(size)
    checks.append({'check':'route','viewport':size['width'],'route':route,'pass':True})
  await page.set_viewport_size({'width':1440,'height':1000})
  await go('projections?r=77&compare=50')
  assert await page.locator('.chart-svg').count()>0
  await page.get_by_label('Показатель',exact=True).select_option('data_22');await page.wait_for_timeout(200)
  assert 'data_22' in await page.evaluate('location.hash')
  await page.get_by_label('Отдельные модели',exact=True).check();await page.wait_for_timeout(200)
  assert 'members=1' in await page.evaluate('location.hash')
  checks.append({'check':'indicator_region_comparison_models_and_source_switch','pass':True})
  await go('projections?tab=map')
  assert await page.locator('[data-region]').count()==89
  await page.locator('[data-region="78"]').focus();await page.keyboard.press('Enter');await page.wait_for_timeout(200)
  assert 'r=78' in await page.evaluate('location.hash') and 'tab=trajectory' in await page.evaluate('location.hash')
  checks.append({'check':'forecast_map_keyboard_drilldown','pass':True})
  await go('projections')
  async with page.expect_download() as d:await page.get_by_role('button',name='Расчёт, входы и параметры JSON',exact=True).click()
  await (await d.value).save_as(out/'indicator.json')
  subprocess.run(['python',str(ROOT/'scripts/reproduce_projection.py'),'indicator',str(out/'indicator.json')],check=True,capture_output=True)
  checks.append({'check':'indicator_export_reproduced_by_python','pass':True})
  for ext in ['SVG','PNG']:
   async with page.expect_download() as d:await page.locator('.figure-tools').first.get_by_role('button',name=ext,exact=True).click()
   f=out/('forecast.'+ext.lower());await (await d.value).save_as(f);assert f.stat().st_size>100
  checks.append({'check':'indicator_svg_png_download','pass':True})
  await go('population')
  assert 'Возрастная база' in await page.locator('#main').inner_text()
  await page.get_by_role('button',name='Открыть учебный пример').click();await page.wait_for_timeout(300)
  assert 'УЧЕБНЫЙ ПРИМЕР' in await page.locator('#main').inner_text()
  checks.append({'check':'missing_inputs_never_fabricated_and_demo_opt_in','pass':True})
  await go('population?r=demo&scenario=custom')
  before=await page.locator('.stat strong').nth(1).inner_text()
  await page.get_by_label('СКР к концу 2030: множитель',exact=True).fill('1.3')
  await page.get_by_label('Изменение ОПЖ к 2030, лет',exact=True).fill('2')
  await page.get_by_label('Миграционное сальдо: множитель',exact=True).fill('0.5')
  await page.get_by_role('button',name='Рассчитать сценарий',exact=True).click();await page.wait_for_timeout(250)
  await page.wait_for_function('(old)=>!document.querySelector("#main").hasAttribute("aria-busy") && document.querySelectorAll(".stat strong")[1]?.textContent!==old',arg=before)
  after=await page.locator('.stat strong').nth(1).inner_text();assert before!=after
  assert not await page.locator('.note.warning').filter(has_text='Расчёт остановлен').count()
  async with page.expect_download() as d:await page.get_by_role('button',name='Скачать воспроизводимый JSON').click()
  await (await d.value).save_as(out/'cohort.json');o=json.loads((out/'cohort.json').read_text());assert o['options']['fertility_scale_end']==1.3 and len(o['result']['months'])==72
  subprocess.run(['python',str(ROOT/'scripts/reproduce_projection.py'),'cohort',str(out/'cohort.json')],check=True,capture_output=True)
  checks.append({'check':'custom_scenario_worker_export_full_python_parity','pass':True})
  await go('population?r=demo&tab=pyramid')
  await page.get_by_label('Месяц возрастной структуры',exact=True).select_option('2026-01');await page.wait_for_timeout(200)
  assert '2026-02-01' in await page.locator('#main').inner_text()
  assert await page.locator('.pyramid-wrap rect[tabindex]').count()==42
  await page.locator('.pyramid-wrap rect[tabindex]').first.focus();assert 'Базовая дата' in await page.locator('#tooltip').inner_text()
  checks.append({'check':'pyramid_month_selection_and_accessible_values','pass':True})
  async with page.expect_download() as d:await page.get_by_role('button',name='Все возраста и месяцы CSV',exact=True).click()
  await (await d.value).save_as(out/'ages.csv');assert len((out/'ages.csv').read_text().splitlines())==7273
  checks.append({'check':'age_export_all_101_ages_72_months','pass':True})
  await page.get_by_text('Загрузить свой расчётный файл',exact=True).click()
  await page.get_by_label('Загрузить входной JSON',exact=True).set_input_files(out/'cohort.json');await page.wait_for_timeout(300)
  assert 'r=uploaded' in await page.evaluate('location.hash')
  assert 'Локальный файл пользователя' in await page.locator('#main').inner_text()
  checks.append({'check':'round_trip_local_import_no_server_upload','pass':True})
  await go('authors');await page.wait_for_timeout(200)
  assert await page.locator('.author-card').count()==4
  assert await page.locator('.author-card h2').all_text_contents()==['РостовскаяТамара Керимовна','СитковскийАрсений Михайлович','СинельниковАлександр Борисович','АрхангельскийВладимир Николаевич']
  assert await page.locator('.author-photo .initials').count()==4
  checks.append({'check':'authors_order_official_links_portrait_failure_fallback','pass':True})
  for route,name in [('map?source=data_20','map'),('projections','forecast'),('population?r=demo&tab=pyramid','cohort_demo'),('authors','authors')]:
   await go(route);await page.screenshot(path=str(out/(name+'_desktop.png')),full_page=False)
  await page.locator('.institution-link').last.scroll_into_view_if_needed();await page.screenshot(path=str(out/'institutions_desktop.png'))
  await page.set_viewport_size({'width':390,'height':844})
  for route,name in [('projections','forecast'),('population?r=demo&tab=pyramid','cohort_demo'),('authors','authors')]:
   await go(route);await page.screenshot(path=str(out/(name+'_mobile.png')))
  await page.get_by_role('button',name='Открыть меню',exact=True).click();await page.locator('.institution-link').last.scroll_into_view_if_needed();await page.screenshot(path=str(out/'institutions_mobile.png'))
  await page.keyboard.press('Escape');assert not await page.locator('body').evaluate('(b)=>b.classList.contains("nav-open")')
  checks.append({'check':'new_nav_and_logo_mobile_keyboard_close','pass':True})
  assert not errors,errors
  await browser.close()
 report={'mode':'virtual_files' if args.virtual else 'http','browser':'Chromium/Playwright','checks':checks,'page_errors':errors,'portrait_requests_forced_unavailable':len(external),'not_tested':['GitHub-hosted deployment','live EMISS','live upstream XLSX/CSV retrieval','actual author photo pixels']}
 (out/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('PASS upgrade:',len(checks),'checks; page errors:',len(errors))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--virtual',action='store_true');p.add_argument('--browser',default='/usr/bin/chromium');p.add_argument('--base',default='http://localhost:8080/');p.add_argument('--output',default='/tmp/semya-upgrade-qa');asyncio.run(execute(p.parse_args()))
