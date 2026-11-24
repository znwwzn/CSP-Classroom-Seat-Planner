"""回归测试：名单里修改性别/身高后，内存、存档、重新加载是否一致。"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QComboBox  # noqa: E402

from app.core import storage  # noqa: E402
from app.core.models import AppState  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.context import AppContext  # noqa: E402
from app.ui.dialogs import write_roster_template  # noqa: E402
from app.ui.pages.students_page import StudentsPage, read_roster  # noqa: E402


def commit_with_delegate(page: StudentsPage, row: int, column: int, value: str) -> None:
    delegate = page.table.itemDelegateForColumn(column)
    combo = QComboBox()
    combo.addItem(value, value)
    combo.setCurrentIndex(0)
    delegate.setModelData(combo, page.table.model(), page.table.model().index(row, column))


def main() -> int:
    data_dir = ROOT / "data" / "_bugtest"
    shutil.rmtree(data_dir, ignore_errors=True)
    os.environ["SEATPLANNER_DATA"] = str(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    theme.apply_theme(app)

    template = data_dir / "名单.xlsx"
    write_roster_template(template)
    students = read_roster(template)
    print("模板读入：", [(s.name, s.gender, s.height) for s in students])
    assert [s.gender for s in students] == ["男", "女", "男"]
    assert [s.height for s in students] == ["中", "低", "高"]
    assert [s.talk for s in students] == ["一般", "爱说话", "不爱说话"]

    state = AppState(class_name="测试班", students=students)
    context = AppContext(state)
    page = StudentsPage(context)
    page.show()
    app.processEvents()

    # 1) 下拉选择（delegate）
    commit_with_delegate(page, 0, 1, "女")
    commit_with_delegate(page, 0, 2, "低")
    app.processEvents()
    print("delegate 后：", [(s.gender, s.height) for s in state.students])

    # 2) 直接输入文字
    page.table.item(1, 1).setText("男")
    page.table.item(1, 2).setText("高")
    app.processEvents()
    print("输入后：", [(s.gender, s.height) for s in state.students])

    # 3) 非法值应被还原
    page.table.item(1, 1).setText("X")
    app.processEvents()
    print("非法值后：", page.table.item(1, 1).text(), state.students[1].gender)

    saved = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))["students"]
    print("存档：", [(s["name"], s["gender"], s["height"]) for s in saved])

    reloaded = storage.load_state()
    print("重新加载：", [(s.name, s.gender, s.height) for s in reloaded.students])

    assert [s.gender for s in reloaded.students] == ["女", "男", "男"], reloaded.students
    assert [s.height for s in reloaded.students] == ["低", "高", "高"], reloaded.students
    print("通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
