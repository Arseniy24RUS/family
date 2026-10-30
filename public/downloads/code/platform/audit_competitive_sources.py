#!/usr/bin/env python3
"""Independent source audit; no imports from the application or its normalizers.

Checks every published observation against the retained input key, then checks
every input observation against the physically retained XLS/SDMX/grid export.
XLS cell addressing and SDMX XML decoding are deliberately implemented here.
Only QA output is written.  Source files are opened read-only.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import xlrd


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
PROJECT = PUBLIC / "data/projects/competitive_economy"
EXPORT = PUBLIC / "downloads/projects/competitive_economy/statistics"
NS = {"g": "http://www.SDMX.org/resources/SDMXML/schemas/v1_0/generic",
      "s": "http://www.SDMX.org/resources/SDMXML/schemas/v1_0/structure"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = Decimal(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
        return n if n.is_finite() else None
    except InvalidOperation:
        return None


def eq_number(a, b):
    return decimal(a) == decimal(b)


def audit_source(bundle):
    sid = bundle.stem
    failures = []
    failure_counts = Counter()
    checks = Counter()

    def check(kind, actual, expected, key=None):
        checks[kind] += 1
        if actual != expected:
            failure_counts[kind] += 1
            if len(failures) < 30:
                failures.append({"check": kind, "key": key, "actual": actual,
                                 "expected": expected})
            return False
        return True

    with zipfile.ZipFile(bundle) as z:
        input_bytes = z.read("input.json")
        inp = json.loads(input_bytes)
        observations = inp["observations"]
        by_key = {o["observation_key"]: o for o in observations}
        check("input_keys_unique", len(by_key), len(observations))
        for o in observations:
            check("independent_raw_numeric_parse", decimal(o["value_raw"]),
                  decimal(o["value_numeric"]), o["observation_key"])

        published_path = PROJECT / "series" / f"{sid}.json"
        published_bytes = published_path.read_bytes()
        pub = json.loads(published_bytes)
        pubrows = pub["observations"]
        check("published_count", len(pubrows), len(observations))
        check("published_keys_complete", sorted(o["source_observation_key"] for o in pubrows),
              sorted(by_key))
        check("published_ids_unique", len({o["id"] for o in pubrows}), len(pubrows))
        check("snapshot_identity", pub["snapshot_id"], inp["snapshot"]["snapshot_id"] if inp["snapshot"] else None)
        check("source_identity", pub["source_id"], sid)

        numeric = missing = 0
        for p in pubrows:
            key = p["source_observation_key"]
            o = by_key.get(key)
            if o is None:
                check("input_key_present", False, True, key)
                continue
            direct_pairs = {
                "raw_value": (p["raw_value"], o["value_raw"]),
                "raw_alias": (p["raw"], o["value_raw"]),
                "numeric_value": (p["value"], o["value_numeric"]),
                "unit": (p["unit"], o["unit"]),
                "year": (p["year"], o["year"]),
                "dimensions": (p["source_dimensions"], json.loads(o["dimensions_json"])),
                "attributes": (p["source_attributes"], json.loads(o["attributes_json"])),
                "source_id": (p["source_id"], o["source_id"]),
                "source_frequency": (p["source_frequency"], o["period_kind"]),
                "source_period_start": (p["source_period_start"], o["period_start"]),
                "source_period_end": (p["source_period_end"], o["period_end"]),
            }
            for name, pair in direct_pairs.items():
                check("published_" + name, *pair, key)
            if p["value"] is None:
                missing += 1
            else:
                numeric += 1

        provenance = json.loads((PROJECT / "provenance" / f"{sid}.json").read_bytes())
        check("published_sha256", digest(published_bytes), provenance["published_sha256"])
        # Provenance names input_bundle as the hashed object (the ZIP), rather
        # than its inner input.json member. Retain both hashes in this audit.
        check("input_bundle_sha256", digest(bundle.read_bytes()), provenance["input_sha256"])
        evidence = []
        for e in inp["evidence_files"]:
            payload = z.read(e["archive_path"])
            check("evidence_sha256", digest(payload), e["sha256"], e["archive_path"])
            check("evidence_bytes", len(payload), e["bytes"], e["archive_path"])
            evidence.append({"path": e["archive_path"], "bytes": len(payload), "sha256": digest(payload)})

        # The convenience CSV must contain the same IDs, original strings, units,
        # and values. Its deliberate omission of detailed dimensions is covered
        # by the full published JSON checks above.
        pub_by_id = {p["id"]: p for p in pubrows}
        with gzip.open(EXPORT / "series" / f"{sid}.csv.gz", "rt", encoding="utf-8-sig", newline="") as f:
            csvrows = list(csv.DictReader(f))
        check("csv_count", len(csvrows), len(pubrows))
        check("csv_ids_complete", sorted(r["id"] for r in csvrows), sorted(pub_by_id))
        for r in csvrows:
            p = pub_by_id[r["id"]]
            check("csv_raw_value", r["raw_value"], p["raw_value"] or "", r["id"])
            check("csv_unit", r["unit"], p["unit"], r["id"])
            check("csv_value", decimal(r["value"]), decimal(p["value"]), r["id"])
            check("csv_period", r["period"], p["period"], r["id"])

        if inp['snapshot'] is None:
            check('metadata_only_without_observations',len(observations),0)
            return {"source_id":sid,"observations":len(pubrows),"numeric":numeric,"missing":missing,
               "input_sha256":digest(input_bytes),"published_sha256":digest(published_bytes),
               "bundle_sha256":digest(bundle.read_bytes()),"evidence_files":evidence,
               "physical_export":{"format":"metadata_only","observations_checked":0},
               "checks":dict(checks),"failure_counts":dict(failure_counts),"failure_examples":failures,
               "national_annual_original_records":[]}

        rawfiles = [n for n in z.namelist() if re.search(r"/part_\d+\.(xls|xml\.gz|json\.gz)$", n)]
        check("one_source_export", len(rawfiles), 1)
        rawname = rawfiles[0]
        rawbytes = z.read(rawname)
        physical = {"path": rawname, "sha256": digest(rawbytes), "observations_checked": len(observations)}
        national_examples = []

        if rawname.endswith(".xls"):
            physical["format"] = "xls"
            book = xlrd.open_workbook(file_contents=rawbytes, formatting_info=True)
            sheet_names = book.sheet_names()
            all_coordinates = set()
            rounding_equivalences = 0
            for o in observations:
                key = o["observation_key"]
                attrs = json.loads(o["attributes_json"])
                dims = json.loads(o["dimensions_json"])
                sheet = book.sheet_by_name(attrs["source_sheet"])
                match = re.fullmatch(r"R(\d+)C(\d+)", attrs["source_cell"])
                if not check("xls_cell_address", bool(match), True, key):
                    continue
                row, col = (int(v) - 1 for v in match.groups())
                check("xls_coordinate_unique", (sheet.name, row, col) not in all_coordinates, True, key)
                all_coordinates.add((sheet.name, row, col))
                cell = sheet.cell_value(row, col)
                a, b = decimal(cell), decimal(o["value_raw"])
                if a is not None and b is not None:
                    if a != b and abs(a - b) <= Decimal("1e-12") * max(Decimal(1), abs(a)):
                        rounding_equivalences += 1
                        check("xls_numeric_cell_with_float_tolerance", True, True, attrs["source_cell"])
                    else:
                        check("xls_numeric_cell", a, b, attrs["source_cell"])
                else:
                    check("xls_missing_or_text_cell", str(cell), o["value_raw"], attrs["source_cell"])
                # Independently read physical axes, including source 62828,
                # whose years are row labels and unit is a merged column header.
                def physical_label(rr,cc):
                    for rlo,rhi,clo,chi in sheet.merged_cells:
                        if rlo <= rr < rhi and clo <= cc < chi:
                            return str(sheet.cell_value(rlo,clo)).strip()
                    return str(sheet.cell_value(rr,cc)).strip()
                rowlabels=[physical_label(row,c) for c in range(2)]
                collabels=[physical_label(r,col) for r in (2,3)]
                filters=json.loads(inp["snapshot"]["metadata_json"])["filters"]
                by_title={f["title"]:f for f in filters}
                year_axis=collabels if by_title["Год"]["object_parameter"]=="columnObjectIds" else rowlabels
                unit_axis=collabels if by_title["Единица измерения"]["object_parameter"]=="columnObjectIds" else rowlabels
                check("xls_year_header", str(o["year"]) in year_axis, True, attrs["source_cell"])
                check("xls_period_header", dims["Период"].strip() in collabels, True, attrs["source_cell"])
                check("xls_unit_axis", o["unit"].strip() in unit_axis, True, attrs["source_cell"])
                territorial = {k: v for k, v in dims.items()
                               if k not in {"Год", "Единица измерения", "Период", "Показатель"}}
                check("xls_one_territory_dimension", len(territorial), 1, attrs["source_cell"])
                for name, value in territorial.items():
                    check("xls_territory_row", str(value).strip() in rowlabels, True, attrs["source_cell"])
                check("xls_indicator_title", str(sheet.cell_value(0, 0)), dims["Показатель"], key)
            # Excel omits all headers for unused future columns. Missing cells
            # under real headers are retained; unlabelled columns are not data.
            all_source_coordinates = set()
            for s in book.sheets():
                for c in range(2, s.ncols):
                    if not str(s.cell_value(3, c)).strip():
                        check("xls_unlabelled_column_empty", all(s.cell(r,c).ctype != xlrd.XL_CELL_NUMBER for r in range(4,s.nrows)), True, str(c))
                        continue
                    all_source_coordinates.update((s.name,r,c) for r in range(4,s.nrows))
            check("xls_complete_source_rectangle", sorted(all_coordinates), sorted(all_source_coordinates))
            physical.update({"sheets": sheet_names, "physical_cells": len(all_source_coordinates),
                             "numeric_float_rounding_equivalences": rounding_equivalences,
                             "headers_checked": ["year", "period", "unit", "territory", "indicator"]})

        elif rawname.endswith(".xml.gz"):
            physical["format"] = "sdmx"
            tree = ET.fromstring(gzip.decompress(rawbytes))
            codelists = {}
            for cl in tree.findall(".//s:CodeList", NS):
                codelists[cl.attrib["id"]] = {
                    "name": cl.findtext("s:Name", namespaces=NS),
                    "codes": {c.attrib["value"]: c.findtext("s:Description", namespaces=NS)
                              for c in cl.findall("s:Code", NS)}}
            physical_records = Counter()
            series_concepts = set()
            decoded_records = []
            for s in tree.findall(".//g:Series", NS):
                codes = {v.attrib["concept"]: v.attrib["value"] for v in s.findall("g:SeriesKey/g:Value", NS)}
                series_concepts.update(codes)
                attributes = {v.attrib["concept"]: v.attrib["value"] for v in s.findall("g:Attributes/g:Value", NS)}
                for obs in s.findall("g:Obs", NS):
                    attrs = dict(attributes)
                    attrs.update({v.attrib["concept"]: v.attrib["value"] for v in obs.findall("g:Attributes/g:Value", NS)})
                    year = obs.findtext("g:Time", namespaces=NS)
                    val = obs.find("g:ObsValue", NS).attrib["value"]
                    key = (tuple(sorted(codes.items())), str(year), attrs.get("EI"), attrs.get("PERIOD"), val)
                    physical_records[key] += 1
                    decoded = {codelists[k]["name"]: codelists[k]["codes"].get(v, v) for k, v in codes.items()}
                    decoded_records.append((key, decoded))
                    if (any("Российская Федерация" in str(v) for v in decoded.values())
                            and attrs.get("PERIOD") == "значение показателя за год"
                            and 2008 <= int(year) <= 2025):
                        national_examples.append({"year": int(year), "unit": attrs.get("EI"),
                            "period_label": attrs.get("PERIOD"), "dimensions": decoded,
                            "raw_value": val, "series_key": codes})
            input_records = Counter()
            by_physical_key = {}
            for o in observations:
                dims = json.loads(o["dimensions_json"])
                codes = json.loads(o["dimension_codes_json"])
                attrs = json.loads(o["attributes_json"])
                key = (tuple(sorted((k, codes.get(k)) for k in series_concepts)), str(o["year"]),
                       o["unit"], dims.get("Период"), o["value_raw"])
                input_records[key] += 1
                by_physical_key[key] = (o, dims)
                check("sdmx_year_dimension", dims["Год"], str(o["year"]), o["observation_key"])
                check("sdmx_unit_attribute", attrs.get("EI"), o["unit"], o["observation_key"])
                check("sdmx_period_attribute", attrs.get("PERIOD"), dims.get("Период"), o["observation_key"])
            check("sdmx_complete_source_records", input_records, physical_records)
            for key, decoded in decoded_records:
                if key not in by_physical_key:
                    continue
                o, dims = by_physical_key[key]
                for name, label in decoded.items():
                    check("sdmx_decoded_dimension", dims.get(name), label, o["observation_key"])
            physical.update({"xml_observations": sum(physical_records.values()),
                "series": len(tree.findall(".//g:Series", NS)), "series_concepts": sorted(series_concepts),
                "code_lists": {k: {"name": v["name"], "codes": len(v["codes"])} for k, v in codelists.items()},
                "national_annual_examples_checked": len(national_examples)})

        elif rawname.endswith(".json.gz"):
            physical["format"] = "grid"
            rows = json.loads(gzip.decompress(rawbytes))["results"]
            metadata = z.read(next(n for n in z.namelist() if n.endswith("metadata.html"))).decode("utf-8")
            titles = {}
            for match in re.finditer(r"\b(\d+):\s*\{\s*title:\s*'((?:\\.|[^'])*)'", metadata):
                rawtitle = match.group(2).replace("\\'", "'").replace('"', '\\"')
                titles[match.group(1)] = json.loads('"' + rawtitle + '"')
            used = set()
            for o in observations:
                attrs = json.loads(o["attributes_json"])
                dims = json.loads(o["dimensions_json"])
                codes = json.loads(o["dimension_codes_json"])
                index = attrs["source_row"]
                row = rows[index]
                field = (f"dim{o['year']}_{codes['33560']}_d{attrs['source_data_id']}"
                         f"_i{attrs['source_cell_indicator_id']}")
                check("grid_coordinate_unique", (index, field) not in used, True, o["observation_key"])
                used.add((index, field))
                check("grid_field_present", field in row, True, o["observation_key"])
                check("grid_raw_value", row.get(field), o["value_raw"], field)
                check("grid_year_code", codes["3"], str(o["year"]), field)
                check("grid_period_label_from_metadata", dims["Период"], titles.get(codes["33560"]), field)
                check("grid_unit", row["dim30611"], o["unit"], field)
                geo_fields=[f for f in json.loads(inp["snapshot"]["metadata_json"])["filters"] if any(k in f["title"].casefold() for k in ("окато","октмо","оксм","территори","регионы российской"))]
                check("grid_one_geography_axis",len(geo_fields),1,field)
                geo=geo_fields[0]
                check("grid_territory", row["dim"+geo["field_id"]], dims[geo["title"]], field)
                check("grid_indicator_title", row["dim0"], dims["Показатель"], field)
            all_grid_fields = {(i, field) for i, row in enumerate(rows) for field in row
                               if re.fullmatch(r"dim\d{4}_\d+_d\d+_i\d+", field)}
            check("grid_complete_source_fields", sorted(used), sorted(all_grid_fields))
            physical.update({"rows": len(rows), "physical_cells": len(all_grid_fields),
                             "period_metadata_titles": len(titles)})
        else:
            raise AssertionError(rawname)

    return {"source_id": sid, "observations": len(pubrows), "numeric": numeric, "missing": missing,
            "input_sha256": digest(input_bytes), "published_sha256": digest(published_bytes),
            "bundle_sha256": digest(bundle.read_bytes()), "evidence_files": evidence,
            "physical_export": physical, "checks": dict(checks),
            "failure_counts": dict(failure_counts), "failure_examples": failures,
            "national_annual_original_records": national_examples}


def json_safe(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Counter):
        return [[list(k), v] for k, v in obj.items()]
    raise TypeError(type(obj).__name__)


def main():
    global ROOT, PUBLIC, PROJECT, EXPORT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    ROOT = args.root.resolve()
    PUBLIC = ROOT / 'public'
    PROJECT = PUBLIC / 'data/projects/competitive_economy'
    EXPORT = PUBLIC / 'downloads/projects/competitive_economy/statistics'
    output_path = args.output or ROOT / '.cache/competitive-source-audit.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    declared = {str(s['id']) for s in json.loads((PROJECT / 'statistics.json').read_text())['sources']}
    bundled = {p.stem for p in (EXPORT / 'emiss_inputs').glob('*.zip')}
    if not declared or bundled != declared:
        raise ValueError('Source bundle membership differs from the published catalogue.')
    sources = []
    for bundle in sorted((EXPORT / "emiss_inputs").glob("*.zip")):
        result = audit_source(bundle)
        sources.append(result)
        print(result["source_id"], result["observations"], result["physical_export"]["format"],
              "failures", sum(result["failure_counts"].values()), flush=True)
    check_counts = Counter()
    failure_counts = Counter()
    formats = Counter()
    for source in sources:
        check_counts.update(source["checks"])
        failure_counts.update(source["failure_counts"])
        formats[source["physical_export"]["format"]] += source["observations"]
    output = {"audit": "Independent physical source to published observation audit",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "method": "No application modules or production normalizers imported. stdlib XML/JSON and xlrd read original retained exports. Exact JSON fields and raw strings checked; numeric Excel cells compared as decimals, allowing only binary-float rounding <=1e-12 relative if necessary.",
        "scope": {"sources": len(sources), "observations": sum(s["observations"] for s in sources),
                  "numeric": sum(s["numeric"] for s in sources), "missing": sum(s["missing"] for s in sources),
                  "evidence_files": sum(len(s["evidence_files"]) for s in sources),
                  "physical_observations_by_format": dict(formats)},
        "checks": dict(check_counts), "failure_counts": dict(failure_counts),
        "passed": not failure_counts, "sources": sources,
        "limits": ["Verifies retained official source snapshots and published fidelity; does not certify source methodology or imply that a network refresh returned newer observations.",
                   "Geographic remapping and analytical eligibility are not inferred from a source value match; they remain separately documented policies."]}
    path = output_path
    # Counters inside failure examples can have tuple keys; only a small readable
    # diagnostic is needed if a complete-record comparison fails.
    for source in output["sources"]:
        for ex in source["failure_examples"]:
            for k in ("actual", "expected"):
                if isinstance(ex[k], Counter):
                    ex[k] = [{"key": repr(key), "count": value} for key, value in list(ex[k].items())[:8]]
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=json_safe) + "\n")
    print(json.dumps({k: output[k] for k in ("scope", "failure_counts", "passed")}, ensure_ascii=False))
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
