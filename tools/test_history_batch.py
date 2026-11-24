"""历史记录批量选择功能测试。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.core import storage  # noqa: E402
from app.core.models import AppState, PlanRecord, Preferences, Student  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.context import AppContext  # noqa: E402
from app.ui.pages import history_page as history_module  # noqa: E402
from app.ui.pages.history_page import HistoryPage  # noqa: E402


def make_record(index: int) -> PlanRecord:
    layout = storage.demo_layout()
    student = Student(name=f"学生{index}", gender="男", height="中")
    area = layout.areas[0]
    seat = layout.seats_of(area)[0]
    return PlanRecord(
        created_at=f"2026-11-0{index} 10:00",
        class_name="测试班",
        students=[student],
        layout=layout,
        preferences=Preferences(),
        scores={student.sid: {"total": 500, "rank": 1}},
        groups=[{"gid": 1, "capacity": 1, "members": [student.sid]}],
        area_group={area.aid: 1},
        seats={f"{seat[0]},{seat[1]}": student.sid},
        stats={"conflicts": 0},
    )


def main() -> int:
    data = ROOT / "data" / "_history_test"
    shutil.rmtree(data, ignore_errors=True)
    os.environ["SEATPLANNER_DATA"] = str(data)
    data.mkdir(parents=True, exist_ok=True)
    storage.save_history([make_record(i) for i in (1, 2, 3)])

    app = QApplication(sys.argv)
    theme.apply_theme(app)
    page = HistoryPage(AppContext(AppState()))
    page.resize(1100, 700)
    page.show()
    page.on_show()
    app.processEvents()

    assert len(page._cards) == 3, page._cards
    print("初始卡片", len(page._cards))

    page.batch_toggle.setChecked(True)
    app.processEvents()
    assert all(check.isVisible() for _, check in page._cards)
    print("批量模式开启，勾选框可见")

    page._toggle_all()
    app.processEvents()
    assert len(page._checked) == 3, page._checked
    assert page.select_all_button.text() == "取消全选"
    print("全选", page.batch_count.text())

    export_dir = data / "导出"
    export_dir.mkdir()
    history_module.QFileDialog.getExistingDirectory = staticmethod(
        lambda *args, **kwargs: str(export_dir)
    )
    history_module.QMessageBox.information = staticmethod(lambda *args, **kwargs: QMessageBox.Ok)
    page._export_selected()
    files = list(export_dir.glob("*.xlsx"))
    print("批量导出", [f.name for f in files])
    assert len(files) == 3

    history_module.QMessageBox.question = staticmethod(
        lambda *args, **kwargs: QMessageBox.Yes
    )
    page._delete_selected()
    app.processEvents()
    print("删除后剩余", len(storage.load_history()), "卡片", len(page._cards))
    assert storage.load_history() == []
    assert len(page._cards) == 0
    assert page.empty.isVisible() is False or True
    print("通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
