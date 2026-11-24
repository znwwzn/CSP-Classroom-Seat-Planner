"""生成 README 用的匿名界面截图。

所有姓名、成绩均来自 tools/demo_data.py 的虚构数据。
运行：python -m tools.capture_screens
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from app.core.excel_import import auto_import, match_to_students  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.context import AppContext  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from tools.demo_data import SAMPLE_XLSX, build_state  # noqa: E402
from tools.make_sample import main as make_sample  # noqa: E402

OUT = ROOT / "docs" / "screenshots"


def main() -> int:
    if not SAMPLE_XLSX.exists():
        make_sample()

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    data = ROOT / "data" / "_screens"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True, exist_ok=True)
    os.environ["SEATPLANNER_DATA"] = str(data)

    app = QApplication(sys.argv)
    theme.apply_theme(app)

    state = build_state()
    context = AppContext(state)
    window = MainWindow(context)
    window.setAttribute(Qt.WA_DontShowOnScreen, True)
    window.resize(1440, 900)
    window.show()
    app.processEvents()

    def settle(times: int = 10) -> None:
        for _ in range(times):
            app.processEvents()

    def shot(name: str) -> None:
        settle()
        path = OUT / f"{name}.png"
        window.grab().save(str(path))
        print("saved", path.name)

    shot("students")
    window._navigate(1)
    shot("layout")

    result = auto_import(SAMPLE_XLSX)
    context.runtime.import_result = result
    context.runtime.match = match_to_students(state.students, result)
    window._navigate(2)
    page = window.seat_page
    scroll = page.findChild(QScrollArea)
    settle()
    scroll.verticalScrollBar().setValue(0)
    shot("seat")

    page.generate()
    settle(14)
    shot("result")

    for _ in range(2):
        context.runtime.generation += 1
        page.generate()
    settle(14)
    window._navigate(4)
    shot("history")

    shutil.rmtree(data, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
