"""智学网成绩表解析。

真实导出文件长这样：
- 工作簿里有「学生成绩汇总（全科）原版」「…修改」等多个 Sheet；
- 第 1 行是合并单元格的大标题（如「示例班级成绩表」）；
- 第 2 行才是表头：A 姓名、B 总分、C 原始分、D/E 校排名、F 班次（班排）…；
- 缺考学生的总分/排名是「缺考，不计排名」或「-」。

解析器会自动定位表头和列，也支持手动指定列作为兜底。
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .models import ExamRow, Student

NAME_ALIASES = ("姓名", "学生姓名", "名字")
TOTAL_ALIASES = ("总分", "总成绩", "合计", "分数")
RANK_ALIASES = ("班次", "班排", "班级排名", "班名", "班级名次", "排名")
SUMMARY_ROW_WORDS = ("平均分", "合计", "总计", "班级平均", "年级平均", "统计")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip().replace("\u3000", " ")


def _clean_header(value: Any) -> str:
    return re.sub(r"\s+", "", _text(value))


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value).replace(",", "").replace("，", "")
    if not text or text in {"-", "—", "/", "缺考", "缺考，不计排名"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(round(number))


@dataclass
class ImportResult:
    path: str
    sheet: str
    header_row: int  # 1-based
    headers: list[str]
    name_col: int  # 0-based
    total_col: int | None
    rank_col: int | None
    rows: list[ExamRow] = field(default_factory=list)
    note: str = ""

    @property
    def valid_count(self) -> int:
        return sum(1 for r in self.rows if r.rank is not None or r.total is not None)

    @property
    def missing_rank_count(self) -> int:
        return sum(1 for r in self.rows if r.rank is None)

    def description(self) -> str:
        bits = [f"工作表「{self.sheet}」", f"表头第 {self.header_row} 行", f"共 {len(self.rows)} 人"]
        if self.rank_col is not None:
            bits.append(f"排名列「{self.headers[self.rank_col]}」")
        elif self.total_col is not None:
            bits.append("无排名列，按总分自动排名")
        return "，".join(bits)


@dataclass
class MatchResult:
    mapping: dict[str, ExamRow]  # sid -> row
    unmatched_rows: list[str]
    missing_students: list[str]  # 名单里有、成绩表里没有

    @property
    def ok(self) -> bool:
        return bool(self.mapping)


# --------------------------------------------------------------------------- #
# 读取工作簿
# --------------------------------------------------------------------------- #


def sheet_names(path: str | Path) -> list[str]:
    if str(path).lower().endswith(".csv"):
        return ["CSV"]
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _sheet_rows(path: str | Path, sheet: str) -> list[list[Any]]:
    if str(path).lower().endswith(".csv"):
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            return [list(row) for row in csv.reader(fh)]
    wb = load_workbook(path, data_only=True)
    try:
        ws = wb[sheet]
        return [list(row) for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def _find_header(rows: list[list[Any]]) -> tuple[int, int, int, int | None, int | None] | None:
    """返回 (header_row_idx, name_col, total_col, rank_col, ...)。"""
    for idx, row in enumerate(rows[:25]):
        headers = [_clean_header(v) for v in row]
        if not any(h in NAME_ALIASES for h in headers):
            continue
        name_col = next(i for i, h in enumerate(headers) if h in NAME_ALIASES)
        total_col = next((i for i, h in enumerate(headers) if h in TOTAL_ALIASES), None)
        if total_col is None:
            total_col = next((i for i, h in enumerate(headers) if "总分" in h), None)
        rank_col = next((i for i, h in enumerate(headers) if h in RANK_ALIASES), None)
        if rank_col is None:
            rank_col = next((i for i, h in enumerate(headers) if "班" in h and "名" in h), None)
        if total_col is None and rank_col is None:
            continue
        return idx, name_col, total_col, rank_col, len(headers)
    return None


def preview_sheet(path: str | Path, sheet: str, max_rows: int = 12) -> list[list[str]]:
    rows = _sheet_rows(path, sheet)[:max_rows]
    width = max((len(r) for r in rows), default=0)
    return [[_text(r[i]) if i < len(r) else "" for i in range(min(width, 40))] for r in rows]


def _build_result(
    path: str | Path,
    sheet: str,
    rows: list[list[Any]],
    header_idx: int,
    name_col: int,
    total_col: int | None,
    rank_col: int | None,
) -> ImportResult:
    headers = [_text(v) for v in rows[header_idx]]
    result_rows: list[ExamRow] = []
    seen: set[str] = set()
    for offset, row in enumerate(rows[header_idx + 1 :], start=header_idx + 1):
        name = _text(row[name_col]) if name_col < len(row) else ""
        if not name or name in seen:
            continue
        if any(word in name for word in SUMMARY_ROW_WORDS):
            continue
        total = _to_float(row[total_col]) if total_col is not None and total_col < len(row) else None
        rank = _to_int(row[rank_col]) if rank_col is not None and rank_col < len(row) else None
        if total is None and rank is None and ("缺考" not in name):
            # 完全空白的行（比如末尾的说明）跳过
            if not any(_text(v) for v in row[: max(name_col + 1, 3)]):
                continue
        seen.add(name)
        result_rows.append(ExamRow(name=name, total=total, rank=rank, order=offset))

    note = ""
    if rank_col is None and total_col is not None:
        # 没有排名列：按总分从高到低补一个班排
        ranked = sorted(
            [r for r in result_rows if r.total is not None],
            key=lambda r: r.total,  # type: ignore[arg-type]
            reverse=True,
        )
        for index, item in enumerate(ranked, start=1):
            item.rank = index
        note = "未找到班排名列，已按总分自动生成排名"

    return ImportResult(
        path=str(path),
        sheet=sheet,
        header_row=header_idx + 1,
        headers=headers,
        name_col=name_col,
        total_col=total_col,
        rank_col=rank_col,
        rows=result_rows,
        note=note,
    )


def auto_import(path: str | Path) -> ImportResult:
    """自动挑选「汇总」表并解析，失败时抛出 ValueError。"""
    path = Path(path)
    if path.suffix.lower() == ".xls":
        raise ValueError("暂不支持旧版 .xls，请用 Excel 另存为 .xlsx 后再导入。")
    if path.suffix.lower() == ".csv":
        rows = _sheet_rows(path, "CSV")
        header = _find_header(rows)
        if not header:
            raise ValueError("CSV 里找不到「姓名」表头")
        idx, name_col, total_col, rank_col, _ = header
        return _build_result(path, "CSV", rows, idx, name_col, total_col, rank_col)

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        names = list(wb.sheetnames)
    finally:
        wb.close()

    preferred = [n for n in names if "汇总" in n] + [n for n in names if "汇总" not in n]
    errors: list[str] = []
    for sheet in preferred:
        rows = _sheet_rows(path, sheet)
        header = _find_header(rows)
        if not header:
            errors.append(sheet)
            continue
        idx, name_col, total_col, rank_col, _ = header
        result = _build_result(path, sheet, rows, idx, name_col, total_col, rank_col)
        if result.rows:
            return result
    raise ValueError("没有找到包含「姓名」和「总分/排名」的工作表，请使用手动指定列。")


def import_with_mapping(
    path: str | Path,
    sheet: str,
    header_row: int,
    name_col: int,
    total_col: int | None,
    rank_col: int | None,
) -> ImportResult:
    rows = _sheet_rows(path, sheet)
    idx = max(0, header_row - 1)
    return _build_result(path, sheet, rows, idx, name_col, total_col, rank_col)


def detect_mapping(path: str | Path, sheet: str) -> dict[str, int | None] | None:
    """猜测某个 Sheet 的表头位置与列号，供“手动指定列”对话框预填。"""
    try:
        rows = _sheet_rows(path, sheet)
    except (OSError, KeyError, ValueError):
        return None
    header = _find_header(rows)
    if not header:
        return None
    idx, name_col, total_col, rank_col, _ = header
    return {
        "header_row": idx + 1,
        "name_col": name_col,
        "total_col": total_col,
        "rank_col": rank_col,
    }


# --------------------------------------------------------------------------- #
# 与班级名单匹配
# --------------------------------------------------------------------------- #


def match_to_students(students: list[Student], result: ImportResult) -> MatchResult:
    by_name: dict[str, list[Student]] = {}
    for student in students:
        by_name.setdefault(student.name.strip(), []).append(student)

    mapping: dict[str, ExamRow] = {}
    unmatched: list[str] = []
    used: set[str] = set()
    for row in result.rows:
        candidates = by_name.get(row.name.strip(), [])
        target = next((s for s in candidates if s.sid not in used), None)
        if target is None:
            unmatched.append(row.name)
            continue
        mapping[target.sid] = row
        used.add(target.sid)

    missing = [s.name for s in students if s.sid not in used]
    return MatchResult(mapping=mapping, unmatched_rows=unmatched, missing_students=missing)


def ordered_students(students: list[Student], mapping: dict[str, ExamRow]) -> list[Student]:
    """按班排排序；缺考/无排名的按原表顺序排在最后。"""
    def key(student: Student) -> tuple:
        row = mapping.get(student.sid)
        if row is None:
            return (2, 0, 10**9)
        if row.rank is None:
            return (1, row.order, 10**9)
        return (0, row.rank, row.order)

    return sorted(students, key=key)


def rank_label(mapping: dict[str, ExamRow], sid: str) -> str:
    row = mapping.get(sid)
    if row is None:
        return "未匹配"
    if row.rank is None:
        return "缺考"
    return f"第 {row.rank} 名"
