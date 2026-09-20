from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
from typing import Any, Iterable

import json5
from lxml import etree, html

from .errors import EmissConnectorError
CONNECTOR_VERSION = "semya-cdo-adapter-1"



PARSER_VERSION = 3

MONTH_NAMES_RU: dict[int, tuple[str, ...]] = {
    1: ("январь", "января", "янв", "01", "1"),
    2: ("февраль", "февраля", "фев", "02", "2"),
    3: ("март", "марта", "мар", "03", "3"),
    4: ("апрель", "апреля", "апр", "04", "4"),
    5: ("май", "мая", "05", "5"),
    6: ("июнь", "июня", "июн", "06", "6"),
    7: ("июль", "июля", "июл", "07", "7"),
    8: ("август", "августа", "авг", "08", "8"),
    9: ("сентябрь", "сентября", "сен", "сент", "09", "9"),
    10: ("октябрь", "октября", "окт", "10"),
    11: ("ноябрь", "ноября", "ноя", "11"),
    12: ("декабрь", "декабря", "дек", "12"),
}

TOTAL_VALUE_TERMS = (
    "всего",
    "итого",
    "все",
    "все население",
    "оба пола",
    "все категории",
    "в целом",
    "российская федерация",
)


def norm(value: str) -> str:
    value = value.replace("ё", "е").replace("\xa0", " ").casefold()
    return re.sub(r"\s+", " ", value).strip(" .,:;\t\r\n")


def field_matches(field_title: str, aliases: Iterable[str]) -> bool:
    normalized = norm(field_title)
    return any(norm(alias) == normalized or norm(alias) in normalized for alias in aliases)


def _extract_balanced(text: str, start: int, opener: str, closer: str) -> str:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise EmissConnectorError(
        f"Не удалось выделить JavaScript-блок {opener}{closer}.",
        category="metadata_contract_changed",
    )


def _flatten_ids(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, (str, int, float)):
        result.append(str(value))
    elif isinstance(value, list):
        for item in value:
            result.extend(_flatten_ids(item))
    elif isinstance(value, dict):
        for item in value.values():
            result.extend(_flatten_ids(item))
    return result


def parse_indicator_metadata(page: str, indicator_id: str) -> dict[str, Any]:
    """Parse the unofficial filter contract embedded in a fedstat indicator page."""

    try:
        document = html.fromstring(page)
    except (etree.ParserError, ValueError) as exc:
        raise EmissConnectorError(
            "Страница показателя ЕМИСС не является корректным HTML.",
            category="invalid_metadata_html",
        ) from exc

    scripts = [script.text or "" for script in document.xpath("//script")]
    candidates = [script for script in scripts if re.search(r"filters\s*:\s*\{", script)]
    if not candidates:
        raise EmissConnectorError(
            "На странице показателя не найден JavaScript-блок filters. Контракт fedstat.ru мог измениться.",
            category="metadata_contract_changed",
        )

    script = max(candidates, key=len)
    match = re.search(r"filters\s*:\s*\{", script)
    assert match is not None
    brace_start = script.find("{", match.start())
    filters_literal = _extract_balanced(script, brace_start, "{", "}")
    # JSON5 accepts identifier keys but not bare numeric keys nested in objects.
    filters_literal = re.sub(r"([,{]\s*)(-?\d+)(\s*:)", r'\1"\2"\3', filters_literal)
    try:
        filters_object = json5.loads(filters_literal)
    except Exception as exc:
        raise EmissConnectorError(
            "Не удалось разобрать фильтры на странице ЕМИСС. Контракт JavaScript мог измениться.",
            category="metadata_contract_changed",
            details={"parser_version": PARSER_VERSION},
        ) from exc

    object_roles: dict[str, str] = {}
    role_map = {
        "left_columns": "lineObjectIds",
        "groups": "lineObjectIds",
        "top_columns": "columnObjectIds",
        # fedstatAPIr historically serialises this source field as lineObjectIds.
        "filterObjectIds": "lineObjectIds",
    }
    for source_name, form_name in role_map.items():
        array_match = re.search(rf"{re.escape(source_name)}\s*:\s*\[", script)
        if not array_match:
            continue
        array_start = script.find("[", array_match.start())
        try:
            array_value = json5.loads(_extract_balanced(script, array_start, "[", "]"))
        except Exception:
            continue
        for field_id in _flatten_ids(array_value):
            object_roles.setdefault(field_id, form_name)

    filters: list[dict[str, Any]] = []
    items = filters_object.items() if isinstance(filters_object, dict) else []
    for field_id, payload in items:
        if not isinstance(payload, dict):
            continue
        values_payload = payload.get("values", {})
        values: list[dict[str, str]] = []
        if isinstance(values_payload, dict):
            for value_id, value_payload in values_payload.items():
                if isinstance(value_payload, dict):
                    title = value_payload.get("title") or value_payload.get("name") or value_id
                else:
                    title = value_payload
                values.append({"id": str(value_id), "title": html_lib.unescape(str(title))})
        filters.append(
            {
                "field_id": str(field_id),
                "title": html_lib.unescape(str(payload.get("title") or payload.get("name") or field_id)),
                "object_parameter": object_roles.get(str(field_id), "lineObjectIds"),
                "values": values,
            }
        )

    indicator_filter = next((item for item in filters if item["field_id"] == "0"), None)
    if indicator_filter is None:
        indicator_filter = {
            "field_id": "0",
            "title": "Показатель",
            "object_parameter": "filterObjectIds",
            "values": [{"id": indicator_id, "title": indicator_id}],
        }
        filters.insert(0, indicator_filter)
    else:
        indicator_filter["object_parameter"] = "filterObjectIds"

    page_title_nodes = document.xpath("//title/text()")
    page_title = page_title_nodes[0].strip() if page_title_nodes else None
    indicator_title = next(
        (value["title"] for value in indicator_filter["values"] if value["id"] == indicator_id),
        None,
    )
    if not indicator_title or indicator_title == indicator_id:
        indicator_title = html_lib.unescape(page_title or indicator_id)

    return {
        "indicator_id": indicator_id,
        "indicator_title": indicator_title,
        "filters": filters,
        "parser_version": PARSER_VERSION,
        "connector_version": CONNECTOR_VERSION,
    }


