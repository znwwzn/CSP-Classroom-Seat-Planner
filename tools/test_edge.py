"""边界情况测试：不等容量、无黑板、缺考、悬空关系等。"""

from __future__ import annotations

from app.core.grouping import build_groups, effective_capacities
from app.core.models import (
    CELL_BOARD,
    CELL_DESK,
    REL_MUST,
    Layout,
    Relation,
    Student,
)
from app.core.seating import solve
from app.core.excel_import import match_to_students, auto_import


def students(n: int) -> list[Student]:
    out = []
    for i in range(n):
        out.append(
            Student(
                name=f"学生{i + 1:02d}",
                gender="男" if i % 3 else "女",
                height=["低", "中", "高"][i % 3],
            )
        )
    return out


def fake_mapping(group: list[Student]):
    from app.core.models import ExamRow

    mapping = {}
    for index, student in enumerate(group):
        mapping[student.sid] = ExamRow(
            name=student.name, total=600 - index * 3.5, rank=index + 1, order=index
        )
    return mapping


def make_layout_with_areas(area_sizes: list[int], board: bool = True) -> Layout:
    """按给定的每组座位数铺一个网格，尽量排成矩形。"""
    total = sum(area_sizes)
    cols = 8
    rows = (total + cols - 1) // cols + 1
    layout = Layout(rows=rows, cols=cols)
    if board:
        for c in range(cols):
            layout.set_cell(0, c, CELL_BOARD)
    seats = []
    for r in range(1, rows):
        for c in range(cols):
            if len(seats) >= total:
                break
            layout.set_cell(r, c, CELL_DESK)
            seats.append((r, c))
    cursor = 0
    for size in area_sizes:
        area = layout.add_area()
        for _ in range(size):
            if cursor >= len(seats):
                break
            layout.assign_to_area(area, *seats[cursor])
            cursor += 1
    return layout


def run(name: str, n: int, area_sizes: list[int], board: bool = True) -> None:
    roster = students(n)
    mapping = fake_mapping(roster)
    layout = make_layout_with_areas(area_sizes, board=board)
    relations = [
        Relation(a=roster[0].sid, b=roster[1].sid, strength=REL_MUST, note="情侣"),
        Relation(a="missing-a", b="missing-b", strength=REL_MUST),
    ]
    caps = effective_capacities([len(layout.seats_of(a)) for a in layout.areas], n)
    plan = build_groups(roster, mapping, layout, relations, seed=1)
    from app.core.grouping import default_area_map

    area_map = default_area_map(layout, len(plan.groups))
    solution = solve(
        layout,
        plan.groups,
        area_map,
        roster,
        mapping,
        relations,
        __import__("app.core.models", fromlist=["Preferences"]).Preferences(),
        seed=2,
    )
    assigned = set(solution.assignment.values())
    expected = {s.sid for g in plan.groups for s in g.members}
    assert assigned == expected, f"{name}: 座位分配不完整 {len(assigned)} vs {len(expected)}"
    same_group = [
        (a, b)
        for a, b in [(roster[0].sid, roster[1].sid)]
        for g in plan.groups
        if a in {s.sid for s in g.members} and b in {s.sid for s in g.members}
    ]
    print(
        f"[{name}] 人数 {n} 容量 {area_sizes} -> 生效 {caps} 组数 {len(plan.groups)} "
        f"已坐 {len(assigned)} 必须分开同组 {len(same_group)} 冲突 {len(solution.analysis.conflicts)}"
    )
    if plan.warnings:
        print("   warn:", plan.warnings[:2])
    if solution.warnings:
        print("   seat warn:", solution.warnings[:2])


def main() -> int:
    run("标准12组", 48, [4] * 12)
    run("不等容量", 36, [6, 6, 5, 5, 4, 4, 3, 3])
    run("无黑板", 20, [5, 5, 5, 5], board=False)
    run("少于座位", 10, [4, 4, 4, 4])
    run("单人小组", 9, [1, 2, 2, 4])

    # 用自带的示例成绩表验证 47 人、48 座时不会有人掉队
    from tools.demo_data import SAMPLE_XLSX

    result = auto_import(SAMPLE_XLSX)
    roster = [Student(name=row.name) for row in result.rows[:47]]
    mapping = match_to_students(roster, result).mapping
    layout = make_layout_with_areas([4] * 12)
    plan = build_groups(roster, mapping, layout, [], seed=5)
    print(f"[示例成绩表] 分组 {len(plan.groups)} 组，待安排 {len(plan.waiting)} 人")
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
