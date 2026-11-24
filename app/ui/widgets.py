"""通用界面组件：卡片、页头、标签、统计块、空状态等。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme


# --------------------------------------------------------------------------- #
# 基础容器
# --------------------------------------------------------------------------- #


class Card(QFrame):
    """白色圆角卡片。"""

    def __init__(self, parent: QWidget | None = None, padding: int = 20, spacing: int = 12) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(spacing)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget


class HLine(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)


class PageHeader(QWidget):
    """页面标题 + 副标题 + 右侧操作区。"""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        self.title = QLabel(title)
        self.title.setObjectName("PageTitle")
        text_col.addWidget(self.title)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("PageSub")
        self.subtitle.setVisible(bool(subtitle))
        text_col.addWidget(self.subtitle)
        row.addLayout(text_col)
        row.addStretch(1)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        row.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> QWidget:
        self.actions.addWidget(widget)
        return widget

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))


# --------------------------------------------------------------------------- #
# 标签
# --------------------------------------------------------------------------- #


class Pill(QLabel):
    """圆角小标签。"""

    def __init__(
        self,
        text: str = "",
        fg: str = theme.MUTED,
        bg: str = theme.SURFACE_ALT,
        parent: QWidget | None = None,
        padding: str = "3px 10px",
    ) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:10px; padding:{padding};"
            f"font-size:12px; font-weight:600;"
        )
        self.setAlignment(Qt.AlignCenter)


class StatTile(QWidget):
    """一个数字 + 一行说明的小统计块。"""

    def __init__(self, value: str, label: str, color: str = theme.TEXT, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"font-size:22px; font-weight:700; color:{color};")
        self.value_label.setAlignment(Qt.AlignCenter)
        col.addWidget(self.value_label)
        self.text_label = QLabel(label)
        self.text_label.setObjectName("Faint")
        self.text_label.setAlignment(Qt.AlignCenter)
        col.addWidget(self.text_label)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def set_value(self, value: str, color: str | None = None) -> None:
        self.value_label.setText(value)
        if color:
            self.value_label.setStyleSheet(f"font-size:22px; font-weight:700; color:{color};")


class Chip(QWidget):
    """带颜色圆点的学生姓名片。"""

    def __init__(
        self,
        text: str,
        dot_color: str | None = None,
        fg: str = theme.TEXT,
        bg: str = theme.SURFACE_ALT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 3, 9, 3)
        row.setSpacing(6)
        if dot_color:
            dot = QLabel()
            dot.setFixedSize(7, 7)
            dot.setStyleSheet(f"background:{dot_color}; border-radius:3px;")
            row.addWidget(dot)
        label = QLabel(text)
        label.setStyleSheet(f"color:{fg}; font-size:12px;")
        row.addWidget(label)
        self.setStyleSheet(f"background:{bg}; border-radius:9px;")


# --------------------------------------------------------------------------- #
# 空状态
# --------------------------------------------------------------------------- #


class EmptyState(QWidget):
    def __init__(self, title: str, hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(24, 30, 24, 30)
        col.setSpacing(8)
        col.addStretch(1)
        self.title = QLabel(title)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet(f"color:{theme.MUTED}; font-size:15px; font-weight:600;")
        col.addWidget(self.title)
        if hint:
            self.hint = QLabel(hint)
            self.hint.setAlignment(Qt.AlignCenter)
            self.hint.setWordWrap(True)
            self.hint.setStyleSheet(f"color:{theme.FAINT}; font-size:12px;")
            col.addWidget(self.hint)
        col.addStretch(1)


# --------------------------------------------------------------------------- #
# 布局
# --------------------------------------------------------------------------- #


class FlowLayout(QLayout):
    """自动换行的横向布局，用来放学生姓名片。"""

    def __init__(self, parent: QWidget | None = None, margin: int = 0, h_spacing: int = 6, v_spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list = []
        self._h = h_spacing
        self._v = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:  # type: ignore[override]
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # type: ignore[override]
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # type: ignore[override]
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # type: ignore[override]
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:  # type: ignore[override]
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # type: ignore[override]
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h
            if next_x - self._h > effective.right() + 1 and line_height > 0:
                x = effective.x()
                y = y + line_height + self._v
                next_x = x + hint.width() + self._h
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


# --------------------------------------------------------------------------- #
# 顶部“已保存”提示
# --------------------------------------------------------------------------- #


class SaveBadge(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("已自动保存", parent)
        self.setStyleSheet(
            f"color:{theme.SUCCESS}; background:{theme.SUCCESS_SOFT};"
            "border-radius:10px; padding:4px 10px; font-size:12px; font-weight:600;"
        )

    def flash(self) -> None:
        self.setText("✓ 已自动保存")
        self.setStyleSheet(
            f"color:{theme.SUCCESS}; background:{theme.SUCCESS_SOFT};"
            "border-radius:10px; padding:4px 10px; font-size:12px; font-weight:600;"
        )

    def error(self, text: str = "保存失败") -> None:
        self.setText(text)
        self.setStyleSheet(
            f"color:{theme.DANGER}; background:{theme.DANGER_SOFT};"
            "border-radius:10px; padding:4px 10px; font-size:12px; font-weight:600;"
        )


# --------------------------------------------------------------------------- #
# 圆角阴影
# --------------------------------------------------------------------------- #


def add_shadow(widget: QWidget, blur: int = 26, y_offset: int = 6, alpha: int = 20) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(31, 42, 68, alpha))
    widget.setGraphicsEffect(effect)


class ComboBox(QComboBox):
    """带自绘箭头的下拉框，避免 Fusion 在圆角边框上画出黑角。"""

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(theme.MUTED))
        pen.setWidthF(1.5)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        cx = self.width() - 15
        cy = self.height() / 2
        painter.drawLine(QPointF(cx - 4, cy - 2), QPointF(cx, cy + 2.2))
        painter.drawLine(QPointF(cx, cy + 2.2), QPointF(cx + 4, cy - 2))
        painter.end()


class ColorDot(QWidget):

    def __init__(self, color: str, size: int = 10, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self._color))
        p.drawEllipse(0, 0, self.width(), self.height())
        p.end()


class LegendDot(QWidget):
    """图例：颜色块 + 文字。"""

    def __init__(self, color: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        block = QLabel()
        block.setFixedSize(10, 10)
        block.setStyleSheet(f"background:{color}; border-radius:3px;")
        row.addWidget(block)
        label = QLabel(text)
        label.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")
        row.addWidget(label)


class SegmentedControl(QWidget):
    """一排互斥的小按钮，用于“异性同桌 / 同性同桌 / 不限制”。"""

    changed = Signal(str)

    def __init__(self, options: list[str], current: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: dict[str, QPushButton] = {}
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for option in options:
            button = QPushButton(option)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setObjectName("Soft")
            button.setStyleSheet(
                f"QPushButton{{background:{theme.SURFACE_ALT};border:1px solid {theme.BORDER};"
                f"border-radius:8px;padding:6px 12px;color:{theme.MUTED};font-size:12px;}}"
                f"QPushButton:checked{{background:{theme.ACCENT};border-color:{theme.ACCENT};"
                f"color:white;font-weight:600;}}"
            )
            button.clicked.connect(lambda _=False, value=option: self.set_current(value, emit=True))
            row.addWidget(button)
            self._buttons[option] = button
        row.addStretch(1)
        self.set_current(current or options[0], emit=False)

    def set_current(self, value: str, emit: bool = False) -> None:
        for option, button in self._buttons.items():
            button.setChecked(option == value)
        if emit:
            self.changed.emit(value)

    def current(self) -> str:
        for option, button in self._buttons.items():
            if button.isChecked():
                return option
        return next(iter(self._buttons), "")
