"""教室布局页：画课桌、黑板、讲台，并把课桌分到区域。"""

from __future__ import annotations

import math

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.models import (
    CELL_BOARD,
    CELL_DESK,
    CELL_EMPTY,
    Area,
    Layout,
)
from .. import theme
from ..context import AppContext
from ..layout_canvas import (
    BRUSH_BOARD,
    BRUSH_DESK,
    BRUSH_ERASE,
    BRUSH_PODIUM,
    LayoutCanvas,
)
from ..widgets import Card, HLine, PageHeader


def _color_icon(color: str, size: int = 12) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(0, 0, size, size, 3, 3)
    p.end()
    return QIcon(pix)


def quick_layout(student_count: int, per_row: int = 6) -> Layout:
    """按人数快速铺一个规整教室：两人一排，两排一区。"""
    per_row = max(2, min(8, per_row))
    pairs = max(1, per_row // 2)
    desk_cols: list[int] = []
    for pair in range(pairs):
        desk_cols.extend([pair * 3, pair * 3 + 1])
    cols = max(desk_cols) + 1
    rows = max(1, math.ceil(student_count / per_row))
    layout = Layout(rows=rows + 1, cols=cols)
    for c in range(cols):
        layout.set_cell(0, c, CELL_BOARD)
    remaining = student_count
    for row in range(1, rows + 1):
        for col in desk_cols:
            if remaining <= 0:
                break
            layout.set_cell(row, col, CELL_DESK)
            remaining -= 1

    seat_rows = list(range(1, rows + 1))
    for band_start in range(0, len(seat_rows), 2):
        band = seat_rows[band_start : band_start + 2]
        for pair in range(pairs):
            cols_pair = desk_cols[pair * 2 : pair * 2 + 2]
            cells = [
                (r, c)
                for r in band
                for c in cols_pair
                if layout.cell(r, c) == CELL_DESK
            ]
            if cells:
                area = layout.add_area()
                for r, c in cells:
                    layout.assign_to_area(area, r, c)
    return layout


class LayoutPage(QWidget):
    nextRequested = Signal()

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._current_area_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        self.header = PageHeader(
            "教室布局",
            "先画黑板和课桌，再选中区域把课桌划进小组；区域数量 = 小组数量。",
        )
        undo_button = QPushButton("撤销")
        undo_button.setObjectName("Ghost")
        undo_button.setCursor(Qt.PointingHandCursor)
        undo_button.clicked.connect(self._undo)
        self.header.add_action(undo_button)

        next_button = QPushButton("下一步：开始排座  →")
        next_button.setObjectName("Primary")
        next_button.setCursor(Qt.PointingHandCursor)
        next_button.clicked.connect(self.nextRequested.emit)
        self.header.add_action(next_button)
        root.addWidget(self.header)

        body = QHBoxLayout()
        body.setSpacing(16)

        # -- 画布 -----------------------------------------------------------
        canvas_card = Card(padding=14, spacing=10)
        self.canvas = LayoutCanvas(context.layout)
        self.canvas.setObjectName("Canvas")
        self.canvas.changed.connect(self._on_canvas_changed)
        self.canvas.hoverInfo.connect(self._on_hover)
        canvas_card.body.addWidget(self.canvas, 1)

        footer = QHBoxLayout()
        self.hover_label = QLabel("拖动鼠标即可绘制；右上角可切换画笔")
        self.hover_label.setObjectName("Faint")
        footer.addWidget(self.hover_label, 1)
        legend = QHBoxLayout()
        legend.setSpacing(10)
        for color, text in ((theme.TEXT, "黑板"), ("#EEF2FA", "讲台"), ("#FFFFFF", "课桌")):
            block = QLabel()
            block.setFixedSize(10, 10)
            block.setStyleSheet(
                f"background:{color}; border:1px solid {theme.BORDER}; border-radius:3px;"
            )
            legend.addWidget(block)
            label = QLabel(text)
            label.setObjectName("Faint")
            legend.addWidget(label)
        footer.addLayout(legend)
        canvas_card.body.addLayout(footer)
        body.addWidget(canvas_card, 1)

        # -- 右侧工具 -------------------------------------------------------
        side = QWidget()
        side.setFixedWidth(306)
        side_col = QVBoxLayout(side)
        side_col.setContentsMargins(0, 0, 0, 0)
        side_col.setSpacing(12)

        size_card = Card(padding=16, spacing=10)
        title = QLabel("画布尺寸")
        title.setObjectName("CardTitle")
        size_card.body.addWidget(title)
        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 20)
        self.rows_spin.setValue(context.layout.rows)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 20)
        self.cols_spin.setValue(context.layout.cols)
        size_row.addWidget(QLabel("行"))
        size_row.addWidget(self.rows_spin)
        size_row.addWidget(QLabel("列"))
        size_row.addWidget(self.cols_spin)
        apply_button = QPushButton("应用")
        apply_button.setObjectName("Ghost")
        apply_button.setCursor(Qt.PointingHandCursor)
        apply_button.clicked.connect(self._apply_size)
        size_row.addWidget(apply_button)
        size_card.body.addLayout(size_row)
        side_col.addWidget(size_card)

        brush_card = Card(padding=16, spacing=10)
        title = QLabel("画笔")
        title.setObjectName("CardTitle")
        brush_card.body.addWidget(title)
        grid = QVBoxLayout()
        grid.setSpacing(6)
        self.brush_group = QButtonGroup(self)
        self.brush_group.setExclusive(True)
        brushes = [
            ("课桌", BRUSH_DESK),
            ("黑板", BRUSH_BOARD),
            ("讲台", BRUSH_PODIUM),
            ("橡皮", BRUSH_ERASE),
        ]
        for index in range(0, len(brushes), 2):
            row = QHBoxLayout()
            row.setSpacing(6)
            for text, value in brushes[index : index + 2]:
                button = QPushButton(text)
                button.setCheckable(True)
                button.setObjectName("Soft")
                button.setCursor(Qt.PointingHandCursor)
                button.setStyleSheet(
                    f"QPushButton{{background:{theme.SURFACE_ALT};border:1px solid {theme.BORDER};"
                    f"border-radius:9px;padding:8px;color:{theme.MUTED};}}"
                    f"QPushButton:checked{{background:{theme.ACCENT};color:white;border-color:{theme.ACCENT};}}"
                )
                button.clicked.connect(lambda _=False, v=value: self._set_brush(v))
                self.brush_group.addButton(button)
                button.setProperty("brush", value)
                row.addWidget(button)
                if value == BRUSH_DESK:
                    button.setChecked(True)
            grid.addLayout(row)
        brush_card.body.addLayout(grid)
        side_col.addWidget(brush_card)

        area_card = Card(padding=16, spacing=8)
        area_head = QHBoxLayout()
        title = QLabel("区域 / 小组")
        title.setObjectName("CardTitle")
        area_head.addWidget(title)
        area_head.addStretch(1)
        add_area_button = QPushButton("＋ 新建")
        add_area_button.setObjectName("LinkBtn")
        add_area_button.setCursor(Qt.PointingHandCursor)
        add_area_button.clicked.connect(self._add_area)
        area_head.addWidget(add_area_button)
        area_card.body.addLayout(area_head)

        self.area_list = QListWidget()
        self.area_list.setObjectName("AreaList")
        self.area_list.setMinimumHeight(150)
        self.area_list.currentItemChanged.connect(self._on_area_selected)
        self.area_list.itemDoubleClicked.connect(lambda _: self._rename_area())
        area_card.body.addWidget(self.area_list, 1)

        self.area_mode = QCheckBox("区域编辑模式（点击课桌加入/移出）")
        self.area_mode.setStyleSheet(f"color:{theme.MUTED}; font-size:12px;")
        self.area_mode.toggled.connect(self._on_area_mode)
        area_card.body.addWidget(self.area_mode)

        area_buttons = QHBoxLayout()
        area_buttons.setSpacing(6)
        rename_button = QPushButton("重命名")
        rename_button.setObjectName("Ghost")
        rename_button.setCursor(Qt.PointingHandCursor)
        rename_button.clicked.connect(self._rename_area)
        area_buttons.addWidget(rename_button)
        delete_button = QPushButton("删除区域")
        delete_button.setObjectName("DangerBtn")
        delete_button.setCursor(Qt.PointingHandCursor)
        delete_button.clicked.connect(self._delete_area)
        area_buttons.addWidget(delete_button)
        area_card.body.addLayout(area_buttons)
        side_col.addWidget(area_card, 1)

        stats_card = Card(padding=16, spacing=8)
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet(f"color:{theme.TEXT}; font-size:12px; line-height:160%;")
        stats_card.body.addWidget(self.stats_label)
        self.problem_label = QLabel("")
        self.problem_label.setWordWrap(True)
        self.problem_label.setStyleSheet(f"color:{theme.WARNING}; font-size:12px;")
        stats_card.body.addWidget(self.problem_label)
        auto_button = QPushButton("按人数一键生成布局")
        auto_button.setObjectName("Ghost")
        auto_button.setCursor(Qt.PointingHandCursor)
        auto_button.clicked.connect(self._auto_generate)
        stats_card.body.addWidget(auto_button)
        side_col.addWidget(stats_card)

        body.addWidget(side)
        root.addLayout(body, 1)

        self.refresh()

    # ------------------------------------------------------------------ #
    # 刷新
    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self.canvas.set_layout(self.context.layout)
        self.rows_spin.setValue(self.context.layout.rows)
        self.cols_spin.setValue(self.context.layout.cols)
        self.refresh()

    def refresh(self) -> None:
        layout = self.context.layout
        self._refresh_areas()
        seats = len(layout.desks())
        areas = len([a for a in layout.areas if layout.seats_of(a)])
        loose = len(layout.unassigned_desks())
        self.stats_label.setText(
            f"课桌 {seats} 张　·　区域 {areas} 个<br>"
            f"每组大约 {round(seats / areas, 1) if areas else 0} 人　·　未分组课桌 {loose} 张"
        )
        problems = layout.problems()
        if problems:
            self.problem_label.setText("⚠ " + "；".join(problems[:2]))
            self.problem_label.setVisible(True)
        else:
            self.problem_label.setVisible(False)
        self.canvas.update()

    def _refresh_areas(self) -> None:
        layout = self.context.layout
        current = self._current_area_id
        self.area_list.blockSignals(True)
        self.area_list.clear()
        selected_row = -1
        for index, area in enumerate(layout.areas):
            count = len(layout.seats_of(area))
            item = QListWidgetItem(_color_icon(area.color_hex), f"  {area.name}    {count} 座")
            item.setData(Qt.UserRole, area.aid)
            self.area_list.addItem(item)
            if area.aid == current:
                selected_row = index
        if selected_row < 0 and self.area_list.count():
            selected_row = 0
        if selected_row >= 0:
            self.area_list.setCurrentRow(selected_row)
        self.area_list.blockSignals(False)
        item = self.area_list.currentItem()
        self._current_area_id = item.data(Qt.UserRole) if item else None

    def _on_hover(self, text: str) -> None:
        self.hover_label.setText(text or "拖动鼠标即可绘制；右上角可切换画笔")

    # ------------------------------------------------------------------ #
    # 画笔 / 区域
    # ------------------------------------------------------------------ #
    def _set_brush(self, brush: str) -> None:
        self.area_mode.setChecked(False)
        self.canvas.set_brush(brush)

    def _on_area_selected(self, current: QListWidgetItem | None, previous=None) -> None:
        if current is None:
            self._current_area_id = None
            return
        self._current_area_id = current.data(Qt.UserRole)
        if self.area_mode.isChecked():
            self.canvas.set_area_mode(True, self._current_area_id)

    def _on_area_mode(self, checked: bool) -> None:
        if checked:
            if self._current_area_id is None:
                QMessageBox.information(self, "区域编辑", "请先在列表里选择一个区域。")
                self.area_mode.setChecked(False)
                return
            self.canvas.set_area_mode(True, self._current_area_id)
        else:
            self.canvas.set_area_mode(False)

    def _add_area(self) -> None:
        name, ok = QInputDialog.getText(
            self, "新建区域", "区域名称：", text=f"区域 {len(self.context.layout.areas) + 1}"
        )
        if not ok or not name.strip():
            return
        area = self.context.layout.add_area(name.strip())
        self.context.invalidate_plan()
        self.context.save()
        self._current_area_id = area.aid
        self.refresh()
        if self.area_mode.isChecked():
            self.canvas.set_area_mode(True, area.aid)

    def _rename_area(self) -> None:
        area = self._selected_area()
        if not area:
            return
        name, ok = QInputDialog.getText(self, "重命名区域", "区域名称：", text=area.name)
        if ok and name.strip():
            area.name = name.strip()
            self.context.invalidate_plan()
            self.context.save()
            self.refresh()

    def _delete_area(self) -> None:
        area = self._selected_area()
        if not area:
            return
        answer = QMessageBox.question(
            self,
            "删除区域",
            f"确定删除「{area.name}」吗？区域里的课桌会保留，但变成未分组。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.context.layout.remove_area(area)
        self.context.invalidate_plan()
        self.context.save()
        self._current_area_id = None
        self.refresh()

    def _selected_area(self) -> Area | None:
        item = self.area_list.currentItem()
        if item is None:
            return None
        aid = item.data(Qt.UserRole)
        return next((a for a in self.context.layout.areas if a.aid == aid), None)

    # ------------------------------------------------------------------ #
    # 画布事件
    # ------------------------------------------------------------------ #
    def _on_canvas_changed(self) -> None:
        self.context.invalidate_plan()
        self.context.save()
        self.refresh()

    def _undo(self) -> None:
        if not self.canvas.undo():
            QMessageBox.information(self, "撤销", "没有可以撤销的操作了。")
            return
        self.context.invalidate_plan()
        self.context.save()
        self.refresh()

    def _apply_size(self) -> None:
        rows, cols = self.rows_spin.value(), self.cols_spin.value()
        if rows == self.context.layout.rows and cols == self.context.layout.cols:
            return
        self.canvas.push_undo()
        self.context.layout.resize(rows, cols)
        self.context.invalidate_plan()
        self.context.save()
        self.refresh()

    # ------------------------------------------------------------------ #
    # 自动生成
    # ------------------------------------------------------------------ #
    def _auto_generate(self) -> None:
        count = len(self.context.state.students)
        if count <= 0:
            QMessageBox.information(self, "一键生成", "请先在「学生名单」里录入学生人数。")
            return
        per_row, ok = QInputDialog.getInt(
            self, "一键生成布局", "每排坐几人（建议 4~8 人）：", 6, 2, 8, 1
        )
        if not ok:
            return
        answer = QMessageBox.question(
            self,
            "一键生成布局",
            f"将按 {count} 人、每排 {per_row} 人重新生成教室，"
            "现有的课桌和区域会被覆盖，确定吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.canvas.push_undo()
        new_layout = quick_layout(count, per_row)
        layout = self.context.layout
        layout.rows = new_layout.rows
        layout.cols = new_layout.cols
        layout.cells = new_layout.cells
        layout.areas = new_layout.areas
        self.context.invalidate_plan()
        self.context.save()
        self.rows_spin.setValue(layout.rows)
        self.cols_spin.setValue(layout.cols)
        self._current_area_id = None
        self.refresh()