def _value_year(value: dict[str, str]) -> int | None:
    candidates = (value.get("id", ""), value.get("title", ""))
    for candidate in candidates:
        match = re.fullmatch(r"\s*((?:19|20|21)\d{2})\s*", candidate)
        if match:
            return int(match.group(1))
    return None


def month_number(value: str) -> int | None:
    normalized = norm(value)
    for number, names in MONTH_NAMES_RU.items():
        if normalized in {norm(name) for name in names}:
            return number
    numeric = re.fullmatch(r"0?([1-9]|1[0-2])", normalized)
    return int(numeric.group(1)) if numeric else None


def _role_scores(field: dict[str, Any]) -> dict[str, float]:
    title = norm(str(field.get("title", "")))
    values = field.get("values", [])
    count = max(1, len(values))
    years = sum(_value_year(value) is not None for value in values)
    months = sum(month_number(value.get("title", "")) is not None for value in values)

    scores = {"territory": 0.0, "year": 0.0, "month": 0.0}
    if title in {"год", "отчетный год", "период год"} or re.search(r"(^|\s)год($|\s)", title):
        scores["year"] += 100
    scores["year"] += 75 * (years / count)

    if "месяц" in title:
        scores["month"] += 100
    elif title in {"период", "период времени"}:
        # Period is also the dimension for annual, quarterly and cumulative
        # labels. decode_period validates which types the source may publish.
        scores["month"] += 100
    scores["month"] += 75 * (months / count)

    if title in {
        "территория",
        "субъект российской федерации",
        "регион",
        "муниципальное образование",
        "федеральный округ",
        "окато",
        "октмо",
        "оксм",
    }:
        scores["territory"] += 120
    elif any(token in title for token in ("территор", "субъект российской", "муниципаль", "регион")):
        scores["territory"] += 75
    if any(token in title for token in ("тип территории", "вид территории", "категория территории")):
        scores["territory"] -= 100
    if len(values) >= 20:
        scores["territory"] += 10
    label_sample = " ".join(norm(value.get("title", "")) for value in values[:100])
    if any(token in label_sample for token in ("москва", "российская федерация", "республика", "область", "край")):
        scores["territory"] += 20
    return scores


def infer_field_map(metadata: dict[str, Any], overrides: dict[str, str] | None = None) -> dict[str, str]:
    fields = [field for field in metadata.get("filters", []) if str(field.get("field_id")) != "0"]
    by_id = {str(field["field_id"]): field for field in fields}
    result: dict[str, str] = {}
    used: set[str] = set()
    for role, field_id in (overrides or {}).items():
        if role not in {"territory", "year", "month"}:
            continue
        if str(field_id) not in by_id:
            raise EmissConnectorError(
                f"Поле {field_id} для роли {role} отсутствует в метаданных показателя.",
                category="invalid_field_mapping",
            )
        result[role] = str(field_id)
        used.add(str(field_id))

    for role in ("territory", "year", "month"):
        if role in result:
            continue
        ranked = sorted(
            (
                (_role_scores(field)[role], str(field["field_id"]))
                for field in fields
                if str(field["field_id"]) not in used
            ),
            reverse=True,
        )
        if ranked and ranked[0][0] >= 70:
            if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
                raise EmissConnectorError(f"Роль {role} неоднозначна; задайте field_overrides.", category="ambiguous_field_mapping")
            result[role] = ranked[0][1]
            used.add(ranked[0][1])
    return result

