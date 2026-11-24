"""爱说话关照规则测试：分组 + 排座。"""

from __future__ import annotations

import random

from app.core.grouping import build_groups, default_area_map
from app.core.models import (
    ExamRow,
    Preferences,
    Student,
    TALK_CHATTY,
    TALK_NORMAL,
    fits_neighbor,
)
from app.core.seating import SeatingModel, solve
from tools.demo_data import make_layout


def build_class(count: int = 48, chatty_count: int = 5):
    chatty_indices = {2, 10, 18, 26, 34}
    students = []
    for index in range(count):
        students.append(
            Student(
                name=f"学生{index + 1:02d}",
                gender="男" if index % 2 == 0 else "女",
                height=["低", "中", "高"][index % 3],
                talk=TALK_CHATTY if index in chatty_indices else TALK_NORMAL,
            )
        )
    mapping = {
        s.sid: ExamRow(name=s.name, total=600 - i * 3.0, rank=i + 1, order=i)
        for i, s in enumerate(students)
    }
    return students, mapping


def main() -> int:
    students, mapping = build_class()
    layout = make_layout()
    focus = {s.sid for s in students if s.talk == TALK_CHATTY}
    print("爱说话学生：", [s.name for s in students if s.sid in focus])

    plan = build_groups(students, mapping, layout, [], seed=3, focus_sids=focus)
    student_of = {s.sid: s for s in students}
    group_bad = 0
    for group in plan.groups:
        for sid in focus:
            target = student_of[sid]
            if not any(m.sid == sid for m in group.members):
                continue
            peers = [m for m in group.members if m.sid != sid]
            need = min(2, len(peers))
            qualified = sum(1 for m in peers if fits_neighbor(m, target))
            shortfall = max(0, need - qualified)
            if shortfall:
                group_bad += shortfall
                print(
                    f"  第{group.gid}组 {target.name} 合格同组 {qualified}/{need}："
                    + "、".join(m.name for m in peers if not fits_neighbor(m, target))
                )
    print("分组阶段不合格同组人数：", group_bad)
    print("分组警告：", plan.warnings[:4])

    area_map = default_area_map(layout, len(plan.groups))
    solution = solve(
        layout,
        plan.groups,
        area_map,
        students,
        mapping,
        [],
        Preferences(),
        seed=3,
        focus_sids=focus,
    )
    analysis = solution.analysis
    print(
        f"排座：已坐 {analysis.seated}，"
        f"爱说话合格 {analysis.chatty_ok}/{analysis.chatty_total}，"
        f"总冲突 {len(analysis.conflicts)}"
    )
    for conflict in analysis.conflicts[:6]:
        print("  -", conflict.text)

    model = SeatingModel(layout)
    seat_of = {sid: key for key, sid in solution.assignment.items()}
    students_map = {s.sid: s for s in students}

    def bad_pairs(assignment: dict[str, str]):
        positions = {sid: key for key, sid in assignment.items()}
        out = []
        for sid in focus:
            target = students_map.get(sid)
            seat = positions.get(sid)
            if target is None or seat is None:
                continue
            for neighbor in model.orthogonal.get(seat, []):
                occupant = assignment.get(neighbor)
                if not occupant or occupant == sid:
                    continue
                other = students_map.get(occupant)
                if other is not None and not fits_neighbor(other, target):
                    out.append((sid, seat, neighbor, occupant))
        return out

    auto_bad = len(bad_pairs(solution.assignment))
    print("自动排座后的不合格邻座数：", auto_bad)
    assert group_bad == 0, "分组阶段就应尽量满足"

    # 模拟结果页的「优化爱说话周围」：允许跨组交换
    assignment = dict(solution.assignment)
    for _ in range(300):
        pairs = bad_pairs(assignment)
        if not pairs:
            break
        improved = False
        for _sid, seat, neighbor, _occupant in pairs:
            best = None
            for other in assignment:
                if other in (seat, neighbor):
                    continue
                trial = dict(assignment)
                trial[neighbor], trial[other] = trial[other], trial[neighbor]
                count = len(bad_pairs(trial))
                if count < len(pairs) and (best is None or count < best[0]):
                    best = (count, trial)
            if best is not None:
                assignment = best[1]
                improved = True
                break
        if not improved:
            break
    final_bad = len(bad_pairs(assignment))
    print("手动优化后的不合格邻座数：", final_bad)
    assert final_bad == 0, "手动优化后应能全部合格"
    print("通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
