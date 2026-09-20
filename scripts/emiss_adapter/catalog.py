from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass(frozen=True)
class EmissCatalogItem:
    indicator_id: str
    title: str
    href: str
    status: str
    metadata: dict[str, object] = field(default_factory=dict)


_INDICATOR_RE = re.compile(r"/indicator/(\d{1,12})")
_STATUS_RANK = {"excluded": 0, "unknown": 1, "actual": 2}
_EXCLUDED_CLASS_TOKENS = {"i_excluded", "group_excluded", "hide", "hidden", "excluded"}


def _class_tokens(classes: list[str]) -> list[str]:
    result: list[str] = []
    for value in classes:
        result.extend(token.casefold() for token in value.split() if token.strip())
    return result


def _status_from_classes(classes: list[str]) -> str:
    tokens = set(_class_tokens(classes))
    if tokens & _EXCLUDED_CLASS_TOKENS:
        return "excluded"
    if "i_actual" in tokens:
        return "actual"
    return "unknown"


def _canonical_href(indicator_id: str) -> str:
    return f"/indicator/{indicator_id}"


class _OrganizationsCatalogParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str]] = []
        self.current: dict[str, object] | None = None
        self.items: list[EmissCatalogItem] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        self.stack.append((tag, attributes.get("class", "")))
        if tag != "a":
            return
        href = attributes.get("href", "")
        match = _INDICATOR_RE.search(href)
        if not match:
            return
        classes = [item[1] for item in self.stack if item[1]]
        indicator_id = match.group(1)
        self.current = {
            "indicator_id": indicator_id,
            "classes": classes,
            "text": [],
        }

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current is not None:
            text = " ".join(" ".join(self.current["text"]).split())  # type: ignore[index]
            indicator_id = str(self.current["indicator_id"])
            classes = [str(item) for item in self.current["classes"]]  # type: ignore[index]
            if text:
                self.items.append(
                    EmissCatalogItem(
                        indicator_id=indicator_id,
                        title=text[:500],
                        href=_canonical_href(indicator_id),
                        status=_status_from_classes(classes),
                        metadata={"class_tokens": sorted(set(_class_tokens(classes)))},
                    )
                )
            self.current = None
        if self.stack:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        if self.current is not None and data.strip():
            self.current["text"].append(data)  # type: ignore[index]


def parse_organizations_catalog(html: str) -> list[EmissCatalogItem]:
    parser = _OrganizationsCatalogParser()
    parser.feed(html)
    by_id: dict[str, EmissCatalogItem] = {}
    for item in parser.items:
        existing = by_id.get(item.indicator_id)
        if existing is None:
            by_id[item.indicator_id] = item
            continue
        if _STATUS_RANK[item.status] > _STATUS_RANK[existing.status]:
            by_id[item.indicator_id] = item
        elif _STATUS_RANK[item.status] == _STATUS_RANK[existing.status] and len(item.title) > len(existing.title):
            by_id[item.indicator_id] = item
    return sorted(by_id.values(), key=lambda item: (item.title.casefold(), item.indicator_id))
