"""核心算法自检脚本（不依赖 Qt）。

用法：python tools/test_core.py
"""

from __future__ import annotations

import random
import time
from pathlib import Path

from app.core.excel_import import auto_import
from app.core.grouping import build_groups, default_area_map
from app.core.models import (
    CELL_BOARD,
    CELL_DESK,
    REL_MUST,
    REL_PREFER,
    Layout,
    Relation,
    Student,
)
from app.core.seating import SeatingModel, analyze, solve
from tools.demo_data import SAMPLE_XLSX

ROOT = Path(__file__).resolve().parents[1]


def make_layout(rows_of_desks: int = 8, cols: int = 8) -> Layout:
    layout = Layout(rows=rows_of_desks + 1, cols=cols)
    for c in range(cols):
        layout.set_cell(0, c, CELL_BOARD)
    seat_cols = [0, 1, 3, 4, 6, 7]
    for r in range(1, rows_of_desks + 1):
        for c in seat_cols:
            layout.set_cell(r, c, CELL_DESK)
    for band in range(rows_of_desks // 2):
        for col_band in range(3):
            area = layout.add_area()
            for r in (1 + band * 2, 2 + band * 2):
                for c in (seat_cols[col_band * 2], seat_cols[col_band * 2 + 1]):
                    layout.assign_to_area(area, r, c)
    return layout


def main() -> int:
    result = auto_import(SAMPLE_XLSX)
    rng = random.Random(42)

    students = []
    for index, row in enumerate(result.rows):
        students.append(
            Student(
                name=row.name,
                gender="男" if rng.random() < 0.52 else "女",
                height=rng.choice(["低", "中", "中", "高"]),
            )
        )
    mapping = {s.sid: r for s, r in zip(students, result.rows)}

    layout = make_layout()
    print("座位数", len(layout.desks()))

    relations = [
        Relation(a=students[0].sid, b=students[1].sid, strength=REL_MUST, note="情侣"),
        Relation(a=students[2].sid, b=students[3].sid, strength=REL_PREFER, note="好友"),
        Relation(a=students[4].sid, b=students[5].sid, strength=REL_PREFER, note="好友"),
    ]

    t0 = time.perf_counter()
    plan = build_groups(students, mapping, layout, relations, seed=7)
    t1 = time.perf_counter()
    print(f"分组耗时 {t1 - t0:.2f}s，共 {len(plan.groups)} 组")
    print("区域容量", plan.capacities)
    for g in plan.groups:
        values = [mapping[m.sid].total for m in g.members if mapping.get(m.sid) and mapping[m.sid].total]
        avg = sum(values) / len(values) if values else 0
        print(f"  {g.title}: {len(g.members)} 人  均分 {avg:.1f}  " + "、".join(m.name for m in g.members))
    print("警告：", plan.warnings)
    if plan.waiting:
        print("待安排：", [s.name for s in plan.waiting])

    area_map = default_area_map(layout, len(plan.groups))
    t2 = time.perf_counter()
    solution = solve(layout, plan.groups, area_map, students, mapping, relations, layout_prefs(), seed=7)
    t3 = time.perf_counter()
    print(f"排座耗时 {t3 - t2:.2f}s")

    a = solution.analysis
    print(f"已坐 {a.seated} 人，未坐 {len(a.unseated)}")
    print(f"身高匹配率 {a.height_ok:.0%}，同桌异性率 {a.gender_ok if a.gender_ok is None else f'{a.gender_ok:.0%}'}")
    print(f"必须分开冲突 {a.must_conflicts}，尽量分开冲突 {a.prefer_conflicts}")
    for c in a.conflicts[:6]:
        print("  -", c.text)
    for note in solution.warnings[:6]:
        print("  *", note)
    return 0


def layout_prefs():
    from app.core.models import Preferences

    return Preferences()


if __name__ == "__main__":
    raise SystemExit(main())
