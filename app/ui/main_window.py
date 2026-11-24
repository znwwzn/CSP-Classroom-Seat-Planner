"""主窗口：侧边导航 + 页面堆栈 + 流程串联。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import storage
from . import theme
from .context import AppContext
from .pages.history_page import HistoryPage
from .pages.layout_page import LayoutPage
from .pages.result_page import ResultPage
from .pages.seat_page import SeatPage
from .pages.students_page import StudentsPage
from .widgets import SaveBadge


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("班级排座助手")
        self.setWindowIcon(theme.app_icon())
        self.resize(1440, 900)
        self.setMinimumSize(1120, 700)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 22, 26, 18)
        content_layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.students_page = StudentsPage(context)
        self.layout_page = LayoutPage(context)
        self.seat_page = SeatPage(context)
        self.result_page = ResultPage(context)
        self.history_page = HistoryPage(context)
        self.pages = [
            self.students_page,
            self.layout_page,
            self.seat_page,
            self.result_page,
            self.history_page,
        ]
        for page in self.pages:
            self.stack.addWidget(page)
        content_layout.addWidget(self.stack, 1)
        layout.addWidget(content, 1)

        self._connect()

        self.result_page.canvas.set_layout(context.layout)
        self._navigate(0)

    # ------------------------------------------------------------------ #
    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(232)
        col = QVBoxLayout(sidebar)
        col.setContentsMargins(16, 20, 16, 16)
        col.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = QLabel("座")
        mark.setObjectName("BrandMark")
        mark.setFixedSize(40, 40)
        mark.setAlignment(Qt.AlignCenter)
        brand.addWidget(mark)
        names = QVBoxLayout()
        names.setSpacing(0)
        name = QLabel("班级排座助手")
        name.setObjectName("BrandName")
        names.addWidget(name)
        sub = QLabel("SEAT PLANNER")
        sub.setObjectName("BrandSub")
        names.addWidget(sub)
        brand.addLayout(names)
        brand.addStretch(1)
        col.addLayout(brand)
        col.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        entries = [
            ("学生名单", "students"),
            ("教室布局", "layout"),
            ("开始排座", "seat"),
            ("排座结果", "check"),
            ("历史记录", "history"),
        ]
        for index, (text, icon) in enumerate(entries):
            button = QPushButton(text)
            button.setObjectName("Nav")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setIcon(theme.make_icon(icon, theme.MUTED, 18))
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(lambda _=False, i=index: self._navigate(i))
            self.nav_group.addButton(button, index)
            col.addWidget(button)
            self.nav_buttons.append(button)
        self.nav_buttons[3].setVisible(False)

        col.addStretch(1)

        save_row = QHBoxLayout()
        save_row.setContentsMargins(2, 0, 2, 0)
        self.save_badge = SaveBadge()
        save_row.addWidget(self.save_badge)
        save_row.addStretch(1)
        col.addLayout(save_row)

        data_button = QPushButton("打开数据文件夹")
        data_button.setObjectName("LinkBtn")
        data_button.setCursor(Qt.PointingHandCursor)
        data_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(storage.data_dir())))
        )
        col.addWidget(data_button, alignment=Qt.AlignLeft)

        version = QLabel("v0.9　·　所有数据保存在本地")
        version.setObjectName("Faint")
        col.addWidget(version)
        return sidebar

    # ------------------------------------------------------------------ #
    def _connect(self) -> None:
        self.students_page.nextRequested.connect(lambda: self._navigate(1))
        self.layout_page.nextRequested.connect(lambda: self._navigate(2))
        self.seat_page.generated.connect(self._on_generated)
        self.result_page.backRequested.connect(lambda: self._navigate(2))
        self.result_page.regenerateRequested.connect(self._regenerate)
        self.history_page.viewRequested.connect(self._view_record)
        self.context.saved.connect(self._on_saved)

    # ------------------------------------------------------------------ #
    def _navigate(self, index: int) -> None:
        if index == 3 and self.context.runtime.record is None:
            return
        if not (0 <= index < len(self.pages)):
            return
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        page = self.pages[index]
        if hasattr(page, "on_show"):
            page.on_show()  # type: ignore[attr-defined]

    def _on_saved(self, ok: bool) -> None:
        if ok:
            self.save_badge.flash()
        else:
            self.save_badge.error()

    def _on_generated(self, record) -> None:
        try:
            storage.append_history(record)
        except OSError:
            pass
        self.result_page.load(record)
        self.nav_buttons[3].setVisible(True)
        self._navigate(3)

    def _regenerate(self) -> None:
        self.context.runtime.generation += 1
        self.seat_page.generate()

    def _view_record(self, record) -> None:
        self.result_page.load(record, readonly=True)
        self.nav_buttons[3].setVisible(True)
        self._navigate(3)

    # ------------------------------------------------------------------ #
    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.context.save()
        super().closeEvent(event)
