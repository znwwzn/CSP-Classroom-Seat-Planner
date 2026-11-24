"""按班排分组。

规则（来自需求）：
1. 第 1 组 = 班排最前面的若干人，第 2 组 = 紧随其后的若干人（即“尖子组”固定）；
2. 其余学生分到剩余小组，使这些小组的平均分尽量接近；
3. 组的人数 = 该组所在区域的座位数（区域容量），因此分组时按容量切；
4. “必须分开”的关系对不能落入同一组。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterable

from .excel_import import ordered_students
from .models import (
    REL_MUST,
    REL_PREFER,
    TALK_CHATTY,
    Area,
    ExamRow,
    Group,
    Layout,
    Relation,
    Student,
    fits_neighbor,
)


@dataclass
class GroupPlan:
    groups: list[Group]
    capacities: list[int]
    area_ids: list[str]
    waiting: list[Student] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def group_by_gid(self, gid: int) -> Group | None:
        return next((g for g in self.groups if g.gid == gid), None)


# --------------------------------------------------------------------------- #
# 容量
# --------------------------------------------------------------------------- #


def area_capacities(layout: Layout) -> list[tuple[Area, int]]:
    return [(area, len(layout.seats_of(area))) for area in layout.areas]


def effective_capacities(seat_counts: list[int], student_count: int) -> list[int]:
    """座位多于学生时，从最大的区域逐个削减，保证人数与座位对齐。"""
    caps = [max(0, int(c)) for c in seat_counts]
    total = sum(caps)
    while total > student_count:
        candidates = [i for i, c in enumerate(caps) if c > 1]
        if not candidates:
            candidates = [i for i, c in enumerate(caps) if c > 0]
        if not candidates:
            break
        index = max(candidates, key=lambda i: (caps[i], i))
        caps[index] -= 1
        total -= 1
    return caps


def default_area_map(layout: Layout, group_count: int) -> dict[str, int]:
    """默认：第 i 个有座位的区域放第 i 组（超出组数的区域不分配）。"""
    mapping: dict[str, int] = {}
    seated = [area for area in layout.areas if layout.seats_of(area)]
    for index, area in enumerate(seated):
        if index < group_count:
            mapping[area.aid] = index + 1
    return mapping


# --------------------------------------------------------------------------- #
# 分组主流程
# --------------------------------------------------------------------------- #


def build_groups(
    students: list[Student],
    mapping: dict[str, ExamRow],
    layout: Layout,
    relations: list[Relation],
    seed: int | None = None,
    focus_sids: set[str] | None = None,
) -> GroupPlan:
    rng = random.Random(seed)
    if not students:
        return GroupPlan(groups=[], capacities=[], area_ids=[], warnings=["班级名单还是空的"])

    areas = [a for a in layout.areas if layout.seats_of(a)]
    seat_counts = [len(layout.seats_of(a)) for a in areas]
    if not areas:
        return GroupPlan(groups=[], capacities=[], area_ids=[], warnings=["还没有可用的区域，请先去教室布局里画课桌并分组"])

    caps = effective_capacities(seat_counts, len(students))
    ordered = ordered_students(students, mapping)
    assigned_total = min(sum(caps), len(ordered))
    waiting = ordered[assigned_total:]

    warnings: list[str] = []
    if sum(seat_counts) > len(students):
        gaps = sum(seat_counts) - len(students)
        if gaps:
            warnings.append(f"座位比学生多 {gaps} 个，这些空位会留空")
    if waiting:
        warnings.append(f"座位不足，{len(waiting)} 名学生需要手动安排：{'、'.join(s.name for s in waiting)}")
    if len(areas) < 2:
        warnings.append("区域少于 2 个，无法分出固定的尖子组")

    score_of = {sid: row.total for sid, row in mapping.items()}
    groups: list[Group] = []
    cursor = 0
    head_caps = caps[:2] if len(caps) >= 2 else caps[:1]

    # 前两组：名次头部连续切
    for index, cap in enumerate(head_caps):
        members = ordered[cursor : cursor + cap]
        cursor += cap
        groups.append(Group(gid=index + 1, members=list(members), capacity=cap))

    rest_caps = caps[len(head_caps) :]
    rest_students = ordered[cursor : cursor + sum(rest_caps)]
    rest_groups = _balanced_partition(rest_students, rest_caps, score_of, relations, rng)
    for offset, members in enumerate(rest_groups):
        groups.append(Group(gid=len(head_caps) + offset + 1, members=members, capacity=rest_caps[offset]))

    groups = [g for g in groups if g.capacity > 0]
    _repair_must_pairs(groups, relations, score_of)
    _repair_head_prefers(groups, relations, score_of)
    focus = (
        set(focus_sids)
        if focus_sids is not None
        else {s.sid for s in students if s.talk == TALK_CHATTY}
    )
    warnings.extend(_repair_chatty_groups(groups, focus, score_of, relations))

    areas_aligned: list[Area] = []
    caps_aligned: list[int] = []
    for area, cap in zip(areas, caps):
        if cap > 0:
            areas_aligned.append(area)
            caps_aligned.append(cap)
    # 组数和区域数必须一致
    if len(groups) != len(areas_aligned):
        warnings.append("分组数量与区域数量不一致，请在排座页手动检查")
    return GroupPlan(
        groups=groups,
        capacities=caps_aligned,
        area_ids=[a.aid for a in areas_aligned],
        waiting=waiting,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# 剩余学生的均衡划分
# --------------------------------------------------------------------------- #


def _means(groups: list[list[Student]], score_of: dict[str, float | None]) -> list[float | None]:
    result: list[float | None] = []
    for members in groups:
        values = [score_of[s.sid] for s in members if score_of.get(s.sid) is not None]
        result.append(sum(values) / len(values) if values else None)  # type: ignore[arg-type]
    return result


def _partition_cost(
    groups: list[list[Student]],
    score_of: dict[str, float | None],
    must_pairs: set[tuple[str, str]],
    prefer_pairs: set[tuple[str, str]] = frozenset(),  # type: ignore[assignment]
) -> float:
    means = [m for m in _means(groups, score_of) if m is not None]
    cost = 0.0
    if len(means) > 1:
        avg = sum(means) / len(means)
        cost += sum((m - avg) ** 2 for m in means) * len(groups)

    male_ratio = 0.0
    total = sum(len(g) for g in groups)
    if total:
        male_ratio = sum(1 for g in groups for s in g if s.gender == "男") / total

    for members in groups:
        sids = {s.sid for s in members}
        for a, b in must_pairs:
            if a in sids and b in sids:
                cost += 5000.0
        for a, b in prefer_pairs:
            if a in sids and b in sids:
                cost += 260.0
        if members:
            ratio = sum(1 for s in members if s.gender == "男") / len(members)
            cost += (ratio - male_ratio) ** 2 * 12.0
    return cost


def _balanced_partition(
    students: list[Student],
    caps: list[int],
    score_of: dict[str, float | None],
    relations: list[Relation],
    rng: random.Random,
) -> list[list[Student]]:
    students = list(students)
    if not students:
        return [[] for _ in caps]
    if len(caps) == 1:
        return [students]

    must_pairs = {
        tuple(sorted((r.a, r.b)))  # type: ignore[misc]
        for r in relations
        if r.strength == REL_MUST and r.a != r.b
    }
    prefer_pairs = {
        tuple(sorted((r.a, r.b)))  # type: ignore[misc]
        for r in relations
        if r.strength == REL_PREFER and r.a != r.b
    }

    order = sorted(
        students,
        key=lambda s: (score_of.get(s.sid) is not None, score_of.get(s.sid) or 0.0),
        reverse=True,
    )
    groups: list[list[Student]] = [[] for _ in caps]
    cursor = 0
    direction = 1
    while cursor < len(order):
        indices = range(len(groups)) if direction == 1 else range(len(groups) - 1, -1, -1)
        placed = False
        for index in indices:
            if cursor >= len(order):
                break
            if len(groups[index]) < caps[index]:
                groups[index].append(order[cursor])
                cursor += 1
                placed = True
        if not placed:
            break
        direction *= -1

    # 局部搜索：随机交换两名学生，保留能让代价下降的交换
    best = _partition_cost(groups, score_of, must_pairs, prefer_pairs)
    for _ in range(12000):
        i, j = rng.sample(range(len(groups)), 2)
        if not groups[i] or not groups[j]:
            continue
        a = rng.randrange(len(groups[i]))
        b = rng.randrange(len(groups[j]))
        groups[i][a], groups[j][b] = groups[j][b], groups[i][a]
        cost = _partition_cost(groups, score_of, must_pairs, prefer_pairs)
        if cost < best - 1e-9:
            best = cost
        else:
            groups[i][a], groups[j][b] = groups[j][b], groups[i][a]
    return groups


def _repair_must_pairs(
    groups: list[Group],
    relations: list[Relation],
    score_of: dict[str, float | None],
) -> None:
    """兜底修复：如果“必须分开”的两名学生仍在同一组，把他们换开。

    若冲突发生在“尖子组”内部，只在尖子组之间交换，保证前两组仍由头部名次组成。
    """
    must = [(r.a, r.b) for r in relations if r.strength == REL_MUST and r.a != r.b]
    must = [(a, b) for a, b in must if a != b]
    if not must:
        return
    prefer = [(r.a, r.b) for r in relations if r.strength == REL_PREFER and r.a != r.b]
    must_set = {tuple(sorted(pair)) for pair in must}
    prefer_set = {tuple(sorted(pair)) for pair in prefer if pair[0] != pair[1]}
    head = min(2, len(groups))

    for _ in range(len(must) * 8):
        position: dict[str, tuple[int, int]] = {}
        for gi, group in enumerate(groups):
            for si, student in enumerate(group.members):
                position[student.sid] = (gi, si)

        violation = None
        for a, b in must:
            if a in position and b in position and position[a][0] == position[b][0]:
                violation = (a, b)
                break
        if violation is None:
            return

        a, b = violation
        ga, _ = position[a]
        ib = position[b][1]
        b_student = groups[ga].members[ib]
        if ga < head and len(groups) > head:
            targets = [i for i in range(head) if i != ga]
        else:
            targets = [i for i in range(len(groups)) if i != ga]

        best: tuple[float, int, int] | None = None
        for gi in targets:
            for si, other in enumerate(groups[gi].members):
                if other.sid in (a, b):
                    continue
                groups[ga].members[ib] = other
                groups[gi].members[si] = b_student
                cost = _partition_cost(
                    [g.members for g in groups], score_of, must_set, prefer_set
                )
                groups[ga].members[ib] = b_student
                groups[gi].members[si] = other
                if best is None or cost < best[0]:
                    best = (cost, gi, si)

        if best is None:
            return
        _, gi, si = best
        other = groups[gi].members[si]
        groups[ga].members[ib] = other
        groups[gi].members[si] = b_student


def _chatty_cost(
    groups: list[Group],
    focus: list[str],
    score_of: dict[str, float | None],
    must_set: set[tuple[str, str]],
    prefer_set: set[tuple[str, str]],
) -> tuple[float, int]:
    """代价 = 不合格邻居数 + 组均分方差 + 关系冲突。返回 (代价, 不合格邻居数)。"""
    student_of = {s.sid: s for g in groups for s in g.members}
    index = {s.sid: gi for gi, g in enumerate(groups) for s in g.members}
    bad = 0
    for sid in focus:
        target = student_of.get(sid)
        gi = index.get(sid)
        if target is None or gi is None:
            continue
        peers = [p for p in groups[gi].members if p.sid != sid]
        qualified = sum(1 for p in peers if fits_neighbor(p, target))
        need = min(2, len(peers))
        bad += max(0, need - qualified)

    means = [m for m in _means([g.members for g in groups], score_of) if m is not None]
    variance = 0.0
    if len(means) > 1:
        avg = sum(means) / len(means)
        variance = sum((m - avg) ** 2 for m in means) / len(means)

    violations = 0
    for group in groups:
        sids = {s.sid for s in group.members}
        for a, b in must_set:
            if a in sids and b in sids:
                violations += 1
        for a, b in prefer_set:
            if a in sids and b in sids:
                violations += 1

    return bad * 100.0 + variance * 2.0 + violations * 5000.0, bad


def _repair_chatty_groups(
    groups: list[Group],
    focus_sids: set[str],
    score_of: dict[str, float | None],
    relations: list[Relation],
) -> list[str]:
    """让“爱说话”的学生同组里尽量都是异性或安静的同学。

    只在同层级的小组之间交换（尖子组只能和尖子组换），避免破坏前两组名次范围。
    """
    student_of = {s.sid: s for g in groups for s in g.members}
    focus = [sid for sid in focus_sids if sid in student_of]
    if not focus or len(groups) < 2:
        return []

    must_set = {
        tuple(sorted((r.a, r.b)))  # type: ignore[misc]
        for r in relations
        if r.strength == REL_MUST and r.a != r.b
    }
    prefer_set = {
        tuple(sorted((r.a, r.b)))  # type: ignore[misc]
        for r in relations
        if r.strength == REL_PREFER and r.a != r.b
    }
    head = min(2, len(groups))
    warnings: list[str] = []

    for _ in range(200):
        cost, bad = _chatty_cost(groups, focus, score_of, must_set, prefer_set)
        if bad == 0:
            break
        index = {s.sid: gi for gi, g in enumerate(groups) for s in g.members}
        unsatisfied = None
        for sid in focus:
            gi = index.get(sid)
            if gi is None:
                continue
            target = student_of[sid]
            peers = [
                (pi, p)
                for pi, p in enumerate(groups[gi].members)
                if p.sid != sid and not fits_neighbor(p, target)
            ]
            need = min(2, len(groups[gi].members) - 1)
            qualified = len(groups[gi].members) - 1 - len(peers)
            if peers and qualified < need:
                unsatisfied = (sid, gi, target, peers)
                break
        if unsatisfied is None:
            break

        sid, gi, target, peers = unsatisfied
        best: tuple[float, int, int, int, Student] | None = None
        for pi, peer in peers:
            for gj, group in enumerate(groups):
                if gj == gi:
                    continue
                if (gi < head) != (gj < head):
                    continue
                for qi, candidate in enumerate(group.members):
                    if candidate.sid == sid or not fits_neighbor(candidate, target):
                        continue
                    groups[gi].members[pi], groups[gj].members[qi] = candidate, peer
                    trial_cost, _ = _chatty_cost(groups, focus, score_of, must_set, prefer_set)
                    groups[gi].members[pi], groups[gj].members[qi] = peer, candidate
                    if best is None or trial_cost < best[0]:
                        best = (trial_cost, gi, pi, gj, candidate)
        if best is None or best[0] >= cost - 1e-6:
            break
        _, gi, pi, gj, candidate = best
        peer = groups[gi].members[pi]
        qi = groups[gj].members.index(candidate)
        groups[gi].members[pi] = candidate
        groups[gj].members[qi] = peer

    index = {s.sid: gi for gi, g in enumerate(groups) for s in g.members}
    for sid in focus:
        target = student_of[sid]
        gi = index.get(sid)
        if gi is None:
            continue
        bad_peers = [
            p.name
            for p in groups[gi].members
            if p.sid != sid and not fits_neighbor(p, target)
        ]
        need = min(2, len(groups[gi].members) - 1)
        qualified = len(groups[gi].members) - 1 - len(bad_peers)
        if bad_peers and qualified < need:
            warnings.append(
                f"「{target.name}」周围还缺少异性或“不爱说话”的同学"
                f"（同组：{'、'.join(bad_peers)}），可在结果页手动调整"
            )
    return warnings[:6]

def _repair_head_prefers(
    groups: list[Group],
    relations: list[Relation],
    score_of: dict[str, float | None],
) -> None:
    """尖子组内部如果塞进了“尽量分开”的一对，和另一个尖子组对调。"""
    prefer = [(r.a, r.b) for r in relations if r.strength == REL_PREFER and r.a != r.b]
    if not prefer or len(groups) < 2:
        return
    must_set = {
        tuple(sorted((r.a, r.b)))  # type: ignore[misc]
        for r in relations
        if r.strength == REL_MUST and r.a != r.b
    }
    prefer_set = {tuple(sorted(pair)) for pair in prefer if pair[0] != pair[1]}
    head = min(2, len(groups))

    for a, b in prefer:
        if a == b:
            continue
        position: dict[str, tuple[int, int]] = {}
        for gi, group in enumerate(groups):
            for si, student in enumerate(group.members):
                position[student.sid] = (gi, si)
        if a not in position or b not in position:
            continue
        ga, _ = position[a]
        gb, ib = position[b]
        if ga != gb or ga >= head:
            continue
        target = next((i for i in range(head) if i != ga), None)
        if target is None:
            continue
        b_student = groups[ga].members[ib]
        best: tuple[float, int] | None = None
        for si, other in enumerate(groups[target].members):
            if other.sid in (a, b):
                continue
            groups[ga].members[ib] = other
            groups[target].members[si] = b_student
            cost = _partition_cost(
                [g.members for g in groups], score_of, must_set, prefer_set
            )
            groups[ga].members[ib] = b_student
            groups[target].members[si] = other
            if best is None or cost < best[0]:
                best = (cost, si)
        if best is None:
            continue
        other = groups[target].members[best[1]]
        groups[ga].members[ib] = other
        groups[target].members[best[1]] = b_student
