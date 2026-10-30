#!/usr/bin/env python3
"""Independent reconciliation against the previously frozen corpus extraction."""
import argparse
import csv
import hashlib
import json
import math
import re
import sqlite3
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


def canonical(path):
    return re.sub(r"\[1\]", "", path).removeprefix("/html")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--package-root",type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument("--output",type=Path,default=Path("outputs/research/finance"))
    a=p.parse_args();root=a.package_root.resolve();out=a.output if a.output.is_absolute() else root/a.output
    c=sqlite3.connect((out/"research_finance.sqlite").as_uri()+"?mode=ro",uri=True);c.row_factory=sqlite3.Row
    src=sqlite3.connect((root/"corpus/data/catalog.sqlite3").as_uri()+"?mode=ro",uri=True);src.row_factory=sqlite3.Row
    prior={}
    for r in src.execute("SELECT sha256,path,period_raw,value_raw,value_decimal FROM web_measurements WHERE series_kind='year_value' AND unit_raw='тыс. руб.'"):
        key=(r['sha256'],canonical(r['path']),r['period_raw'])
        if key in prior and dict(prior[key])!=dict(r):raise AssertionError('Conflicting prior source key')
        prior[key]=r
    results=[]
    flows=list(c.execute('SELECT * FROM f_cashflows'))
    errors=[]
    for r in flows:
        old=prior.get((r['source_sha256'],canonical(r['source_xpath']),str(r['year'])))
        if old is None:errors.append({'record_id':r['record_id'],'reason':'missing_in_original_extraction'});continue
        new=Decimal(r['amount_thousand_rub']) if r['amount_thousand_rub'] is not None else None
        oldvalue=Decimal(old['value_decimal']) if old['value_decimal'] is not None else None
        if new!=oldvalue:errors.append({'record_id':r['record_id'],'reason':'value_differs_from_original_extraction'})
    results.append({'check':'independent_original_corpus_extraction','cases':len(flows),'passed':not errors,'errors':errors[:20]})
    groups=defaultdict(list)
    for r in c.execute('SELECT * FROM f_federal_shares'):groups[r['project_id'],r['period']].append(r)
    tested=0;bad=[]
    for r in c.execute('SELECT * FROM f_concentration'):
        rows=groups[r['project_id'],r['period']]
        valid=[x for x in rows if x['amount_thousand_rub'] is not None]
        amounts=[float(Decimal(x['amount_thousand_rub'])) for x in valid]
        denom=math.fsum(amounts)
        if denom:
            hhi=math.fsum((x/denom)**2 for x in amounts)
            if not math.isclose(hhi,r['hhi_visible_only_0_1'],rel_tol=1e-12,abs_tol=1e-12):bad.append([r['project_id'],r['period'],'visible_hhi'])
            if r['hhi_0_1'] is not None:
                tested+=1
                if len(valid)!=r['linked_federal_projects'] or not math.isclose(hhi,r['hhi_0_1'],rel_tol=1e-12):bad.append([r['project_id'],r['period'],'strict_hhi'])
                if not math.isclose(math.fsum(x['share_percent'] for x in rows),100,abs_tol=1e-9):bad.append([r['project_id'],r['period'],'share_sum'])
                if not 1/len(rows)-1e-12<=hhi<=1+1e-12:bad.append([r['project_id'],r['period'],'hhi_bound'])
    results.append({'check':'independent_float_hhi_shares_bounds','cases':tested,'passed':not bad,'errors':bad})
    partial=[]
    for r in c.execute("SELECT * FROM f_documents WHERE financing_empty_notice IS NOT NULL"):
        if r['header_declared_total_thousand_rub'] is not None:partial.append(r['source_url'])
    results.append({'check':'no_zero_imputation_for_absent_financing','cases':c.execute('SELECT count(*) FROM f_documents WHERE financing_empty_notice IS NOT NULL').fetchone()[0],'passed':not partial,'errors':partial})
    fam=list(c.execute("SELECT * FROM f_family_reference WHERE period='2025–2030'"))
    results.append({'check':'family_control_original_89_70285298_percent','cases':len(fam),'passed':len(fam)==5 and math.isclose(max(r['share_percent'] for r in fam),89.70285298269692,abs_tol=1e-10),'errors':[]})
    duplicates=c.execute('SELECT count(*)-count(DISTINCT record_id) FROM f_cashflows').fetchone()[0]
    results.append({'check':'unique_source_records','cases':len(flows),'passed':duplicates==0,'errors':[]})
    report={'version':'1.2.0','passed':all(r['passed'] for r in results),'checks':results,
            'source': 'independent frozen web_measurements extraction from release1.1; Decimal and separate float recomputation',
            'limitations':'Arithmetic and extraction checks do not certify legal edition, transfer consolidation or execution.'}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
