"""教室布局画布：画笔涂格子 + 区域归属。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget

from ..core.models import (
    CELL_BOARD,
    CELL_DESK,
    CELL_EMPTY,
    CELL_PODIUM,
    Area,
    Layout,
)
from . import theme

BRUSH_DESK = "desk"
BRUSH_BOARD = "board"
BRUSH_PODIUM = "podium"
BRUSH_ERASE = "erase"


class LayoutCanvas(QWidget):
    changed = Signal()
    hoverInfo = Signal(str)
    areaClicked = Signal(str)

    def __init__(self, layout: Layout, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout = layout
        self.brush = BRUSH_DESK
        self.area_mode = False
        self.active_area_id: str | None = None
        self._cell = 48.0
        self._origin = QPointF(0, 0)
        self._hover: tuple[int, int] | None = None
        self._painting = False
        self._undo: list[dict] = []
        self._last_cell: tuple[int, int] | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(520, 400)
        self.setCursor(Qt.CrossCursor)

    # ------------------------------------------------------------------ #
    # 外部接口
    # ------------------------------------------------------------------ #
    def set_layout(self, layout: Layout) -> None:
        self.layout = layout
        self._undo.clear()
        self.update()

    def set_brush(self, brush: str) -> None:
        self.brush = brush
        self.area_mode = False
        self.setCursor(Qt.CrossCursor)
        self.update()

    def set_area_mode(self, enabled: bool, area_id: str | None = None) -> None:
        self.area_mode = enabled
        if area_id is not None:
            self.active_area_id = area_id
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.CrossCursor)
        self.update()

    def push_undo(self) -> None:
        self._undo.append(self.layout.to_dict())
        if len(self._undo) > 40:
            self._undo.pop(0)

    def undo(self) -> bool:
        if not self._undo:
            return False
        snapshot = self._undo.pop()
        restored = Layout.from_dict(snapshot)
        self.layout.rows = restored.rows
        self.layout.cols = restored.cols
        self.layout.cells = restored.cells
        self.layout.areas = restored.areas
        self.update()
        self.changed.emit()
        return True

    def can_undo(self) -> bool:
        return bool(self._undo)

    # ------------------------------------------------------------------ #
    # 几何
    # ------------------------------------------------------------------ #
    def _compute_geometry(self) -> None:
        if not self.layout.rows or not self.layout.cols:
            return
        margin = 26
        available_w = max(120, self.width() - margin * 2)
        available_h = max(120, self.height() - margin * 2)
        self._cell = max(24.0, min(available_w / self.layout.cols, available_h / self.layout.rows, 72.0))
        grid_w = self._cell * self.layout.cols
        grid_h = self._cell * self.layout.rows
        self._origin = QPointF(
            (self.width() - grid_w) / 2,
            (self.height() - grid_h) / 2,
        )

    def cell_rect(self, row: int, col: int) -> QRectF:
        pad = self._cell * 0.06
        return QRectF(
            self._origin.x() + col * self._cell + pad,
            self._origin.y() + row * self._cell + pad,
            self._cell - pad * 2,
            self._cell - pad * 2,
        )

    def _cell_at(self, position: QPointF) -> tuple[int, int] | None:
        if self._cell <= 0:
            return None
        col = int((position.x() - self._origin.x()) // self._cell)
        row = int((position.y() - self._origin.y()) // self._cell)
        if 0 <= row < self.layout.rows and 0 <= col < self.layout.cols:
            return row, col
        return None

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #
    def paintEvent(self, event) -> None:  # type: ignore[override]
        self._compute_geometry()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(theme.SURFACE))

        # 背景网格
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#FBFCFE"))
        grid = QRectF(
            self._origin.x(),
            self._origin.y(),
            self._cell * self.layout.cols,
            self._cell * self.layout.rows,
        )
        painter.drawRoundedRect(grid.adjusted(-8, -8, 8, 8), 12, 12)

        area_index = {area.aid: index for index, area in enumerate(self.layout.areas)}
        area_first_cell: dict[str, tuple[int, int]] = {}
        for area in self.layout.areas:
            cells = sorted(area.cells, key=lambda c: (c[0], c[1]))
            if cells:
                area_first_cell[area.aid] = (cells[0][0], cells[0][1])

        self._paint_boards(painter)
        for row in range(self.layout.rows):
            for col in range(self.layout.cols):
                self._paint_cell(painter, row, col, area_index, area_first_cell)

        # 悬停高亮
        if self._hover:
            rect = self.cell_rect(*self._hover)
            pen = QPen(QColor(theme.ACCENT))
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 8, 8)

        painter.end()

    def _paint_boards(self, painter: QPainter) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.TEXT))
        for row in range(self.layout.rows):
            col = 0
            while col < self.layout.cols:
                if self.layout.cell(row, col) == CELL_BOARD:
                    start = col
                    while col + 1 < self.layout.cols and self.layout.cell(row, col + 1) == CELL_BOARD:
                        col += 1
                    left = self.cell_rect(row, start).left()
                    right = self.cell_rect(row, col).right()
                    top = self.cell_rect(row, start).top()
                    height = self.cell_rect(row, start).height()
                    rect = QRectF(left, top, right - left, height)
                    painter.drawRoundedRect(rect, 9, 9)
                    if rect.width() > 44:
                        painter.setPen(QColor("white"))
                        font = QFont(theme.FONT_FAMILY, 10)
                        font.setBold(True)
                        painter.setFont(font)
                        painter.drawText(rect, Qt.AlignCenter, "黑　板")
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QColor(theme.TEXT))
                col += 1

    def _paint_cell(
        self,
        painter: QPainter,
        row: int,
        col: int,
        area_index: dict[str, int],
        area_first: dict[str, tuple[int, int]],
    ) -> None:
        rect = self.cell_rect(row, col)
        kind = self.layout.cell(row, col)
        area = self.layout.area_of(row, col)
        radius = min(9.0, rect.width() * 0.18)

        if kind == CELL_EMPTY:
            painter.setPen(QPen(QColor("#EEF2FA"), 1))
            painter.setBrush(QColor("#FDFEFF"))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)
            return

        if kind == CELL_BOARD:
            return

        if kind == CELL_PODIUM:
            painter.setPen(QPen(QColor("#D7E0F2"), 1))
            painter.setBrush(QColor("#EEF2FA"))
            painter.drawRoundedRect(rect, radius, radius)
            painter.setPen(QColor(theme.MUTED))
            painter.setFont(QFont(theme.FONT_FAMILY, 9))
            painter.drawText(rect, Qt.AlignCenter, "讲台")
            return

        # 课桌
        if area:
            color = QColor(area.color_hex)
            fill = QColor(color)
            fill.setAlpha(26)
            border = QColor(color)
            border.setAlpha(120)
            painter.setBrush(fill)
            painter.setPen(QPen(border, 1.2))
        else:
            painter.setBrush(QColor("white"))
            painter.setPen(QPen(QColor("#CBD8EF"), 1.2))
        painter.drawRoundedRect(rect, radius, radius)

        if area:
            # 左侧色条
            bar = QRectF(rect.left() + 1.5, rect.top() + rect.height() * 0.22, 3.2, rect.height() * 0.56)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(area.color_hex))
            painter.drawRoundedRect(bar, 1.6, 1.6)

            # 区域编号徽标（只在区域左上角那张桌画）
            if area_first.get(area.aid) == (row, col):
                badge = QRectF(rect.right() - 20, rect.top() + 4, 16, 16)
                painter.setBrush(QColor(area.color_hex))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(badge)
                painter.setPen(QColor("white"))
                font = QFont(theme.FONT_FAMILY, 7)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(badge, Qt.AlignCenter, str(area_index.get(area.aid, 0) + 1))
        else:
            painter.setPen(QColor(theme.FAINT))
            font = QFont(theme.FONT_FAMILY, 7)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignBottom | Qt.AlignHCenter, "未分组")

    # ------------------------------------------------------------------ #
    # 鼠标
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton:
            return
        cell = self._cell_at(event.position())
        if cell is None:
            return
        self.push_undo()
        self._painting = True
        self._last_cell = None
        self._apply(*cell)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        cell = self._cell_at(event.position())
        if cell != self._hover:
            self._hover = cell
            self.update()
        if cell:
            kind = self.layout.cell(*cell)
            labels = {
                CELL_DESK: "课桌",
                CELL_BOARD: "黑板",
                CELL_PODIUM: "讲台",
                CELL_EMPTY: "过道",
            }
            area = self.layout.area_of(*cell)
            suffix = f" · {area.name}" if area else ""
            self.hoverInfo.emit(f"第 {cell[0] + 1} 行 · 第 {cell[1] + 1} 列　{labels.get(kind, '')}{suffix}")
        if self._painting and cell and cell != self._last_cell:
            self._apply(*cell)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._painting:
            self._painting = False
            self.changed.emit()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hover = None
        self.hoverInfo.emit("")
        self.update()

    # ------------------------------------------------------------------ #
    # 应用画笔
    # ------------------------------------------------------------------ #
    def _apply(self, row: int, col: int) -> None:
        self._last_cell = (row, col)
        if self.area_mode:
            area = next((a for a in self.layout.areas if a.aid == self.active_area_id), None)
            if area is None:
                return
            if self.layout.cell(row, col) != CELL_DESK:
                return
            if area.contains(row, col):
                area.remove(row, col)
            else:
                self.layout.assign_to_area(area, row, col)
            return

        if self.brush == BRUSH_ERASE:
            self.layout.set_cell(row, col, CELL_EMPTY)
        elif self.brush == BRUSH_DESK:
            if self.layout.cell(row, col) != CELL_DESK:
                self.layout.set_cell(row, col, CELL_DESK)
        elif self.brush == BRUSH_BOARD:
            self.layout.set_cell(row, col, CELL_BOARD)
        elif self.brush == BRUSH_PODIUM:
            self.layout.set_cell(row, col, CELL_PODIUM)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(720, 520)
