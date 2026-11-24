"""程序入口。"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from . import __version__
from .core import storage
from .ui import theme
from .ui.context import AppContext
from .ui.main_window import MainWindow


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("班级排座助手")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("SeatPlanner")
    app.setWindowIcon(theme.app_icon())
    theme.apply_theme(app)

    state = storage.load_state()
    context = AppContext(state)
    window = MainWindow(context)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
