#!/usr/bin/env python3
"""Export a compact source-backed foundation for eleven national projects.

Uses only Python's standard library and opens the research database read-only.
Displayed statistical values come exclusively from the current live EMISS
snapshot, with unit, frequency, category and original observation identity.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

PROJECTS = (
    "family", "long_active_life", "youth_children", "tourism", "personnel",
    "life_infrastructure", "efficient_transport", "environment",
    "international_export", "data_economy", "competitive_economy",
)
AS_OF = "2026-10-15"
DOCUMENTARY_AS_OF = "2026-10-19"
RELEASE = "1.2.0"
TABLES = {
    "indicators": "outputs/tables/indicator_audit.csv",
    "projects": "outputs/tables/project_audit.csv",
    "results": "outputs/tables/project_results.csv",
    "panels": "outputs/tables/multivariate_panels.csv",
    "documents": "outputs/tables/document_sources.csv",
    "crosswalk": "outputs/tables/corpus_project_crosswalk.csv",
    "summary": "outputs/research/tables/r_project_summary.csv",
    "methods": "outputs/research/audit/project_method_matrix.csv",
    "eligibility": "outputs/research/audit/project_method_eligibility.csv",
    "sections": "outputs/research/audit/section_order.csv",
    "corpus": "corpus/data/project_summary.csv",
}
NUMERIC = {
    "coverage_pct", "region_coverage_pct", "imputed_pct", "silhouette",
    "pc12_variance", "complete_case_ari", "k", "seed", "numeric_indicators",
    "regional_indicators", "registry_indicators", "indicators_with_numeric",
    "indicators_with_regional", "observations_numeric", "documents", "goal_nodes",
    "task_nodes", "indicator_nodes", "result_nodes", "unresolved_link_claims",
    "shared_task_result_indicator_links", "results_linked_through_documented_task",
    "results_with_lexical_candidate", "explicit_result_indicator_links",
    "family_original_manual_edges", "passport_financing_2025_2030_thousand_rub",
    "strict_financing_hhi", "unique_pdf_files", "pages", "national_passport_files",
    "federal_passport_files", "presentation_files", "legal_reprints",
    "section_number", "order", "multivariate_n_regions", "multivariate_n_features",
}


def typed(row: dict) -> dict:
    result = {}
    for key, value in row.items():
        if key.startswith("n_") or key in NUMERIC:
            if value in ("", None):
                result[key] = None
            else:
                number = float(value)
                result[key] = int(number) if number.is_integer() else number
        else:
            result[key] = value
    return result


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [typed(row) for row in csv.DictReader(handle)]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_national(connection: sqlite3.Connection) -> list[dict]:
    # Restrict observations to the exact current source snapshot. Equal period
    # dates are broken deterministically by observation_key, never by value.
    query = """
        WITH ranked AS (
          SELECT a.*, s.unit, s.territory_name, sp.acquired_at, sp.origin_kind,
                 src.source_title, src.source_url,
                 ROW_NUMBER() OVER (
                   PARTITION BY a.series_id
                   ORDER BY a.period_end DESC, a.period_index DESC, a.observation_key
                 ) AS rank_in_series
          FROM a_observations AS a
          JOIN a_series AS s ON s.series_id = a.series_id
          JOIN current_sources AS cur
            ON cur.source_id = a.source_id AND cur.snapshot_id = a.snapshot_id
          JOIN snapshots AS sp ON sp.snapshot_id = a.snapshot_id
          JOIN sources AS src ON src.source_id = a.source_id
          WHERE a.geo_level = 'national'
            AND a.analysis_status = 'usable'
            AND a.domain_violation = 0 AND a.after_as_of = 0
            AND sp.origin_kind = 'live_emiss'
            AND a.period_end <= ? AND a.value IS NOT NULL
        )
        SELECT * FROM ranked WHERE rank_in_series = 1 ORDER BY source_id, series_id
    """
    keep = ("series_id", "source_id", "source_url", "source_title", "value", "unit",
            "period", "period_end", "frequency", "territory_name", "snapshot_id",
            "observation_key", "acquired_at", "origin_kind", "analysis_status")
    result = []
    for row in connection.execute(query, (AS_OF,)):
        item = {key: row[key] for key in keep}
        item["category"] = json.loads(row["category_json"] or "{}")
        result.append(item)
    return result


def document_row(row: dict) -> dict:
    urls = [url for url in json.loads(row["source_urls_json"] or "[]")
            if url.startswith(("https://", "http://"))]
    return {
        "title": row["title"], "url": urls[0] if urls else None, "urls": urls,
        **{key: row[key] for key in ("format", "document_level", "sha256", "qualification",
           "retrieved_at", "publisher_version_label", "publisher_updated_label",
           "approval_date", "edition_date", "source_type")},
        "source_file_in_research_package": row["source_file"],
    }


def section_evidence(section: dict, project: dict, summary: dict, panel: dict) -> str:
    explanations = {
        "framework": "Реестр методов и их ограничений подготовлен; содержательные выводы требуют отдельной авторской экспертизы.",
        "logic": f"В исследовательском корпусе: {summary.get('goal_nodes', 0)} целей, {summary.get('task_nodes', 0)} задач, {summary.get('result_nodes', 0)} результатов. Документальная связь не является доказательством причинного эффекта.",
        "audit": f"В реестре {project['n_registry']} показателей; числовые данные доступны для {project['n_with_numeric']}, региональные для {project['n_with_regional']}.",
        "targets": "Паспортные цели и статистические ряды сопоставляются только при подтверждённом совпадении показателя, единицы измерения, территории и периода.",
        "map": f"Региональные данные имеются для {project['n_with_regional']} показателей. Карты требуют отдельной проверки сопоставимости выбранного периода.",
        "regions": f"Статус многомерной панели: {panel.get('status', 'нет панели')}; территорий: {panel.get('n_regions') or 0}, признаков: {panel.get('n_features') or 0}. Региональная типология не тождественна оценке эффективности.",
        "finance": "Финансовые суммы и доли сохраняют единицы исходного паспорта. Оценка распределения средств зависит от сопоставимости заголовков федеральных проектов.",
        "network": "В корпусе разделены документальные связи, совместная принадлежность задаче и лексические кандидаты. Автоматическая похожесть не превращается в доказанную связь.",
        "texts": f"Документальная основа исследовательского модуля: {summary.get('documents', 0)} документов. Лексические признаки рассматриваются совместно с контекстом.",
        "domains": "Сферы жизнедеятельности выделяются по корпусу и словарям; полнота охвата требует содержательной проверки экспертом.",
        "causal": "Причинный эффект нацпроекта в имеющемся наборе источников не идентифицирован. Для его оценки нужен самостоятельный исследовательский дизайн.",
        "proposals": "Рекомендации формируются после проверки фактов и содержательной экспертизы, с указанием адресата, механизма и ожидаемого результата.",
    }
    return explanations[section["section_id"]]


def export(research_root: Path, site_root: Path) -> dict:
    tables = {name: read_csv(research_root / relative) for name, relative in TABLES.items()}
    database = research_root / "outputs/national_projects_analytics.sqlite"
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    national = load_national(connection)
    links = collections.defaultdict(list)
    for row in connection.execute("SELECT indicator_code, source_id FROM indicator_sources ORDER BY indicator_code, source_id"):
        links[row["indicator_code"]].append(row["source_id"])
    project_sources = {row["project_id"]: dict(row) for row in connection.execute("SELECT * FROM projects WHERE included=1")}
    connection.close()

    national_by_source = collections.defaultdict(list)
    for observation in national:
        national_by_source[observation["source_id"]].append(observation)
    root = site_root / "public/data/projects"
    shared = site_root / "public/downloads/projects/shared"
    shared.mkdir(parents=True, exist_ok=True)
    download_specs = (
        ("indicators", "indicator_audit.csv", "Аудит 339 показателей"),
        ("projects", "project_audit.csv", "Сводный аудит 11 нацпроектов"),
        ("methods", "project_method_matrix.csv", "Матрица методов по нацпроектам"),
        ("eligibility", "project_method_eligibility.csv", "Применимость методов и доступность данных"),
    )
    downloads = []
    for key, name, title in download_specs:
        shutil.copyfile(research_root / TABLES[key], shared / name)
        downloads.append({"title": title, "url": "downloads/projects/shared/" + name,
                          "sha256": digest(shared / name), "bytes": (shared / name).stat().st_size})

    inventory = []
    nested_count = 0
    for project_id in PROJECTS:
        project = next(row for row in tables["projects"] if row["project_id"] == project_id)
        summary = next(row for row in tables["summary"] if row["project_id"] == project_id)
        panel = next((row for row in tables["panels"] if row["project_id"] == project_id), {})
        result = next(row for row in tables["results"] if row["project_id"] == project_id)
        methods = [row for row in tables["methods"] if row["project_id"] == project_id]
        indicators = []
        for row in tables["indicators"]:
            if row["project_id"] != project_id:
                continue
            latest = [observation for source in links[row["indicator_code"]] for observation in national_by_source[source]]
            indicators.append({**row, "source_ids": links[row["indicator_code"]], "latest_national": latest})
            nested_count += len(latest)
        # Family uses its separate retained reference edition. The crosswalk for
        # the new PDF/HTML corpus deliberately contains only the ten additions.
        corpus_id = next((row["corpus_project_id"] for row in tables["crosswalk"] if row["analytics_project_id"] == project_id), project_id)
        corpus = next((row for row in tables["corpus"] if row["project"] == corpus_id), {})
        sources = [document_row(row) for row in tables["documents"]
                   if corpus_id in json.loads(row["projects_json"] or "[]")]
        sources.sort(key=lambda row: (row["document_level"] != "national", row["format"] != "PDF", row["title"]))
        sections = [{**section, "publication_status": "planned",
                     "evidence": section_evidence(section, project, summary, panel),
                     "method_ids": [method["method_id"] for method in methods if method["section_number"] == section["order"]]}
                    for section in tables["sections"]]
        foundation = {
            "schema_version": 1, "project_id": project_id,
            "project_name": project["project_name"], "release_version": RELEASE,
            "statistical_as_of": AS_OF, "documentary_as_of": "2026-05-14" if project_id == "family" else DOCUMENTARY_AS_OF,
            "release_date": "2026-10-27", "author_expertise_status": "next_requested_stage",
            "registry": project, "panel": panel, "research": summary,
            "results": result, "corpus": corpus,
            "method_summary": {"total": len(methods), "by_status": dict(collections.Counter(row["status_1_2"] for row in methods))},
            "sections": sections, "sources": sources, "downloads": downloads,
            "registry_source_url": project_sources[project_id]["source_url"],
            "interpretation": "Актуальный доступный статистический срез на указанную дату. Дата сборки сайта не означает обновление первичных данных. Новые авторские страницы экспертизы добавляются после отдельной проверки.",
        }
        write_json(root / project_id / "foundation.json", foundation)
        write_json(root / project_id / "indicators.json", {
            "schema_version": 1, "project_id": project_id, "as_of": AS_OF,
            "origin_policy": "current_sources + live_emiss + usable + period_end <= as_of",
            "items": indicators,
        })
        write_json(root / project_id / "methods.json", {
            "schema_version": 1, "project_id": project_id, "release_version": RELEASE,
            "items": methods,
        })
        inventory.append({"project_id": project_id, "indicators": len(indicators),
                          "methods": len(methods), "latest_national": sum(len(item["latest_national"]) for item in indicators),
                          "sources": len(sources)})

    provenance = {
        "schema_version": 1, "research_release": RELEASE,
        "statistical_as_of": AS_OF, "documentary_as_of": DOCUMENTARY_AS_OF,
        "sources": [{"path": relative, "sha256": digest(research_root / relative),
                     "bytes": (research_root / relative).stat().st_size} for relative in TABLES.values()],
        "database": {"path": "outputs/national_projects_analytics.sqlite", "sha256": digest(database), "mode": "read_only"},
        "national_selection": "One latest usable observation per national series in the exact current live_emiss snapshot; category, unit and frequency are retained separately.",
    }
    write_json(root / "provenance.json", provenance)
    write_json(root / "publication.json", {
        "schema_version": 1, "research_release": RELEASE, "statistical_as_of": AS_OF,
        "documentary_as_of": DOCUMENTARY_AS_OF, "projects": inventory,
        "note": "Inventory of source data, not an approval registry for authorial expertise pages.",
    })
    verification = {
        "research_release": RELEASE, "projects": len(inventory),
        "indicators": sum(row["indicators"] for row in inventory),
        "method_rows": sum(row["methods"] for row in inventory),
        "latest_national_observations": len(national), "nested_national_observations": nested_count,
        "all_national_current_live_usable": all(row["origin_kind"] == "live_emiss" and row["analysis_status"] == "usable" and row["period_end"] <= AS_OF for row in national),
        "unique_national_series": len({row["series_id"] for row in national}),
        "null_numeric_values": sum(row["value"] is None for row in national),
        "project_inventory": inventory,
    }
    assert verification["projects"] == 11
    assert verification["indicators"] == len(tables["indicators"])
    assert verification["method_rows"] == len(tables["methods"])
    assert verification["unique_national_series"] == len(national)
    assert verification["all_national_current_live_usable"]
    assert verification["null_numeric_values"] == 0
    write_json(root / "export-validation.json", verification)
    return verification


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("research_root", type=Path, help="Unpacked NationalProjects_Analytics_1.2.0 directory")
    parser.add_argument("--site-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(export(args.research_root.resolve(), args.site_root.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
