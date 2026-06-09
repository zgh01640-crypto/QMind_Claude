"""Parsing helpers for appendix reference-price tables."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable


MARKDOWN_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*([^|]+?)\s*\|\s*$"
)


@dataclass(frozen=True)
class ReferencePriceRow:
    sequence_no: int
    name: str
    unit: str
    price: Decimal
    source_page_no: int
    confidence: Decimal
    raw_text: str


def normalize_text(value: str) -> str:
    value = value.replace("\u00a0", " ").replace("\u3000", " ")
    return re.sub(r"\s+", " ", value).strip()


def parse_price(value: str) -> Decimal:
    # OCR commonly inserts spaces in thousands, for example "1 888.81".
    normalized = re.sub(r"(?<=\d)\s+(?=\d)", "", value)
    normalized = normalized.replace(",", "").replace("，", "").strip()
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"invalid price: {value!r}") from exc


def parse_markdown_table(
    markdown: str,
    source_page_no: int,
    confidence: Decimal | float | None = None,
) -> list[ReferencePriceRow]:
    rows: list[ReferencePriceRow] = []
    row_confidence = Decimal(str(confidence if confidence is not None else "0.9900"))
    for line in markdown.splitlines():
        match = MARKDOWN_ROW.match(line)
        if not match:
            continue
        sequence_no, name, unit, price = match.groups()
        rows.append(
            ReferencePriceRow(
                sequence_no=int(sequence_no),
                name=normalize_text(name),
                unit=normalize_text(unit),
                price=parse_price(price),
                source_page_no=source_page_no,
                confidence=row_confidence,
                raw_text=line,
            )
        )
    return rows


def validate_rows(rows: Iterable[ReferencePriceRow], expected_count: int) -> list[ReferencePriceRow]:
    result = sorted(rows, key=lambda row: row.sequence_no)
    sequence_numbers = [row.sequence_no for row in result]
    expected = list(range(1, expected_count + 1))
    if sequence_numbers != expected:
        missing = sorted(set(expected) - set(sequence_numbers))
        duplicates = sorted(
            number for number in set(sequence_numbers) if sequence_numbers.count(number) > 1
        )
        extras = sorted(set(sequence_numbers) - set(expected))
        raise ValueError(
            f"appendix sequence validation failed: missing={missing}, "
            f"duplicates={duplicates}, extras={extras}"
        )
    for row in result:
        if not row.name or not row.unit or row.price <= 0:
            raise ValueError(f"incomplete reference-price row: {row}")
    return result

