#!/usr/bin/env python3
"""Reproducible passport-financing analysis; no network, no execution-rate claims."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import html

YEARS = tuple(range(2025, 2031))
REFERENCE_COMMIT = "50ad21c1ad1c94e3cf07857363333df120558617"


def cls(name):
    return f'contains(concat(" ",normalize-space(@class)," ")," {name} ")'


def text(node):
    return " ".join(node.text_content().split()) if node is not None else ""


def first(node, name):
    found = node.xpath(f'.//*[{cls(name)}]')
    return found[0] if found else None


def decimal(value):
    s = re.sub(r"[\s\u00a0\u202f]", "", str(value)).replace(",", ".")
    if s in {"", "-", "–", "—", "null", "None"}:
        return None
    try:
        d = Decimal(s)
        return d if d.is_finite() else None
    except InvalidOperation:
        return None


def dstr(value):
    return str(value) if value is not None else None


def total(values, expected=None):
    values = list(values)
    if not values or any(v is None for v in values):
        return None
    if expected is not None and len(values) != expected:
        return None
    return sum(values, Decimal(0))


def checksum(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def export_table(conn, output, name, rows, empty_fields=None):
    fields = list(rows[0]) if rows else list(empty_fields or ["project_id", "status"])
    for row in rows:
        if set(row) != set(fields):
            raise ValueError(f"Inconsistent columns in {name}")
    types = {}
    for field in fields:
        vals = [r[field] for r in rows if r[field] is not None]
        types[field] = "INTEGER" if vals and all(isinstance(v, int) for v in vals) else "REAL" if vals and all(isinstance(v, (float, int)) for v in vals) else "TEXT"
    conn.execute(f'DROP TABLE IF EXISTS "{name}"')
    conn.execute(f'CREATE TABLE "{name}" (' + ",".join(f'"{k}" {types[k]}' for k in fields) + ")")
    conn.executemany(f'INSERT INTO "{name}" VALUES (' + ",".join("?" for _ in fields) + ")", [[r.get(k) for k in fields] for r in rows])
    with (output / (name + ".csv")).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_html_finance(root):
    db = sqlite3.connect((root / "corpus/data/catalog.sqlite3").as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    documents = [dict(r) for r in db.execute("SELECT * FROM web_documents WHERE source_type='secondary_epbs_rendering' ORDER BY project,document_level,url")]
    links = [dict(r) for r in db.execute("SELECT * FROM web_project_links ORDER BY parent_sha256,child_url")]
    with (root / "outputs/tables/corpus_project_crosswalk.csv").open(encoding="utf-8-sig", newline="") as f:
        crosswalk = {r["corpus_project_id"]:r for r in csv.DictReader(f)}
    cashflows, doc_rows, errors = [], [], []

    def add_chips(doc, tree, container, row_type, subject_xpath, subject_name, source_name):
        unit = text(first(container, "db-passport-fo-unit"))
        for chip in container.xpath(f'.//*[{cls("db-passport-year-chip")}]'):
            period = text(first(chip, "db-passport-year-label"))
            if not re.fullmatch(r"20\d{2}", period):
                continue
            value = text(first(chip, "db-passport-year-value"))
            amount = decimal(value) if unit == "тыс. руб." else None
            xpath = tree.getroottree().getpath(chip)
            key = "|".join([doc["sha256"], row_type, xpath])
            cashflows.append({
                "record_id": hashlib.sha256(key.encode()).hexdigest()[:24],
                "project_id": crosswalk[doc["project"]]["analytics_project_id"],
                "project_name": crosswalk[doc["project"]]["project_name"],
                "row_type": row_type, "document_level": doc["document_level"],
                "document_title": doc["title"], "subject_name": subject_name,
                "source_name": source_name, "year": int(period), "value_raw": value,
                "amount_thousand_rub": dstr(amount),
                "amount_billion_rub": float(amount / Decimal(1000000)) if amount is not None else None,
                "unit_raw": unit, "source_sha256": doc["sha256"],
                "source_url": doc["url"], "local_html": "corpus/data/" + doc["html_path"],
                "source_xpath": xpath, "subject_xpath": subject_xpath,
                "edition_label": doc["publisher_version_label"],
                "publisher_updated_label": doc["publisher_updated_label"],
                "retrieved_at": doc["retrieved_at"],
                "source_kind": "secondary_epbs_rendering",
                "value_interpretation": "passport_financing_not_execution",
                "parse_status": "numeric" if amount is not None else "missing_or_unsupported_unit",
            })

    for doc in documents:
        file = root / "corpus/data" / doc["html_path"]
        if checksum(file) != doc["sha256"]:
            raise ValueError("Source SHA-256 mismatch: " + str(file))
        tree = html.fromstring(file.read_bytes())
        headers = tree.xpath(f'//header[{cls("db-exp-hero")}]')
        declared = None
        all_header_values = []
        for header in headers:
            for kpi in header.xpath(f'.//*[{cls("db-exp-kpi-item")}]'):
                if text(first(kpi, "db-exp-kpi-label")) == "Финансирование всего, тыс. руб.":
                    declared = decimal(text(first(kpi, "db-exp-kpi-value")))
            for container in header.xpath(f'.//*[{cls("db-exp-finance-years")}]'):
                add_chips(doc, tree, container, "document_header", tree.getroottree().getpath(header), doc["title"], "all_sources_declared")
        for section in tree.xpath('//*[@id="passport-finsupports"]'):
            for row in section.xpath(f'.//*[{cls("db-finsupport-row")}]'):
                source_name = text(first(row, "db-finsupport-source"))
                for container in row.xpath(f'./*[{cls("db-finsupport-years")}]'):
                    add_chips(doc, tree, container, "document_source", tree.getroottree().getpath(row), doc["title"], source_name)
        for card in tree.xpath(f'//*[@id="passport-results"]//details[{cls("db-result-fold")}]'):
            title = text(first(card, "db-result-fold-title"))
            for row in card.xpath(f'.//*[{cls("db-finsupport-row")}]'):
                source_name = text(first(row, "db-finsupport-source"))
                for container in row.xpath(f'./*[{cls("db-finsupport-years")}]'):
                    add_chips(doc, tree, container, "result_source", tree.getroottree().getpath(card), title, source_name)
        mine = [r for r in cashflows if r["source_sha256"] == doc["sha256"] and r["row_type"] == "document_header"]
        header_sum = total(decimal(r["amount_thousand_rub"]) for r in mine)
        target_period = [r for r in mine if r["year"] in YEARS]
        selected_sum = total((decimal(r["amount_thousand_rub"]) for r in target_period), len(YEARS))
        fin_sections = tree.xpath('//*[@id="passport-finsupports"]')
        fin_text = text(fin_sections[0]) if fin_sections else ""
        doc_rows.append({
            "project_id": crosswalk[doc["project"]]["analytics_project_id"],
            "project_name": crosswalk[doc["project"]]["project_name"],
            "source_sha256":doc["sha256"], "document_level":doc["document_level"], "document_title":doc["title"],
            "source_url":doc["url"], "local_html":"corpus/data/"+doc["html_path"],
            "edition_label":doc["publisher_version_label"], "publisher_updated_label":doc["publisher_updated_label"],
            "project_period_label":doc["period_label"],
            "financing_empty_notice":"Нет данных о финансировании с положительными суммами." if "Нет данных о финансировании с положительными суммами." in fin_text else None,
            "header_declared_total_thousand_rub":dstr(declared),
            "visible_header_year_sum_thousand_rub":dstr(header_sum),
            "header_years":json.dumps(sorted(r["year"] for r in mine)),
            "selected_2025_2030_total_thousand_rub":dstr(selected_sum),
            "header_total_difference_thousand_rub":dstr(header_sum-declared) if declared is not None and header_sum is not None else None,
            "source_kind":"secondary_epbs_rendering",
        })
    db.close()
    if len({r["record_id"] for r in cashflows}) != len(cashflows):
        raise ValueError("Duplicate financial evidence key")
    return cashflows, doc_rows, links, errors


def analyse(cashflows, documents, links):
    docs = {r["source_sha256"]:r for r in documents}
    by_url = {r["source_url"]:r for r in documents}
    headers, sources = defaultdict(list), defaultdict(list)
    for row in cashflows:
        if row["row_type"] == "document_header":
            headers[(row["source_sha256"], row["year"])].append(row)
        elif row["row_type"] == "document_source":
            sources[(row["source_sha256"], row["year"])].append(row)
    def header(sha, year):
        rows = headers[(sha, year)]
        return decimal(rows[0]["amount_thousand_rub"]) if len(rows) == 1 else None
    def period_amount(doc, years):
        observed = total((header(doc["source_sha256"], y) for y in years), len(years))
        if observed is not None:
            return observed, "sum_complete_annual_headers"
        # A declared project total can describe the whole selected horizon even
        # when the website suppresses some annual cells. No missing annual cell
        # is filled with zero. Require an explicit period entirely inside 2025–2030,
        # no visible year outside it, and an arithmetic reconciliation to the total.
        if tuple(years) == YEARS:
            span = re.fullmatch(r"\d{2}\.\d{2}\.(\d{4})\s*[-–—]\s*\d{2}\.\d{2}\.(\d{4})", doc["project_period_label"] or "")
            visible_years = json.loads(doc["header_years"])
            declared = decimal(doc["header_declared_total_thousand_rub"])
            visible = decimal(doc["visible_header_year_sum_thousand_rub"])
            if span and int(span[1]) >= 2025 and int(span[2]) <= 2030 and visible_years and all(y in YEARS for y in visible_years) and declared is not None and visible is not None and abs(declared-visible) <= Decimal("0.01")*(len(visible_years)+1):
                return declared, "explicit_full_project_total_within_selected_horizon"
        return None, "not_observed_no_zero_imputation"
    children = defaultdict(list)
    federal_links = []
    for link in links:
        parent = docs.get(link["parent_sha256"])
        if parent is None:
            continue
        child = by_url.get(link["child_url"])
        valid = child is not None and child["document_level"] == "federal" and child["project_id"] == parent["project_id"]
        if valid:
            children[parent["source_sha256"]].append(child)
        federal_links.append({"project_id":parent["project_id"], "parent_sha256":parent["source_sha256"],
                              "child_url":link["child_url"], "child_sha256":child["source_sha256"] if child else None,
                              "link_text":link["link_text"], "status":"resolved_same_project" if valid else "unresolved_or_conflicting"})
    year_summary, concentration, shares, reconciliations = [], [], [], []
    for doc in documents:
        for year in YEARS:
            head = header(doc["source_sha256"], year)
            rows = sources[(doc["source_sha256"], year)]
            vals = [decimal(r["amount_thousand_rub"]) for r in rows]
            summed = total(vals)
            difference = summed - head if summed is not None and head is not None else None
            tolerance = Decimal("0.01") * (len(rows) + 1)
            status = "not_comparable_missing" if difference is None else "arithmetically_matches" if abs(difference) <= tolerance else "does_not_reconcile"
            reconciliations.append({"project_id":doc["project_id"], "document_level":doc["document_level"],
                "source_sha256":doc["source_sha256"], "source_url":doc["source_url"], "year":year,
                "header_total_thousand_rub":dstr(head), "visible_source_rows":len(rows),
                "sum_visible_sources_thousand_rub":dstr(summed), "difference_thousand_rub":dstr(difference),
                "relative_difference_percent":float(difference/head*100) if difference is not None and head else None,
                "rounding_tolerance_thousand_rub":dstr(tolerance), "status":status,
                "interpretation":"diagnostic_only_no_consolidated_sum_or_execution_rate"})
        if doc["document_level"] != "national":
            continue
        kids = children[doc["source_sha256"]]
        declared_count = sum(1 for l in federal_links if l["parent_sha256"] == doc["source_sha256"])
        for period in [str(y) for y in YEARS] + ["2025–2030"]:
            selected_years = YEARS if "–" in period else (int(period),)
            amounts = [(kid, period_amount(kid, selected_years)[0]) for kid in kids]
            np_amount = period_amount(doc, selected_years)[0]
            fp_sum = total((a for _,a in amounts), declared_count) if len(kids) == declared_count else None
            visible_amounts = [a for _,a in amounts if a is not None and a >= 0]
            visible_sum = total(visible_amounts)
            visible_hhi = sum((a/visible_sum)**2 for a in visible_amounts) if visible_sum else None
            complete = bool(amounts) and fp_sum is not None and fp_sum > 0 and all(a is not None and a >= 0 for _,a in amounts)
            hhi = sum((a/fp_sum)**2 for _,a in amounts) if complete else None
            max_share = max((a/fp_sum for _,a in amounts), default=None) if complete else None
            leader = max(amounts, key=lambda x:x[1])[0]["document_title"] if complete else None
            concentration.append({"project_id":doc["project_id"], "project_name":doc["project_name"], "period":period,
                "national_sha256":doc["source_sha256"], "linked_federal_projects":declared_count,
                "resolved_federal_projects":len(kids), "numeric_federal_projects":sum(a is not None for _,a in amounts),
                "denominator_sum_fp_thousand_rub":dstr(fp_sum), "national_header_thousand_rub":dstr(np_amount),
                "visible_federal_sum_thousand_rub":dstr(visible_sum),
                "hhi_visible_only_0_1":float(visible_hhi) if visible_hhi is not None else None,
                "visible_scope_warning":"all_linked_fp_numeric" if complete else "incomplete_financial_disclosure_do_not_generalize_to_all_fp",
                "hhi_0_1":float(hhi) if hhi is not None else None, "hhi_0_10000":float(hhi*10000) if hhi is not None else None,
                "effective_number_1_over_hhi":float(1/hhi) if hhi else None,
                "largest_fp_share_percent":float(max_share*100) if max_share is not None else None,
                "largest_federal_project":leader,
                "status":"computed_complete_visible_fp_headers" if complete else "insufficient_comparable_headers",
                "edition_scope":"saved_html_2026_10_19_different_passport_versions",
                "interpretation":"allocation_concentration_not_efficiency"})
            for kid, amount in amounts:
                shares.append({"project_id":doc["project_id"], "period":period, "federal_project":kid["document_title"],
                    "source_sha256":kid["source_sha256"], "source_url":kid["source_url"], "edition_label":kid["edition_label"],
                    "amount_basis":period_amount(kid, selected_years)[1],
                    "amount_thousand_rub":dstr(amount), "denominator_sum_fp_thousand_rub":dstr(fp_sum),
                    "share_percent":float(amount/fp_sum*100) if complete else None,
                    "national_header_share_percent":float(amount/np_amount*100) if amount is not None and np_amount else None,
                    "share_denominator":"sum_of_linked_fp_headers_same_saved_corpus_not_consolidated_execution"})
            if "–" not in period:
                diff = fp_sum - np_amount if fp_sum is not None and np_amount is not None else None
                tolerance = Decimal("0.01") * (declared_count + 1)
                year_summary.append({"project_id":doc["project_id"], "project_name":doc["project_name"], "year":int(period),
                    "national_header_thousand_rub":dstr(np_amount), "national_header_billion_rub":float(np_amount/1000000) if np_amount is not None else None,
                    "linked_fp_sum_thousand_rub":dstr(fp_sum), "fp_minus_national_thousand_rub":dstr(diff),
                    "reconciliation_status":"missing" if diff is None else "arithmetically_matches" if abs(diff)<=tolerance else "does_not_reconcile",
                    "national_sha256":doc["source_sha256"], "national_source_url":doc["source_url"],
                    "national_edition_label":doc["edition_label"]})
    return {"f_federal_links":federal_links, "f_project_year":year_summary,
            "f_concentration":concentration, "f_federal_shares":shares, "f_source_reconciliation":reconciliations}


def family_reference(root):
    source = root / "research/audit/evidence/public/downloads/data/budget_by_federal_project.csv"
    if not source.exists():
        return [], {"status":"reference_not_available_yet", "expected_file":str(source.relative_to(root))}
    with source.open(encoding="utf-8-sig",newline="") as f:
        rows = list(csv.DictReader(f))
    output = []
    for period in [str(y) for y in YEARS] + ["2025–2030"]:
        amounts = [(r["federal_project"], decimal(r[period]) if "–" not in period else total(decimal(r[str(y)]) for y in YEARS)) for r in rows]
        denom = total(a for _,a in amounts)
        hhi = sum((a/denom)**2 for _,a in amounts) if denom else None
        for name, amount in amounts:
            output.append({"project_id":"family", "period":period, "federal_project":name,
                "amount_thousand_rub":dstr(amount), "denominator_thousand_rub":dstr(denom),
                "share_percent":float(amount/denom*100) if denom else None,
                "hhi_0_1":float(hhi) if hhi is not None else None,
                "source_file":str(source.relative_to(root)), "source_sha256":checksum(source),
                "source_url":f"https://github.com/Arseniy24RUS/family/blob/{REFERENCE_COMMIT}/public/downloads/data/budget_by_federal_project.csv",
                "edition_scope":"family_reference_snapshot_not_october_html_edition"})
    return output, {"status":"recomputed_from_original_csv", "source_file":str(source.relative_to(root)), "rows":len(output)}


def figures(output, tables):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family":"DejaVu Serif", "font.size":10, "svg.fonttype":"none"})
    dest = output / "figures"
    dest.mkdir(exist_ok=True)
    all_period_rows = [r for r in tables["f_concentration"] if r["period"] == "2025–2030"]
    rows = [r for r in all_period_rows if r["hhi_0_1"] is not None]
    rows.sort(key=lambda r:r["hhi_0_1"])
    labels = {"long_active_life":"Продолжительная и активная жизнь", "life_infrastructure":"Инфраструктура для жизни", "efficient_transport":"Эффективная транспортная система", "environment":"Экологическое благополучие", "international_export":"Международная кооперация и экспорт", "youth_children":"Молодёжь и дети", "personnel":"Кадры", "tourism":"Туризм и гостеприимство", "data_economy":"Экономика данных", "competitive_economy":"Эффективная и конкурентная экономика"}
    fig,ax=plt.subplots(figsize=(12,6.8))
    vals=[r["hhi_0_1"] for r in rows]
    bars=ax.barh([labels[r["project_id"]] for r in rows], vals, color="#207f8c")
    ax.set_xlim(0,1.04);ax.set_xlabel("Концентрация паспортного финансирования по ФП, HHI (0–1)")
    for b,r in zip(bars,rows):ax.text(b.get_width()+.012,b.get_y()+b.get_height()/2,f'{r["hhi_0_1"]:.3f} · {r["resolved_federal_projects"]} ФП',va="center",fontsize=9)
    ax.spines[["top","right"]].set_visible(False)
    ax.grid(axis="x",alpha=.18);ax.set_axisbelow(True)
    fig.subplots_adjust(left=.40,right=.97,top=.97,bottom=.13)
    for ext in ["svg","png"]:fig.savefig(dest/f"financing_concentration_2025_2030.{ext}",dpi=180)
    plt.close(fig)
    totals=sorted([r for r in all_period_rows if r["national_header_thousand_rub"] is not None],key=lambda r:Decimal(r["national_header_thousand_rub"]))
    fig,ax=plt.subplots(figsize=(12,6.8))
    vals=[float(Decimal(r["national_header_thousand_rub"])/Decimal(1000000000)) for r in totals]
    bars=ax.barh([labels[r["project_id"]] for r in totals],vals,color="#275d86")
    ax.set_xlabel("Паспортное финансирование 2025–2030, трлн руб. в номинальных ценах")
    ax.set_xlim(0,max(vals)*1.17 if vals else 1)
    for b,v in zip(bars,vals):ax.text(b.get_width()+max(vals)*.01,b.get_y()+b.get_height()/2,f"{v:.3f}",va="center",fontsize=9)
    ax.spines[["top","right"]].set_visible(False);ax.grid(axis="x",alpha=.18);ax.set_axisbelow(True)
    fig.subplots_adjust(left=.40,right=.97,top=.97,bottom=.13)
    for ext in ["svg","png"]:fig.savefig(dest/f"passport_financing_totals_2025_2030.{ext}",dpi=180)
    plt.close(fig)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output",type=Path,default=Path("outputs/research/finance"))
    parser.add_argument("--skip-figures",action="store_true")
    args=parser.parse_args(argv)
    root=args.package_root.resolve();output=args.output if args.output.is_absolute() else root/args.output
    output.mkdir(parents=True,exist_ok=True)
    cash,documents,links,errors=read_html_finance(root)
    tables={"f_documents":documents,"f_cashflows":cash,**analyse(cash,documents,links)}
    family,family_status=family_reference(root);tables["f_family_reference"]=family
    conn=sqlite3.connect(output/"research_finance.sqlite")
    for name,rows in tables.items():export_table(conn,output,name,rows)
    conn.execute('CREATE INDEX IF NOT EXISTS f_cashflows_source_subject ON f_cashflows(source_sha256,subject_xpath,year)')
    conn.execute('CREATE INDEX IF NOT EXISTS f_cashflows_project_type ON f_cashflows(project_id,row_type,year)')
    conn.commit();integrity=conn.execute("PRAGMA quick_check").fetchall();conn.close()
    summary={"version":"1.2.0", "method":"passport_financing_structure_and_concentration", "years":list(YEARS),
        "source_snapshot":"2026-10-19", "source_documents":len(documents), "projects":len({d["project_id"] for d in documents}),
        "tables":{name:len(rows) for name,rows in tables.items()}, "cashflow_types":dict(Counter(r["row_type"] for r in cash)),
        "computed_periods":dict(Counter(r["status"] for r in tables["f_concentration"])),
        "fp_header_reconciliation":dict(Counter(r["reconciliation_status"] for r in tables["f_project_year"])),
        "source_reconciliation":dict(Counter(r["status"] for r in tables["f_source_reconciliation"])),
        "family_reference":family_status, "sqlite_quick_check":integrity,
        "limitations":["Паспортное финансирование не является кассовым исполнением.", "Сохранены разные редакции паспортов, их одновременное утверждение не подтверждено.", "Сумма источников не считается консолидированным бюджетом без проверки трансфертов.", "HHI описывает концентрацию средств среди доступных ФП, не эффективность расходов.", "Расходы на единицу эффекта не рассчитаны: нет сопоставимого исполнения и идентифицированного эффекта."]}
    (output/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    if not args.skip_figures:figures(output,tables)
    (output/"METHODS_RU.md").write_text('''# Финансовая структура: протокол 1.2.0

Расчёт использует неизменные HTML-снимки Databudget, включённые в корпус. Перед извлечением каждого файла проверяется SHA-256. Databudget является вторичным представлением сведений ЕПБС. Подлинность подписанного паспорта и действующая юридическая редакция этим расчётом не удостоверяются.

## Измерение

`f_cashflows` сохраняет три разных уровня: итог документа в заголовке, строки источников финансового обеспечения документа и источники финансового обеспечения конкретного результата. Уровни никогда не складываются друг с другом. Денежные значения переводятся в Decimal из исходной строки, тысяч рублей. Месячные строки и итоги внутри помесячного плана не включаются в годовые суммы. Исходный год, DOM-путь, SHA-256, URL и метка редакции сохраняются у каждой записи. Текстовое NULL отличается от нуля.

Основной горизонт – 2025–2030. В исходной таблице сохраняются также годы за этим горизонтом. Общий итог заголовка сверяется со всеми явно показанными годами, а не автоматически трактуется как сумма за 2025–2030. Данные относятся к паспортному финансовому обеспечению, не к кассовому исполнению или фактическим затратам.

## Концентрация и знаменатель

Для каждого национального проекта используется именно список федеральных проектов `web_project_links`. Подтверждаются документ, принадлежность проекту и числовое значение каждого ФП. Доли рассчитываются как s_i = B_i / sum(B_i), HHI = sum(s_i²), эффективное число ФП = 1/HHI. Значения HHI находятся в пределах 1/n и 1. На шкале 0–10000 используется HHI×10000. В таблице есть отдельные результаты по годам и за шесть лет. Ненаблюдаемые бюджеты не заменяются нулём, а неполная группа не получает HHI.

Знаменатель HHI – сумма заголовков связанных ФП из сохранённого корпуса. Заголовок национального проекта хранится отдельно. Между паспортами могут различаться редакции, поэтому совпадение сумм проверяется, а расхождения публикуются. Порог арифметической сверки равен 0,01 тыс. руб. × (число слагаемых + 1). Совпадение в пределах округления не доказывает отсутствие трансфертов или полную согласованность версий.

Для шестилетнего итога допускается прямо опубликованное «Финансирование всего», если весь указанный срок ФП находится внутри 2025–2030, все показанные финансовые годы входят в этот горизонт и их сумма совпадает с опубликованным итогом. Основание отмечается `explicit_full_project_total_within_selected_horizon`. Отсутствующие годовые ячейки при этом остаются пропусками. Сообщение сайта «Нет данных о финансировании с положительными суммами» не заменяется нулевым бюджетом. При неполном раскрытии строгий HHI всех ФП отсутствует. Поле `hhi_visible_only_0_1` отдельно описывает только числовую наблюдаемую часть и не переносится на полный состав проекта.

## Источники и результаты

`f_source_reconciliation` сравнивает сумму видимых строк источников с заголовком документа. Непересекаемость источников не предполагается. Расхождение является диагностическим сигналом: возможны трансферты, неполное представление и разные правила агрегирования. Процент исполнения бюджета на этих данных не рассчитывается. Записи `result_source` связываются с текстовым реестром по source_sha256 + subject_xpath, сохраняя отдельно источник финансирования.

Доли и HHI исходной «Семьи» при наличии эталонного CSV пересчитаны в `f_family_reference`. Они имеют метку family_reference_snapshot и отдельную редакцию. Их нельзя трактовать как синхронный октябрьский снимок остальных десяти проектов.

## Интерпретация и воспроизводимость

Большая концентрация означает большую долю одного ФП в выбранном финансовом контуре. Она не означает неэффективность, низкую результативность или ненадлежащие расходы. Сопоставление номинальных сумм не содержит поправки на инфляцию. Удельная стоимость результата и экономическая отдача не оцениваются без согласованных расходов, получателей и причинно идентифицированных исходов.

Запуск из корня комплекта:

```bash
python research/finance_analysis.py --output outputs/research/finance
```

Зависимости: lxml, matplotlib. Точные денежные расчёты используют стандартный decimal. Сеть не используется.
''',encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary


if __name__ == "__main__":
    main()
