"""Independent source-cell, graph, report-coverage and text-model checks."""
from pathlib import Path
from decimal import Decimal
import collections,csv,gzip,hashlib,json,re,sys,unittest,zipfile
from lxml import html

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))

PROJECT='data_economy'
DATA=ROOT/'public/data/projects'/PROJECT
OUT=ROOT/'public/downloads/projects'/PROJECT
DOCX_SHA='9327e9be19dc565d1175da75d14b2c7b657b52e985fc814ea1a0463faa8a801f'

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def normalized(value):return re.sub(r'\s+',' ',str(value or '')).strip().lower().replace('ё','е')
def independent_decimal(raw):
 s=re.sub(r'[\s\u00a0\u202f]','',raw).replace(',','.').replace('−','-')
 return Decimal(s) if re.fullmatch(r'-?\d+(?:\.\d+)?',s) else None

def child_text(element,cls):
 found=element.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," '+cls+' ")]')
 if len(found)!=1:raise AssertionError((cls,len(found)))
 return re.sub(r'\s+',' ',' '.join(found[0].itertext())).strip()

class DataEconomyDocumentaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.full=read(OUT/'documentary/documentary_full.json');cls.runtime=read(DATA/'documentary.json')
  cls.report=read(DATA/'expertise.json');cls.extraction=read(OUT/'report/report_extraction.json')
  cls.coverage=read(OUT/'report/coverage_manifest.json');cls.manifest=read(ROOT/'inputs/dataeconomy/documentary/source_manifest.json')
  cls.selected=[d for d in cls.manifest['documents'] if d['project_id']==PROJECT];cls.raw={};cls.trees={}
  with zipfile.ZipFile(ROOT/cls.manifest['archive_path']) as z:
   for d in cls.selected:
    raw=z.read(d['archive_entry']);cls.raw[d['document_id']]=raw;cls.trees[d['document_id']]=html.fromstring(raw).getroottree()
  cls.nodes={n['node_id']:n for n in cls.full['network']['nodes']}
  cls.profiles=json.loads(gzip.decompress((ROOT/'inputs/personnel/documentary_inputs.json.gz').read_bytes()))['profiles']

 def test_original_report_and_all_images_are_unchanged(self):
  original=OUT/'report/expertise_dataeconomy_2026.docx'
  self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),DOCX_SHA)
  with zipfile.ZipFile(original) as z:
   for original_figure,published in zip(self.extraction['figures'],self.report['figures']):
    block=next(b for b in self.extraction['blocks'] if b['index']==original_figure['block'])
    self.assertEqual(z.read(block['images'][0]),(ROOT/'public'/published['url']).read_bytes())

 def test_report_complete_single_assignment(self):
  summary=self.coverage['summary'];self.assertEqual(summary['substantive_blocks'],383)
  self.assertEqual(summary['assigned_blocks'],383);self.assertFalse(summary['unmapped_substantive_blocks']);self.assertFalse(summary['duplicate_assignments'])
  indices=[b for p in self.report['pages'].values() for b in p['source_blocks']]
  substantive=[b['index'] for b in self.extraction['blocks'] if b['index']>=72 and (b.get('text') or b.get('images') or b['type']=='table')]
  self.assertEqual(sorted(indices),substantive);self.assertEqual(len(self.report['pages']),21)

 def test_report_tables_and_csv_retain_every_cell(self):
  self.assertEqual(len(self.report['tables']),15)
  for original,published in zip(self.extraction['tables'],self.report['tables']):
   rows=[[c['label'] for c in published['columns']]]+[[r[c['key']] for c in published['columns']] for r in published['rows']]
   self.assertEqual(rows,original['rows'])
   with (OUT/'report'/f"{published['id']}.csv").open(encoding='utf-8-sig',newline='') as f:self.assertEqual(list(csv.reader(f)),rows)

 def test_footnotes_and_formula_mean_notation_are_retained(self):
  notes={s['note_number']:s for s in self.report['sources'] if s.get('kind')=='source_note'}
  self.assertEqual(len(notes),140)
  for n in self.extraction['footnotes']:self.assertEqual(notes[n['id']]['text'],n['text'])
  formulas=[b for p in self.report['pages'].values() for b in p['blocks'] if b['type']=='formula']
  self.assertEqual(len(formulas),7)
  last=next(f for f in formulas if f['number']==7);self.assertEqual(last['text'].count('Ȳ'),4);self.assertEqual(last['latex'].count('\\overline{Y}'),4)
  self.assertEqual(self.report['meta']['source_pages'],119)
  self.assertTrue(all(b['page']>=4 for p in self.report['pages'].values() for b in p['blocks'] if b.get('page') is not None),'Content locators must not resolve to the table of contents.')

 def test_passport_bytes_dates_and_shared_reference(self):
  self.assertEqual(len(self.selected),10)
  archive=ROOT/self.manifest['archive_path'];self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),self.manifest['archive_sha256'])
  for meta in self.selected:
   self.assertEqual(hashlib.sha256(self.raw[meta['document_id']]).hexdigest(),meta['sha256'])
   self.assertEqual((ROOT/'public'/meta['download_path']).read_bytes(),self.raw[meta['document_id']])
   self.assertEqual(meta['publication_date'],'16.10.2026');self.assertTrue(meta['retrieved_at'].startswith('2026-10-19'))

 def test_all_194_nodes_resolve_to_unique_source_locations(self):
  addresses=[]
  for node in self.nodes.values():
   tree=self.trees[node['document_id']];parts=tree.xpath(node.get('source_value_locator') or node['source_locator'])
   self.assertEqual(len(parts),1)
   self.assertIn(normalized(node['title']),normalized(' '.join(parts[0].itertext())))
   addresses.append((node['document_id'],node['kind'],node['source_locator']))
  self.assertEqual(len(addresses),194);self.assertEqual(len(set(addresses)),194)
  card_ids=collections.Counter((n['document_id'],n['source_card_id']) for n in self.nodes.values() if n.get('source_card_id'))
  self.assertTrue(any(count>1 for count in card_ids.values()),'Fixture must exercise repeated HTML identifiers')

 def test_original_finance_cells_decimal_and_years(self):
  rows=self.full['finance']['sourceRows'];self.assertEqual(len(rows),598)
  for row in rows:
   cell=self.trees[row['document_id']].xpath(row['source_locator'])[0]
   raw=child_text(cell,'db-passport-year-value');year=child_text(cell,'db-passport-year-label')
   self.assertEqual(row['value_raw'],raw);self.assertEqual(str(row['year']),year)
   actual=independent_decimal(raw);expected=Decimal(row['amount_decimal']) if row['amount_decimal'] is not None else None
   self.assertEqual(actual,expected)

 def test_finance_total_is_independently_summed_from_visible_sources(self):
  rows=self.full['finance']['sourceRows'];labels={'Федеральный бюджет, всего','Консолидированные бюджеты субъектов Российской Федерации, всего','Внебюджетные источники, всего'}
  selected=[r for r in rows if r['scope']=='document' and r['source'] in labels and 2025<=r['year']<=2030 and r['amount_decimal'] is not None]
  national=sum((Decimal(r['amount_decimal']) for r in selected if r['fp']=='Ц'),Decimal(0))
  federal=sum((Decimal(r['amount_decimal']) for r in selected if r['fp']!='Ц'),Decimal(0))
  self.assertEqual(national,Decimal('1212749112.29'));self.assertEqual(federal,Decimal('1212749112.29'))
  self.assertEqual(national,Decimal(self.full['finance']['nationalDecimal']));self.assertEqual(federal,Decimal(self.full['finance']['federalDecimal']))

 def test_intergovernmental_components_are_not_added_twice(self):
  components=[r for r in self.full['finance']['sourceRows'] if r['source'].startswith('из них:')]
  self.assertTrue(components)
  self.assertTrue(all(r['is_subcomponent'] and not r['included_in_additive_total'] for r in components))
  for frame in self.full['finance']['frames']:
   self.assertFalse(any(r.get('source_code')=='federal_transfer_component' for r in frame['rows']))

 def test_missing_internet_year_and_extended_government_horizon(self):
  projects={p['code']:p for p in self.full['finance']['projects']}
  self.assertEqual(len(projects),9)
  internet=next(r for r in projects['Ц1']['years'] if r['year']==2030)
  self.assertIsNone(internet['amount_decimal']);self.assertTrue(internet['missing_reason'])
  self.assertEqual(sum(p['totalDecimal'] is not None for p in projects.values()),9)
  government=next(r for r in self.full['finance']['horizonSummaries'] if r['code']=='Ц4' and r['first_year']==2031)
  self.assertEqual(Decimal(government['amount_decimal']),Decimal('5708673.00'))
  self.assertEqual(Decimal(projects['Ц4']['totalDecimal']),Decimal('507804696.17'))

 def test_all_source_year_totals_reconcile_exactly(self):
  for row in self.full['finance']['sourceReconciliation']:
   self.assertEqual(Decimal(row['difference_decimal']),0)
  for row in self.full['finance']['yearTotals']:
   self.assertEqual(Decimal(row['difference_decimal']),0)

 def test_budget_all_372_cells_match_original_html(self):
  spec=read(ROOT/'inputs/dataeconomy/documentary/budget_source.json');raw=(ROOT/spec['source_input_path']).read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),spec['source_html_sha256']);tree=html.fromstring(raw).getroottree()
  rows=self.full['finance']['budgetBill']['rows'];self.assertEqual(len(rows),372)
  for row in rows:
   cell=tree.xpath(row['source_locator']);self.assertEqual(len(cell),1)
   self.assertEqual(independent_decimal(' '.join(cell[0].itertext())),Decimal(row['amount_decimal']))
   self.assertEqual(row['unit'],'млн руб.');self.assertEqual(row['source_code'],'federal')
   self.assertEqual(row['kind'],'budget_allocation' if row['year']==2026 else 'budget_bill')

 def test_budget_total_and_components_remain_separate_levels(self):
  bill=self.full['finance']['budgetBill'];self.assertEqual(len(bill['totals']),4);self.assertEqual(len(bill['projectRows']),32)
  self.assertEqual([Decimal(r['amount_decimal']) for r in bill['totals']],[Decimal(x) for x in ['169352.7','147056.4','163141.3','160462.2']])
  self.assertTrue(all(r['level']=='federal_project' for r in bill['projectRows']))
  self.assertTrue(all(r['scope'] in ['national','federal_project'] for r in bill['reconciliation']))

 def test_budget_change_components_and_rounding_are_distinct(self):
  bill=self.full['finance']['budgetBill'];change=bill['change2026_2027'];diffs=change['changes']
  for row in change['rows']:
   self.assertEqual(Decimal(row['total_million_decimal']),sum((Decimal(row[k+'_million_decimal']) for k in ['named_projects','other_elements','reserve','rounding']),Decimal(0)))
  self.assertEqual(Decimal(diffs['total']['difference_million_decimal']),Decimal('-22296.3'))
  self.assertEqual(Decimal(diffs['named_projects']['difference_million_decimal']),Decimal('10557.8'))
  self.assertEqual(Decimal(diffs['other_elements']['difference_million_decimal']),Decimal('-32854.3'))
  self.assertEqual(Decimal(diffs['rounding']['difference_million_decimal']),Decimal('0.2'))
  self.assertEqual([r['amount_million_rub'] for r in bill['structuralRows'] if r['fp']=='reserve'],[0,0,489,487.2])
  self.assertTrue(all(r['amount_decimal'] is None for r in bill['missingProjectRows']))
  self.assertEqual(len(bill['source_locators']),2)

 def test_all_target_cells_and_original_years_are_source_addressed(self):
  path=OUT/'documentary/targets_all_years.csv'
  with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
  self.assertEqual(len(rows),1140)
  for row in rows:
   cell=self.trees[row['document_id']].xpath(row['source_locator'])[0]
   self.assertEqual(child_text(cell,'db-purpose-year'),row['year'])
   self.assertEqual(child_text(cell,'db-purpose-year-val'),row['value_raw'])
   self.assertEqual(independent_decimal(row['value_raw']),Decimal(row['value_decimal']) if row['value_decimal'] else None)
  self.assertGreater(max(int(r['year']) for r in rows),2030)

 def test_target_registry_identity_and_separate_proxy_cards(self):
  targets=self.full['targets'];self.assertEqual(len(targets['items']),49);self.assertEqual(len(targets['allCards']),60)
  extra=[r for r in targets['allCards'] if r['indicator_code'] is None]
  self.assertEqual(len(extra),2);self.assertEqual({r['source_document'] for r in extra},{'fp_340','fp_343'})
  self.assertEqual(targets['numeric_targets'],284);self.assertEqual(targets['missing_targets'],10)
  self.assertTrue(all(set(r['years'])==set(map(str,range(2025,2031))) for r in targets['items']))
  self.assertTrue(next(r for r in targets['items'] if r['indicator_code']=='2.14.Ц6.4')['target_is_proxy'])

 def test_network_shared_pairs_resolve_both_memberships(self):
  edges=self.full['network']['sharedTaskPairs'];self.assertEqual(len(edges),632)
  for edge in edges:
   result=self.nodes[edge['result_node_id']];indicator=self.nodes[edge['indicator_node_id']];task=self.nodes[edge['task_node_id']]
   self.assertEqual(result['task_node_id'],task['node_id']);self.assertEqual(indicator['task_node_id'],task['node_id'])
   self.assertEqual(result['document_id'],indicator['document_id']);self.assertTrue(task['membership_eligible'])
   self.assertEqual(edge['causal_status'],'not_identified')
  self.assertEqual(len(self.full['network']['resultTaskLinks']),90)

 def test_unresolved_influence_never_becomes_a_direct_edge(self):
  network=self.full['network'];self.assertEqual(len(network['unresolvedClaims']),168)
  self.assertFalse(network['directLinks']);self.assertFalse(network['reviewedEdges'])
  for claim in network['unresolvedClaims']:
   self.assertIsNone(claim['indicator_node_id']);self.assertFalse(claim['target_assignment_permitted'])
   dt=self.trees[claim['document_id']].xpath(claim['source_locator'])[0]
   self.assertEqual(normalized(' '.join(dt.itertext())),'влияние результата на показатель')
   self.assertEqual(independent_decimal(' '.join(dt.getnext().itertext())),Decimal(claim['value_raw'].replace(',','.')))

 def test_semantic_candidates_are_top3_across_national_project(self):
  candidates=self.full['network']['semanticCandidates'];by=collections.defaultdict(list)
  for row in candidates:
   by[row['result_node_id']].append(row);self.assertGreaterEqual(row['cosine'],.1);self.assertIsNone(row['official_weight'])
   self.assertEqual(row['review_status'],'unreviewed');self.assertEqual(self.nodes[row['result_node_id']]['project_id'],self.nodes[row['indicator_node_id']]['project_id'])
  self.assertEqual(len(candidates),150);self.assertEqual(len(by),68);self.assertTrue(all(len(rows)<=3 for rows in by.values()))
  self.assertTrue(any(not r['same_document'] for r in candidates),'Cross-FP and NP candidate selection must remain allowed')

 def test_all_reference_profiles_and_original_code_are_checksum_pinned(self):
  cfg=self.full['text']['method'];self.assertEqual(hashlib.sha256((ROOT/cfg['shared_profiles_input']).read_bytes()).hexdigest(),cfg['shared_profiles_sha256'])
  self.assertEqual(hashlib.sha256((ROOT/'public'/cfg['source_code_download']).read_bytes()).hexdigest(),cfg['source_code_sha256'])
  self.assertEqual(len(self.profiles['documents']),137)
  for doc in self.profiles['documents']:self.assertEqual(hashlib.sha256(doc['text'].encode()).hexdigest(),doc['profile_text_sha256'])

 def test_digital_profiles_match_exact_html_source_nodes(self):
  profiles={d['source_sha256']:d for d in self.profiles['documents']};tokens=0
  for meta in self.selected:
   packet=read(DATA/'documentary-text'/f"{meta['document_id']}.json")
   self.assertEqual('\n'.join(u['text'] for u in packet['units']),profiles[meta['sha256']]['text'])
   for unit in packet['units']:
    node=self.nodes[unit['node_id']]
    element=self.trees[meta['document_id']].xpath(node.get('source_value_locator') or unit['source_locator'])[0]
    raw=normalized(' '.join(element.itertext()))
    self.assertIn(normalized(node['title']),raw)
    if node.get('description'): self.assertIn(normalized(node['description']),raw)
    self.assertEqual(unit['text'],normalized(node['title']+' '+node.get('description','')))
    tokens+=len(re.findall(r'[а-яёa-z]{2,}(?:-[а-яёa-z]{2,})?',unit['text']))
  self.assertEqual(tokens,12479)

 def test_text_model_matches_reference_without_rounding_away_errors(self):
  checks=self.full['text']['replicationAudit'];self.assertEqual(len(checks),199)
  self.assertTrue(all(r['equal'] for r in checks));self.assertLessEqual(max(abs(r['difference']) for r in checks),1e-12)
  self.assertEqual(self.full['text']['features'],20000);self.assertTrue(self.full['text']['authorExactCodeAvailable'])
  near=self.full['text']['projectSimilarity'];self.assertEqual([r['project_id'] for r in near[:3]],['competitive_economy','youth_children','personnel'])
  self.assertAlmostEqual(near[0]['cosine'],.30206865620192885,places=13)

 def test_sensitivity_preserves_corpus_and_genre_scope(self):
  text=self.full['text'];self.assertEqual(len(text['sensitivity']),6);self.assertEqual(len(text['projectSimilarity']),9)
  self.assertNotIn('family',[r['project_id'] for r in text['projectSimilarity']]);self.assertNotIn('health_technologies',[r['project_id'] for r in text['projectSimilarity']])
  for row in text['sensitivity']:
   self.assertEqual(row['source_corpus_documents'],137);self.assertEqual(row['compared_projects'],10);self.assertIsNone(row['author_spearman'])
   self.assertEqual(row['origin'],'author_specification_replayed' if row['variant'] in ['base','stemming'] else 'additional_platform_sensitivity')

 def test_all_frame_frequencies_and_kwic_counts_have_real_denominators(self):
  text=self.full['text'];self.assertEqual(len(text['frameScores']),180);count=0
  for meta in text['documents']:
   packet=read(DATA/'documentary-text'/f"{meta['document_id']}.json");profile=normalized('\n'.join(u['text'] for u in packet['units']))
   for frame in text['frames']:
    rx=re.compile('|'.join('(?:'+p+')' for p in frame['patterns']));matches=list(rx.finditer(profile))
    row=next(r for r in text['frameScores'] if r['document_id']==meta['document_id'] and r['frame_id']==frame['id'])
    self.assertEqual(row['count'],len(matches));self.assertAlmostEqual(row['per1000'],len(matches)/meta['profile_token_count']*1000)
    contexts=[r for r in packet['contexts'] if r['frame']==frame['id']];self.assertEqual(len(contexts),len(matches));count+=len(contexts)
  self.assertEqual(count,1179);self.assertEqual(count,text['contextCount'])

 def test_orphan_transfer_cells_do_not_claim_complete_result_cost(self):
  orphans=self.full['finance']['orphanComponents'];self.assertTrue(orphans)
  self.assertTrue(all(not r['parent_source_available'] and not r['included_in_additive_total'] for r in orphans))
  affected={r['result_id'] for r in orphans if r['scope']=='result'}
  for row in self.full['finance']['resultSums']:
   self.assertFalse(row['total_is_complete'])
   if row['result_id'] in affected:self.assertEqual(row['coverage_status'],'orphan_transfer_without_parent')

 def test_author_node_tie_rule_reconstructed_from_source_identity(self):
  ref=read(ROOT/'inputs/dataeconomy/documentary/author_reference_tables.json')['semantic_candidates']
  by={(r['result_source_url'],r['result_source_xpath'],r['indicator_source_url'],r['indicator_source_xpath']):r for r in ref}
  for pair in self.full['network']['semanticCandidates']:
   key=(pair['source_url'],pair['result_locator'],pair['indicator_source_url'],pair['indicator_locator']);old=by[key]
   for kind in ['result','indicator']:
    node=self.nodes[pair[kind+'_node_id']]
    expected=hashlib.sha256('\x1f'.join(['node',node['kind'],'html:'+node['source_sha256'],node['source_locator'],node['title']]).encode()).hexdigest()[:24]
    self.assertEqual(pair['author_'+kind+'_node_id'],expected);self.assertEqual(expected,old[kind+'_node_id'])
   self.assertEqual(pair['rank_for_result'],int(old['rank_for_result']))
   self.assertAlmostEqual(pair['cosine'],float(old['cosine_similarity']),places=12)

 def test_compact_runtime_pairs_roundtrip_to_full_export(self):
  fields={'result_title','indicator_title','source_url','result_locator','indicator_locator','task_title','task_locator','indicator_source_url'}
  for layer in ['sameProjectPairs','sharedTaskPairs','semanticCandidates']:
   full=self.full['network'][layer];runtime=self.runtime['network'][layer];self.assertEqual(len(full),len(runtime))
   for original,compact in zip(full,runtime):
    self.assertEqual(compact,{k:v for k,v in original.items() if k not in fields})
    result=self.nodes[compact['result_node_id']];indicator=self.nodes[compact['indicator_node_id']]
    self.assertEqual(original['result_title'],result['title']);self.assertEqual(original['indicator_title'],indicator['title'])
    self.assertEqual(original['result_locator'],result['source_locator']);self.assertEqual(original['indicator_locator'],indicator['source_locator'])
  self.assertTrue(self.full['finance']['sourceRows']);self.assertNotIn('sourceRows',self.runtime['finance'])
  lazy=read(ROOT/'public'/self.runtime['finance']['resultsFile'])
  self.assertEqual(lazy['resultYears'],self.full['finance']['resultYears'])
  self.assertEqual(lazy['resultSums'],self.full['finance']['resultSums'])
  self.assertEqual(len(lazy['resultSums']),90)
  self.assertEqual(sum(r['amount_decimal'] is None for r in lazy['resultSums']),1)

if __name__=='__main__':unittest.main()
