"""界面主题：现代浅色蓝。

所有颜色、尺寸集中在这里，QSS 负责大部分观感，
少量图标用 QPainter 现画，避免依赖外部图片资源。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

# --------------------------------------------------------------------------- #
# 调色板
# --------------------------------------------------------------------------- #

BG = "#F4F7FD"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F7F9FE"
ACCENT = "#2F6BFF"
ACCENT_DARK = "#1E4FD8"
ACCENT_SOFT = "#E8F0FF"
TEXT = "#1F2A44"
MUTED = "#6B7A99"
FAINT = "#9AA8C4"
BORDER = "#E4EAF6"
SUCCESS = "#16A34A"
SUCCESS_SOFT = "#E7F7EE"
WARNING = "#D97706"
WARNING_SOFT = "#FEF3E2"
DANGER = "#E4484A"
DANGER_SOFT = "#FDECEC"

FONT_FAMILY = "Microsoft YaHei UI"
FONT_FALLBACK = "Microsoft YaHei"


def font(size: int = 10, weight: int = 400, italic: bool = False) -> QFont:
    f = QFont(FONT_FAMILY, size)
    f.setStyleStrategy(QFont.PreferAntialias)
    if weight != 400:
        f.setWeight(QFont.Weight(weight))
    f.setItalic(italic)
    return f


# --------------------------------------------------------------------------- #
# QSS
# --------------------------------------------------------------------------- #


def qss() -> str:
    return f"""
    * {{
        font-family: "{FONT_FAMILY}", "{FONT_FALLBACK}";
        font-size: 13px;
        color: {TEXT};
        outline: none;
    }}
    QMainWindow, QWidget#Root {{ background: {BG}; }}
    QToolTip {{
        background: {TEXT};
        color: white;
        border: none;
        padding: 6px 9px;
        border-radius: 6px;
        font-size: 12px;
    }}

    /* ---------- 侧边栏 ---------- */
    QWidget#Sidebar {{
        background: {SURFACE};
        border-right: 1px solid {BORDER};
    }}
    QLabel#BrandMark {{
        background: {ACCENT};
        color: white;
        border-radius: 10px;
        font-size: 18px;
        font-weight: 700;
    }}
    QLabel#BrandName {{ font-size: 16px; font-weight: 700; color: {TEXT}; }}
    QLabel#BrandSub {{ font-size: 11px; color: {FAINT}; }}

    QPushButton#Nav {{
        text-align: left;
        padding: 11px 14px;
        border: none;
        border-radius: 10px;
        background: transparent;
        color: {MUTED};
        font-size: 14px;
    }}
    QPushButton#Nav:hover {{ background: {SURFACE_ALT}; color: {TEXT}; }}
    QPushButton#Nav:checked {{
        background: {ACCENT_SOFT};
        color: {ACCENT};
        font-weight: 700;
    }}
    QPushButton#Nav:checked:hover {{ background: {ACCENT_SOFT}; }}
    QFrame#NavIndicator {{
        background: {ACCENT};
        border-radius: 2px;
    }}

    /* ---------- 卡片 ---------- */
    QFrame#Card {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 16px;
    }}
    QFrame#SoftCard {{
        background: {SURFACE_ALT};
        border: 1px solid {BORDER};
        border-radius: 12px;
    }}
    QFrame#Divider {{ background: {BORDER}; max-height: 1px; border: none; }}

    QLabel#PageTitle {{ font-size: 24px; font-weight: 700; color: {TEXT}; }}
    QLabel#PageSub {{ font-size: 13px; color: {MUTED}; }}
    QLabel#CardTitle {{ font-size: 15px; font-weight: 700; color: {TEXT}; }}
    QLabel#CardHint {{ font-size: 12px; color: {MUTED}; }}
    QLabel#StepNo {{
        background: {ACCENT_SOFT}; color: {ACCENT};
        border-radius: 11px; font-size: 12px; font-weight: 700;
    }}
    QLabel#Muted {{ color: {MUTED}; }}
    QLabel#Faint {{ color: {FAINT}; font-size: 12px; }}
    QLabel#Danger {{ color: {DANGER}; }}
    QLabel#Success {{ color: {SUCCESS}; }}

    /* ---------- 按钮 ---------- */
    QPushButton {{
        border-radius: 9px;
        padding: 7px 14px;
        border: 1px solid transparent;
        background: transparent;
    }}
    QPushButton#Primary {{
        background: {ACCENT};
        color: white;
        font-weight: 700;
        padding: 10px 20px;
        border-radius: 10px;
    }}
    QPushButton#Primary:hover {{ background: {ACCENT_DARK}; }}
    QPushButton#Primary:pressed {{ background: #1840B8; }}
    QPushButton#Primary:disabled {{ background: #C3D2F0; color: #F2F6FF; }}

    QPushButton#Ghost {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        color: {TEXT};
        padding: 8px 14px;
    }}
    QPushButton#Ghost:hover {{ border-color: {ACCENT}; color: {ACCENT}; background: #F7FAFF; }}
    QPushButton#Ghost:disabled {{ color: {FAINT}; border-color: {BORDER}; background: {SURFACE_ALT}; }}

    QPushButton#Soft {{
        background: {SURFACE_ALT};
        border: 1px solid {BORDER};
        color: {MUTED};
    }}
    QPushButton#Soft:hover {{ background: {ACCENT_SOFT}; color: {ACCENT}; border-color: {ACCENT_SOFT}; }}
    QPushButton#Soft:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}

    QPushButton#DangerBtn {{
        background: transparent; border: 1px solid transparent; color: {DANGER}; padding: 6px 10px;
    }}
    QPushButton#DangerBtn:hover {{ background: {DANGER_SOFT}; }}

    QPushButton#LinkBtn {{
        background: transparent; border: none; color: {ACCENT}; padding: 2px 4px; font-size: 12px;
    }}
    QPushButton#LinkBtn:hover {{ color: {ACCENT_DARK}; text-decoration: underline; }}

    /* ---------- 输入 ---------- */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 9px;
        padding: 7px 10px;
        min-height: 20px;
        selection-background-color: {ACCENT_SOFT};
        selection-color: {TEXT};
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: #C9D6EE; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{ border: 1px solid {ACCENT}; }}
    QLineEdit#ClassInput {{
        font-size: 20px; font-weight: 700; border: 1px solid transparent;
        background: transparent; padding: 2px 4px;
    }}
    QLineEdit#ClassInput:focus {{ border: 1px solid {ACCENT}; background: {SURFACE}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
    QComboBox QAbstractItemView {{
        background: white; border: 1px solid {BORDER}; border-radius: 8px;
        padding: 4px; selection-background-color: {ACCENT_SOFT}; selection-color: {ACCENT};
    }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}

    /* ---------- 表格 ---------- */
    QTableWidget {{
        background: {SURFACE};
        alternate-background-color: #F8FAFF;
        border: none;
        gridline-color: transparent;
        selection-background-color: {ACCENT_SOFT};
        selection-color: {TEXT};
    }}
    QTableWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {BORDER}; }}
    QTableWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
    QHeaderView::section {{
        background: {SURFACE_ALT};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 10px 8px;
        color: {MUTED};
        font-weight: 700;
        font-size: 12px;
    }}
    QTableCornerButton::section {{ background: {SURFACE_ALT}; border: none; }}

    /* ---------- 列表 / 滚动区 ---------- */
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: #D5DEEE; border-radius: 3px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: #B9C8E2; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: #D5DEEE; border-radius: 3px; min-width: 30px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    QListWidget#AreaList {{
        background: transparent; border: none; outline: none;
    }}
    QListWidget#AreaList::item {{
        background: {SURFACE_ALT};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 8px 10px;
        margin: 3px 0;
        color: {TEXT};
    }}
    QListWidget#AreaList::item:selected {{
        background: {ACCENT_SOFT};
        border: 1px solid {ACCENT};
        color: {ACCENT};
    }}

    /* ---------- 滑块 ---------- */
    QSlider::groove:horizontal {{
        height: 5px; background: {BORDER}; border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: white; border: 2px solid {ACCENT}; width: 13px; height: 13px;
        margin: -6px 0; border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{ background: {ACCENT_SOFT}; }}

    /* ---------- 复选框 ---------- */
    QCheckBox {{ spacing: 8px; color: {TEXT}; }}
    QCheckBox::indicator {{
        width: 17px; height: 17px; border-radius: 5px;
        border: 1px solid #C9D6EE; background: white;
    }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
    QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}

    QMenu {{
        background: white; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px;
    }}
    QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}

    QDialog {{ background: {BG}; }}
    QMessageBox {{ background: {SURFACE}; }}
    """


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(font(10))
    app.setStyleSheet(qss())


# --------------------------------------------------------------------------- #
# 用 QPainter 画小图标
# --------------------------------------------------------------------------- #


def make_icon(kind: str, color: str = MUTED, size: int = 20) -> QIcon:
    pix = QPixmap(size, size)
    pix.setDevicePixelRatio(1.0)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    s = size / 20.0
    painter.scale(s, s)

    if kind == "students":
        painter.drawEllipse(QRectF(3.5, 3.0, 5.2, 5.2))
        painter.drawEllipse(QRectF(11.3, 3.0, 5.2, 5.2))
        painter.drawArc(QRectF(1.0, 9.2, 10.2, 8.0), 0, 180 * 16)
        painter.drawArc(QRectF(8.8, 9.2, 10.2, 8.0), 0, 180 * 16)
    elif kind == "layout":
        for r in range(2):
            for c in range(2):
                painter.drawRoundedRect(QRectF(3 + c * 7.4, 3 + r * 7.4, 6.4, 6.4), 1.6, 1.6)
    elif kind == "seat":
        painter.drawRoundedRect(QRectF(3.2, 4.0, 13.6, 6.2), 2.0, 2.0)
        painter.drawLine(QPointF(5.6, 10.4), QPointF(5.0, 16.2))
        painter.drawLine(QPointF(14.4, 10.4), QPointF(15.0, 16.2))
    elif kind == "history":
        painter.drawEllipse(QRectF(3.0, 3.0, 14.0, 14.0))
        painter.drawLine(QPointF(10, 6.0), QPointF(10, 10.4))
        painter.drawLine(QPointF(10, 10.4), QPointF(13.2, 12.2))
    elif kind == "export":
        painter.drawRoundedRect(QRectF(3.4, 3.2, 13.2, 13.6), 2.0, 2.0)
        painter.drawLine(QPointF(6.8, 7.4), QPointF(13.2, 7.4))
        painter.drawLine(QPointF(6.8, 10.2), QPointF(13.2, 10.2))
        painter.drawLine(QPointF(6.8, 13.0), QPointF(11.0, 13.0))
    elif kind == "plus":
        painter.drawLine(QPointF(10, 4.5), QPointF(10, 15.5))
        painter.drawLine(QPointF(4.5, 10), QPointF(15.5, 10))
    elif kind == "spark":
        painter.drawLine(QPointF(10, 3.2), QPointF(10, 6.0))
        painter.drawLine(QPointF(10, 14.0), QPointF(10, 16.8))
        painter.drawLine(QPointF(3.2, 10), QPointF(6.0, 10))
        painter.drawLine(QPointF(14.0, 10), QPointF(16.8, 10))
        painter.drawLine(QPointF(5.2, 5.2), QPointF(7.0, 7.0))
        painter.drawLine(QPointF(13.0, 13.0), QPointF(14.8, 14.8))
        painter.drawLine(QPointF(14.8, 5.2), QPointF(13.0, 7.0))
        painter.drawLine(QPointF(7.0, 13.0), QPointF(5.2, 14.8))
    elif kind == "check":
        painter.drawPolyline([QPointF(4.0, 10.2), QPointF(8.2, 14.2), QPointF(16.0, 5.8)])
    elif kind == "trash":
        painter.drawLine(QPointF(4.5, 5.8), QPointF(15.5, 5.8))
        painter.drawLine(QPointF(8.0, 3.6), QPointF(12.0, 3.6))
        painter.drawRoundedRect(QRectF(6.0, 6.6, 8.0, 9.8), 1.4, 1.4)
        painter.drawLine(QPointF(9.0, 9.0), QPointF(9.0, 13.4))
        painter.drawLine(QPointF(11.0, 9.0), QPointF(11.0, 13.4))
    elif kind == "back":
        painter.drawPolyline([QPointF(11.5, 5.0), QPointF(6.5, 10.0), QPointF(11.5, 15.0)])
    painter.end()
    return QIcon(pix)


def app_icon() -> QIcon:
    """程序图标：蓝底白格。"""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(ACCENT))
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
    p.setBrush(QColor("white"))
    for r in range(2):
        for c in range(2):
            p.drawRoundedRect(QRectF(15 + c * 19, 15 + r * 19, 14, 14), 4, 4)
    p.end()
    return QIcon(pix)
