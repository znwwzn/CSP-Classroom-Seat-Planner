"""生成演示用的虚构成绩表 samples/示例成绩表.xlsx。

姓名、成绩全部为假数据，仅用于演示和测试。
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples" / "示例成绩表.xlsx"


def main() -> int:
    wb = Workbook()
    ws = wb.active
    ws.title = "学生成绩汇总（全科）示例"
    ws.merge_cells("A1:H1")
    cell = ws["A1"]
    cell.value = "示例班级 · 成绩表（全部为虚构数据）"
    cell.font = Font(name="微软雅黑", size=14, bold=True, color="1F2A44")
    cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    headers = ["姓名", "总分", "原始分", "校次", "校次排名", "校方向名次", "校选考名次", "班次"]
    for index, header in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=index, value=header)
        cell.font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2F6BFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 24

    total_students = 48
    absent_from = 44
    for index in range(total_students):
        row = index + 3
        name = f"学生{index + 1:02d}"
        ws.cell(row=row, column=1, value=name)
        if index >= absent_from:
            ws.cell(row=row, column=2, value="缺考，不计排名")
            ws.cell(row=row, column=3, value="缺考，不计排名")
            for column in range(4, 9):
                ws.cell(row=row, column=column, value="-")
        else:
            total = 620 - index * 4
            ws.cell(row=row, column=2, value=float(total))
            ws.cell(row=row, column=3, value=float(total - 60))
            ws.cell(row=row, column=4, value=index + 1)
            ws.cell(row=row, column=5, value=index + 1)
            ws.cell(row=row, column=6, value=index + 1)
            ws.cell(row=row, column=7, value=index + 1)
            ws.cell(row=row, column=8, value=index + 1)
        for column in range(1, 9):
            ws.cell(row=row, column=column).font = Font(name="微软雅黑", size=10)
            ws.cell(row=row, column=column).alignment = Alignment(horizontal="center")

    widths = [14, 10, 10, 8, 10, 12, 12, 8]
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width

    note = wb.create_sheet("说明")
    note.column_dimensions["A"].width = 80
    lines = [
        "这是软件自带的演示数据，所有姓名和分数均为虚构。",
        "格式模仿智学网导出的「学生成绩汇总」：第 1 行大标题、第 2 行表头、F 列（第 8 列）为班次。",
        "最后 4 名学生为“缺考，不计排名”，用来演示缺考处理。",
        "可以用自己的成绩表替换它，只要表头包含 姓名 / 总分 / 班次 即可。",
    ]
    for index, text in enumerate(lines, start=1):
        cell = note.cell(row=index, column=1, value=text)
        cell.font = Font(name="微软雅黑", size=11)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print("saved", OUT, OUT.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
