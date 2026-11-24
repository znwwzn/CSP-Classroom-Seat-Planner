"""导出冒烟测试：构造一份排座结果并导出 Excel。"""

from __future__ import annotations

from pathlib import Path

from app.core.excel_export import export_plan
from app.core.excel_import import auto_import
from app.core.grouping import build_groups, default_area_map
from app.core.models import Preferences, PlanRecord, Relation, Student
from app.core.seating import solve
from tools.demo_data import SAMPLE_XLSX, make_layout

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = auto_import(SAMPLE_XLSX)
    students = []
    for index, row in enumerate(result.rows):
        students.append(
            Student(
                name=row.name,
                gender="男" if index % 2 == 0 else "女",
                height=["低", "中", "中", "高"][index % 4],
            )
        )
    mapping = {s.sid: r for s, r in zip(students, result.rows)}
    layout = make_layout()
    relations = [Relation(a=students[0].sid, b=students[1].sid)]
    plan = build_groups(students, mapping, layout, relations, seed=3)
    area_map = default_area_map(layout, len(plan.groups))
    prefs = Preferences()
    solution = solve(layout, plan.groups, area_map, students, mapping, relations, prefs, seed=3)

    record = PlanRecord(
        created_at="2026-11-01 20:00",
        class_name="示例班级",
        source_file=Path(result.path).name,
        students=students,
        layout=layout,
        preferences=prefs,
        scores={
            sid: {"total": row.total, "rank": row.rank} for sid, row in mapping.items()
        },
        groups=[
            {"gid": g.gid, "capacity": g.capacity, "members": [m.sid for m in g.members]}
            for g in plan.groups
        ],
        area_group=area_map,
        seats=solution.assignment,
        stats={"height_ok": solution.analysis.height_ok},
    )
    out = ROOT / "data" / "test_export.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    export_plan(record, out)
    print("导出成功", out, out.stat().st_size, "字节")

    from openpyxl import load_workbook

    wb = load_workbook(out)
    print("Sheets:", wb.sheetnames)
    ws = wb["座位表"]
    for row in ws.iter_rows(min_row=1, max_row=8, values_only=True):
        print([v for v in row if v is not None])
    print("名单表头:", [c.value for c in wb["名单"][1]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
