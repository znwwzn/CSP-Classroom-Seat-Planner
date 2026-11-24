"""把排座结果导出成 Excel：

Sheet1「座位表」——按教室真实布局绘制，可直接打印张贴；
Sheet2「名单」——组号、区域、排/列、同桌、成绩等明细。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .models import (
    CELL_BOARD,
    CELL_DESK,
    CELL_PODIUM,
    PlanRecord,
    cell_key,
)

FONT_NAME = "微软雅黑"
ACCENT = "2F6BFF"
INK = "1F2A44"
MUTED = "6B7A99"
BORDER_COLOR = "FFD9E2F2"

THIN = Side(style="thin", color=BORDER_COLOR)
CARD_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _argb(color: str) -> str:
    value = color.lstrip("#")
    return value if len(value) == 8 else "FF" + value


def _tint(hex_color: str, factor: float = 0.86) -> str:
    """把颜色向白色混合，做浅色底。"""
    value = hex_color.lstrip("#")
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"{r:02X}{g:02X}{b:02X}"


def _fill(color: str) -> PatternFill:
    value = color.lstrip("#")
    if len(value) == 6:
        value = "FF" + value
    return PatternFill("solid", fgColor=value)


def _center(vertical: str = "center") -> Alignment:
    return Alignment(horizontal="center", vertical=vertical, wrap_text=True)


def _group_of_student(record: PlanRecord) -> dict[str, int]:
    """优先按“座位所在区域 → 该区指定的组”计算，这样手动拖动换座后名单也一致。"""
    mapping: dict[str, int] = {}
    for key, sid in record.seats.items():
        if not sid:
            continue
        try:
            row, col = (int(x) for x in key.split(","))
        except ValueError:
            continue
        area = record.layout.area_of(row, col)
        if area and area.aid in record.area_group:
            mapping[sid] = int(record.area_group[area.aid])
    for group in record.groups:
        gid = int(group.get("gid", 0))
        for sid in group.get("members", []):
            mapping.setdefault(sid, gid)
    return mapping


def _area_name(record: PlanRecord, aid: str | None) -> str:
    if aid is None:
        return ""
    for area in record.layout.areas:
        if area.aid == aid:
            return area.name
    return ""


def _seat_order(record: PlanRecord) -> list[tuple[int, int]]:
    return sorted(
        (int(k.split(",")[0]), int(k.split(",")[1]))
        for k in record.seats
        if record.seats[k]
    )


# --------------------------------------------------------------------------- #
# 座位表
# --------------------------------------------------------------------------- #


def _write_seat_map(ws: Worksheet, record: PlanRecord) -> None:
    layout = record.layout
    total_cols = layout.cols + 1  # 第 1 列放“第 n 排”
    title = f"{record.class_name or '班级'} · 座位表"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(2, total_cols))
    cell = ws.cell(row=1, column=1, value=title)
    cell.font = Font(name=FONT_NAME, size=18, bold=True, color=INK)
    cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 40

    stamp = record.created_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    subtitle = f"导出时间 {stamp}　·　共 {len(record.seats)} 人"
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(2, total_cols))
    cell = ws.cell(row=2, column=1, value=subtitle)
    cell.font = Font(name=FONT_NAME, size=9, color=MUTED)
    cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    info_row = 3
    ws.cell(row=info_row, column=1, value="方向").font = Font(name=FONT_NAME, size=8, color=MUTED)
    ws.cell(row=info_row, column=1).alignment = _center()
    # 顶部提示黑板方向
    boards = layout.blackboards()
    hint = "↑ 黑板/讲台方向" if boards and min(r for r, _ in boards) < (layout.rows / 2) else "↓ 黑板/讲台方向"
    ws.merge_cells(start_row=info_row, start_column=2, end_row=info_row, end_column=max(2, total_cols))
    cell = ws.cell(row=info_row, column=2, value=hint)
    cell.font = Font(name=FONT_NAME, size=9, color=MUTED)
    cell.alignment = Alignment(horizontal="left", vertical="center")

    start_row = 5
    students = {s.sid: s for s in record.students}
    group_map = _group_of_student(record)
    area_colors = {a.aid: a.color_hex for a in layout.areas}
    area_names = {a.aid: a.name for a in layout.areas}

    desk_rows = sorted({r for r, _ in layout.desks()})
    desk_row_index = {r: i for i, r in enumerate(desk_rows)}
    desk_row_label = {r: f"第{i + 1}排" for r, i in desk_row_index.items()}

    for col in range(layout.cols):
        letter = get_column_letter(col + 2)
        ws.column_dimensions[letter].width = 11
    ws.column_dimensions["A"].width = 8

    for row in range(layout.rows):
        excel_row = start_row + row
        ws.row_dimensions[excel_row].height = 36
        label = ws.cell(row=excel_row, column=1, value=desk_row_label.get(row, ""))
        label.font = Font(name=FONT_NAME, size=9, color=MUTED)
        label.alignment = _center()
        label.border = Border()

        col = 0
        while col < layout.cols:
            kind = layout.cell(row, col)
            excel_col = col + 2
            target = ws.cell(row=excel_row, column=excel_col)
            if kind == CELL_BOARD:
                # 合并连续的同一行黑板
                end = col
                while end + 1 < layout.cols and layout.cell(row, end + 1) == CELL_BOARD:
                    end += 1
                if end > col:
                    ws.merge_cells(
                        start_row=excel_row,
                        start_column=excel_col,
                        end_row=excel_row,
                        end_column=end + 2,
                    )
                target.value = "黑　板"
                target.font = Font(name=FONT_NAME, size=12, bold=True, color="FFFFFF")
                target.fill = _fill("1F2A44")
                target.alignment = _center()
                for c in range(col, end + 1):
                    ws.cell(row=excel_row, column=c + 2).border = CARD_BORDER
                    ws.cell(row=excel_row, column=c + 2).fill = _fill("1F2A44")
                col = end + 1
                continue
            if kind == CELL_PODIUM:
                target.value = "讲　台"
                target.font = Font(name=FONT_NAME, size=11, bold=True, color=INK)
                target.fill = _fill("EEF2FA")
                target.alignment = _center()
                target.border = CARD_BORDER
            elif kind == CELL_DESK:
                key = cell_key(row, col)
                sid = record.seats.get(key)
                student = students.get(sid) if sid else None
                if student:
                    target.value = student.name
                    target.font = Font(name=FONT_NAME, size=12, bold=True, color=INK)
                    gid = group_map.get(student.sid)
                    area = layout.area_of(row, col)
                    color = area_colors.get(area.aid, ACCENT) if area else ACCENT
                    target.fill = _fill(_tint(color, 0.88))
                    target.border = Border(
                        left=Side(style="medium", color=_argb(color)),
                        right=THIN,
                        top=THIN,
                        bottom=THIN,
                    )
                    target.alignment = _center()
                else:
                    target.value = "空"
                    target.font = Font(name=FONT_NAME, size=9, color="B6C2D9")
                    target.fill = _fill("F7F9FD")
                    target.alignment = _center()
                    target.border = Border(
                        left=THIN, right=THIN, top=THIN, bottom=THIN,
                        outline=CARD_BORDER.outline,
                    )
            col += 1

    # 图例
    legend_row = start_row + layout.rows + 1
    ws.cell(row=legend_row, column=1, value="区域").font = Font(
        name=FONT_NAME, size=9, bold=True, color=MUTED
    )
    column = 2
    for area in layout.areas:
        if not layout.seats_of(area):
            continue
        cell = ws.cell(row=legend_row, column=column, value=f" {area.name} ")
        cell.font = Font(name=FONT_NAME, size=9, color=INK)
        cell.fill = _fill(_tint(area.color_hex, 0.8))
        cell.alignment = _center()
        cell.border = Border(left=Side(style="medium", color=_argb(area.color_hex)), right=THIN, top=THIN, bottom=THIN)
        column += 1
        if column > total_cols:
            column = 2
            legend_row += 1

    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


# --------------------------------------------------------------------------- #
# 名单
# --------------------------------------------------------------------------- #


def _write_roster(ws: Worksheet, record: PlanRecord) -> None:
    headers = ["组号", "区域", "姓名", "性别", "身高", "爱说话", "排", "列", "同桌", "总分", "班排"]
    widths = [8, 12, 12, 8, 8, 10, 8, 8, 12, 10, 8]
    for index, (header, width) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=1, column=index, value=header)
        cell.font = Font(name=FONT_NAME, size=11, bold=True, color="FFFFFF")
        cell.fill = _fill(ACCENT)
        cell.alignment = _center()
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.row_dimensions[1].height = 28

    students = {s.sid: s for s in record.students}
    group_map = _group_of_student(record)
    desk_rows = sorted({r for r, _ in record.layout.desks()})
    desk_index = {r: i for i, r in enumerate(desk_rows)}
    rows = []  # (gid, area_name, row, col, sid)
    for key, sid in record.seats.items():
        if not sid:
            continue
        r, c = (int(x) for x in key.split(","))
        area = record.layout.area_of(r, c)
        gid = group_map.get(sid, 0)
        rows.append((gid, _area_name(record, area.aid if area else None), r, c, sid))
    rows.sort(key=lambda item: (item[0], item[2], item[3]))

    def neighbor_name(row: int, col: int) -> str:
        for other_col in (col - 1, col + 1):
            if 0 <= other_col < record.layout.cols:
                other = record.seats.get(cell_key(row, other_col))
                if other and other in students:
                    return students[other].name
        return ""

    for index, (gid, area_name, row, col, sid) in enumerate(rows, start=2):
        student = students[sid]
        score = record.scores.get(sid, {})
        values = [
            gid,
            area_name,
            student.name,
            student.gender,
            student.height,
            student.talk,
            desk_index.get(row, row) + 1,
            col + 1,
            neighbor_name(row, col),
            score.get("total", ""),
            score.get("rank", "缺考") if score.get("rank") is not None else "缺考",
        ]
        for col_index, value in enumerate(values, start=1):
            cell = ws.cell(row=index, column=col_index, value=value)
            cell.font = Font(name=FONT_NAME, size=10, color=INK)
            cell.alignment = _center()
            cell.border = Border(
                left=THIN, right=THIN, top=THIN, bottom=THIN
            )
            if index % 2 == 0:
                cell.fill = _fill("F7F9FD")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:K{max(1, len(rows) + 1)}"


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #


def export_plan(record: PlanRecord, path: str | Path) -> Path:
    path = Path(path)
    wb = Workbook()
    seat_sheet = wb.active
    seat_sheet.title = "座位表"
    _write_seat_map(seat_sheet, record)
    roster = wb.create_sheet("名单")
    _write_roster(roster, record)

    wb.properties.title = f"{record.class_name} 座位表"
    wb.properties.creator = "班级排座助手"
    wb.save(path)
    return path


def export_data(preview: dict[str, Any], path: str | Path) -> Path:
    """导出任意二维数据（备用）。"""
    path = Path(path)
    wb = Workbook()
    ws = wb.active
    for r, row in enumerate(preview.get("rows", []), start=1):
        for c, value in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=value)
    wb.save(path)
    return path
