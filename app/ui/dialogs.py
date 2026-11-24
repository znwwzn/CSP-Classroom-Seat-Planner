"""对话框：特殊关系管理、成绩表手动指定列、名单模板。"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import excel_import
from ..core.models import (
    GENDERS,
    HEIGHTS,
    REL_MUST,
    REL_PREFER,
    REL_STRENGTHS,
    Student,
    Relation,
)
from . import theme
from .widgets import Card, ComboBox, HLine, Pill


# --------------------------------------------------------------------------- #
# 下拉框列代理
# --------------------------------------------------------------------------- #


class OptionDelegate(QStyledItemDelegate):
    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.options = options

    def createEditor(self, parent, option, index):  # type: ignore[override]
        combo = QComboBox(parent)
        for value, label in self.options:
            combo.addItem(label, value)
        return combo

    def setEditorData(self, editor, index):  # type: ignore[override]
        value = index.data(Qt.UserRole)
        position = editor.findData(value)
        if position >= 0:
            editor.setCurrentIndex(position)

    def setModelData(self, editor, model, index):  # type: ignore[override]
        model.setData(index, editor.currentText(), Qt.DisplayRole)
        model.setData(index, editor.currentData(), Qt.UserRole)


# --------------------------------------------------------------------------- #
# 特殊关系
# --------------------------------------------------------------------------- #


class RelationsDialog(QDialog):
    def __init__(self, students: list[Student], relations: list[Relation], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.students = students
        self.setWindowTitle("特殊关系")
        self.setMinimumSize(760, 560)
        self.setStyleSheet(theme.qss())

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(14)

        title = QLabel("特殊关系")
        title.setStyleSheet(f"font-size:20px; font-weight:700; color:{theme.TEXT};")
        root.addWidget(title)
        hint = QLabel(
            "「必须分开」= 不同区域且不相邻（情侣、闹矛盾）；"
            "「尽量分开」= 能拆就拆，排不下时允许相邻（好友、话搭子）。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.MUTED}; font-size:12px;")
        root.addWidget(hint)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["学生 A", "学生 B", "处理方式", "备注"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(2, 130)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setStyleSheet(
            f"QTableWidget{{border:1px solid {theme.BORDER}; border-radius:10px;}}"
        )

        student_options = [(s.sid, s.name or "（未命名）") for s in students]
        self.table.setItemDelegateForColumn(0, OptionDelegate(student_options, self))
        self.table.setItemDelegateForColumn(1, OptionDelegate(student_options, self))
        self.table.setItemDelegateForColumn(
            2, OptionDelegate([(s, s) for s in REL_STRENGTHS], self)
        )
        root.addWidget(self.table, 1)

        toolbar = QHBoxLayout()
        add_button = QPushButton("＋ 添加一组关系")
        add_button.setObjectName("Ghost")
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.clicked.connect(lambda: self.add_row())
        toolbar.addWidget(add_button)
        toolbar.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color:{theme.MUTED}; font-size:12px;")
        toolbar.addWidget(self.count_label)
        root.addLayout(toolbar)

        buttons = QDialogButtonBox()
        cancel = buttons.addButton("取消", QDialogButtonBox.RejectRole)
        save = buttons.addButton("保存", QDialogButtonBox.AcceptRole)
        save.setObjectName("Primary")
        cancel.setObjectName("Ghost")
        for button in (cancel, save):
            button.setCursor(Qt.PointingHandCursor)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        for relation in relations:
            self.add_row(relation)
        self._refresh_count()

    # -- 行操作 -------------------------------------------------------------
    def add_row(self, relation: Relation | None = None) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        a_sid = relation.a if relation else ""
        b_sid = relation.b if relation else ""
        strength = relation.strength if relation else REL_MUST
        note = relation.note if relation else ""

        for column, sid in ((0, a_sid), (1, b_sid)):
            item = QTableWidgetItem(self._name_of(sid) if sid else "")
            item.setData(Qt.UserRole, sid)
            self.table.setItem(row, column, item)

        item = QTableWidgetItem(strength)
        item.setData(Qt.UserRole, strength)
        self.table.setItem(row, 2, item)

        note_item = QTableWidgetItem(note)
        self.table.setItem(row, 3, note_item)

        if relation is None:
            self.table.setCurrentCell(row, 0)
            self.table.editItem(self.table.item(row, 0))
        self._refresh_count()

    def _name_of(self, sid: str) -> str:
        for student in self.students:
            if student.sid == sid:
                return student.name
        return ""

    def _refresh_count(self) -> None:
        self.count_label.setText(f"共 {self.table.rowCount()} 组关系")

    # -- 保存 ---------------------------------------------------------------
    def _on_accept(self) -> None:
        collected: list[Relation] = []
        seen: dict[tuple[str, str], Relation] = {}
        for row in range(self.table.rowCount()):
            a_item = self.table.item(row, 0)
            b_item = self.table.item(row, 1)
            s_item = self.table.item(row, 2)
            n_item = self.table.item(row, 3)
            a = a_item.data(Qt.UserRole) if a_item else ""
            b = b_item.data(Qt.UserRole) if b_item else ""
            if not a or not b:
                continue
            if a == b:
                QMessageBox.warning(self, "关系无效", f"第 {row + 1} 行的两名学生是同一个人，请修改。")
                return
            strength = (s_item.data(Qt.UserRole) if s_item else REL_MUST) or REL_MUST
            note = n_item.text().strip() if n_item else ""
            key = tuple(sorted((a, b)))
            relation = Relation(a=a, b=b, strength=strength, note=note)
            if key in seen:
                existing = seen[key]
                if strength == REL_MUST:
                    existing.strength = REL_MUST
                if note and note not in existing.note:
                    existing.note = (existing.note + " " + note).strip()
                continue
            seen[key] = relation
            collected.append(relation)
        self.relations = collected
        self.accept()


# --------------------------------------------------------------------------- #
# 成绩表手动指定列
# --------------------------------------------------------------------------- #


class ScoreMappingDialog(QDialog):
    def __init__(self, path: str | Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = str(path)
        self.setWindowTitle("手动指定成绩列")
        self.setMinimumSize(820, 640)
        self.setStyleSheet(theme.qss())

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(12)

        title = QLabel("手动指定列")
        title.setStyleSheet(f"font-size:20px; font-weight:700; color:{theme.TEXT};")
        root.addWidget(title)
        hint = QLabel(f"文件：{Path(path).name}\n如果自动识别失败，请在下面选定工作表、表头行和对应列。")
        hint.setStyleSheet(f"color:{theme.MUTED}; font-size:12px;")
        root.addWidget(hint)

        form = QHBoxLayout()
        form.setSpacing(10)
        self.sheet_combo = QComboBox()
        self.sheet_combo.addItems(excel_import.sheet_names(path))
        self.sheet_combo.currentTextChanged.connect(self._load_sheet)
        form.addWidget(QLabel("工作表"))
        form.addWidget(self.sheet_combo, 2)

        self.header_spin = QSpinBox()
        self.header_spin.setRange(1, 30)
        self.header_spin.setValue(2)
        self.header_spin.valueChanged.connect(self._refresh_columns)
        form.addWidget(QLabel("表头行"))
        form.addWidget(self.header_spin)

        self.name_combo = QComboBox()
        self.total_combo = QComboBox()
        self.rank_combo = QComboBox()
        for label, combo in (("姓名列", self.name_combo), ("总分列", self.total_combo), ("排名列", self.rank_combo)):
            form.addWidget(QLabel(label))
            form.addWidget(combo, 1)
        root.addLayout(form)

        self.preview = QTableWidget(0, 0)
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview.verticalHeader().setVisible(False)
        self.preview.setStyleSheet(f"QTableWidget{{border:1px solid {theme.BORDER}; border-radius:10px;}}")
        root.addWidget(self.preview, 1)

        buttons = QDialogButtonBox()
        cancel = buttons.addButton("取消", QDialogButtonBox.RejectRole)
        ok = buttons.addButton("用这组列导入", QDialogButtonBox.AcceptRole)
        ok.setObjectName("Primary")
        cancel.setObjectName("Ghost")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._load_sheet(self.sheet_combo.currentText())

    def _load_sheet(self, sheet: str) -> None:
        if not sheet:
            return
        try:
            rows = excel_import.preview_sheet(self.path, sheet, max_rows=20)
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.critical(self, "读取失败", str(exc))
            return
        self.preview.clear()
        self.preview.setRowCount(len(rows))
        self.preview.setColumnCount(max((len(r) for r in rows), default=0))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.preview.setItem(r, c, QTableWidgetItem(str(value)))
        self.preview.resizeColumnsToContents()

        guess = excel_import.detect_mapping(self.path, sheet)
        if guess:
            self.header_spin.setValue(int(guess["header_row"] or 1))
            self._refresh_columns()
            self._select(self.name_combo, guess["name_col"])
            self._select(self.total_combo, guess["total_col"])
            self._select(self.rank_combo, guess["rank_col"])
        else:
            self._refresh_columns()

    def _select(self, combo: QComboBox, index) -> None:
        if index is None:
            combo.setCurrentIndex(0)
            return
        position = combo.findData(int(index))
        if position >= 0:
            combo.setCurrentIndex(position)

    def _refresh_columns(self) -> None:
        header_index = self.header_spin.value() - 1
        rows = excel_import.preview_sheet(self.path, self.sheet_combo.currentText(), max_rows=max(header_index + 1, 3))
        headers = rows[header_index] if 0 <= header_index < len(rows) else []
        width = max(len(r) for r in rows) if rows else 0
        for combo, optional in ((self.name_combo, False), (self.total_combo, True), (self.rank_combo, True)):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("（不使用）", None)
            for index in range(width):
                text = headers[index] if index < len(headers) else ""
                label = f"{get_column_letter(index + 1)}　{text}".rstrip()
                combo.addItem(label, index)
            position = combo.findData(current)
            combo.setCurrentIndex(position if position >= 0 else 0)
            combo.blockSignals(False)

    def mapping(self) -> dict:
        return {
            "sheet": self.sheet_combo.currentText(),
            "header_row": self.header_spin.value(),
            "name_col": self.name_combo.currentData(),
            "total_col": self.total_combo.currentData(),
            "rank_col": self.rank_combo.currentData(),
        }


# --------------------------------------------------------------------------- #
# 名单模板
# --------------------------------------------------------------------------- #


def write_roster_template(path: str | Path) -> Path:
    path = Path(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "学生名单"
    headers = ["姓名", "性别", "身高", "爱说话程度", "备注"]
    widths = [18, 10, 10, 16, 30]
    for index, (header, width) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=1, column=index, value=header)
        cell.font = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2F6BFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.row_dimensions[1].height = 26

    samples = [
        ("张三", "男", "中", "一般", "示例行，导入前可删除"),
        ("李四", "女", "低", "爱说话", ""),
        ("王五", "男", "高", "不爱说话", ""),
    ]
    for row_index, values in enumerate(samples, start=2):
        for col_index, value in enumerate(values, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.font = Font(name="微软雅黑", size=10)
            cell.alignment = Alignment(horizontal="center", vertical="center")

    note = wb.create_sheet("填写说明")
    lines = [
        "填写说明",
        "1. 「姓名」必填，不能为空。",
        "2. 「性别」只能填 男 或 女。",
        "3. 「身高」只能填 低、中、高 三档中的一档。",
        "4. 「爱说话程度」填 不爱说话 / 一般 / 爱说话 三档之一；留空按「一般」处理。",
        "5. 「备注」可留空。",
        "6. 特殊关系在软件里单独维护，不需要写在这张表里。",
        "7. 表头行请保留，示例行删除后再导入。",
    ]
    for index, line in enumerate(lines, start=1):
        cell = note.cell(row=index, column=1, value=line)
        cell.font = Font(name="微软雅黑", size=12 if index == 1 else 10, bold=index == 1)
    note.column_dimensions["A"].width = 60

    wb.save(path)
    return path
