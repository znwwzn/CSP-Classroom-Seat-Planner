"""核心数据模型。

所有配置都以纯 Python 对象表示，便于 JSON 持久化与单元测试。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

GENDERS = ("男", "女")
HEIGHTS = ("低", "中", "高")
HEIGHT_SCORE = {"低": 0.0, "中": 1.0, "高": 2.0}

TALK_QUIET = "不爱说话"
TALK_NORMAL = "一般"
TALK_CHATTY = "爱说话"
TALK_LEVELS = (TALK_QUIET, TALK_NORMAL, TALK_CHATTY)

GENDER_MODE_MIXED = "异性同桌"
GENDER_MODE_SAME = "同性同桌"
GENDER_MODE_FREE = "不限制"
GENDER_MODES = (GENDER_MODE_MIXED, GENDER_MODE_SAME, GENDER_MODE_FREE)

REL_MUST = "必须分开"
REL_PREFER = "尽量分开"
REL_STRENGTHS = (REL_MUST, REL_PREFER)

CELL_EMPTY = "empty"
CELL_DESK = "desk"
CELL_BOARD = "board"
CELL_PODIUM = "podium"
CELL_KINDS = (CELL_DESK, CELL_BOARD, CELL_PODIUM, CELL_EMPTY)
CELL_LABELS = {
    CELL_DESK: "课桌",
    CELL_BOARD: "黑板",
    CELL_PODIUM: "讲台",
    CELL_EMPTY: "过道",
}

AREA_COLORS = (
    "#2F6BFF", "#16A34A", "#F59E0B", "#A855F7", "#EC4899",
    "#0EA5E9", "#65A30D", "#F97316", "#6366F1", "#14B8A6",
    "#0F766E", "#BE123C", "#7C3AED", "#B45309",
)


def new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def cell_key(row: int, col: int) -> str:
    return f"{row},{col}"


def parse_cell_key(key: str) -> tuple[int, int]:
    row, col = key.split(",")
    return int(row), int(col)


# --------------------------------------------------------------------------- #
# 学生 / 关系
# --------------------------------------------------------------------------- #


@dataclass
class Student:
    sid: str = field(default_factory=lambda: new_id("s"))
    name: str = ""
    gender: str = "男"
    height: str = "中"
    talk: str = TALK_NORMAL
    note: str = ""

    @property
    def height_score(self) -> float:
        return HEIGHT_SCORE.get(self.height, 1.0)

    @property
    def is_chatty(self) -> bool:
        return self.talk == TALK_CHATTY

    @property
    def is_quiet(self) -> bool:
        return self.talk == TALK_QUIET

    def to_dict(self) -> dict[str, Any]:
        return {
            "sid": self.sid,
            "name": self.name,
            "gender": self.gender,
            "height": self.height,
            "talk": self.talk,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Student":
        return cls(
            sid=data.get("sid") or new_id("s"),
            name=data.get("name", ""),
            gender=data.get("gender", "男"),
            height=data.get("height", "中"),
            talk=data.get("talk", TALK_NORMAL),
            note=data.get("note", ""),
        )


def fits_neighbor(neighbor: Student, target: Student) -> bool:
    """作为“爱说话”学生的邻居是否合格：异性，或不爱说话。"""
    return neighbor.gender != target.gender or neighbor.talk == TALK_QUIET


@dataclass
class Relation:
    """两名学生之间的特殊关系（情侣、好友、闹矛盾等）。"""

    rid: str = field(default_factory=lambda: new_id("r"))
    a: str = ""  # 学生 sid
    b: str = ""  # 学生 sid
    strength: str = REL_MUST
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rid": self.rid,
            "a": self.a,
            "b": self.b,
            "strength": self.strength,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Relation":
        return cls(
            rid=data.get("rid") or new_id("r"),
            a=data.get("a", ""),
            b=data.get("b", ""),
            strength=data.get("strength", REL_MUST),
            note=data.get("note", ""),
        )


# --------------------------------------------------------------------------- #
# 教室布局
# --------------------------------------------------------------------------- #


@dataclass
class Area:
    """一组课桌，排座时一个区域坐一个学生小组。"""

    aid: str = field(default_factory=lambda: new_id("a"))
    name: str = "区域"
    color: int = 0
    cells: list[list[int]] = field(default_factory=list)

    # -- 便捷访问 -----------------------------------------------------------
    @property
    def cell_tuples(self) -> list[tuple[int, int]]:
        return [tuple(c) for c in self.cells]  # type: ignore[misc]

    def contains(self, row: int, col: int) -> bool:
        return any(c[0] == row and c[1] == col for c in self.cells)

    def add(self, row: int, col: int) -> None:
        if not self.contains(row, col):
            self.cells.append([row, col])

    def remove(self, row: int, col: int) -> None:
        self.cells = [c for c in self.cells if not (c[0] == row and c[1] == col)]

    @property
    def color_hex(self) -> str:
        return AREA_COLORS[self.color % len(AREA_COLORS)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "aid": self.aid,
            "name": self.name,
            "color": self.color,
            "cells": [list(c) for c in self.cells],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Area":
        return cls(
            aid=data.get("aid") or new_id("a"),
            name=data.get("name", "区域"),
            color=int(data.get("color", 0)),
            cells=[list(c) for c in data.get("cells", [])],
        )


@dataclass
class Layout:
    rows: int = 6
    cols: int = 8
    cells: dict[str, str] = field(default_factory=dict)  # "r,c" -> CELL_*
    areas: list[Area] = field(default_factory=list)

    # -- 单元格 -------------------------------------------------------------
    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.cols

    def cell(self, row: int, col: int) -> str:
        return self.cells.get(cell_key(row, col), CELL_EMPTY)

    def set_cell(self, row: int, col: int, kind: str) -> None:
        if not self.in_bounds(row, col):
            return
        key = cell_key(row, col)
        if kind == CELL_EMPTY:
            self.cells.pop(key, None)
        else:
            self.cells[key] = kind
        if kind != CELL_DESK:
            self.detach(row, col)

    def desks(self) -> list[tuple[int, int]]:
        out = []
        for key, kind in self.cells.items():
            if kind == CELL_DESK:
                out.append(parse_cell_key(key))
        out.sort(key=lambda rc: (rc[0], rc[1]))
        return out

    def blackboards(self) -> list[tuple[int, int]]:
        return sorted(
            (parse_cell_key(k) for k, v in self.cells.items() if v == CELL_BOARD),
            key=lambda rc: (rc[0], rc[1]),
        )

    def podiums(self) -> list[tuple[int, int]]:
        return sorted(
            (parse_cell_key(k) for k, v in self.cells.items() if v == CELL_PODIUM),
            key=lambda rc: (rc[0], rc[1]),
        )

    # -- 区域 ---------------------------------------------------------------
    def area_of(self, row: int, col: int) -> Area | None:
        for area in self.areas:
            if area.contains(row, col):
                return area
        return None

    def detach(self, row: int, col: int) -> None:
        for area in self.areas:
            area.remove(row, col)

    def assign_to_area(self, area: Area, row: int, col: int) -> None:
        """把课桌加入区域（会先从其他区域摘除）。"""
        if self.cell(row, col) != CELL_DESK:
            return
        self.detach(row, col)
        area.add(row, col)

    def add_area(self, name: str | None = None) -> Area:
        if name is None:
            used = {a.name for a in self.areas}
            index = 1
            while f"区域 {index}" in used:
                index += 1
            name = f"区域 {index}"
        area = Area(name=name, color=len(self.areas))
        self.areas.append(area)
        return area

    def remove_area(self, area: Area) -> None:
        if area in self.areas:
            self.areas.remove(area)

    def seats_of(self, area: Area) -> list[tuple[int, int]]:
        return sorted(
            (tuple(c) for c in area.cells if self.cell(c[0], c[1]) == CELL_DESK),
            key=lambda rc: (rc[0], rc[1]),
        )

    def unassigned_desks(self) -> list[tuple[int, int]]:
        out = []
        for rc in self.desks():
            if self.area_of(*rc) is None:
                out.append(rc)
        return out

    def resize(self, rows: int, cols: int) -> None:
        rows = max(1, int(rows))
        cols = max(1, int(cols))
        kept: dict[str, str] = {}
        for key, kind in self.cells.items():
            r, c = parse_cell_key(key)
            if r < rows and c < cols:
                kept[key] = kind
        self.rows, self.cols = rows, cols
        self.cells = kept
        for area in self.areas:
            area.cells = [c for c in area.cells if c[0] < rows and c[1] < cols]

    def problems(self) -> list[str]:
        """返回布局中阻碍排座的问题描述。"""
        issues: list[str] = []
        desks = self.desks()
        if not desks:
            issues.append("还没有画任何课桌")
        if not self.areas:
            issues.append("还没有创建任何区域")
        loose = self.unassigned_desks()
        if loose:
            issues.append(f"有 {len(loose)} 张课桌不属于任何区域")
        empty_areas = [a.name for a in self.areas if not self.seats_of(a)]
        if empty_areas:
            issues.append("这些区域里没有课桌：" + "、".join(empty_areas))
        if not self.blackboards():
            issues.append("还没有标记黑板（将默认以最上排为前排）")
        return issues

    # -- 序列化 -------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "cells": dict(self.cells),
            "areas": [a.to_dict() for a in self.areas],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Layout":
        return cls(
            rows=int(data.get("rows", 6)),
            cols=int(data.get("cols", 8)),
            cells=dict(data.get("cells", {})),
            areas=[Area.from_dict(a) for a in data.get("areas", [])],
        )


# --------------------------------------------------------------------------- #
# 偏好
# --------------------------------------------------------------------------- #


@dataclass
class Preferences:
    gender_mode: str = GENDER_MODE_MIXED
    height_weight: int = 70
    gender_weight: int = 70
    relation_weight: int = 80
    talk_weight: int = 80

    def to_dict(self) -> dict[str, Any]:
        return {
            "gender_mode": self.gender_mode,
            "height_weight": self.height_weight,
            "gender_weight": self.gender_weight,
            "relation_weight": self.relation_weight,
            "talk_weight": self.talk_weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Preferences":
        return cls(
            gender_mode=data.get("gender_mode", GENDER_MODE_MIXED),
            height_weight=int(data.get("height_weight", 70)),
            gender_weight=int(data.get("gender_weight", 70)),
            relation_weight=int(data.get("relation_weight", 80)),
            talk_weight=int(data.get("talk_weight", 80)),
        )


# --------------------------------------------------------------------------- #
# 总配置
# --------------------------------------------------------------------------- #


@dataclass
class AppState:
    class_name: str = ""
    students: list[Student] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    layout: Layout = field(default_factory=Layout)
    preferences: Preferences = field(default_factory=Preferences)
    last_score_file: str = ""
    version: int = 1

    # -- 查询 ---------------------------------------------------------------
    def student_by_id(self, sid: str) -> Student | None:
        for s in self.students:
            if s.sid == sid:
                return s
        return None

    def relations_of(self, sid: str) -> list[Relation]:
        return [r for r in self.relations if r.a == sid or r.b == sid]

    def counts(self) -> dict[str, int]:
        male = sum(1 for s in self.students if s.gender == "男")
        return {
            "total": len(self.students),
            "male": male,
            "female": len(self.students) - male,
            "low": sum(1 for s in self.students if s.height == "低"),
            "mid": sum(1 for s in self.students if s.height == "中"),
            "high": sum(1 for s in self.students if s.height == "高"),
        }

    # -- 序列化 -------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "class_name": self.class_name,
            "students": [s.to_dict() for s in self.students],
            "relations": [r.to_dict() for r in self.relations],
            "layout": self.layout.to_dict(),
            "preferences": self.preferences.to_dict(),
            "last_score_file": self.last_score_file,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppState":
        return cls(
            class_name=data.get("class_name", ""),
            students=[Student.from_dict(s) for s in data.get("students", [])],
            relations=[Relation.from_dict(r) for r in data.get("relations", [])],
            layout=Layout.from_dict(data.get("layout", {})),
            preferences=Preferences.from_dict(data.get("preferences", {})),
            last_score_file=data.get("last_score_file", ""),
            version=int(data.get("version", 1)),
        )


# --------------------------------------------------------------------------- #
# 成绩与分组
# --------------------------------------------------------------------------- #


@dataclass
class ExamRow:
    """从智学网成绩表中读到的一行。"""

    name: str
    total: float | None
    rank: int | None
    order: int  # 在原表中的行序，用于缺考学生排序
    gender: str | None = None


@dataclass
class Group:
    gid: int
    members: list[Student] = field(default_factory=list)
    capacity: int = 0

    @property
    def title(self) -> str:
        return f"第 {self.gid} 组"


# --------------------------------------------------------------------------- #
# 排座结果（历史记录用，自带快照，可独立渲染/导出）
# --------------------------------------------------------------------------- #


@dataclass
class PlanRecord:
    pid: str = field(default_factory=lambda: new_id("p"))
    created_at: str = ""
    class_name: str = ""
    source_file: str = ""
    students: list[Student] = field(default_factory=list)
    layout: Layout = field(default_factory=Layout)
    preferences: Preferences = field(default_factory=Preferences)
    relations: list["Relation"] = field(default_factory=list)
    scores: dict[str, dict[str, Any]] = field(default_factory=dict)
    groups: list[dict[str, Any]] = field(default_factory=list)
    area_group: dict[str, int] = field(default_factory=dict)
    seats: dict[str, str] = field(default_factory=dict)
    focus_sids: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def student_by_id(self, sid: str) -> Student | None:
        for s in self.students:
            if s.sid == sid:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "created_at": self.created_at,
            "class_name": self.class_name,
            "source_file": self.source_file,
            "students": [s.to_dict() for s in self.students],
            "layout": self.layout.to_dict(),
            "preferences": self.preferences.to_dict(),
            "relations": [r.to_dict() for r in self.relations],
            "scores": self.scores,
            "groups": self.groups,
            "area_group": self.area_group,
            "seats": self.seats,
            "focus_sids": self.focus_sids,
            "stats": self.stats,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanRecord":
        return cls(
            pid=data.get("pid") or new_id("p"),
            created_at=data.get("created_at", ""),
            class_name=data.get("class_name", ""),
            source_file=data.get("source_file", ""),
            students=[Student.from_dict(s) for s in data.get("students", [])],
            layout=Layout.from_dict(data.get("layout", {})),
            preferences=Preferences.from_dict(data.get("preferences", {})),
            relations=[Relation.from_dict(r) for r in data.get("relations", [])],
            scores=data.get("scores", {}),
            groups=data.get("groups", []),
            area_group=data.get("area_group", {}),
            seats=data.get("seats", {}),
            focus_sids=data.get("focus_sids", []),
            stats=data.get("stats", {}),
        )
