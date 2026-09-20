from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from lxml import etree

from .errors import EmissConnectorError


ValueStatus = Literal["ok", "missing", "invalid"]


class SdmxParseError(ValueError):
    def __init__(self, message: str, *, root_type: str | None = None) -> None:
        super().__init__(message)
        self.root_type = root_type


@dataclass(slots=True)
class ParsedSdmxObservation:
    value: float | None
    period: str | None
    dimensions: dict[str, str] = field(default_factory=dict)
    dimension_codes: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)
    raw_value: str | None = None
    value_status: ValueStatus = "ok"


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def _first_text(element: etree._Element, local_name: str) -> str | None:
    result = element.xpath(f".//*[local-name()='{local_name}'][1]")
    if not result:
        return None
    text = result[0].text
    return text.strip() if text else None


def _number(value: str | None) -> tuple[float | None, ValueStatus]:
    if value is None:
        return None, "missing"
    cleaned = (
        value.strip()
        .replace("\xa0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    if cleaned.casefold() in {
        "",
        "…",
        "...",
        "-",
        "—",
        "–",
        "na",
        "n/a",
        "nan",
        "null",
        "н/д",
        "нетданных",
    }:
        return None, "missing"
    try:
        return float(cleaned), "ok"
    except ValueError:
        return None, "invalid"


def _attribute_values(parent: etree._Element) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in parent.xpath("./*[local-name()='Attributes']/*[local-name()='Value']"):
        concept = value.get("concept") or value.get("id")
        if concept:
            result[concept] = value.get("value") or (value.text or "").strip() or None
    return result


def _observation_from_element(
    obs: etree._Element,
    series_codes: dict[str, str],
    series_attributes: dict[str, Any],
    convert_dimensions: Any,
) -> ParsedSdmxObservation:
    codes = dict(series_codes)
    for value in obs.xpath("./*[local-name()='ObsKey']/*[local-name()='Value']"):
        concept = value.get("concept") or value.get("id")
        code = value.get("value")
        if concept and code is not None:
            codes[concept] = code

    for key, value in obs.attrib.items():
        if key.upper() not in {"TIME_PERIOD", "OBS_VALUE", "TIME", "VALUE"}:
            codes.setdefault(key, value)

    period = obs.get("TIME_PERIOD") or obs.get("time")
    if period is None:
        time_nodes = obs.xpath("./*[local-name()='Time' or local-name()='ObsDimension']")
        if time_nodes:
            period = time_nodes[0].get("value") or (time_nodes[0].text or "").strip() or None

    raw_value = obs.get("OBS_VALUE") or obs.get("value")
    if raw_value is None:
        value_nodes = obs.xpath("./*[local-name()='ObsValue']")
        if value_nodes:
            raw_value = value_nodes[0].get("value") or (value_nodes[0].text or "").strip() or None

    numeric, value_status = _number(raw_value)
    attributes = dict(series_attributes)
    attributes.update(_attribute_values(obs))
    return ParsedSdmxObservation(
        value=numeric,
        period=period,
        dimensions=convert_dimensions(codes),
        dimension_codes=codes,
        attributes=attributes,
        raw_value=raw_value,
        value_status=value_status,
    )


def parse_sdmx(content: bytes) -> tuple[list[ParsedSdmxObservation], dict[str, Any]]:
    """Parse GenericData and compact SDMX variants returned by fedstat.ru.

    Namespace prefixes are intentionally ignored because the source has changed
    declarations over time. External entities and network access are disabled.
    """

    stripped = content.lstrip()
    if not stripped.startswith(b"<"):
        raise SdmxParseError("Ответ не является XML")
    if stripped[:256].lower().startswith((b"<!doctype html", b"<html")):
        raise SdmxParseError("Вместо SDMX получен HTML", root_type="html")

    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        recover=False,
        huge_tree=False,
        remove_comments=True,
    )
    try:
        root = etree.fromstring(content, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise SdmxParseError(f"Некорректный XML: {exc.__class__.__name__}") from exc

    root_type = _local_name(root)
    if root_type.casefold() in {"error", "message"}:
        message = " ".join(text.strip() for text in root.itertext() if text.strip())[:500]
        raise SdmxParseError(f"Источник вернул XML-ошибку: {message}", root_type=root_type)

    code_lists: dict[str, dict[str, str]] = {}
    dimension_titles: dict[str, str] = {}
    for code_list in root.xpath("//*[local-name()='CodeList']"):
        code_list_id = code_list.get("id") or code_list.get("ID")
        if not code_list_id:
            continue
        dimension_titles[code_list_id] = _first_text(code_list, "Name") or code_list_id
        values: dict[str, str] = {}
        for code in code_list.xpath("./*[local-name()='Code']"):
            code_value = code.get("value") or code.get("id") or code.get("ID")
            if not code_value:
                continue
            label = _first_text(code, "Description") or _first_text(code, "Name")
            if not label:
                label = "".join(code.itertext()).strip() or code_value
            values[code_value] = label
        code_lists[code_list_id] = values

    def convert_dimensions(codes: dict[str, str]) -> dict[str, str]:
        labels: dict[str, str] = {}
        for concept, code in codes.items():
            title = dimension_titles.get(concept, concept)
            labels[title] = code_lists.get(concept, {}).get(code, code)
        return labels

    observations: list[ParsedSdmxObservation] = []
    series_elements = root.xpath("//*[local-name()='Series']")
    for series in series_elements:
        series_codes: dict[str, str] = {}
        for value in series.xpath("./*[local-name()='SeriesKey']/*[local-name()='Value']"):
            concept = value.get("concept") or value.get("id")
            code = value.get("value")
            if concept and code is not None:
                series_codes[concept] = code

        if not series_codes:
            for key, value in series.attrib.items():
                if key.upper() not in {"TIME_PERIOD", "OBS_VALUE"}:
                    series_codes[key] = value

        series_attributes = _attribute_values(series)
        for obs in series.xpath("./*[local-name()='Obs']"):
            observations.append(
                _observation_from_element(obs, series_codes, series_attributes, convert_dimensions)
            )

    if not observations:
        for obs in root.xpath("//*[local-name()='DataSet']/*[local-name()='Obs']"):
            observations.append(_observation_from_element(obs, {}, {}, convert_dimensions))

    metadata = {
        "dimension_titles": dimension_titles,
        "code_lists": code_lists,
        "root_type": root_type,
        "observation_count": len(observations),
        "missing_value_count": sum(item.value_status == "missing" for item in observations),
        "invalid_value_count": sum(item.value_status == "invalid" for item in observations),
    }
    return observations, metadata
