#!/usr/bin/env python3
"""1.2 visual/interaction regression checks. Real app files, optional virtual transport.
Browser plugin absent; Playwright + system Chromium. External Actions not covered.
"""
import argparse,asyncio,csv,io,json,mimetypes,math,subprocess,sys
from pathlib import Path
from urllib.parse import urlparse,unquote
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]

async def execute(args):
 out=Path(args.output);out.mkdir(parents=True,exist_ok=True);checks=[];errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,executable_path=args.browser)
  ctx=await browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True,reduced_motion='reduce')
  async def serve(route):
   f=(ROOT/'docs'/unquote(urlparse(route.request.url).path.lstrip('/'))).resolve()
   if (ROOT/'docs').resolve() not in f.parents or not f.is_file():await route.fulfill(status=404,body='Missing');return
   await route.fulfill(body=f.read_bytes(),content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
  await ctx.route('https://semya.test/**',serve)
  page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  await page.set_content((ROOT/'docs/index.html').read_text().replace('<head>','<head><base href="https://semya.test/">'),wait_until='networkidle')
  await page.wait_for_selector('#main[data-ready=true]')
  async def go(route):
   await page.evaluate('(r)=>location.hash="#/"+r',route);await page.wait_for_timeout(170)
   await page.wait_for_function('(r)=>document.querySelector("#main").dataset.page===r && !document.querySelector("#main").hasAttribute("aria-busy")',arg=route.split('?')[0])
   assert not await page.locator('.error-view').count(),route
  for w,h in [(1440,1000),(1024,768),(768,1024),(390,844),(320,740)]:
   await page.set_viewport_size({'width':w,'height':h});await go('projections')
   assert await page.locator('header .institution-link').count()==3
   assert await page.locator('.sidebar .institution-link').count()==0
   a=await page.locator('.institution-link').evaluate_all('(xs)=>xs.map(x=>({text:x.textContent.trim(),childCount:x.children.length,tag:x.children[0].tagName,width:x.children[0].naturalWidth,box:x.getBoundingClientRect().toJSON()}))')
   assert all(x['text']=='' and x['tag']=='IMG' and x['childCount']==1 and x['width']>0 for x in a),a
   assert all(x['box']['left']>=0 and x['box']['right']<=w for x in a),a
   assert all(a[i]['box']['right']<=a[i+1]['box']['left'] for i in range(2))
   assert await page.locator('.site-header').evaluate('(x)=>getComputedStyle(x).backgroundColor')=='rgb(255, 255, 255)'
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+2')
   checks.append({'check':'white_header_three_image_only_logos_fit','width':w})
   units=await page.locator('.chart-svg').first.locator('text').evaluate_all('(xs)=>xs.filter(x=>["детей на женщину","Прогноз"].includes(x.textContent)).map(x=>({text:x.textContent,b:x.getBoundingClientRect().toJSON()}))')
   if len(units)==2:
    assert units[0]['b']['right']<=units[1]['b']['left'] or units[1]['b']['right']<=units[0]['b']['left'] or units[0]['b']['bottom']<=units[1]['b']['top'] or units[1]['b']['bottom']<=units[0]['b']['top'],units
   checks.append({'check':'forecast_axis_unit_and_boundary_labels_do_not_overlap','width':w})
   await page.screenshot(path=str(out/f'forecast_{w}.png'))
  await page.set_viewport_size({'width':1440,'height':1000});await go('projections')
  o=json.loads((ROOT/'docs/data/projections/indicators/data_21/RU.json').read_text())
  line=page.locator('.data-line[data-series="Прогноз · ансамбль"]')
  coords=await line.evaluate('(x)=>x.getAttribute("d").slice(1).split("L").map(p=>p.split(",").map(Number))')
  data=[o['observations'][-1],*o['forecast']]
  assert len(coords)==len(data)==58
  k=(coords[-1][1]-coords[0][1])/(data[-1]['value']-data[0]['value']);b=coords[0][1]-k*data[0]['value']
  assert all(abs(p[1]-k*r['value']-b)<1e-8 for p,r in zip(coords,data))
  assert max(abs(data[i+1]['value']-2*data[i]['value']+data[i-1]['value']) for i in range(1,len(data)-1))>1e-6
  checks.append({'check':'curve_58_points_exact_affine_image_of_computed_values_no_spline'})
  await page.get_by_role('button',name='Ближайшие 24 месяца',exact=True).click();await page.wait_for_timeout(180)
  assert 'horizon=24' in await page.evaluate('location.hash')
  assert (await page.locator('.data-line[data-series="Прогноз · ансамбль"]').get_attribute('d')).count('L')==24
  async with page.expect_download() as d:await page.locator('.figure-tools').first.get_by_role('button',name='CSV',exact=True).click()
  f=out/'forecast_24.csv';await (await d.value).save_as(f)
  rows=list(csv.DictReader(io.StringIO(f.read_text(encoding='utf-8-sig')),delimiter=';'));assert len(rows)==24
  assert all(abs(float(r['value'])-p['value'])<1e-10 for r,p in zip(rows,o['forecast']))
  checks.append({'check':'24_month_view_and_csv_match_exact_computed_values'})
  await page.get_by_label('Отдельные модели',exact=True).check();await page.wait_for_timeout(170)
  assert await page.locator('.data-line').count()==8
  assert 'гауссовский процесс' in await page.locator('.legend').first.inner_text()
  await page.get_by_label('Тренд без колебаний',exact=True).check();await page.wait_for_timeout(170)
  assert await page.locator('.data-line[data-series="Тренд без колебаний"]').count()==1
  checks.append({'check':'five_members_and_trend_can_be_inspected'})
  await go('projections?tab=structure');assert await page.locator('.chart-svg').count()==2
  assert 'Календарная составляющая' in await page.locator('#main').inner_text()
  checks.append({'check':'structure_tab_displays_curve_trend_and_components'})
  await page.screenshot(path=str(out/'structure_1440.png'))
  await go('projections?tab=validation')
  text=await page.locator('#main').inner_text()
  formatted=lambda v:format(v,'.5f').rstrip('0').rstrip('.').replace('.',',')
  assert formatted(o['validation']['mae']) in text and formatted(o['validation']['last_value_mae']) in text,text[:1800]
  assert 'гауссовский процесс' in text and '14' in text
  checks.append({'check':'validation_discloses_ensemble_and_same_pair_baseline_error'})
  await page.screenshot(path=str(out/'validation_1440.png'))
  await go('projections?source=data_22&r=77&compare=78&tab=structure');assert await page.locator('.chart-svg').count()==2
  checks.append({'check':'structure_available_for_birth_order_and_region'})
  await go('projections?tab=map');assert await page.locator('[data-region]').count()==89
  checks.append({'check':'new_regional_forecast_maps_keep_missing_regions'})
  await go('projections?archive=1');assert await page.locator('.data-line[data-series="Прогноз исходной экспертизы"]').count()==1
  checks.append({'check':'original_research_forecast_remains_separate'})
  await page.set_viewport_size({'width':390,'height':844});await go('overview')
  await page.get_by_role('button',name='Открыть меню',exact=True).click()
  assert await page.locator('.workspace').evaluate('(x)=>x.inert')
  assert await page.locator('.site-header .institution-links').evaluate('(x)=>x.inert')
  await page.keyboard.press('Escape');assert not await page.locator('.workspace').evaluate('(x)=>x.inert')
  checks.append({'check':'mobile_menu_inert_and_escape_header_restore'})
  # Final design evidence. The supplied logos are not regenerated/recoloured.
  for w,h in [(1440,1000),(390,844)]:
   await page.set_viewport_size({'width':w,'height':h})
   for route,name in [('overview','overview'),('map?source=data_20','map'),('network','network'),('authors','authors'),('projections','forecast')]:
    await go(route);await page.screenshot(path=str(out/f'{name}_{w}.png'));await page.screenshot(path=str(out/f'{name}_{w}_full.png'),full_page=True)
    checks.append({'check':'final_render_no_blank_no_overflow','route':route,'width':w})
    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+2')
  assert not errors,errors
  await browser.close()
 report={'mode':'Playwright virtual transport; real repository modules and JSON','checks':checks,'page_errors':errors,'not_tested':['live GitHub Pages','live EMISS','external age-input downloads']}
 (out/'redesign_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('PASS redesign:',len(checks),'checks')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--browser',default='/usr/bin/chromium');p.add_argument('--output',default='/tmp/semya-redesign');asyncio.run(execute(p.parse_args()))
