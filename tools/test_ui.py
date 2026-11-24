"""界面流程冒烟测试（不弹窗、无需显示器）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core import storage  # noqa: E402
from app.core.excel_export import export_plan  # noqa: E402
from app.core.excel_import import auto_import, match_to_students  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.context import AppContext  # noqa: E402
from app.ui.dialogs import RelationsDialog, ScoreMappingDialog, write_roster_template  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.pages.students_page import read_roster  # noqa: E402
from tools.demo_data import SAMPLE_XLSX, build_state  # noqa: E402


def test_relations(app) -> None:
    state = build_state()
    dialog = RelationsDialog(state.students, [], None)
    dialog.add_row()
    dialog.table.item(0, 0).setData(Qt.UserRole, state.students[0].sid)
    dialog.table.item(0, 1).setData(Qt.UserRole, state.students[1].sid)
    dialog.table.item(0, 2).setData(Qt.UserRole, "必须分开")
    dialog.table.item(0, 3).setText("情侣")
    dialog._on_accept()
    assert len(dialog.relations) == 1, dialog.relations
    assert dialog.relations[0].strength == "必须分开"
    print("[关系对话框] ok")


def _workdir() -> Path:
    path = ROOT / "data" / "_uitest"
    if path.exists():
        import shutil

        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_template(app) -> None:
    tmp = _workdir()
    path = tmp / "模板.xlsx"
    write_roster_template(path)
    students = read_roster(path)
    assert len(students) == 3
    assert students[0].name == "张三"
    assert students[0].height == "中"
    print("[名单模板] ok", [s.name for s in students])


def test_mapping_dialog(app) -> None:
    dialog = ScoreMappingDialog(SAMPLE_XLSX, None)
    mapping = dialog.mapping()
    assert mapping["sheet"] and mapping["name_col"] is not None
    print("[手动指定列] ok", mapping)


def test_export_and_history(app) -> None:
    state = build_state()
    context = AppContext(state)
    window = MainWindow(context)
    window.setAttribute(Qt.WA_DontShowOnScreen, True)
    window.resize(1440, 900)
    window.show()
    app.processEvents()

    sample = SAMPLE_XLSX
    result = auto_import(sample)
    context.runtime.import_result = result
    context.runtime.match = match_to_students(state.students, result)
    window._navigate(2)
    app.processEvents()
    record = window.seat_page.generate()
    assert record is not None
    app.processEvents()

    tmp = _workdir()
    path = tmp / "导出.xlsx"
    export_plan(record, path)
    assert path.exists() and path.stat().st_size > 5000
    print("[导出] ok", path.stat().st_size, "字节")
    # 历史记录查看
    window._view_record(record)
    app.processEvents()
    assert window.result_page.record is record
    assert window.result_page.readonly
    print("[历史查看] ok", record.created_at)

    # 拖拽换座
    keys = [k for k, v in record.seats.items() if v]
    before = dict(record.seats)
    window.result_page._on_swap(keys[0], keys[1])
    assert record.seats[keys[0]] == before[keys[1]]
    print("[拖拽换座] ok")

    window.result_page._export if False else None
    window.close()


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply_theme(app)
    test_relations(app)
    test_template(app)
    test_mapping_dialog(app)
    test_export_and_history(app)
    print("界面流程全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
