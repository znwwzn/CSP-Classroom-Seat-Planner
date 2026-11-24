"""座位求解器。

把每个小组安排进它对应的区域，并在区域内部决定“谁坐哪张桌”，
同时权衡三类因素：

* 身高：离黑板越近越矮、越远越高（按几何距离，而不是死板三分）；
* 性别：左右相邻的两张桌构成“同桌”，可要求异性 / 同性 / 不限制；
* 特殊关系：“必须分开”是强约束，“尽量分开”是软约束。

区域内部的座位数通常 3~7 个，规模很小，直接用全排列求最优；
超过 7 个座位时改用随机交换的爬山法。
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field
from typing import Any

from .models import (
    GENDER_MODE_FREE,
    GENDER_MODE_MIXED,
    GENDER_MODE_SAME,
    REL_MUST,
    REL_PREFER,
    TALK_CHATTY,
    Area,
    ExamRow,
    Group,
    Layout,
    Preferences,
    Relation,
    Student,
    cell_key,
    fits_neighbor,
    parse_cell_key,
)

PERMUTATION_LIMIT = 6


# --------------------------------------------------------------------------- #
# 座位几何
# --------------------------------------------------------------------------- #


@dataclass
class Seat:
    key: str
    row: int
    col: int
    area_id: str | None
    dist: float
    dn: float  # 归一化后的“离黑板远近”，0=最近，1=最远

    @property
    def label(self) -> str:
        return f"{self.row + 1}排{self.col + 1}列"


class SeatingModel:
    """布局的几何信息：每个座位到黑板的距离、同桌关系、邻接关系。"""

    def __init__(self, layout: Layout) -> None:
        self.layout = layout
        boards = layout.blackboards()
        desks = layout.desks()
        raw: dict[str, float] = {}
        for row, col in desks:
            if boards:
                raw[cell_key(row, col)] = min(
                    math.hypot(row - br, col - bc) for br, bc in boards
                )
            else:
                raw[cell_key(row, col)] = float(row)
        maximum = max(raw.values(), default=0.0)
        minimum = min(raw.values(), default=0.0)
        span = maximum - minimum

        self.seats: dict[str, Seat] = {}
        for row, col in desks:
            key = cell_key(row, col)
            area = layout.area_of(row, col)
            distance = raw[key]
            dn = (distance - minimum) / span if span > 1e-9 else 0.5
            self.seats[key] = Seat(key, row, col, area.aid if area else None, distance, dn)

        # 同桌：同一行、左右紧挨的两张桌（中间隔着过道就不算）
        self.desk_pairs: list[tuple[str, str]] = []
        for seat in self.seats.values():
            right = cell_key(seat.row, seat.col + 1)
            if right in self.seats:
                self.desk_pairs.append((seat.key, right))

        # 邻接：切比雪夫距离 1（前后左右 + 斜角）
        self.adjacency: dict[str, list[str]] = {key: [] for key in self.seats}
        for seat in self.seats.values():
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    other = cell_key(seat.row + dr, seat.col + dc)
                    if other in self.seats:
                        self.adjacency[seat.key].append(other)

        # 前后左右（不含斜角），“爱说话”学生只按这四个方向检查
        self.orthogonal: dict[str, list[str]] = {key: [] for key in self.seats}
        for seat in self.seats.values():
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                other = cell_key(seat.row + dr, seat.col + dc)
                if other in self.seats:
                    self.orthogonal[seat.key].append(other)

        self.area_seats: dict[str, list[str]] = {}
        for area in layout.areas:
            keys = [
                cell_key(r, c)
                for r, c in layout.seats_of(area)
                if cell_key(r, c) in self.seats
            ]
            keys.sort(key=lambda k: (self.seats[k].dist, self.seats[k].row, self.seats[k].col))
            self.area_seats[area.aid] = keys

        self.deg: dict[str, int] = {key: len(v) for key, v in self.adjacency.items()}

    def distance_between(self, a: str, b: str) -> int:
        sa, sb = self.seats[a], self.seats[b]
        return max(abs(sa.row - sb.row), abs(sa.col - sb.col))

    def area_of_seat(self, key: str) -> str | None:
        return self.seats[key].area_id

    def seat_order_in_area(self, area_id: str) -> list[str]:
        return self.area_seats.get(area_id, [])


# --------------------------------------------------------------------------- #
# 结果
# --------------------------------------------------------------------------- #


@dataclass
class Conflict:
    kind: str  # 同桌 / 关系
    text: str
    seats: list[str] = field(default_factory=list)
    severity: str = "warn"  # warn / hard


@dataclass
class SeatAnalysis:
    seated: int = 0
    unseated: list[str] = field(default_factory=list)
    height_ok: float = 0.0
    gender_ok: float | None = None
    must_conflicts: int = 0
    prefer_conflicts: int = 0
    chatty_total: int = 0
    chatty_ok: int = 0
    conflicts: list[Conflict] = field(default_factory=list)
    seat_flags: dict[str, list[str]] = field(default_factory=dict)
    group_notes: list[str] = field(default_factory=list)


@dataclass
class SeatSolution:
    assignment: dict[str, str]  # 座位 key -> 学生 sid
    warnings: list[str] = field(default_factory=list)
    analysis: SeatAnalysis = field(default_factory=SeatAnalysis)


# --------------------------------------------------------------------------- #
# 求解
# --------------------------------------------------------------------------- #


class _Optimizer:
    def __init__(
        self,
        model: SeatingModel,
        assignment: dict[str, str],
        students: dict[str, Student],
        relations: list[Relation],
        prefs: Preferences,
        focus_sids: set[str],
    ) -> None:
        self.model = model
        self.assignment = assignment
        self.students = students
        self.prefs = prefs
        self.focus_sids = {sid for sid in focus_sids if sid in students}
        self.w_h = max(0.0, prefs.height_weight / 100.0)
        self.w_g = max(0.0, prefs.gender_weight / 100.0)
        self.w_r = max(0.0, prefs.relation_weight / 100.0)
        self.w_t = max(0.0, prefs.talk_weight / 100.0)
        self.pairs = [
            (r.a, r.b, r.strength)
            for r in relations
            if r.a != r.b and r.a in {s.sid for s in students.values()} and r.b in {s.sid for s in students.values()}
        ]
        self.seat_of_student = {sid: key for key, sid in assignment.items()}

    # -- 单项代价 -----------------------------------------------------------
    def _height_cost(self, key: str, sid: str) -> float:
        seat = self.model.seats[key]
        height = self.students[sid].height_score / 2.0
        return ((height - seat.dn) ** 2) * 55.0 * self.w_h

    def _rank_cost(self, area_id: str, keys_to_sid: dict[str, str]) -> float:
        keys = [k for k in self.model.area_seats.get(area_id, []) if k in keys_to_sid]
        if len(keys) <= 1:
            return 0.0
        members = [keys_to_sid[k] for k in keys]
        by_height = sorted(range(len(members)), key=lambda i: self.students[members[i]].height_score)
        rank_of = {members[idx]: rank for rank, idx in enumerate(by_height)}
        total = 0.0
        for position, sid in enumerate(members):
            total += (position - rank_of[sid]) ** 2
        return total / len(members) * 9.0 * self.w_h

    def _gender_cost(self, sid_a: str, sid_b: str) -> float:
        mode = self.prefs.gender_mode
        if mode == GENDER_MODE_FREE:
            return 0.0
        same = self.students[sid_a].gender == self.students[sid_b].gender
        if mode == GENDER_MODE_MIXED and same:
            return 14.0 * self.w_g
        if mode == GENDER_MODE_SAME and not same:
            return 14.0 * self.w_g
        return 0.0

    def _relation_cost(self, sid_a: str, sid_b: str, strength: str, lookup) -> float:
        seat_a = lookup(sid_a)
        seat_b = lookup(sid_b)
        if seat_a is None or seat_b is None:
            return 0.0
        gap = self.model.distance_between(seat_a, seat_b)
        scale = 0.35 + self.w_r
        if strength == REL_MUST:
            if gap <= 1:
                return 500.0 * scale
            if gap == 2:
                return 30.0 * scale
            return 0.0
        if gap <= 1:
            return 16.0 * scale
        if gap == 2:
            return 3.0 * scale
        return 0.0

    def _seat_lookup(self, override: dict[str, str] | None = None):
        seat_of = dict(self.seat_of_student)
        if override:
            for key, sid in override.items():
                seat_of[sid] = key
        return seat_of.get

    # -- 区域代价 -----------------------------------------------------------
    def area_cost(self, area_id: str, keys_to_sid: dict[str, str]) -> float:
        cost = 0.0
        for key, sid in keys_to_sid.items():
            cost += self._height_cost(key, sid)
        cost += self._rank_cost(area_id, keys_to_sid)

        lookup = self._seat_lookup(keys_to_sid)

        for key_a, key_b in self.model.desk_pairs:
            if key_a in keys_to_sid and key_b in keys_to_sid:
                cost += self._gender_cost(keys_to_sid[key_a], keys_to_sid[key_b])
            elif key_a in keys_to_sid:
                if self.assignment.get(key_b):
                    cost += self._gender_cost(keys_to_sid[key_a], self.assignment[key_b])
            elif key_b in keys_to_sid:
                if self.assignment.get(key_a):
                    cost += self._gender_cost(keys_to_sid[key_b], self.assignment[key_a])

        members = set(keys_to_sid.values())
        for a, b, strength in self.pairs:
            if a in members or b in members:
                cost += self._relation_cost(a, b, strength, lookup)
        cost += self._chatty_area_cost(keys_to_sid)
        return cost

    def _chatty_area_cost(self, keys_to_sid: dict[str, str]) -> float:
        """“爱说话”学生周围必须是异性或“不爱说话”的同学。"""
        if not self.focus_sids or self.w_t <= 0:
            return 0.0
        cost = 0.0
        inside = set(keys_to_sid)
        for sid in self.focus_sids:
            target = self.students[sid]
            seat = next((k for k, v in keys_to_sid.items() if v == sid), None)
            if seat is None:
                seat = self.seat_of_student.get(sid)
            if seat is None:
                continue
            if seat not in inside and not any(
                neighbor in inside for neighbor in self.model.orthogonal.get(seat, [])
            ):
                continue
            for neighbor in self.model.orthogonal.get(seat, []):
                occupant = keys_to_sid.get(neighbor) or self.assignment.get(neighbor)
                if not occupant or occupant == sid:
                    continue
                other = self.students.get(occupant)
                if other is not None and not fits_neighbor(other, target):
                    cost += 80.0 * self.w_t
        return cost

    # -- 优化单个区域 -------------------------------------------------------
    def optimize_area(self, area_id: str, rng: random.Random) -> None:
        keys_all = self.model.area_seats.get(area_id, [])
        keys = [k for k in keys_all if k in self.assignment]
        if len(keys) < 2:
            return

        if len(keys) <= PERMUTATION_LIMIT:
            best = None
            best_cost = float("inf")
            order = list(range(len(keys)))
            rng.shuffle(order)
            seat_order = [keys[i] for i in order]
            members = [self.assignment[k] for k in keys]
            for perm in itertools.permutations(range(len(members))):
                candidate = {seat_order[i]: members[perm[i]] for i in range(len(members))}
                cost = self.area_cost(area_id, candidate)
                if cost < best_cost - 1e-9:
                    best_cost = cost
                    best = candidate
            if best:
                self._apply(best)
            return

        # 座位较多：爬山法
        current = {k: self.assignment[k] for k in keys}
        current_cost = self.area_cost(area_id, current)
        best = dict(current)
        best_cost = current_cost
        for _ in range(6000):
            i, j = rng.sample(range(len(keys)), 2)
            trial = dict(current)
            trial[keys[i]], trial[keys[j]] = trial[keys[j]], trial[keys[i]]
            cost = self.area_cost(area_id, trial)
            if cost < current_cost - 1e-9:
                current, current_cost = trial, cost
                if cost < best_cost:
                    best, best_cost = dict(trial), cost
        self._apply(best)

    def _apply(self, mapping: dict[str, str]) -> None:
        for key, sid in mapping.items():
            old = self.assignment.get(key)
            if old == sid:
                continue
            self.assignment[key] = sid
            self.seat_of_student[sid] = key

    def chatty_violation_areas(self) -> set[str]:
        """返回当前“爱说话”学生周围不合格的座位所在区域。"""
        areas: set[str] = set()
        if not self.focus_sids:
            return areas
        for sid in self.focus_sids:
            seat = self.seat_of_student.get(sid)
            target = self.students.get(sid)
            if seat is None or target is None:
                continue
            for neighbor in self.model.orthogonal.get(seat, []):
                occupant = self.assignment.get(neighbor)
                if not occupant or occupant == sid:
                    continue
                other = self.students.get(occupant)
                if other is not None and not fits_neighbor(other, target):
                    areas.add(self.model.seats[seat].area_id or "")
                    areas.add(self.model.seats[neighbor].area_id or "")
        areas.discard("")
        return areas


def solve(
    layout: Layout,
    groups: list[Group],
    area_group: dict[str, int],
    students: list[Student],
    mapping: dict[str, ExamRow],
    relations: list[Relation],
    prefs: Preferences,
    seed: int | None = None,
    focus_sids: set[str] | None = None,
) -> SeatSolution:
    rng = random.Random(seed)
    model = SeatingModel(layout)
    students_by_id = {s.sid: s for s in students}
    focus = (
        set(focus_sids)
        if focus_sids is not None
        else {s.sid for s in students if s.talk == TALK_CHATTY}
    )
    group_by_gid = {g.gid: g for g in groups}
    assignment: dict[str, str] = {}
    warnings: list[str] = []

    for area in layout.areas:
        seats = model.area_seats.get(area.aid, [])
        if not seats:
            continue
        gid = area_group.get(area.aid)
        group = group_by_gid.get(gid) if gid is not None else None
        if group is None:
            warnings.append(f"「{area.name}」还没有指定小组，座位会空着")
            continue
        members = list(group.members)
        if len(members) > len(seats):
            warnings.append(f"「{area.name}」只有 {len(seats)} 个座位，第 {group.gid} 组多出的 {len(members) - len(seats)} 人没有位置")
            members = members[: len(seats)]
        elif len(members) < len(seats):
            warnings.append(f"「{area.name}」有 {len(seats)} 个座位，第 {group.gid} 组只有 {len(members)} 人，会空出 {len(seats) - len(members)} 个位置")
        # 初始：矮的坐靠近黑板的座位
        jitter = lambda s: s.height_score + rng.random() * 0.35
        members.sort(key=jitter)
        for seat_key, student in zip(seats, members):
            assignment[seat_key] = student.sid

    optimizer = _Optimizer(model, assignment, students_by_id, relations, prefs, focus)
    order = [aid for aid in model.area_seats if model.area_seats[aid]]
    for _ in range(4):
        rng.shuffle(order)
        for area_id in order:
            optimizer.optimize_area(area_id, rng)
    # 针对“爱说话”学生的遗留冲突，反复重排相关区域，避免区域之间的先后顺序互相干扰
    for _ in range(8):
        areas = optimizer.chatty_violation_areas()
        if not areas:
            break
        for area_id in areas:
            optimizer.optimize_area(area_id, rng)
    assignment = optimizer.assignment

    analysis = analyze(
        model, assignment, students_by_id, relations, prefs, focus_sids=focus
    )
    warnings.extend(analysis.group_notes)
    return SeatSolution(assignment=assignment, warnings=warnings, analysis=analysis)


# --------------------------------------------------------------------------- #
# 分析 / 冲突检测
# --------------------------------------------------------------------------- #


def analyze(
    model: SeatingModel,
    assignment: dict[str, str],
    students: dict[str, Student],
    relations: list[Relation],
    prefs: Preferences,
    focus_sids: set[str] | None = None,
) -> SeatAnalysis:
    analysis = SeatAnalysis()
    analysis.seated = sum(1 for sid in assignment.values() if sid in students)
    seated_ids = {sid for sid in assignment.values() if sid in students}
    analysis.unseated = [sid for sid in students if sid not in seated_ids]
    seat_of = {sid: key for key, sid in assignment.items() if sid in students}
    focus = (
        set(focus_sids)
        if focus_sids is not None
        else {sid for sid, s in students.items() if s.talk == TALK_CHATTY}
    )

    flags: dict[str, list[str]] = {}

    # 身高：区域内的相对顺序是否符合“前矮后高”
    ok = 0
    total = 0
    for area_id, keys in model.area_seats.items():
        present = [k for k in keys if assignment.get(k) in students]
        if len(present) < 2:
            continue
        members = [assignment[k] for k in present]
        by_height = sorted(range(len(members)), key=lambda i: students[members[i]].height_score)
        rank_of = {members[idx]: rank for rank, idx in enumerate(by_height)}
        for position, sid in enumerate(members):
            total += 1
            if abs(position - rank_of[sid]) <= 1:
                ok += 1
    analysis.height_ok = ok / total if total else 0.0

    # 同桌性别
    pairs_satisfied = 0
    pairs_total = 0
    for key_a, key_b in model.desk_pairs:
        sid_a = assignment.get(key_a)
        sid_b = assignment.get(key_b)
        if not sid_a or not sid_b or sid_a not in students or sid_b not in students:
            continue
        pairs_total += 1
        same = students[sid_a].gender == students[sid_b].gender
        if prefs.gender_mode == GENDER_MODE_MIXED and same:
            analysis.conflicts.append(
                Conflict(
                    kind="同桌",
                    text=f"{students[sid_a].name} 与 {students[sid_b].name} 同性同桌",
                    seats=[key_a, key_b],
                )
            )
            flags.setdefault(key_a, []).append("同性同桌")
            flags.setdefault(key_b, []).append("同性同桌")
        elif prefs.gender_mode == GENDER_MODE_SAME and not same:
            analysis.conflicts.append(
                Conflict(
                    kind="同桌",
                    text=f"{students[sid_a].name} 与 {students[sid_b].name} 异性同桌",
                    seats=[key_a, key_b],
                )
            )
            flags.setdefault(key_a, []).append("异性同桌")
            flags.setdefault(key_b, []).append("异性同桌")
        else:
            pairs_satisfied += 1
    analysis.gender_ok = (pairs_satisfied / pairs_total) if pairs_total else None

    # 关系
    for relation in relations:
        if relation.a == relation.b:
            continue
        if relation.a not in students or relation.b not in students:
            continue
        seat_a = seat_of.get(relation.a)
        seat_b = seat_of.get(relation.b)
        if not seat_a or not seat_b:
            continue
        gap = model.distance_between(seat_a, seat_b)
        adjacent = gap <= 1
        same_area = model.area_of_seat(seat_a) == model.area_of_seat(seat_b)
        if relation.strength == REL_MUST:
            if same_area or adjacent:
                analysis.must_conflicts += 1
                analysis.conflicts.append(
                    Conflict(
                        kind="关系",
                        text=f"{students[relation.a].name} 与 {students[relation.b].name} 应当分开"
                        + ("（同一区域）" if same_area else "（相邻）"),
                        seats=[seat_a, seat_b],
                        severity="hard",
                    )
                )
                flags.setdefault(seat_a, []).append("必须分开")
                flags.setdefault(seat_b, []).append("必须分开")
        elif adjacent:
            analysis.prefer_conflicts += 1
            analysis.conflicts.append(
                Conflict(
                    kind="关系",
                    text=f"{students[relation.a].name} 与 {students[relation.b].name} 坐得太近",
                    seats=[seat_a, seat_b],
                )
            )
            flags.setdefault(seat_a, []).append("尽量分开")
            flags.setdefault(seat_b, []).append("尽量分开")

    # 爱说话学生：周围一圈必须是异性或不爱说话的同学
    focus_list = [sid for sid in focus if sid in students and seat_of.get(sid)]
    analysis.chatty_total = len(focus_list)
    chatty_ok = 0
    for sid in focus_list:
        target = students[sid]
        seat = seat_of[sid]
        bad: list[tuple[str, Student]] = []
        for neighbor in model.orthogonal.get(seat, []):
            occupant = assignment.get(neighbor)
            if not occupant or occupant == sid:
                continue
            other = students.get(occupant)
            if other is not None and not fits_neighbor(other, target):
                bad.append((neighbor, other))
        if bad:
            for neighbor, other in bad:
                analysis.conflicts.append(
                    Conflict(
                        kind="爱说话",
                        text=f"{target.name} 周围有 {other.name}（同性别且不属于“不爱说话”）",
                        seats=[seat, neighbor],
                    )
                )
                flags.setdefault(seat, []).append("周围需调整")
                flags.setdefault(neighbor, []).append("爱说话旁边")
            analysis.group_notes.append(
                f"「{target.name}」周围还有 {len(bad)} 个座位不理想，可点“优化爱说话周围”或手动拖拽"
            )
        else:
            chatty_ok += 1
    analysis.chatty_ok = chatty_ok

    # 组的位置与身高是否匹配
    for area_id, keys in model.area_seats.items():
        present = [k for k in keys if assignment.get(k) in students]
        if not present:
            continue
        heights = [students[assignment[k]].height_score for k in present if assignment[k] in students]
        if not heights:
            continue
        avg_height = sum(heights) / len(heights)
        avg_dn = sum(model.seats[k].dn for k in present) / len(present)
        area_name = next((a.name for a in model.layout.areas if a.aid == area_id), "区域")
        if avg_height >= 1.35 and avg_dn <= 0.35:
            analysis.group_notes.append(f"「{area_name}」的学生整体偏高，却安排在靠前的区域，建议往后调")
        elif avg_height <= 0.65 and avg_dn >= 0.65:
            analysis.group_notes.append(f"「{area_name}」的学生整体偏矮，却安排在靠后的区域，建议往前调")

    analysis.seat_flags = flags
    analysis.conflicts.sort(key=lambda c: (c.severity != "hard", c.kind))
    return analysis


def reassign(
    model: SeatingModel,
    assignment: dict[str, str],
    seat_a: str,
    seat_b: str,
) -> dict[str, str]:
    """交换两个座位上的学生，返回新的 assignment（用于界面拖拽）。"""
    result = dict(assignment)
    result[seat_a], result[seat_b] = result.get(seat_b, ""), result.get(seat_a, "")
    result = {k: v for k, v in result.items() if v}
    return result
