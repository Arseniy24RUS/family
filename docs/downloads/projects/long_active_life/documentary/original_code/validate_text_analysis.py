#!/usr/bin/env python3
"""Independent checks against raw HTML/SQLite and published text outputs."""
from pathlib import Path
import argparse, collections, hashlib, json, math, re, sqlite3
import numpy as np
from lxml import html

def connect(p):
 c=sqlite3.connect(Path(p).resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--package-root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--output',type=Path,default=Path('outputs/research/text'));args=ap.parse_args();root=args.package_root;out=args.output if args.output.is_absolute() else root/args.output
 c=connect(out/'research_text.sqlite');src=connect(root/'corpus/data/catalog.sqlite3');checks=[]
 def check(name,passed,**detail):checks.append({'check':name,'passed':bool(passed),**detail})
 for kind,label in [('result','Характеристика результата'),('indicator','Код показателя')]:
  a=src.execute('select count(*) from web_fields where label=?',(label,)).fetchone()[0];b=c.execute('select count(*) from t_nodes where kind=?',(kind,)).fetchone()[0];check('all_source_'+kind+'_fields_extracted',a==b,source=a,output=b)
 nodes=[dict(r) for r in c.execute('select * from t_nodes')];groups=collections.defaultdict(list)
 for n in nodes:groups[n['local_file']].append(n)
 xpath_count=0;literal_count=0;unresolved=[];anchor_count=0;taskref_count=0;indicator_task_count=0;source_indicator_task_claims=0
 byid={n['node_id']:n for n in nodes}
 for file,rows in groups.items():
  tree=html.parse(str(root/file))
  source_indicator_task_claims+=len(tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," db-purpose-task ")]'))
  for n in rows:
   els=tree.xpath(n['source_xpath']);xpath_count+=int(len(els)==1)
   if not els:unresolved.append(n['node_id']);continue
   el=els[0];body=' '.join(el.text_content().split())
   if el.tag=='dt' and el.getnext() is not None:body+=' '+' '.join(el.getnext().text_content().split())
   literal_count+=int(n['title'] in body or n['title'] in (el.get('title') or ''))
  docids={n['document_id'] for n in rows}
  for e in c.execute('select * from t_edges where relation="result_declares_task"'):
   if e['document_id'] not in docids:continue
   if e['target_resolution']=='same_document_exact_anchor':
    target=byid[e['target_node_id']];p=tree.xpath(e['source_xpath']);a=p[0].xpath('.//a/@href') if p else []
    anchor_count+=int(target['document_id']==e['document_id'] and '#'+target['source_card_id'] in a and len(tree.xpath('//*[@id=$tid]',tid=target['source_card_id']))==1)
   elif e['target_resolution']=='unresolved_anchor_literal_reference':taskref_count+=1
  for e in c.execute('select * from t_edges where relation="indicator_declares_task"'):
   if e['document_id'] not in docids:continue
   target=byid[e['target_node_id']];p=tree.xpath(e['source_xpath'])
   text=' '.join(p[0].text_content().split()).lower().replace('ё','е') if p else ''
   indicator_task_count+=int(target['document_id']==e['document_id'] and target['title'].lower().replace('ё','е')==text and byid[e['source_node_id']]['kind']=='indicator')
 check('all_node_xpaths_resolve',xpath_count==len(nodes),verified=xpath_count,total=len(nodes),unresolved=unresolved)
 check('all_titles_present_at_source_location',literal_count==len(nodes),verified=literal_count,total=len(nodes))
 expected_anchors=c.execute('select count(*) from t_edges where relation="result_declares_task" and target_resolution="same_document_exact_anchor"').fetchone()[0]
 check('all_exact_task_anchors_independently_verified',anchor_count==expected_anchors,verified=anchor_count,total=expected_anchors)
 check('all_source_indicator_task_rows_preserved',source_indicator_task_claims==c.execute('select count(*) from t_indicator_task_claims').fetchone()[0],source_rows=source_indicator_task_claims,output_rows=c.execute('select count(*) from t_indicator_task_claims').fetchone()[0])
 check('all_exact_indicator_task_names_verified',indicator_task_count==c.execute('select count(*) from t_edges where relation="indicator_declares_task"').fetchone()[0],verified=indicator_task_count)
 edges={e['edge_id']:dict(e) for e in c.execute('select * from t_edges')};badchains=[]
 for e in c.execute('select * from t_result_indicator_shared_task'):
  a=edges[e['result_task_edge_id']];b=edges[e['indicator_task_edge_id']]
  ok=a['relation']=='result_declares_task' and b['relation']=='indicator_declares_task' and a['source_node_id']==e['result_node_id'] and b['source_node_id']==e['indicator_node_id'] and a['target_node_id']==b['target_node_id']==e['shared_task_node_id'] and a['document_id']==b['document_id']==e['document_id'] and e['evidence_class']=='structural_inference' and e['direct_effect_claimed']==0
  if not ok:badchains.append(e['link_id'])
 check('all_shared_task_chains_resolve_two_same_document_explicit_edges',not badchains,invalid=badchains)
 check('shared_task_link_ids_unique',c.execute('select count(*) from t_result_indicator_shared_task').fetchone()[0]==c.execute('select count(distinct link_id) from t_result_indicator_shared_task').fetchone()[0])
 check('at_most_one_declared_task_per_result',c.execute('select count(*) from (select source_node_id,count(*) n from t_edges where relation="result_declares_task" group by 1 having n>1)').fetchone()[0]==0)
 check('all_source_link_claims_preserved',src.execute('select count(*) from web_fields where label="Влияние результата на показатель"').fetchone()[0]==c.execute('select count(*) from t_link_claims').fetchone()[0])
 docs=[dict(r) for r in c.execute('select * from t_documents')];hashes={}
 for d in docs:
  p=root/d['local_file']
  if d['local_file'] not in hashes:
   with p.open('rb') as f:hashes[d['local_file']]=hashlib.file_digest(f,'sha256').hexdigest()
  check('source_file_sha256_'+d['document_id'],hashes[d['local_file']]==d['local_file_sha256'])
  if d['hash_kind']=='source_file_bytes':check('source_sha256_kind_'+d['document_id'],d['source_sha256']==d['local_file_sha256'])
  else:check('text_hash_explicitly_distinguished_'+d['document_id'],d['hash_kind']=='extracted_document_text_utf8' and d['source_sha256']!=d['local_file_sha256'])
 # Reconstruct the analyzed profiles from exported source units, without importing analysis code.
 profiles={}
 for d in docs:
  texts=[r['text'] for r in c.execute('select text from t_units where document_id=? and include_document_profile=1 order by rowid',(d['document_id'],))]
  normal=lambda s:re.sub(r'\s+',' ',s).strip().lower().replace('ё','е')
  if d['source_kind']=='secondary_epbs_rendering':texts=list(dict.fromkeys(normal(t) for t in texts))
  profiles[d['document_id']]=normal('\n'.join(texts))
 dic=json.loads((out/'dictionary.json').read_text());stop=set(dic['stopwords']);vocab=[dict(r) for r in c.execute('select * from t_vocabulary order by rowid')];vocabset={r['term'] for r in vocab};counts={};docfreq=collections.Counter();vectors={}
 for d in docs:
  words=re.findall(r'(?u)\b[а-яa-z][а-яa-z-]{1,}\b',profiles[d['document_id']]);words=[w for w in words if w not in stop]
  ct=collections.Counter(words);ct.update(a+' '+b for a,b in zip(words,words[1:]));ct={k:v for k,v in ct.items() if k in vocabset};counts[d['document_id']]=ct;docfreq.update(ct.keys())
 n=len(docs);idf_errors=[]
 for row in vocab:
  expected=1+math.log((1+n)/(1+docfreq[row['term']]))
  if abs(row['idf']-expected)>1e-12:idf_errors.append(row['term'])
 check('all_20000_idfs_recomputed_from_exported_units',not idf_errors,features=len(vocab),errors=idf_errors[:20])
 for d in docs:
  ct=counts[d['document_id']];v=np.array([(1+math.log(ct[r['term']]))*r['idf'] if r['term'] in ct else 0 for r in vocab]);v/=np.linalg.norm(v) or 1;vectors[d['document_id']]=v
 # Full upper triangle, explicit scalar dot products against the exported vectors.
 maximum=0
 for row in c.execute('select * from t_document_similarity'):
  error=abs(float(np.dot(vectors[row['document_a']],vectors[row['document_b']]))-row['cosine_similarity']);maximum=max(maximum,error)
 check('all_document_cosines_independently_recomputed',maximum<1e-10,pairs=c.execute('select count(*) from t_document_similarity').fetchone()[0],maximum_absolute_error=maximum)
 # Independently check every word-frequency denominator and dictionary counter.
 f_errors=0;maxfreqerr=0;token_re=re.compile(dic['token_regex'],re.I)
 for row in c.execute('select * from t_frame_scores'):
  text=profiles[row['document_id']];den=len(token_re.findall(text));rx=re.compile('|'.join('(?:'+s+')' for s in dic['frames'][row['frame_id']]['patterns']));cnt=len(list(rx.finditer(text)))
  f_errors+=int(cnt!=row['count'] or den!=row['n_tokens']);maxfreqerr=max(maxfreqerr,abs(cnt/den*1000-row['per_1000_tokens']) if den else 0)
 check('all_frame_counts_and_denominators_recomputed',f_errors==0 and maxfreqerr<1e-10,rows=c.execute('select count(*) from t_frame_scores').fetchone()[0],mismatched_rows=f_errors,maximum_frequency_error=maxfreqerr)
 # Each KWIC match must exist at the advertised offset in its original normalized unit.
 unittexts={r['unit_id']:normal(r['text']) for r in c.execute('select unit_id,text from t_units')};kwic_errors=0
 for row in c.execute('select * from t_kwic'):
  text=unittexts[row['unit_id']];kwic_errors+=int(text[row['start_offset_normalized']:row['end_offset_normalized']]!=row['matched_text'])
 check('all_kwic_offsets_resolve_to_literal_matches',kwic_errors==0,mismatches=kwic_errors)
 check('no_candidate_marked_approved',c.execute('select count(*) from t_semantic_candidates where review_status!="unreviewed" or evidence_class!="semantic_candidate"').fetchone()[0]==0)
 check('source_and_output_sqlite_integrity',c.execute('pragma quick_check').fetchone()[0]=='ok' and src.execute('pragma quick_check').fetchone()[0]=='ok')
 report={'status':'PASS' if all(r['passed'] for r in checks) else 'FAIL','checks_total':len(checks),'checks_passed':sum(r['passed'] for r in checks),'checks':checks}
 (out/'independent_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({k:v for k,v in report.items() if k!='checks'},ensure_ascii=False))
 for r in checks:
  if not r['passed']:print(json.dumps(r,ensure_ascii=False))
 if report['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
