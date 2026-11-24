"""虚构的演示数据。

所有姓名、成绩均为随机生成的假数据，仅用于测试、截图和示例，
不包含任何真实学生或班级信息。
"""

from __future__ import annotations

from pathlib import Path

from app.core.models import (
    CELL_BOARD,
    CELL_DESK,
    REL_MUST,
    REL_PREFER,
    TALK_CHATTY,
    TALK_NORMAL,
    TALK_QUIET,
    AppState,
    ExamRow,
    Layout,
    Relation,
    Student,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_XLSX = ROOT / "samples" / "示例成绩表.xlsx"

DEMO_CLASS = "示例班级"
CHATTY_INDEXES = (2, 10, 18, 26, 34)
QUIET_INDEXES = (5, 13, 21, 29, 37)


def make_layout(rows_of_desks: int = 8, cols: int = 8) -> Layout:
    """48 个座位、12 个 4 人区域的示例教室。"""
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


def build_students(count: int = 48) -> list[Student]:
    students: list[Student] = []
    for index in range(count):
        talk = TALK_NORMAL
        if index in CHATTY_INDEXES:
            talk = TALK_CHATTY
        elif index in QUIET_INDEXES:
            talk = TALK_QUIET
        students.append(
            Student(
                name=f"学生{index + 1:02d}",
                gender="男" if index % 2 == 0 else "女",
                height=["低", "中", "高"][index % 3],
                talk=talk,
            )
        )
    return students


def build_mapping(students: list[Student]) -> dict[str, ExamRow]:
    mapping: dict[str, ExamRow] = {}
    for index, student in enumerate(students):
        mapping[student.sid] = ExamRow(
            name=student.name,
            total=620.0 - index * 4.0,
            rank=index + 1,
            order=index,
        )
    return mapping


def build_relations(students: list[Student]) -> list[Relation]:
    return [
        Relation(a=students[0].sid, b=students[1].sid, strength=REL_MUST, note="示例：情侣"),
        Relation(a=students[2].sid, b=students[3].sid, strength=REL_PREFER, note="示例：好友"),
        Relation(a=students[4].sid, b=students[5].sid, strength=REL_PREFER, note="示例：好友"),
    ]


def build_state() -> AppState:
    students = build_students()
    return AppState(
        class_name=DEMO_CLASS,
        students=students,
        relations=build_relations(students),
        layout=make_layout(),
    )
