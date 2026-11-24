"""排座结果画布：显示座位与姓名，支持拖动换座。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..core.models import CELL_BOARD, CELL_DESK, CELL_PODIUM, Layout, Student
from . import theme


class SeatCanvas(QWidget):
    swapRequested = Signal(str, str)
    seatHovered = Signal(str)
    seatSelected = Signal(str)

    def __init__(self, layout: Layout, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout = layout
        self.assignment: dict[str, str] = {}
        self.students: dict[str, Student] = {}
        self.flags: dict[str, list[str]] = {}
        self.group_of: dict[str, int] = {}
        self._cell = 62.0
        self._origin = QPointF(0, 0)
        self._hover: str | None = None
        self._selected: str | None = None
        self._drag_from: str | None = None
        self._drag_pos = QPointF(0, 0)
        self.setMinimumSize(640, 420)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    # ------------------------------------------------------------------ #
    def set_layout(self, layout: Layout) -> None:
        self.layout = layout
        self.update()

    def set_data(
        self,
        assignment: dict[str, str],
        students: dict[str, Student],
        flags: dict[str, list[str]] | None = None,
        group_of: dict[str, int] | None = None,
    ) -> None:
        self.assignment = dict(assignment)
        self.students = students
        self.flags = flags or {}
        self.group_of = group_of or {}
        self.update()

    def clear_drag(self) -> None:
        self._drag_from = None
        self.update()

    # ------------------------------------------------------------------ #
    def _compute_geometry(self) -> None:
        margin = 24
        available_w = max(120, self.width() - margin * 2)
        available_h = max(120, self.height() - margin * 2)
        self._cell = max(30.0, min(available_w / self.layout.cols, available_h / self.layout.rows, 96.0))
        grid_w = self._cell * self.layout.cols
        grid_h = self._cell * self.layout.rows
        self._origin = QPointF((self.width() - grid_w) / 2, (self.height() - grid_h) / 2)

    def cell_rect(self, row: int, col: int) -> QRectF:
        pad = self._cell * 0.055
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

    def _key_at(self, position: QPointF) -> str | None:
        cell = self._cell_at(position)
        if cell is None:
            return None
        if self.layout.cell(*cell) != CELL_DESK:
            return None
        return f"{cell[0]},{cell[1]}"

    # ------------------------------------------------------------------ #
    def paintEvent(self, event) -> None:  # type: ignore[override]
        self._compute_geometry()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(theme.SURFACE))

        grid = QRectF(
            self._origin.x(),
            self._origin.y(),
            self._cell * self.layout.cols,
            self._cell * self.layout.rows,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#FBFCFE"))
        painter.drawRoundedRect(grid.adjusted(-8, -8, 8, 8), 12, 12)

        for row in range(self.layout.rows):
            for col in range(self.layout.cols):
                kind = self.layout.cell(row, col)
                if kind == CELL_DESK:
                    self._paint_desk(painter, row, col)
                elif kind == CELL_PODIUM:
                    self._paint_block(painter, row, col, "#EEF2FA", "讲台", theme.MUTED)

        self._paint_boards(painter)

        if self._drag_from:
            self._paint_ghost(painter)
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
                    first = self.cell_rect(row, start)
                    last = self.cell_rect(row, col)
                    rect = QRectF(first.left(), first.top(), last.right() - first.left(), first.height())
                    painter.drawRoundedRect(rect, 8, 8)
                    if rect.width() > 44:
                        painter.setPen(QColor("white"))
                        painter.setFont(QFont(theme.FONT_FAMILY, 9, QFont.Bold))
                        painter.drawText(rect, Qt.AlignCenter, "黑　板")
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QColor(theme.TEXT))
                col += 1

    def _paint_block(self, painter: QPainter, row: int, col: int, fill: str, text: str, fg: str) -> None:
        rect = self.cell_rect(row, col)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QColor(fg))
        painter.setFont(QFont(theme.FONT_FAMILY, 9, QFont.Bold))
        painter.drawText(rect, Qt.AlignCenter, text)

    def _paint_desk(self, painter: QPainter, row: int, col: int) -> None:
        rect = self.cell_rect(row, col)
        key = f"{row},{col}"
        area = self.layout.area_of(row, col)
        sid = self.assignment.get(key)
        student = self.students.get(sid) if sid else None
        flags = self.flags.get(key, [])

        if student:
            color = QColor(area.color_hex if area else theme.ACCENT)
            fill = QColor(color)
            fill.setAlpha(24)
            painter.setBrush(fill)
        else:
            painter.setBrush(QColor("#FCFDFF"))

        if flags:
            border = QColor(theme.DANGER)
            width = 2.0
        elif key == self._selected:
            border = QColor(theme.ACCENT)
            width = 2.4
        elif key == self._hover and self._drag_from:
            border = QColor(theme.SUCCESS)
            width = 2.2
        elif area:
            border = QColor(area.color_hex)
            border.setAlpha(150)
            width = 1.2
        else:
            border = QColor("#D6E0F0")
            width = 1.2

        painter.setPen(QPen(border, width))
        painter.drawRoundedRect(rect, min(10, rect.width() * 0.16), min(10, rect.width() * 0.16))

        if not student:
            painter.setPen(QColor(theme.FAINT))
            painter.setFont(QFont(theme.FONT_FAMILY, 8))
            painter.drawText(rect, Qt.AlignCenter, "空")
            return

        # 姓名
        name_rect = QRectF(rect.left() + 5, rect.top() + rect.height() * 0.18, rect.width() - 10, rect.height() * 0.44)
        painter.setPen(QColor(theme.TEXT))
        font = QFont(theme.FONT_FAMILY, 11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(name_rect, Qt.AlignCenter, student.name)

        # 性别 / 身高
        info_rect = QRectF(rect.left() + 4, rect.top() + rect.height() * 0.62, rect.width() - 8, rect.height() * 0.28)
        painter.setPen(QColor(theme.MUTED))
        painter.setFont(QFont(theme.FONT_FAMILY, 7))
        painter.drawText(info_rect, Qt.AlignCenter, f"{student.gender} · {student.height}")

        # 组号徽标
        gid = self.group_of.get(student.sid)
        if gid and area:
            badge = QRectF(rect.left() + 5, rect.top() + 5, 15, 15)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(area.color_hex))
            painter.drawEllipse(badge)
            painter.setPen(QColor("white"))
            painter.setFont(QFont(theme.FONT_FAMILY, 7, QFont.Bold))
            painter.drawText(badge, Qt.AlignCenter, str(gid))

        # 冲突标记
        if flags:
            dot = QRectF(rect.right() - 17, rect.top() + 5, 12, 12)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.DANGER))
            painter.drawEllipse(dot)
            painter.setPen(QColor("white"))
            painter.setFont(QFont(theme.FONT_FAMILY, 7, QFont.Bold))
            painter.drawText(dot, Qt.AlignCenter, "!")

    def _paint_ghost(self, painter: QPainter) -> None:
        sid = self.assignment.get(self._drag_from)
        student = self.students.get(sid) if sid else None
        if not student:
            return
        font = QFont(theme.FONT_FAMILY, 10)
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(student.name) + 24
        height = 30
        rect = QRectF(self._drag_pos.x() - width / 2, self._drag_pos.y() - height / 2, width, height)
        painter.setPen(QPen(QColor(theme.ACCENT), 1.4))
        painter.setBrush(QColor(255, 255, 255, 235))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QColor(theme.ACCENT))
        painter.drawText(rect, Qt.AlignCenter, student.name)

    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton:
            return
        key = self._key_at(event.position())
        if key is None:
            self._selected = None
            self.seatSelected.emit("")
            self.update()
            return
        self._selected = key
        self.seatSelected.emit(key)
        if self.assignment.get(key):
            self._drag_from = key
            self._drag_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        key = self._key_at(event.position())
        if key != self._hover:
            self._hover = key
            self.seatHovered.emit(key or "")
            self.update()
        if self._drag_from:
            self._drag_pos = event.position()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton:
            return
        source = self._drag_from
        self._drag_from = None
        self.setCursor(Qt.ArrowCursor)
        if source is None:
            return
        target = self._key_at(event.position())
        if target and target != source:
            self.swapRequested.emit(source, target)
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hover = None
        self.update()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key_Escape:
            self.clear_drag()
            return
        super().keyPressEvent(event)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(760, 520)
