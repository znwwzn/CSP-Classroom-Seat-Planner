"""爱说话功能的界面流程测试：勾选名单 → 生成 → 优化周围 → 导出。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.core import storage  # noqa: E402
from app.core.excel_export import export_plan  # noqa: E402
from app.core.excel_import import auto_import, match_to_students  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.context import AppContext  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.pages import result_page as result_module  # noqa: E402
from tools.demo_data import SAMPLE_XLSX, build_state  # noqa: E402
from app.core.models import TALK_CHATTY  # noqa: E402


def main() -> int:
    data = ROOT / "data" / "_chatty_ui"
    shutil.rmtree(data, ignore_errors=True)
    os.environ["SEATPLANNER_DATA"] = str(data)
    data.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    theme.apply_theme(app)

    state = build_state()
    for index in (2, 10, 18, 26, 34):
        state.students[index].talk = TALK_CHATTY

    context = AppContext(state)
    window = MainWindow(context)
    window.resize(1440, 900)
    window.show()
    app.processEvents()

    sample = SAMPLE_XLSX
    result = auto_import(sample)
    context.runtime.import_result = result
    context.runtime.match = match_to_students(state.students, result)

    window._navigate(2)
    app.processEvents()
    page = window.seat_page
    print("关照名单勾选框：", len(page.focus_checks))
    assert len(page.focus_checks) == 5
    print("默认全选：", page.focus_pill.text())
    assert len(context.runtime.focus_sids) == 5

    # 取消勾选一个，生成时应只关照剩下 4 个
    victim = list(page.focus_checks)[0]
    page.focus_checks[victim].setChecked(False)
    app.processEvents()
    assert context.runtime.focus_dirty
    assert len(context.runtime.focus_sids) == 4
    print("取消一个后：", page.focus_pill.text())

    page._apply_focus()
    app.processEvents()
    assert not context.runtime.focus_dirty
    assert context.runtime.plan is not None
    print("应用并重新分组后，关照名单仍为：", len(context.runtime.focus_sids))

    record = page.generate()
    assert record is not None
    print("记录里的关照名单：", len(record.focus_sids))
    assert len(record.focus_sids) == 4
    assert record.stats["chatty_total"] == 4
    print("生成后合格：", record.stats["chatty_ok"], "/", record.stats["chatty_total"])

    app.processEvents()
    result_page = window.result_page
    students = {s.sid: s for s in record.students}
    before = len(result_page._chatty_bad(record.seats, students))
    print("优化前不合格邻座：", before)
    result_module.QMessageBox.information = staticmethod(lambda *args, **kwargs: QMessageBox.Ok)
    result_page._optimize_chatty()
    app.processEvents()
    after = len(result_page._chatty_bad(record.seats, students))
    print("优化后不合格邻座：", after)
    assert after <= before

    out = data / "导出.xlsx"
    export_plan(record, out)
    wb = load_workbook(out)
    header = [c.value for c in wb["名单"][1]]
    print("名单表头：", header)
    assert "爱说话" in header
    values = [row[5] for row in wb["名单"].iter_rows(min_row=2, max_row=4, values_only=True)]
    print("爱说话列示例：", values)
    print("通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
