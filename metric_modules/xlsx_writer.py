from __future__ import annotations

import math
import os
import re
import zipfile
from collections.abc import Iterable, Sequence
from typing import Any, IO
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

EXCEL_MAX_ROWS = 1_048_576
_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
_ILLEGAL_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
</styleSheet>
"""

_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""


def _col_letter(col_idx: int) -> str:
    letters: list[str] = []
    index = col_idx
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters))


def _sanitize_xml_text(value: str) -> str:
    cleaned = _ILLEGAL_XML_CHARS.sub("", value)
    return escape(cleaned)


def _sanitize_sheet_name(name: str, used: set[str]) -> str:
    cleaned = _INVALID_SHEET_CHARS.sub("_", name).strip("'") or "Sheet"
    base = cleaned[:31]
    candidate = base
    suffix = 1
    while candidate in used:
        tag = f"_{suffix}"
        candidate = f"{base[: 31 - len(tag)]}{tag}"
        suffix += 1
    used.add(candidate)
    return candidate


def _write_sheet_xml(
    stream: IO[bytes],
    headers: Sequence[str],
    rows: Iterable[Sequence[Any]],
) -> bool:
    stream.write(
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        b"<sheetData>"
    )

    col_letters = [_col_letter(idx) for idx in range(1, len(headers) + 1)]
    header_cells: list[str] = ['<row r="1">']
    for idx, header in enumerate(headers):
        ref = f"{col_letters[idx]}1"
        text = _sanitize_xml_text(str(header))
        header_cells.append(
            f'<c r="{ref}" t="inlineStr" s="1"><is><t xml:space="preserve">{text}</t></is></c>'
        )
    header_cells.append("</row>")
    stream.write("".join(header_cells).encode("utf-8"))

    truncated = False
    row_num = 1
    for row in rows:
        row_num += 1
        if row_num > EXCEL_MAX_ROWS:
            truncated = True
            break
        parts: list[str] = [f'<row r="{row_num}">']
        for col_idx, val in enumerate(row):
            if val is None or val == "":
                continue
            if col_idx >= len(col_letters):
                col_letters.append(_col_letter(col_idx + 1))
            ref = f"{col_letters[col_idx]}{row_num}"
            if not isinstance(val, bool) and isinstance(val, (int, float)):
                if math.isfinite(val):
                    parts.append(f'<c r="{ref}"><v>{val}</v></c>')
                continue
            text = _sanitize_xml_text(str(val))
            parts.append(
                f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
            )
        parts.append("</row>")
        stream.write("".join(parts).encode("utf-8"))

    stream.write(b"</sheetData></worksheet>")
    return truncated


def write_xlsx(
    path: str,
    sheets: Sequence[tuple[str, Sequence[str], Iterable[Sequence[Any]]]],
) -> list[str]:
    """Writes a multi-sheet OOXML workbook without external dependencies.

    Returns a list of sheet names whose data exceeded Excel's row limit and had
    to be truncated.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    used_names: set[str] = set()
    sheet_names = [_sanitize_sheet_name(name, used_names) for name, _, _ in sheets]
    truncated_sheets: list[str] = []

    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '  <Default Extension="xml" ContentType="application/xml"/>',
        '  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    workbook_sheets = []
    workbook_rels = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]

    for idx, sheet_name in enumerate(sheet_names, start=1):
        content_types.append(
            f'  <Override PartName="/xl/worksheets/sheet{idx}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        escaped_name = escape(sheet_name, {'"': "&quot;"})
        workbook_sheets.append(
            f'    <sheet name="{escaped_name}" sheetId="{idx}" r:id="rId{idx}"/>'
        )
        workbook_rels.append(
            f'  <Relationship Id="rId{idx}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>'
        )

    styles_rel_id = len(sheet_names) + 1
    workbook_rels.append(
        f'  <Relationship Id="rId{styles_rel_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    workbook_rels.append("</Relationships>")
    content_types.append("</Types>")

    workbook_xml = "\n".join([
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
        "  <sheets>",
        *workbook_sheets,
        "  </sheets>",
        "</workbook>",
    ])

    tmp_path = f"{path}.tmp"
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", "\n".join(content_types).encode("utf-8"))
            zf.writestr("_rels/.rels", _RELS_XML.encode("utf-8"))
            zf.writestr("xl/workbook.xml", workbook_xml.encode("utf-8"))
            zf.writestr("xl/_rels/workbook.xml.rels", "\n".join(workbook_rels).encode("utf-8"))
            zf.writestr("xl/styles.xml", _STYLES_XML.encode("utf-8"))

            for idx, (sheet_name, (_, headers, rows)) in enumerate(zip(sheet_names, sheets), start=1):
                with zf.open(f"xl/worksheets/sheet{idx}.xml", "w") as sheet_stream:
                    if _write_sheet_xml(sheet_stream, headers, rows):
                        truncated_sheets.append(sheet_name)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise

    return truncated_sheets


def _col_index_from_ref(ref: str) -> int:
    idx = 0
    for ch in ref:
        if "A" <= ch <= "Z":
            idx = idx * 26 + (ord(ch) - 64)
        elif "a" <= ch <= "z":
            idx = idx * 26 + (ord(ch) - 96)
        else:
            break
    return idx - 1 if idx > 0 else -1


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _extract_xml_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter() if _local_tag(node.tag) == "t")


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return [_extract_xml_text(si) for si in root if _local_tag(si.tag) == "si"]


def _resolve_sheet_targets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    rels_map: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in zf.namelist():
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in rels_root:
            if _local_tag(rel.tag) != "Relationship":
                continue
            rel_id = rel.attrib.get("Id", "")
            target = rel.attrib.get("Target", "").lstrip("/")
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            rels_map[rel_id] = target

    wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
    sheets: list[tuple[str, str]] = []
    for elem in wb_root.iter():
        if _local_tag(elem.tag) != "sheet":
            continue
        name = elem.attrib.get("name", "")
        rel_id = next(
            (val for key, val in elem.attrib.items() if _local_tag(key) == "id"),
            "",
        )
        target = rels_map.get(rel_id, "")
        if name and target:
            sheets.append((name, target))
    return sheets


def read_xlsx_sheets(path: str) -> dict[str, tuple[list[str], list[list[str]]]]:
    """Reads all sheets from an OOXML workbook into {name: (headers, rows)}."""
    result: dict[str, tuple[list[str], list[list[str]]]] = {}
    with zipfile.ZipFile(path, "r") as zf:
        shared_strings = _read_shared_strings(zf)
        available = set(zf.namelist())
        for sheet_name, target in _resolve_sheet_targets(zf):
            if target not in available:
                continue
            root = ET.fromstring(zf.read(target))
            parsed_rows: list[list[str]] = []
            for row_elem in root.iter():
                if _local_tag(row_elem.tag) != "row":
                    continue
                row_values: list[str] = []
                for cell in row_elem:
                    if _local_tag(cell.tag) != "c":
                        continue
                    col_idx = _col_index_from_ref(cell.attrib.get("r", ""))
                    if col_idx < 0:
                        col_idx = len(row_values)
                    while len(row_values) <= col_idx:
                        row_values.append("")

                    cell_type = cell.attrib.get("t", "")
                    value = ""
                    if cell_type == "inlineStr":
                        value = _extract_xml_text(cell)
                    else:
                        v_text = ""
                        for child in cell:
                            if _local_tag(child.tag) == "v" and child.text is not None:
                                v_text = child.text
                                break
                        if cell_type == "s" and v_text:
                            try:
                                value = shared_strings[int(v_text)]
                            except (ValueError, IndexError):
                                value = v_text
                        else:
                            value = v_text
                    row_values[col_idx] = value
                parsed_rows.append(row_values)

            if parsed_rows:
                headers = parsed_rows[0]
                width = len(headers)
                data_rows = [
                    row + [""] * (width - len(row)) if len(row) < width else row
                    for row in parsed_rows[1:]
                ]
                result[sheet_name] = (headers, data_rows)
            else:
                result[sheet_name] = ([], [])
    return result
