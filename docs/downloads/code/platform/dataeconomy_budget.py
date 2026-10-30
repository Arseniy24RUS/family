"""Extract the two physical HTML parts of table 4.1.12, retaining source cells."""
from pathlib import Path
from decimal import Decimal
import hashlib,json,re
from extract_dataeconomy_passports import decimal,ws

NAMES={'Цифровые платформы в отраслях социальной сферы':'Ц2','Искусственный интеллект':'Ц3',
 'Цифровое государственное управление':'Ц4','Отечественные решения':'Ц5',
 'Прикладные исследования и перспективные разработки':'Ц6','Инфраструктура кибербезопасности':'Ц7',
 'Кадры для цифровой трансформации':'Ц8','Государственная статистика':'Ц9'}

def build_budget(root,folder):
 from lxml import html
 spec=json.loads((folder/'budget_source.json').read_text());source=root/spec['source_input_path']
 assert hashlib.sha256(source.read_bytes()).hexdigest()==spec['source_html_sha256']
 tree=html.fromstring(source.read_bytes());rt=tree.getroottree();all_tables=tree.xpath('//table')
 start=[i for i,t in enumerate(all_tables) if '169 352,7' in ws(t.text_content()) and '147 056,4' in ws(t.text_content())]
 assert len(start)==1
 tables=all_tables[start[0]:start[0]+2]
 assert 'Федеральный проект "Инфраструктура кибербезопасности"' in ws(tables[1].text_content())
 assert 'Зарезервированные бюджетные ассигнования на реализацию национального проекта' in ws(tables[1].text_content())
 rows=[];active=None
 for table in tables:
  for row in table.xpath('.//tr'):
   cells=row.xpath('./th|./td')
   if len(cells)!=5:continue
   label=ws(cells[0].text_content())
   if re.fullmatch(r'\d+',label):continue
   values=[decimal(ws(c.text_content())) for c in cells[1:]]
   if any(v is None for v in values):continue
   if label=='Всего':kind='national_total';code='Ц';name='Всего'
   elif label.startswith('Федеральный проект '):
    name=label.split('"',2)[1];code=NAMES[name];active=code;kind='federal_project'
   elif label=='Иные структурные элементы национального проекта':
    kind='other_structural_elements';code='other';name=label;active=None
   elif label.startswith('Зарезервированные бюджетные ассигнования'):
    kind='reserve';code='reserve';name=label;active=None
   else:
    assert active,(label,rt.getpath(row))
    kind='direction';code=active;name=label
   for year,value,cell in zip(range(2026,2030),values,cells[1:]):
    val=Decimal(value)
    rows.append({'year':year,'fp':code,'code':code,'name':name,'label':label,'level':kind,
     'source_code':'federal','source_name':'Федеральный бюджет','source':'Федеральный бюджет',
     'amount_decimal':value,'amount_million_rub':float(val),'amount_billion_rub':float(val/1000),
     'amount_thousand_rub':float(val*1000),'amountThousandRub':float(val*1000),'value':float(val),
     'value_raw':ws(cell.text_content()),'unit':'млн руб.','kind':'budget_allocation' if year==2026 else 'budget_bill',
     'status':spec['periods'][str(year)],'source_locator':rt.getpath(cell),'source_row_locator':rt.getpath(row),
     'source_url':spec['source_url'],'source_sha256':spec['source_html_sha256'],
     'included_in_national_reconciliation':kind in ['federal_project','other_structural_elements','reserve'],
     'included_in_project_reconciliation':kind=='direction','origin':spec['verification_status']})
 totals=[r for r in rows if r['level']=='national_total'];projects=[r for r in rows if r['level']=='federal_project']
 structural=[r for r in rows if r['level'] in ['other_structural_elements','reserve']]
 assert len(totals)==4 and len(projects)==32 and len(structural)==8
 assert [r['amount_decimal'] for r in totals]==['169352.7','147056.4','163141.3','160462.2']
 reconciliation=[]
 for total in totals+projects:
  national=total['level']=='national_total'
  children=[r for r in rows if r['year']==total['year'] and
    (r['included_in_national_reconciliation'] if national else r['level']=='direction' and r['fp']==total['fp'])]
  value=sum((Decimal(r['amount_decimal']) for r in children),Decimal(0));published=Decimal(total['amount_decimal'])
  reconciliation.append({'year':total['year'],'fp':total['fp'],'scope':'national' if national else 'federal_project',
    'published_total_decimal':str(published),'child_sum_decimal':str(value),'child_minus_published_decimal':str(value-published),
    'unit':'млн руб.','child_count':len(children),'total_locator':total['source_locator'],
    'child_locators':[r['source_locator'] for r in children],'source_url':spec['source_url'],
    'source_sha256':spec['source_html_sha256'],'note':'Сверяются округлённые строки одного уровня. Весь итог ФП и его компоненты повторно не складываются.'})
 changes_rows=[]
 for year in [2026,2027]:
  total=next(r for r in totals if r['year']==year);named=[r for r in projects if r['year']==year]
  other=next(r for r in structural if r['year']==year and r['fp']=='other')
  reserve=next(r for r in structural if r['year']==year and r['fp']=='reserve')
  values={'total':Decimal(total['amount_decimal']),'named_projects':sum((Decimal(r['amount_decimal']) for r in named),Decimal(0)),
   'other_elements':Decimal(other['amount_decimal']),'reserve':Decimal(reserve['amount_decimal'])}
  values['rounding']=values['total']-values['named_projects']-values['other_elements']-values['reserve']
  changes_rows.append({'year':year,**{k+'_million_decimal':str(v) for k,v in values.items()},
   **{k+'_billion_rub':float(v/1000) for k,v in values.items()},'source_url':spec['source_url'],
   'total_locator':total['source_locator'],'named_project_locators':[r['source_locator'] for r in named],
   'other_elements_locator':other['source_locator'],'reserve_locator':reserve['source_locator']})
 changes={}
 for key in ['total','named_projects','other_elements','reserve','rounding']:
  before=Decimal(changes_rows[0][key+'_million_decimal']);after=Decimal(changes_rows[1][key+'_million_decimal'])
  changes[key]={'difference_million_decimal':str(after-before),'difference_billion_rub':float((after-before)/1000),
   'change_percent':float((after/before-1)*100) if before and key!='rounding' else None}
 assert changes['total']['difference_million_decimal']=='-22296.3'
 assert changes['named_projects']['difference_million_decimal']=='10557.8'
 assert changes['other_elements']['difference_million_decimal']=='-32854.3'
 missing=[{'fp':'Ц1','name':'Инфраструктура доступа к информационно-телекоммуникационной сети «Интернет»',
    'year':year,'amount_million_rub':None,'amount_decimal':None,'missing_reason':'not_separately_identified_in_table_4_1_12',
    'source_url':spec['source_url'],'source_sha256':spec['source_html_sha256']} for year in range(2026,2030)]
 return {**spec,'source_locator':rt.getpath(tables[0]),'source_locators':[rt.getpath(t) for t in tables],
  'rows':rows,'projectRows':projects,'structuralRows':structural,'totals':totals,'directionShares':[],
  'reconciliation':reconciliation,'published_numeric_cells':len(rows),'missingProjectRows':missing,
  'change2026_2027':{'rows':changes_rows,'changes':changes,'components':['named_projects','other_elements','reserve','rounding'],
   'comparison':'2026 allocation at 01.09.2026 vs introduced 2027 budget bill'},
  'note':'2026 год: роспись на 01.09.2026. 2027–2029 годы: внесённый законопроект. Ц1 не выделен отдельной строкой. Иные структурные элементы и резерв не присваиваются ему. Остаток округления показывается отдельно. Суммы не являются кассовым исполнением.'}
