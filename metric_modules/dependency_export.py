from __future__ import annotations

import csv
import math
import os
from typing import Any

from . import event_logger
from .stanza_conllu import parse_conllu
from .xlsx_writer import read_xlsx_sheets, write_xlsx

DEPENDENCY_FIELDS = [
    "filename",
    "sid",
    "token_id",
    "token",
    "lemma",
    "upos",
    "head_id",
    "head_token",
    "deprel",
    "dep_distance",
    "sentence",
]
_DEPENDENCY_INT_INDICES = (1, 2, 6, 9)


def extract_stanza_dependencies(filename: str, conllu_str: str) -> list[list[Any]]:
    if not conllu_str:
        return []
    rows: list[list[Any]] = []
    for sid, sent in enumerate(parse_conllu(conllu_str), start=1):
        id_to_form = {int(token[0]): token[1] for token in sent}
        sentence = " ".join(token[1] for token in sent)
        for token in sent:
            token_id = int(token[0])
            head_id = int(token[6])
            head_token = "ROOT" if head_id == 0 else id_to_form.get(head_id, "")
            dep_distance = 0 if head_id == 0 else abs(token_id - head_id)
            rows.append([
                filename,
                sid,
                token_id,
                token[1],
                token[2],
                token[3],
                head_id,
                head_token,
                token[7],
                dep_distance,
                sentence,
            ])
    return rows


def read_udpipe_raw_csv(filename: str, raw_csv_path: str) -> list[list[Any]]:
    if not os.path.exists(raw_csv_path):
        return []
    grouped: list[tuple[int, list[dict[str, str]]]] = []
    by_sid: dict[int, list[dict[str, str]]] = {}
    with open(raw_csv_path, "r", encoding="utf-8", newline="") as csvfile:
        for row in csv.DictReader(csvfile):
            try:
                sid = int(row["sid"])
            except (KeyError, ValueError):
                continue
            bucket = by_sid.get(sid)
            if bucket is None:
                bucket = []
                by_sid[sid] = bucket
                grouped.append((sid, bucket))
            bucket.append(row)

    rows: list[list[Any]] = []
    for sid, group in grouped:
        sentence = " ".join(item.get("token", "") for item in group)
        for item in group:
            try:
                token_id = int(item["token_id"])
                head_id = int(item["head_token_id"])
            except (KeyError, ValueError):
                continue
            head_token = item.get("token_head") or ("ROOT" if head_id == 0 else "")
            dep_distance = 0 if head_id == 0 else abs(token_id - head_id)
            rows.append([
                filename,
                sid,
                token_id,
                item.get("token", ""),
                item.get("lemma", ""),
                item.get("upos", ""),
                head_id,
                head_token,
                item.get("dep_relation", ""),
                dep_distance,
                sentence,
            ])
    return rows


def _coerce_metric_value(value: Any, col_index: int) -> Any:
    if value is None or value == "":
        return ""
    if col_index == 0:
        return str(value)
    if not isinstance(value, bool) and isinstance(value, (int, float)):
        return value if math.isfinite(value) else ""
    text = str(value)
    try:
        return int(text)
    except ValueError:
        pass
    try:
        numeric = float(text)
        if math.isfinite(numeric):
            return numeric
    except ValueError:
        pass
    return text


def _coerce_dep_row(raw_row: list[str]) -> list[Any]:
    row: list[Any] = list(raw_row[: len(DEPENDENCY_FIELDS)])
    while len(row) < len(DEPENDENCY_FIELDS):
        row.append("")
    for idx in _DEPENDENCY_INT_INDICES:
        text = str(row[idx])
        if text:
            try:
                row[idx] = int(text)
            except ValueError:
                pass
    return row


def read_existing_workbook(
    output_xlsx: str,
) -> tuple[
    set[str],
    list[str] | None,
    list[dict[str, Any]],
    list[list[Any]] | None,
    list[list[Any]] | None,
]:
    if not os.path.exists(output_xlsx):
        return set(), None, [], None, None

    sheets = read_xlsx_sheets(output_xlsx)
    if "Metrics" not in sheets:
        return set(), None, [], None, None

    headers, raw_metric_rows = sheets["Metrics"]
    if not headers:
        return set(), None, [], None, None

    processed_files: set[str] = set()
    metric_rows: list[dict[str, Any]] = []
    for raw_row in raw_metric_rows:
        row_dict = {
            field: (raw_row[idx] if idx < len(raw_row) else "")
            for idx, field in enumerate(headers)
        }
        filename = str(row_dict.get("filename", ""))
        if filename:
            processed_files.add(filename)
            metric_rows.append(row_dict)

    existing_stanza = (
        [_coerce_dep_row(row) for row in sheets["Stanza_UD"][1]]
        if "Stanza_UD" in sheets
        else None
    )
    existing_udpipe = (
        [_coerce_dep_row(row) for row in sheets["UDPipe_UD"][1]]
        if "UDPipe_UD" in sheets
        else None
    )
    return processed_files, headers, metric_rows, existing_stanza, existing_udpipe


def write_category_workbook(
    output_xlsx: str,
    fieldnames: list[str],
    metric_rows: list[dict[str, Any]],
    stanza_rows: list[list[Any]] | None,
    udpipe_rows: list[list[Any]] | None,
) -> str:
    coerced_metrics = [
        [_coerce_metric_value(row.get(field, ""), idx) for idx, field in enumerate(fieldnames)]
        for row in metric_rows
    ]
    sheets: list[tuple[str, list[str], list[list[Any]]]] = [
        ("Metrics", fieldnames, coerced_metrics),
    ]
    if stanza_rows is not None:
        sheets.append(("Stanza_UD", DEPENDENCY_FIELDS, stanza_rows))
    if udpipe_rows is not None:
        sheets.append(("UDPipe_UD", DEPENDENCY_FIELDS, udpipe_rows))

    truncated = write_xlsx(output_xlsx, sheets)
    if truncated:
        event_logger.log(
            "warning",
            f"Excel row limit reached for {', '.join(truncated)}; remaining rows were truncated.",
        )
    return output_xlsx
