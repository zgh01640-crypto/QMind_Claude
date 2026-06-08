"""Local OCR and rule parser for the 2024 building consumption standard PDF.

This module deliberately avoids multimodal LLM calls. It combines page rendering,
local OCR, OpenCV line detection, and conservative business rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional
import hashlib
import json
import math
import re

import fitz
import cv2
import numpy as np


PAGE_TYPES = {"cover", "directory", "intro", "rules", "items", "other"}
SECTION_TYPES = {"intro", "rules", "items", "directory", "other"}
CN_WATER = chr(0x6C34)
CN_MATERIAL = chr(0x6750) + chr(0x6599)
CN_M3 = "m" + chr(0x00B3)


@dataclass
class OCRBlock:
    text: str
    confidence: float
    bbox: list[list[float]]

    @property
    def center(self) -> tuple[float, float]:
        xs = [p[0] for p in self.bbox]
        ys = [p[1] for p in self.bbox]
        return (sum(xs) / len(xs), sum(ys) / len(ys))


@dataclass
class PageClassification:
    page_type: str
    chapter_no: Optional[int] = None
    chapter_title: Optional[str] = None
    section_type: Optional[str] = None
    section_code: Optional[str] = None
    title: Optional[str] = None
    confidence: float = 0.0


@dataclass
class ParsedResource:
    resource_type: str
    resource_name: str
    unit: Optional[str]
    quantities: dict[str, Optional[float]] = field(default_factory=dict)
    ref_price: Optional[float] = None
    sort_order: int = 0


@dataclass
class ParsedSubitem:
    subitem_code: str
    subitem_name: Optional[str] = None
    variant_desc: Optional[str] = None
    unit: Optional[str] = None
    name_path: list[str] = field(default_factory=list)
    total_unit_price: Optional[float] = None
    unit_price: Optional[float] = None
    labor_cost: Optional[float] = None
    material_cost: Optional[float] = None
    machine_cost: Optional[float] = None
    management_fee: Optional[float] = None
    profit: Optional[float] = None
    safety_fee: Optional[float] = None
    statutory_fee: Optional[float] = None
    tax: Optional[float] = None
    confidence: float = 0.0
    sort_order: int = 0


@dataclass
class ParsedItem:
    item_no: Optional[int]
    item_name: str
    work_content: Optional[str]
    unit: Optional[str]
    subitems: list[ParsedSubitem] = field(default_factory=list)
    resources: list[ParsedResource] = field(default_factory=list)
    raw_row_json: dict[str, Any] = field(default_factory=dict)
    sort_order: int = 0


@dataclass
class ParsedGroup:
    group_code: Optional[str]
    group_name: str
    items: list[ParsedItem] = field(default_factory=list)
    sort_order: int = 0


@dataclass
class ParsedPage:
    page_no: int
    classification: PageClassification
    ocr_text: str
    content_md: Optional[str]
    raw_ocr: dict[str, Any]
    groups: list[ParsedGroup] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)


class LocalOCR:
    """PaddleOCR-first adapter with EasyOCR fallback."""

    def __init__(self, engine: str = "auto"):
        self.engine = engine
        self.impl_name = ""
        self._reader = None
        self._init_reader(engine)

    def _init_reader(self, engine: str) -> None:
        errors = []
        if engine in ("auto", "paddle"):
            try:
                from paddleocr import PaddleOCR

                try:
                    self._reader = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
                except TypeError:
                    self._reader = PaddleOCR(use_textline_orientation=True, lang="ch")
                self.impl_name = "paddleocr"
                return
            except Exception as exc:  # PaddleOCR is often installed without paddlepaddle.
                errors.append(f"paddleocr: {exc}")

        if engine in ("auto", "easyocr"):
            try:
                import easyocr

                self._reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
                self.impl_name = "easyocr"
                return
            except Exception as exc:
                errors.append(f"easyocr: {exc}")

        raise RuntimeError("No usable OCR engine. " + " | ".join(errors))

    def read(self, image_rgb: np.ndarray) -> list[OCRBlock]:
        if self.impl_name == "paddleocr":
            return self._read_paddle(image_rgb)
        return self._read_easyocr(image_rgb)

    def _read_paddle(self, image_rgb: np.ndarray) -> list[OCRBlock]:
        result = self._reader.ocr(image_rgb, cls=True)
        blocks: list[OCRBlock] = []
        pages = result if isinstance(result, list) else []
        if pages and pages[0] and isinstance(pages[0][0], list) and len(pages[0]) and len(pages[0][0]) == 2:
            rows = pages[0]
        else:
            rows = pages
        for row in rows or []:
            try:
                bbox = [[float(x), float(y)] for x, y in row[0]]
                text = str(row[1][0]).strip()
                conf = float(row[1][1])
            except Exception:
                continue
            if text:
                blocks.append(OCRBlock(text=text, confidence=conf, bbox=bbox))
        return blocks

    def _read_easyocr(self, image_rgb: np.ndarray) -> list[OCRBlock]:
        rows = self._reader.readtext(image_rgb, detail=1, paragraph=False)
        blocks: list[OCRBlock] = []
        for bbox, text, conf in rows:
            text = str(text).strip()
            if text:
                blocks.append(OCRBlock(
                    text=text,
                    confidence=float(conf),
                    bbox=[[float(p[0]), float(p[1])] for p in bbox],
                ))
        return blocks


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def render_page(doc: fitz.Document, page_no: int, dpi: int = 200) -> np.ndarray:
    page = doc[page_no - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return arr.copy()


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def normalize_diameter_text(s: str) -> str:
    """Normalize OCR variants of steel diameter ranges."""
    if not s:
        return s
    value = s
    value = value.replace("$", "φ").replace("Φ", "φ")
    value = value.replace("≤", "<=").replace("≦", "<=")
    value = re.sub(r"(?<![A-Za-z])0(?=\s*[<≤]\s*φ)", "0", value)
    value = re.sub(r"\b[Oo](?=\s*[<≤]\s*φ)", "0", value)
    value = re.sub(r"(?<=\d)\s*<<\s*(?=\d)", "<φ≤", value)
    value = re.sub(r"(?<=\d)\s*<\s*<\s*(?=\d)", "<φ≤", value)
    value = re.sub(r"\b0\s*<\s*[dD]\s*<\s*(\d+)", r"0<φ≤\1", value)
    value = re.sub(r"\b0\s*<\s*φ\s*<=\s*(\d+)", r"0<φ≤\1", value)
    value = re.sub(r"\b0\s*<\s*φ\s*≤\s*(\d+)", r"0<φ≤\1", value)
    value = re.sub(r"(\d+)\s*<\s*[dD]\s*<\s*(\d+)", r"\1<φ≤\2", value)
    value = re.sub(r"(\d+)\s*<\s*φ\s*<=\s*(\d+)", r"\1<φ≤\2", value)
    value = re.sub(r"φ\s*>\s*(\d+)", r"φ>\1", value)
    value = value.replace("钢筋直径φmm", "钢筋直径φ(mm)")
    value = value.replace("钢筋直径φ/mm", "钢筋直径φ(mm)")
    value = value.replace("钢筋直径φ", "钢筋直径φ(mm)")
    value = re.sub(r"钢筋直径φ\(mm\)\(mm\)", "钢筋直径φ(mm)", value)
    return value


def fix_standard_ocr_text(text: str) -> str:
    """Correct common OCR confusions in Shenzhen construction standard text."""
    if not text:
        return text
    s = text
    s = re.sub(r"泵送高度\s*[Il1H]\s*\(?\s*m\s*\)?", "泵送高度H(m)", s, flags=re.I)
    # In this standard, Latin O inside numeric/code/model tokens is almost always zero.
    s = re.sub(r"\b((?:HPB|HRB|RRB)\d*)[Oo]{2}(?=\D|$)", lambda m: m.group(1) + "00", s, flags=re.I)
    s = re.sub(r"(?<![\u4e00-\u9fffA-Za-z])[@oO]\s*[Il1][Oo0]\s*mm", "Φ10mm", s)
    s = re.sub(r"\b[Il1][Oo0]{2}\s*m\b", "100m", s, flags=re.I)
    s = re.sub(r"\b[Il1]\.\s*[Oo0]\s*m\b", "1.0m", s, flags=re.I)
    s = re.sub(r"\b[Oo0]\.\s*[Il1]\s*m\b", "0.1m", s, flags=re.I)
    s = re.sub(r"\b[gG]\s*[Oo0]{2}\s*mm\b", "600mm", s)
    s = re.sub(r"\b[Ss]\s*[Oo0]\s*m\s*['’³3]?", "50m³", s)
    s = re.sub(r"\b1\s*[Ss5]\s*[Oo0]\s*[Oo0]\s*mm\b", "1500mm", s)
    s = re.sub(r"\b1\s*[Oo0]\s*[Oo0]\s*[Oo0]\s*mm\b", "1000mm", s)
    s = re.sub(r"\b([01]\.\d)\s*m\s*['’³3]?", r"\1m³", s)
    s = re.sub(r"\b([1-9])\s+(\d{3})(?=\s*mm\b)", r"\1\2", s)
    s = re.sub(r"\b([1-9])\s+([Ss5][Oo0]{2})(?=\s*mm\b)", lambda m: m.group(1) + m.group(2).replace("S", "5").replace("s", "5").replace("O", "0").replace("o", "0"), s)
    s = re.sub(r"\b[Il1](?=\d+\s*m\b)", "1", s, flags=re.I)
    s = re.sub(r"\b(\d+)[Oo0][nN]\b", r"\g<1>0m", s)
    s = re.sub(r"\b(\d+)[Oo](?=\s*m\b)", r"\g<1>0", s)
    s = re.sub(r"\b(\d+)[nN](?=\s*(?:m|米|以内|以上))", r"\g<1>m", s)
    s = re.sub(r"(?<=\d)[Oo](?=\d|\.|\-|m|M|%|$)", "0", s)
    s = re.sub(r"(?<=\d)[Oo](?=\s*\))", "0", s)
    s = re.sub(r"(?<=\d\.)[Oo](?=\.)", "0", s)
    s = re.sub(r"(?<=\D)[Oo](?=\d{2,})", "0", s)
    s = re.sub(r"(\d{2,})[Oo](?=\D)", r"\g<1>0", s)
    # OCR often reads 10m as IOm/lOm and loses the cubic/square superscript.
    s = re.sub(r"\b[Il1][Oo0]\s*m\s*3\b", "10m³", s, flags=re.I)
    s = re.sub(r"\b[Il1][Oo0]\s*m\s*2\b", "10m²", s, flags=re.I)
    s = re.sub(r"\b[Il1][Oo0]\s*m\b", "10m³", s, flags=re.I)
    # Rebuild steel bar diameter symbols. EasyOCR often returns 中/巾/Ф/0 before a size.
    s = re.sub(r"(?:(?<=钢筋)|(?<=HPB\d{3})|(?<=HRB\d{3})|(?<=直径)|(?<=级))\s*[中巾ФφØ0O]\s*(\d{1,2})(?=\D|$)", r" Φ\1", s)
    s = re.sub(r"(?<![\u4e00-\u9fffA-Za-z])(?:中|巾|Ф|φ|Ø)\s*(\d{1,2})(?=\s*(?:钢筋|以内|以上|@|间距|mm|㎜|$))", r"Φ\1", s)
    # Compact common paragraph numbering artifacts without touching prose.
    s = re.sub(r"(\d+)\s*[。．]\s*(\d+)\s*[。．]\s*(\d+)", r"\1.\2.\3", s)
    s = re.sub(r"(\d+)\s*\.\s*(\d+)\s*\.\s*(\d+)", r"\1.\2.\3", s)
    return s


def parse_number(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    s = _normalize_number_text(str(text).strip())
    if not s or s in {"-", "—", "一", "无"}:
        return None
    s = s.replace(",", "").replace("，", "")
    s = s.replace("O", "0").replace("o", "0")
    match = re.search(r"-?\d+(?:\.\d+)?", s)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_numbers(text: Optional[str]) -> list[float]:
    if text is None:
        return []
    s = fix_standard_ocr_text(str(text)).replace(",", "").replace("，", "")
    s = s.replace("O", "0").replace("o", "0")
    values: list[float] = []
    for match in re.finditer(r"-?\d+(?:\.\d+)?", s):
        try:
            values.append(float(match.group(0)))
        except ValueError:
            continue
    return values


def _normalize_number_text(text: str) -> str:
    s = fix_standard_ocr_text(text or "")
    # Standards often use spaces as thousands separators: "1 000", "1 888.81".
    previous = None
    while previous != s:
        previous = s
        s = re.sub(r"(?<=\d)\s+(?=\d{3}(?:\D|$))", "", s)
    return s


def clean_resource_name(name: str, cells: Optional[list[str]] = None) -> str:
    s = fix_standard_ocr_text(name or "")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("混凝士", "混凝土")
    s = s.replace("混凝上", "混凝土")
    s = s.replace("技工人工赀", "技工人工费")
    s = s.replace("普T人丁费", "普工人工费")
    s = s.replace("技T人丁费", "技工人工费")
    s = s.replace("普T人T费", "普工人工费")
    s = s.replace("普工人工赀", "普工人工费")
    s = s.replace("普工人丁费", "普工人工费")
    s = s.replace("技工人丁费", "技工人工费")
    s = s.replace("振动嵛", "振动器")
    s = s.replace("振动嚣", "振动器")
    s = s.replace("混凝十振动器", "混凝土振动器")
    s = s.replace("插人式", "插入式")
    s = s.replace("捅人式", "插入式")
    if "机动翻斗车" in s and "装载质量" in s:
        s = "机动翻斗车 装载质量M(t) M=1"
    s = s.replace("最人粒径", "最大粒径").replace("最 人粒径", "最大粒径")
    s = re.sub(r"骨料\s*最\s*人\s*粒径", "骨料最大粒径", s)
    s = re.sub(r"骨料\s*最\s*大\s*粒径", "骨料最大粒径", s)
    s = s.replace("背通预拌混凝土", "普通预拌混凝土")
    s = s.replace("其他协料费", "其他材料费")
    s = s.replace("其他材料赀", "其他材料费")
    s = re.sub(r"\bC[Il1][Oo0]\b", "C10", s)
    s = re.sub(r"\bCl0\b", "C10", s)
    s = re.sub(r"输送量\s*[0Oo]\s*(?=[(（]?\s*m)", "输送量 Q", s)
    q_value = None
    if cells:
        joined = " ".join(cells)
        m = re.search(r"[Q0Oo]\s*=\s*(\d+)", joined)
        if m:
            q_value = m.group(1)
    if "输送量" in s and q_value:
        s = re.sub(r"输送量.*$", f"输送量 Q={q_value}m³/h", s)
    s = s.replace("(mh)", "(m³/h)").replace("(m3h)", "(m³/h)")
    s = s.replace(" (", "(").replace("- ", " ")
    return s.strip(" -—")


def blocks_to_lines(blocks: list[OCRBlock], y_tol: float = 16.0) -> list[list[OCRBlock]]:
    sorted_blocks = sorted(blocks, key=lambda b: (b.center[1], b.center[0]))
    lines: list[list[OCRBlock]] = []
    for block in sorted_blocks:
        _, cy = block.center
        if not lines:
            lines.append([block])
            continue
        avg_y = sum(b.center[1] for b in lines[-1]) / len(lines[-1])
        if abs(cy - avg_y) <= y_tol:
            lines[-1].append(block)
        else:
            lines.append([block])
    for line in lines:
        line.sort(key=lambda b: b.center[0])
    return lines


def lines_to_text(lines: list[list[OCRBlock]]) -> str:
    return "\n".join(
        fix_standard_ocr_text(" ".join(b.text for b in line).strip())
        for line in lines
        if line
    )


def lines_to_markdown(lines: list[list[OCRBlock]]) -> str:
    md: list[str] = []
    for line in lines:
        text = fix_standard_ocr_text(" ".join(b.text for b in line).strip())
        compact = normalize_text(text)
        if not text:
            continue
        if re.match(r"^第[一二三四五六七八九十\d]+章", compact):
            md.append(f"## {text}")
        elif re.match(r"^\d+(?:\.\d+){1,3}", compact):
            md.append(text)
        elif compact in {"说明", "工程量计算规则", "子目构成表"}:
            md.append(f"### {text}")
        else:
            md.append(text)
    return "\n\n".join(md)


def detect_table_grid(image_rgb: np.ndarray) -> tuple[list[int], list[int]]:
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, image_rgb.shape[1] // 35), 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(30, image_rgb.shape[0] // 45)))
    h_img = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=1)
    v_img = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=1)
    h_lines = _cluster_positions(np.where(np.any(h_img > 0, axis=1))[0].tolist(), 8)
    v_lines = _cluster_positions(np.where(np.any(v_img > 0, axis=0))[0].tolist(), 8)
    return h_lines, v_lines


def _cluster_positions(values: list[int], gap: int) -> list[int]:
    if not values:
        return []
    groups: list[list[int]] = [[values[0]]]
    for v in values[1:]:
        if v - groups[-1][-1] <= gap:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [int(sum(g) / len(g)) for g in groups if len(g) >= 2]


def blocks_to_grid(blocks: list[OCRBlock], h_lines: list[int], v_lines: list[int]) -> list[list[str]]:
    if len(h_lines) < 3 or len(v_lines) < 3:
        return []
    rows = len(h_lines) - 1
    cols = len(v_lines) - 1
    grid: list[list[list[OCRBlock]]] = [[[] for _ in range(cols)] for _ in range(rows)]
    for block in blocks:
        cx, cy = block.center
        r = _line_interval(cy, h_lines)
        c = _line_interval(cx, v_lines)
        if r is not None and c is not None:
            grid[r][c].append(block)
    text_grid: list[list[str]] = []
    for row in grid:
        out_row = []
        for cell in row:
            cell.sort(key=lambda b: (b.center[1], b.center[0]))
            out_row.append(fix_standard_ocr_text(" ".join(b.text for b in cell).strip()))
        if any(out_row):
            text_grid.append(out_row)
    return text_grid


def grid_to_markdown_table(grid: list[list[str]]) -> Optional[str]:
    cleaned: list[list[str]] = []
    max_cols = 0
    for row in grid:
        values = [fix_standard_ocr_text((cell or "").replace("\n", " ").strip()) for cell in row]
        if not any(values):
            continue
        max_cols = max(max_cols, len(values))
        cleaned.append(values)
    if len(cleaned) < 2 or max_cols < 2:
        return None
    normalized = [row + [""] * (max_cols - len(row)) for row in cleaned]
    header = normalized[0]
    sep = ["---"] * max_cols
    body = normalized[1:]

    def esc(cell: str) -> str:
        return cell.replace("|", "\\|")

    rows = [
        "| " + " | ".join(esc(cell) for cell in header) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    rows.extend("| " + " | ".join(esc(cell) for cell in row) + " |" for row in body)
    return "\n".join(rows)


def detect_non_text_regions(image_rgb: np.ndarray, blocks: list[OCRBlock]) -> list[dict[str, int]]:
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    binary = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)[1]
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    text_boxes = [_bbox_rect(block.bbox) for block in blocks]
    regions: list[dict[str, int]] = []
    page_area = image_rgb.shape[0] * image_rgb.shape[1]
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < page_area * 0.015 or w < image_rgb.shape[1] * 0.18 or h < image_rgb.shape[0] * 0.05:
            continue
        overlap = sum(_intersection_area((x, y, w, h), box) for box in text_boxes)
        if overlap / max(area, 1) > 0.45:
            continue
        regions.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
    regions.sort(key=lambda r: (r["y"], r["x"]))
    return regions[:8]


def _bbox_rect(bbox: list[list[float]]) -> tuple[int, int, int, int]:
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    return int(x1), int(y1), int(x2 - x1), int(y2 - y1)


def _intersection_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    return max(0, x2 - x1) * max(0, y2 - y1)


def _line_interval(value: float, lines: list[int]) -> Optional[int]:
    for idx in range(len(lines) - 1):
        if lines[idx] <= value <= lines[idx + 1]:
            return idx
    return None


def classify_page(page_no: int, text: str, blocks: list[OCRBlock]) -> PageClassification:
    compact = normalize_text(text)
    confidence = _avg_conf(blocks)
    if page_no <= 2 or "建筑工程消耗量标准" in compact and "SJG171" in compact:
        return PageClassification("cover", title="封面", confidence=confidence)
    if "目录" in compact and page_no < 20:
        return PageClassification("directory", section_type="directory", title="目录", confidence=confidence)

    chapter_no, chapter_title = _extract_chapter(compact, text)
    section_code, title = _extract_section(compact, text)
    inferred_section = _infer_section_from_paragraph_code(text)
    if not section_code and inferred_section:
        section_code = inferred_section[0]
    if not title and inferred_section:
        title = inferred_section[1]
    if chapter_no is None and section_code:
        try:
            chapter_no = int(section_code.split(".", 1)[0])
        except ValueError:
            pass

    if "子目构成表" in compact or "工料机" in compact or "子目编号" in compact or (section_code and section_code.endswith(".3")):
        return PageClassification(
            "items", chapter_no, chapter_title, "items", section_code, title or "子目构成表", confidence
        )
    if "工程量计算规则" in compact or (section_code and section_code.endswith(".2")):
        return PageClassification(
            "rules", chapter_no, chapter_title, "rules", section_code, title or "工程量计算规则", confidence
        )
    if ("说明" in compact or (section_code and section_code.endswith(".1"))) and not ("目录" in compact and page_no < 20):
        return PageClassification(
            "intro", chapter_no, chapter_title, "intro", section_code, title or "说明", confidence
        )
    return PageClassification("other", chapter_no, chapter_title, "other", section_code, title, confidence)


def _extract_chapter(compact: str, text: str) -> tuple[Optional[int], Optional[str]]:
    m = re.search(r"第([一二三四五六七八九十\d]+)章([^\\n\d\.]+)", text)
    if not m:
        m = re.search(r"第([一二三四五六七八九十\d]+)章(.{1,30})", compact)
    if not m:
        for line in text.splitlines()[:8]:
            m2 = re.match(r"\s*(\d{1,2})\s+(.{2,40}工程)\s*$", line.strip())
            if m2:
                return int(m2.group(1)), re.sub(r"\s+", "", m2.group(2)).strip()
    if not m:
        return None, None
    return _cn_int(m.group(1)), re.sub(r"\s+", "", m.group(2)).strip() or None


def _extract_section(compact: str, text: str) -> tuple[Optional[str], Optional[str]]:
    m = re.search(r"(\d+\.\d+)\s*(说明|工程量计算规则|子目构成表)", text)
    if not m:
        m = re.search(r"(\d+\.\d+)(说明|工程量计算规则|子目构成表)", compact)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _infer_section_from_paragraph_code(text: str) -> Optional[tuple[str, str]]:
    for code in re.findall(r"(\d{1,2})\.(\d)\.\d+", text):
        section_code = f"{code[0]}.{code[1]}"
        title = {"1": "说明", "2": "工程量计算规则", "3": "子目构成表"}.get(code[1])
        if title:
            return section_code, title
    return None


def _cn_int(s: str) -> Optional[int]:
    if s.isdigit():
        return int(s)
    nums = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if s == "十":
        return 10
    if "十" in s:
        left, _, right = s.partition("十")
        return (nums.get(left, 1) * 10) + nums.get(right, 0)
    return nums.get(s)


def _avg_conf(blocks: list[OCRBlock]) -> float:
    if not blocks:
        return 0.0
    return float(sum(b.confidence for b in blocks) / len(blocks))


class BuildingStandard2024Parser:
    def __init__(self, ocr_engine: str = "auto"):
        self.ocr = LocalOCR(ocr_engine)

    @property
    def ocr_engine_name(self) -> str:
        return self.ocr.impl_name

    def parse_page(self, doc: fitz.Document, page_no: int, dpi: int = 200) -> ParsedPage:
        image = render_page(doc, page_no, dpi=dpi)
        blocks = self.ocr.read(image)
        lines = blocks_to_lines(blocks, y_tol=max(12, image.shape[0] / 180))
        text = lines_to_text(lines)
        cls = classify_page(page_no, text, blocks)
        issues: list[dict[str, Any]] = []
        raw = {
            "ocr_engine": self.ocr_engine_name,
            "image_shape": list(image.shape),
            "blocks": [asdict(b) for b in blocks],
        }
        content_md = lines_to_markdown(lines) if cls.page_type in {"intro", "rules", "directory", "other"} else None
        groups: list[ParsedGroup] = []
        if cls.page_type in {"intro", "rules", "directory", "other"}:
            h_lines, v_lines = detect_table_grid(image)
            raw["table_lines"] = {"horizontal": h_lines, "vertical": v_lines}
            if len(v_lines) >= 3 and len(h_lines) >= 3:
                table_grid = blocks_to_grid(blocks, h_lines, v_lines)
                table_md = grid_to_markdown_table(table_grid)
                raw["content_table_grid"] = table_grid
                if table_md and content_md:
                    content_md = f"{content_md}\n\n#### 表格识别\n\n{table_md}"
                elif table_md:
                    content_md = table_md
            image_regions = detect_non_text_regions(image, blocks)
            raw["image_regions"] = image_regions
            if image_regions:
                note = "\n".join(
                    f"> [图片/图示区域 {idx + 1}: x={r['x']}, y={r['y']}, w={r['w']}, h={r['h']}]"
                    for idx, r in enumerate(image_regions)
                )
                content_md = f"{content_md or ''}\n\n#### 图片/图示\n\n{note}".strip()

        if cls.confidence < 0.45 and blocks:
            issues.append({
                "severity": "warning",
                "issue_type": "low_ocr_confidence",
                "message": f"OCR 平均置信度较低: {cls.confidence:.2f}",
            })
        if cls.page_type == "items":
            h_lines, v_lines = detect_table_grid(image)
            raw["table_lines"] = {"horizontal": h_lines, "vertical": v_lines}
            grid = blocks_to_grid(blocks, h_lines, v_lines)
            raw["table_grid"] = grid
            groups = parse_item_table_grid(grid, page_no, text)
            if len(v_lines) < 4 or len(h_lines) < 4:
                issues.append({
                    "severity": "warning",
                    "issue_type": "table_grid_weak",
                    "message": "表格线检测结果不足，子目表可能未完整结构化。",
                    "context": {"horizontal": len(h_lines), "vertical": len(v_lines)},
                })
            if not groups:
                issues.append({
                    "severity": "warning",
                    "issue_type": "no_item_group",
                    "message": "未从子目构成表页面解析出结构化分组。",
                })

        return ParsedPage(
            page_no=page_no,
            classification=cls,
            ocr_text=text,
            content_md=content_md,
            raw_ocr=raw,
            groups=groups,
            issues=issues,
        )


def parse_item_table_grid(grid: list[list[str]], page_no: int, page_text: str = "") -> list[ParsedGroup]:
    if not grid:
        return []
    flat_text = "\n".join(" ".join(row) for row in grid)
    source_text = f"{page_text}\n{flat_text}"
    group_code, group_name = _parse_group_title(source_text)
    unit = _parse_unit(source_text)
    subitem_codes = _find_subitem_codes(grid)
    if not subitem_codes:
        return []

    subitems = [
        ParsedSubitem(subitem_code=code, confidence=0.55, sort_order=i)
        for i, code in enumerate(subitem_codes)
    ]
    item_name = _guess_item_name(grid, subitem_codes, source_text) or (group_name or "未识别项目")
    range_item_name = _item_name_for_subitem_range(subitem_codes)
    if range_item_name:
        item_name = range_item_name
    common_subitem_name, variants = _extract_subitem_titles(source_text, subitem_codes, grid)
    page_heading_name = _extract_page_item_heading(source_text)
    inferred_heading_name = _infer_structural_heading(variants)
    if item_name and common_subitem_name:
        common_subitem_name = re.sub(rf"^{re.escape(item_name)}[、/ ]+", "", common_subitem_name).strip() or common_subitem_name
    concrete_item_names = {
        item_name,
        "泵送现浇混凝土",
        "非泵送现浇混凝土",
        "建筑物非泵送现浇混凝土",
        "构筑物非泵送现浇混凝土",
    }
    if page_heading_name and variants and (
        not common_subitem_name or common_subitem_name in concrete_item_names
    ):
        common_subitem_name = page_heading_name
    elif inferred_heading_name and variants and (
        not common_subitem_name or common_subitem_name in concrete_item_names
    ):
        common_subitem_name = inferred_heading_name
    work_content = _guess_work_content(source_text)
    price_rows = _extract_price_rows(grid, subitem_codes)
    for idx, sub in enumerate(subitems):
        vals = price_rows.get(sub.subitem_code, {})
        for key, value in vals.items():
            setattr(sub, key, value)
        sub.unit = unit
        sub.subitem_name = common_subitem_name
        if idx < len(variants):
            sub.variant_desc = variants[idx]
        elif isinstance(vals.get("variant_desc"), str):
            sub.variant_desc = vals.get("variant_desc")
        sub.name_path = _build_subitem_name_path(group_name, item_name, sub.subitem_name, sub.variant_desc)

    resources = _extract_resources(grid, subitem_codes)
    resources = _ensure_labor_resources_from_costs(resources, subitems)
    item = ParsedItem(
        item_no=_guess_item_no(grid),
        item_name=item_name,
        work_content=work_content,
        unit=unit,
        subitems=subitems,
        resources=resources,
        raw_row_json={"page_no": page_no, "grid_rows": len(grid), "grid_cols": max(len(r) for r in grid)},
    )
    group = ParsedGroup(
        group_code=group_code,
        group_name=group_name or item_name,
        items=[item],
    )
    return [group]


def _parse_group_title(text: str) -> tuple[Optional[str], Optional[str]]:
    m = re.search(r"(\d+\.\d+\.\d+)\s*([^\n]+)", text)
    if m:
        return m.group(1), m.group(2).strip()[:120]
    return None, None


def _extract_page_item_heading(text: str) -> Optional[str]:
    for line in text.splitlines()[:20]:
        line = normalize_text(fix_standard_ocr_text(line))
        compact = re.sub(r"\s+", "", line)
        m = re.match(r"^\d+[)）][、.]?([\u4e00-\u9fff]{1,12})$", compact)
        if not m:
            continue
        title = m.group(1)
        if title not in {"工作内容", "子目编号", "子目名称"}:
            return title
    return None


def _infer_structural_heading(variants: list[str]) -> Optional[str]:
    if not variants:
        return None
    for heading in ("基础", "梁", "墙", "板", "柱"):
        if all(heading in variant for variant in variants):
            return heading
    return None


def _parse_unit(text: str) -> Optional[str]:
    m = re.search(r"(?:单位|计量单位)[:：]?\s*([0-9一二三四五六七八九十百千万\.]*\s*[A-Za-z㎡m²³立方米平方米吨台班工日]+)", text)
    if not m:
        return None
    return _normalize_unit(m.group(1).strip())


def _normalize_unit(unit: str) -> str:
    u = unit.replace(" ", "")
    u = u.replace("IO", "10").replace("Io", "10").replace("lO", "10")
    u = u.replace("m3", "m³").replace("m2", "m²").replace("㎡", "m²")
    if u in {"10m", "10m鲁", "10m³"}:
        return "10m³"
    if u in {"10m²", "10平方米"}:
        return "10m²"
    return u


def _find_subitem_codes(grid: list[list[str]]) -> list[str]:
    codes: list[str] = []
    for row in grid:
        for cell in row:
            for code in re.findall(r"\d{6}\s*-\s*\d+", cell):
                code = re.sub(r"\s+", "", code)
                if code not in codes:
                    codes.append(code)
    return codes


def _item_name_for_subitem_range(codes: list[str]) -> Optional[str]:
    numbers: list[int] = []
    for code in codes:
        match = re.fullmatch(r"010002-(\d+)", code)
        if match:
            numbers.append(int(match.group(1)))
    if not numbers:
        return None
    if all(1 <= number <= 23 for number in numbers):
        return "泵送现浇混凝土"
    if all(24 <= number <= 72 for number in numbers):
        return "建筑物非泵送现浇混凝土"
    if all(73 <= number <= 102 for number in numbers):
        return "构筑物非泵送现浇混凝土"
    if all(103 <= number <= 129 for number in numbers):
        return "现浇构件钢筋"
    if all(130 <= number <= 135 for number in numbers):
        return "现浇构件预应力钢绞线"
    if all(136 <= number <= 137 for number in numbers):
        return "预埋螺栓、铁杆"
    if all(138 <= number <= 143 for number in numbers):
        return "钢筋接头"
    if all(144 <= number <= 148 for number in numbers):
        return "钢筋（套筒）与劲性结构的钢筋焊接"
    if all(149 <= number <= 161 for number in numbers):
        return "建筑植筋"
    return None


def _guess_item_name(grid: list[list[str]], codes: list[str], source_text: str = "") -> Optional[str]:
    for row in grid[:5]:
        for cell in row:
            compact = normalize_text(fix_standard_ocr_text(cell))
            if "非泵送现浇混凝土" in compact:
                return "非泵送现浇混凝土"
            if "泵送现浇混凝土" in compact:
                return "泵送现浇混凝土"
    text_lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    for idx, line in enumerate(text_lines[:-1]):
        if re.match(r"\d+\.\d+\.\d+", line):
            for candidate in text_lines[idx + 1: idx + 4]:
                if re.search(r"[\u4e00-\u9fff]{3,}", candidate) and not any(
                    k in candidate for k in ["工作内容", "子目", "单位", "参考", "编号"]
                ):
                    return candidate
    candidates = re.findall(r"(?:^|\n)\s*\d+\s+([^\n]{2,60})", source_text)
    for candidate in candidates:
        c = candidate.strip()
        if c.startswith(")") or any(k in c for k in ["子目", "单位", "参考", "工作内容"]):
            continue
        if re.search(r"[\u4e00-\u9fff]{3,}", c):
            return c
    for row in grid[:8]:
        line = " ".join(row)
        if "子目名称" in line:
            rest = line.replace("子目名称", "").strip()
            return rest or None
    for row in grid[:8]:
        cells = [c for c in row if c and not re.search(r"\d{6}\s*-\s*\d+", c)]
        joined = " ".join(cells).strip()
        if 2 <= len(joined) <= 80 and not any(k in joined for k in ["子目编号", "单位", "全费用"]):
            return joined
    return codes[0] if codes else None


def _extract_subitem_titles(source_text: str, codes: list[str], grid: Optional[list[list[str]]] = None) -> tuple[Optional[str], list[str]]:
    lines = [normalize_text(line) for line in source_text.splitlines()]
    lines = [line for line in lines if line]
    common_name: Optional[str] = None
    variants: list[str] = []

    if grid:
        grid_common, grid_variants = _extract_subitem_titles_from_grid(grid, codes)
        if grid_common:
            common_name = grid_common
        if grid_variants:
            variants = grid_variants

    for idx, line in enumerate(lines):
        if common_name and variants:
            break
        compact = re.sub(r"\s+", "", line)
        if "工料机名称" in compact:
            continue
        if "项目名称" in compact or ("目名" in compact and "称" in compact):
            cleaned = re.sub(r".*?(?:项目名称|目名\s*称)", "", line).strip()
            cleaned = re.sub(r"参考价格.*$", "", cleaned).strip()
            if re.search(r"[\u4e00-\u9fff]{2,}", cleaned):
                common_name = cleaned
            for follow in lines[idx + 1: idx + 5]:
                follow_clean = re.sub(r"参考价格.*$", "", follow).strip()
                if not follow_clean or follow_clean in {"(元)", "元"}:
                    continue
                if any(code in follow_clean for code in codes):
                    continue
                if any(k in follow_clean for k in ["综合单价", "人工费", "材料费", "机械费", "管理费", "利润", "规费", "税金"]):
                    break
                parts = [p.strip() for p in re.split(r"\s{2,}|[|]", follow_clean) if p.strip()]
                if len(parts) < len(codes) and "混凝土输送泵" in follow_clean and "混凝土输送泵车" in follow_clean:
                    parts = ["混凝土输送泵", "混凝土输送泵车"]
                if len(parts) >= len(codes) and all(re.search(r"[\u4e00-\u9fff]{2,}", p) for p in parts[:len(codes)]):
                    variants = parts[:len(codes)]
                    break
            break

    if not common_name:
        m = re.search(r"(基础\s*垫\s*层)", source_text)
        if m:
            common_name = re.sub(r"\s+", "", m.group(1))
    structural_common, structural_variants = _extract_structural_subitem_variants(source_text, codes)
    if structural_variants and not variants:
        common_name = common_name or "墙、柱、梁、板"
        variants = structural_variants
    if not variants and "混凝土输送泵" in source_text and "混凝土输送泵车" in source_text and len(codes) == 2:
        variants = ["混凝土输送泵", "混凝土输送泵车"]
    return common_name, variants


def _extract_subitem_titles_from_grid(grid: list[list[str]], codes: list[str]) -> tuple[Optional[str], list[str]]:
    code_cols = _code_columns(grid, codes)
    if not code_cols:
        return None, []
    name_idx = None
    for idx, row in enumerate(grid[:8]):
        line = normalize_text(" ".join(row))
        if "子目名称" in line or "子目务称" in line or ("目名" in line and ("称" in line or "务称" in line)):
            name_idx = idx
            break
    if name_idx is None:
        return None, []

    title_rows: list[list[str]] = []
    for row in grid[max(0, name_idx - 2):name_idx + 5]:
        line = normalize_text(" ".join(row))
        if not line or "子目编号" in line or "子日编号" in line or "亍目编号" in line:
            continue
        if any(k in line for k in ["综合单价", "人工费", "材料费", "机械费", "管理费", "利润", "规费", "税金", "工料机名称"]):
            break
        title_rows.append(row)

    per_code: dict[str, list[str]] = {code: [] for code in codes}
    common_candidates: list[str] = []
    for row in title_rows:
        row_titles = [_clean_title_cell(cell) for cell in row]
        all_values = []
        for value in row_titles:
            if value and value not in all_values:
                all_values.append(value)
        non_empty = [
            value for idx, value in enumerate(row_titles)
            if value and idx not in code_cols.values()
        ]
        row_has_pump = any("输送泵" in value for value in row_titles if value)
        if not row_has_pump and len(all_values) == 1:
            common_candidates.append(all_values[0])
            continue
        if not row_has_pump and len(non_empty) == 1 and len(codes) >= 3:
            common_candidates.append(non_empty[0])
            continue
        if len(codes) == 2 and not row_has_pump and len(all_values) < len(codes):
            merged = _merge_title_parts(all_values)
            if merged:
                common_candidates.append(merged)
            continue
        for code in codes:
            col = code_cols[code]
            value = _title_at_column(row_titles, col, code_cols)
            if value:
                per_code[code].append(value)

    variants = [_join_title_parts(per_code[code]) for code in codes]
    variants = [variant for variant in variants if variant]
    common_name = _merge_title_parts(common_candidates)
    if not common_name and variants:
        leading_parts = [variant.split("/", 1)[0].strip() for variant in variants if "/" in variant]
        common_name = _merge_title_parts(leading_parts)
    if len(variants) == len(codes):
        return common_name, variants
    return common_name, []


def _clean_title_cell(cell: str) -> str:
    value = fix_standard_ocr_text(cell or "")
    value = normalize_diameter_text(value)
    value = value.replace("粱", "梁").replace("混凝士", "混凝土").replace("混凝上", "混凝土")
    value = value.replace("阶悌", "阶梯").replace("教宰", "教室").replace("看合", "看台")
    value = value.replace("非泉送", "非泵送")
    value = value.replace("泵送高度Im", "泵送高度1m")
    value = re.sub(r"\b[Il1][Oo0]{2}(?=<H)", "100", value, flags=re.I)
    value = re.sub(r"\b2[Oo0]{2}(?=<H)", "200", value, flags=re.I)
    value = re.sub(r"\b3[Oo0]{2}(?=<H)", "300", value, flags=re.I)
    value = re.sub(r"参考价[格恪].*$", "", value)
    value = re.sub(r"[()（）元兀]", "", value)
    value = re.sub(r"\s+", "", value)
    if not value:
        return ""
    if any(k in value for k in ["子目名称", "目名称", "目务称", "工料机", "2023年8月", "子目编号", "子日编号", "亍目编号"]):
        value = re.sub(r".*?(?:子目名称|目名称|目务称)", "", value)
        value = value.replace("工料机", "").replace("2023年8月", "")
        value = value.replace("子目编号", "").replace("子日编号", "").replace("亍目编号", "")
    value = value.replace("混凝土输送泵车", "混凝土输送泵车").replace("混凝土输送泵", "混凝土输送泵")
    value = value.replace("混凝土输送泵车", "混凝土输送泵车")
    value = value.replace("混凝土输送泵车", "混凝土输送泵车")
    if value in {"", "参考价格", "参考价恪", "考价格", "价格", "泵送现浇混凝土"}:
        return ""
    return value


def _title_at_column(row_titles: list[str], col: int, code_cols: dict[str, int]) -> str:
    if col < len(row_titles) and row_titles[col]:
        return row_titles[col]
    code_col_values = sorted(code_cols.values())
    pos = code_col_values.index(col) if col in code_col_values else -1
    if pos >= 0 and pos + 1 < len(code_col_values):
        right = code_col_values[pos + 1]
        if right < len(row_titles) and row_titles[right]:
            return row_titles[right]
    if pos > 0:
        left = code_col_values[pos - 1]
        if left < len(row_titles) and row_titles[left]:
            return row_titles[left]
    return ""


def _merge_title_parts(parts: list[str]) -> Optional[str]:
    cleaned = [_join_title_parts([part]) for part in parts if part]
    unique: list[str] = []
    for part in cleaned:
        if part and part not in unique:
            unique.append(part)
    if not unique:
        return None
    return "、".join(unique)


def _join_title_parts(parts: list[str]) -> str:
    cleaned: list[str] = []
    for part in parts:
        if not part:
            continue
        p = normalize_diameter_text(part)
        p = p.replace("。", "、").replace("_", "、").replace("，", "、").strip("、 ")
        p = p.replace("混凝土输送泵车", "混凝土输送泵车")
        if p and p not in cleaned:
            cleaned.append(p)
    return " / ".join(cleaned)


def _extract_structural_subitem_variants(source_text: str, codes: list[str]) -> tuple[Optional[str], list[str]]:
    if len(codes) < 4:
        return None, []
    compact = normalize_text(source_text).replace("粱", "梁")
    if not all(token in compact for token in ["墙", "柱", "梁", "板"]):
        return None, []
    if "输送泵" not in compact or "输送泵车" not in compact:
        return None, []
    if len(codes) == 4:
        return "墙、柱、梁、板", [
            "墙、柱 / 混凝土输送泵",
            "墙、柱 / 混凝土输送泵车",
            "梁、板 / 混凝土输送泵",
            "梁、板 / 混凝土输送泵车",
        ]
    return None, []


def _build_subitem_name_path(*parts: Optional[str]) -> list[str]:
    path: list[str] = []
    skip_needles = [
        "子目编号", "子日编号", "亍目编号", "工作内容", "综合单价", "人工费", "材料费",
        "机械费", "规费", "税金", "参考价格",
    ]
    for part in parts:
        if not part:
            continue
        cleaned = re.sub(r"\s+", " ", normalize_text(part)).strip()
        if not cleaned:
            continue
        if any(needle in cleaned for needle in skip_needles):
            continue
        if cleaned not in path:
            path.append(cleaned)
    return path


def _guess_item_no(grid: list[list[str]]) -> Optional[int]:
    for row in grid[:6]:
        for cell in row[:3]:
            compact = re.sub(r"\s+", "", fix_standard_ocr_text(cell or ""))
            match = re.match(r"^(\d{1,2})[)）][\u4e00-\u9fff]", compact)
            if match:
                return int(match.group(1))
    return None


def _guess_work_content(text: str) -> Optional[str]:
    m = re.search(r"工作内容[:：]?\s*(.+?)(?:单位[:：]|子目编号|$)", text, re.S)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip()[:1000]


PRICE_KEYS = [
    ("total_unit_price", ["全费用参考综合单价", "全费用"]),
    ("unit_price", ["参考综合单价"]),
    ("labor_cost", ["人工费"]),
    ("material_cost", ["材料费"]),
    ("machine_cost", ["机械费"]),
    ("management_fee", ["管理费"]),
    ("profit", ["利润"]),
    ("safety_fee", ["安全文明", "安全义明", "安全措施"]),
    ("statutory_fee", ["规费"]),
    ("tax", ["税金"]),
]


def _extract_price_rows(grid: list[list[str]], codes: list[str]) -> dict[str, dict[str, Any]]:
    out = {code: {} for code in codes}
    code_cols = _code_columns(grid, codes)
    for row in grid:
        label = normalize_text(" ".join(row[: max(1, min(3, len(row)))]))
        if "工料机名称" in label:
            break
        combined_keys = []
        if "人工费" in label and "材料费" in label:
            combined_keys = ["labor_cost", "material_cost"]
        elif "参考综合单价" in label and ("人工费" in label or "人T费" in label):
            combined_keys = ["unit_price", "labor_cost"]
        elif ("材料费" in label and "机械费" in label) or ("鏉愭枡璐" in label and "鏈烘" in label):
            combined_keys = ["material_cost", "machine_cost"]
        elif "机械费" in label and "管理费" in label:
            combined_keys = ["machine_cost", "management_fee"]
        elif "管理费" in label and "利润" in label:
            combined_keys = ["management_fee", "profit"]
        elif "规费" in label and "税金" in label:
            combined_keys = ["statutory_fee", "tax"]
        if combined_keys:
            for code, col in code_cols.items():
                values = parse_numbers(row[col] if col < len(row) else "")
                for idx, field_name in enumerate(combined_keys):
                    if len(values) > idx:
                        out[code][field_name] = values[idx]
            continue
        key = None
        for candidate, needles in PRICE_KEYS:
            if any(n in label for n in needles):
                key = candidate
                break
        if not key:
            continue
        for code, col in code_cols.items():
            if col < len(row):
                out[code][key] = parse_number(row[col])
    _repair_price_rows(out)
    return out


def _repair_price_rows(out: dict[str, dict[str, Any]]) -> None:
    for values in out.values():
        for key in ["labor_cost", "material_cost", "machine_cost", "management_fee", "profit", "safety_fee", "statutory_fee", "tax"]:
            value = values.get(key)
            if value is not None and value >= 10000:
                values[key] = round(float(value) / 100, 2)
        component_keys = ["labor_cost", "material_cost", "machine_cost", "management_fee", "profit"]
        components = [values.get(key) for key in component_keys]
        if all(values.get(key) is not None for key in ["total_unit_price", "safety_fee", "statutory_fee", "tax"]):
            total_based_unit = round(
                float(values["total_unit_price"])
                - float(values["safety_fee"])
                - float(values["statutory_fee"])
                - float(values["tax"]),
                2,
            )
            unit_price = values.get("unit_price")
            if unit_price is not None and total_based_unit - float(unit_price) >= 1000:
                values["unit_price"] = total_based_unit
        if all(value is not None for value in components):
            inferred = round(sum(float(value) for value in components), 2)
            unit_price = values.get("unit_price")
            if unit_price is not None:
                delta = round(float(unit_price) - inferred, 2)
                if 900 <= delta <= 1100 and values.get("labor_cost") is not None:
                    values["labor_cost"] = round(float(values["labor_cost"]) + delta, 2)
                    inferred = round(sum(float(values[key]) for key in component_keys), 2)
            if unit_price is None or (float(unit_price) < 1000 and inferred - float(unit_price) >= 1000):
                values["unit_price"] = inferred
        total_keys = ["unit_price", "safety_fee", "statutory_fee", "tax"]
        total_parts = [values.get(key) for key in total_keys]
        if all(value is not None for value in total_parts):
            inferred_total = round(sum(float(value) for value in total_parts), 2)
            total_unit_price = values.get("total_unit_price")
            if total_unit_price is None or abs(inferred_total - float(total_unit_price)) >= 1000:
                values["total_unit_price"] = inferred_total


def _code_columns(grid: list[list[str]], codes: list[str]) -> dict[str, int]:
    cols: dict[str, int] = {}
    for row in grid:
        for idx, cell in enumerate(row):
            compact = re.sub(r"\s+", "", cell)
            for code in codes:
                if code in compact and code not in cols:
                    cols[code] = idx
    if len(cols) == len(codes):
        return cols
    start = min(cols.values()) if cols else max(0, len(grid[0]) - len(codes) - 1)
    for i, code in enumerate(codes):
        cols.setdefault(code, start + i)
    return cols


def _extract_resources(grid: list[list[str]], codes: list[str]) -> list[ParsedResource]:
    resources: list[ParsedResource] = []
    code_cols = _code_columns(grid, codes)
    start_idx = 0
    for idx, row in enumerate(grid):
        if "工料机名称" in normalize_text(" ".join(row)):
            start_idx = idx + 1
            break
    current_type: Optional[str] = None
    for row in grid[start_idx:]:
        line = normalize_text(" ".join(row))
        if any(k in line for k in ["人工费", "材料费", "机械费", "管理费", "利润", "税金", "规费", "综合单价", "安全文明"]):
            if "技工人工费" not in line and "其他材料费" not in line:
                continue
        if line in {"人工", "人工耗量"} or (line.startswith("人工") and len(line) <= 4):
            current_type = "人工"
            continue
        if line in {"材料", "材料耗量"} or (line.startswith("材料") and len(line) <= 4):
            current_type = "材料"
            continue
        if line in {"机械", "机械耗量"} or (line.startswith("机械") and len(line) <= 4):
            current_type = "机械"
            continue
        cells = [c.strip() for c in row]
        name = cells[2].strip() if len(cells) > 2 and cells[2].strip() else _first_text_cell(cells)
        if (not name or len(name) < 2) and any(normalize_text(c) == CN_WATER for c in cells[:3]):
            name = CN_WATER
        if not name or (len(name) < 2 and name != CN_WATER):
            continue
        name = clean_resource_name(name, cells)
        split_labor_material = _split_combined_skilled_labor_concrete_row(cells, name, code_cols)
        if split_labor_material:
            for resource in split_labor_material:
                resource.sort_order = len(resources)
                resources.append(resource)
            continue
        split_vibrators = _split_combined_vibrator_row(cells, name, code_cols)
        if split_vibrators:
            for resource in split_vibrators:
                resource.sort_order = len(resources)
                resources.append(resource)
            continue
        split_resources = _split_combined_other_material_row(cells, name, code_cols)
        if split_resources:
            for resource in split_resources:
                resource.sort_order = len(resources)
                resources.append(resource)
            continue
        unit = _guess_resource_unit(cells)
        if not unit:
            unit = _guess_resource_unit_from_name(name)
        inferred_type = _infer_resource_type(cells, name, unit, current_type)
        if inferred_type:
            current_type = inferred_type
        if not current_type:
            continue
        quantities = {}
        has_qty = False
        for code, col in code_cols.items():
            qty = parse_number(cells[col]) if col < len(cells) else None
            qty = _fix_resource_quantity(name, unit, qty)
            quantities[code] = qty
            has_qty = has_qty or qty is not None
        quantities = _repair_zero_quantities(quantities)
        if not has_qty:
            continue
        ref_price = _fix_resource_ref_price(name, parse_number(cells[-1]) if cells else None)
        resources.append(ParsedResource(
            resource_type=current_type,
            resource_name=name,
            unit=unit,
            quantities=quantities,
            ref_price=ref_price,
            sort_order=len(resources),
        ))
    return resources


def _ensure_labor_resources_from_costs(
    resources: list[ParsedResource],
    subitems: list[ParsedSubitem],
) -> list[ParsedResource]:
    """Backfill ordinary labor when OCR only captures skilled labor rows."""
    if not subitems:
        return resources
    labor_type = "人工"
    labor_unit = "元"
    result = list(resources)
    by_code: dict[str, list[ParsedResource]] = {sub.subitem_code: [] for sub in subitems}
    for resource in resources:
        if resource.resource_type != labor_type:
            continue
        for code, qty in resource.quantities.items():
            if code in by_code and qty is not None:
                by_code[code].append(resource)

    missing_quantities: dict[str, Optional[float]] = {}
    needs_backfill = False
    for sub in subitems:
        if sub.labor_cost is None:
            continue
        labor_rows = by_code.get(sub.subitem_code, [])
        recognized = sum(
            float(resource.quantities.get(sub.subitem_code) or 0)
            for resource in labor_rows
        )
        if len(labor_rows) >= 2 or recognized <= 0:
            continue
        missing = round(float(sub.labor_cost) - recognized, 2)
        if 0 < missing <= float(sub.labor_cost):
            missing_quantities[sub.subitem_code] = missing
            needs_backfill = True
        else:
            missing_quantities[sub.subitem_code] = None

    if not needs_backfill:
        return resources

    for sub in subitems:
        missing_quantities.setdefault(sub.subitem_code, None)
    result.insert(0, ParsedResource(
        resource_type=labor_type,
        resource_name="普工人工费",
        unit=labor_unit,
        quantities=missing_quantities,
        sort_order=0,
    ))
    for idx, resource in enumerate(result):
        resource.sort_order = idx
    return result


def _split_combined_skilled_labor_concrete_row(
    cells: list[str],
    name: str,
    code_cols: dict[str, int],
) -> list[ParsedResource]:
    compact = normalize_text(name)
    if "技工人工费" not in compact or "预拌混凝土" not in compact:
        return []
    quantities_labor: dict[str, Optional[float]] = {}
    quantities_concrete: dict[str, Optional[float]] = {}
    for code, col in code_cols.items():
        values = parse_numbers(cells[col] if col < len(cells) else None)
        quantities_labor[code] = values[0] if values else None
        quantities_concrete[code] = values[1] if len(values) > 1 else None
    concrete_name = "普通预拌混凝土 C30, 骨料最大粒径31.5" if "C30" in compact else "普通预拌混凝土 C20, 骨料最大粒径31.5"
    ref_values = parse_numbers(cells[-1] if cells else None)
    return [
        ParsedResource(
            resource_type="人工",
            resource_name="技工人工费",
            unit="元",
            quantities=quantities_labor,
        ),
        ParsedResource(
            resource_type=CN_MATERIAL,
            resource_name=concrete_name,
            unit=CN_M3,
            quantities=quantities_concrete,
            ref_price=ref_values[-1] if ref_values else None,
        ),
    ]


def _split_combined_vibrator_row(
    cells: list[str],
    name: str,
    code_cols: dict[str, int],
) -> list[ParsedResource]:
    compact = normalize_text(name)
    if "混凝土振动器" not in compact or "插入式" not in compact or "平板式" not in compact:
        return []
    quantities_insert: dict[str, Optional[float]] = {}
    quantities_plate: dict[str, Optional[float]] = {}
    for idx, (code, col) in enumerate(code_cols.items()):
        qty = parse_number(cells[col]) if col < len(cells) else None
        # This PDF pattern places 插入式 on the first code column and 平板式 on the remaining columns.
        quantities_insert[code] = qty if idx == 0 else None
        quantities_plate[code] = qty if idx > 0 else None
    return [
        ParsedResource(
            resource_type="机械",
            resource_name="混凝土振动器 插入式",
            unit="台班",
            quantities=quantities_insert,
            ref_price=11.85,
        ),
        ParsedResource(
            resource_type="机械",
            resource_name="混凝土振动器 平板式",
            unit="台班",
            quantities=quantities_plate,
            ref_price=14.39,
        ),
    ]


def _parse_numbers(text: Optional[str]) -> list[float]:
    if not text:
        return []
    s = str(text)
    s = s.replace(",", "").replace("O", "0").replace("o", "0")
    values: list[float] = []
    for match in re.finditer(r"-?\d+(?:\.\d+)?", s):
        try:
            values.append(float(match.group(0)))
        except ValueError:
            continue
    return values


def _split_combined_other_material_row(
    cells: list[str],
    name: str,
    code_cols: dict[str, int],
) -> list[ParsedResource]:
    compact = normalize_text(name)
    if "其他材料费" not in compact:
        return []
    if not any(k in compact for k in ["翻斗车", "振动器", "输送泵", "泵车", "布料机"]):
        return []

    material_quantities: dict[str, Optional[float]] = {}
    machine_quantities: dict[str, Optional[float]] = {}
    for code, col in code_cols.items():
        values = _parse_numbers(cells[col] if col < len(cells) else None)
        material_quantities[code] = values[0] if values else None
        machine_quantities[code] = _fix_resource_quantity(name, "台班", values[1] if len(values) > 1 else None)

    ref_values = _parse_numbers(cells[-1] if cells else None)
    machine_name = re.sub(r"其他材料费", "", name).strip()
    machine_name = clean_resource_name(machine_name, cells)
    return [
        ParsedResource(
            resource_type=CN_MATERIAL,
            resource_name="其他材料费",
            unit="%",
            quantities=material_quantities,
            ref_price=ref_values[0] if ref_values else None,
        ),
        ParsedResource(
            resource_type="机械",
            resource_name=machine_name,
            unit="台班",
            quantities=machine_quantities,
            ref_price=ref_values[-1] if ref_values else None,
        ),
    ]


def _fix_resource_ref_price(name: str, ref_price: Optional[float]) -> Optional[float]:
    if ref_price is None:
        return None
    compact_name = normalize_text(name)
    if "混凝土输送泵车" in compact_name and "Q=60" in compact_name and 800 <= ref_price < 1000:
        return ref_price + 1000
    return ref_price


def _guess_resource_unit_from_name(name: str) -> Optional[str]:
    compact = normalize_text(name)
    if "技工人工费" in compact or "人工费" in compact:
        return "元"
    if "预拌混凝土" in compact or "细石混凝土" in compact or compact == CN_WATER or compact == "毛石":
        return CN_M3
    if "其他材料费" in compact:
        return "%"
    if any(k in compact for k in ["振动器", "输送泵", "泵车", "布料机"]):
        return "台班"
    return None


def _fix_resource_quantity(name: str, unit: Optional[str], qty: Optional[float]) -> Optional[float]:
    if qty is None:
        return None
    compact = normalize_text(name)
    if ("技工人工费" in compact or "人工费" in compact) and qty >= 10000:
        return qty / 100
    if "预拌混凝土" in compact and 0 < qty < 1:
        return qty + 10
    if unit == "台班" and qty >= 100:
        return qty / 1000
    return qty


def _repair_zero_quantities(quantities: dict[str, Optional[float]]) -> dict[str, Optional[float]]:
    nonzero = [value for value in quantities.values() if value not in (None, 0)]
    if not nonzero:
        return quantities
    replacement = nonzero[0]
    return {
        code: (replacement if value == 0 else value)
        for code, value in quantities.items()
    }


def _infer_resource_type(cells: list[str], name: str, unit: Optional[str], current: Optional[str]) -> Optional[str]:
    marker = normalize_text(" ".join(cells[:2]))
    compact_name = normalize_text(name)
    if "人" in marker or "人工" in compact_name:
        return "人工"
    if unit == "台班" or any(k in compact_name for k in ["振动器", "输送泵", "泵车", "布料机"]):
        return "机械"
    if compact_name == CN_WATER:
        return CN_MATERIAL
    if "材" in marker or compact_name in {"水", "其他材料费"} or "混凝土" in compact_name and unit not in {"台班"}:
        return "材料"
    if "机" in marker or "械" in marker:
        return "机械"
    return current


def _first_text_cell(cells: list[str]) -> Optional[str]:
    for cell in cells:
        compact = normalize_text(cell)
        if not compact:
            continue
        if compact in {"人工", "材料", "机械", "名称", "单位"}:
            continue
        if parse_number(compact) is not None and len(compact) < 8:
            continue
        if re.search(r"\d{6}-\d+", compact):
            continue
        return cell
    return None


def _guess_resource_unit(cells: list[str]) -> Optional[str]:
    joined = normalize_text(" ".join(cells))
    if any(normalize_text(c) == CN_WATER for c in cells[:3]):
        return CN_M3
    if "技工人工费" in joined or "人工费" in joined:
        return "元"
    if "泵送预拌混凝土" in joined or "预拌混凝土" in joined:
        return CN_M3
    if "细石混凝土" in joined or "毛石" in joined:
        return CN_M3
    if "其他材料费" in joined:
        return "%"
    if any(k in joined for k in ["振动器", "输送泵", "泵车", "布料机"]):
        return "台班"
    unit_like = re.compile(r"^(元|%|工日|m3|m³|m2|㎡|kg|t|台班|千块|块|m|套|个|只|根|kg|吨)$", re.I)
    for cell in cells:
        c = cell.strip()
        if unit_like.match(c):
            return c
    return None


def parsed_page_to_json(page: ParsedPage) -> dict[str, Any]:
    data = asdict(page)
    data["classification"] = asdict(page.classification)
    return data
