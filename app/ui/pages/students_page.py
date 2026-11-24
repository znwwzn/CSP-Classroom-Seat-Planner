"""学生名单页：表格录入、Excel 导入、特殊关系维护。"""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import storage
from ...core.excel_import import auto_import
from ...core.models import GENDERS, HEIGHTS, TALK_CHATTY, TALK_LEVELS, TALK_NORMAL, TALK_QUIET, Student
from .. import theme
from ..context import AppContext
from ..dialogs import OptionDelegate, RelationsDialog, write_roster_template
from ..widgets import Card, HLine, PageHeader, Pill, StatTile


# --------------------------------------------------------------------------- #
# 名单 Excel 解析
# --------------------------------------------------------------------------- #


def _normalize_gender(text: str) -> str:
    value = (text or "").strip()
    lower = value.lower()
    if "男" in value or lower in ("m", "male", "boy", "1"):
        return "男"
    if "女" in value or lower in ("f", "female", "girl", "0", "2"):
        return "女"
    return "男"


def _normalize_height(text: str) -> str:
    value = (text or "").strip()
    if value in HEIGHTS:
        return value
    if "低" in value or "矮" in value:
        return "低"
    if "高" in value:
        return "高"
    if "中" in value:
        return "中"
    lower = value.lower()
    if lower in ("low", "l", "short"):
        return "低"
    if lower in ("high", "h", "tall"):
        return "高"
    if lower in ("mid", "m", "middle", "medium"):
        return "中"
    # 兼容直接填厘米数
    try:
        number = float(value.replace("cm", "").replace("厘米", ""))
    except ValueError:
        return "中"
    if number < 162:
        return "低"
    if number < 176:
        return "中"
    return "高"


def _normalize_talk(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return TALK_NORMAL
    if "不爱" in value or "安静" in value or "内向" in value or "少" in value:
        return TALK_QUIET
    if "爱说" in value or "话多" in value or "特别" in value or "多" in value:
        return TALK_CHATTY
    if "一般" in value or "中" in value or "普通" in value:
        return TALK_NORMAL
    return TALK_NORMAL


def read_roster(path: str | Path) -> list[Student]:
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    header_index = None
    columns: dict[str, int] = {}
    for index, row in enumerate(rows[:10]):
        texts = [str(v).strip() if v is not None else "" for v in row]
        if any("姓名" in text for text in texts):
            header_index = index
            for position, text in enumerate(texts):
                if "姓名" in text:
                    columns.setdefault("name", position)
                elif "性别" in text:
                    columns.setdefault("gender", position)
                elif "身高" in text:
                    columns.setdefault("height", position)
                elif "爱说话" in text or "说话" in text or "话多" in text:
                    columns.setdefault("talk", position)
                elif "备注" in text:
                    columns.setdefault("note", position)
            break
    if header_index is None:
        raise ValueError("表格里找不到「姓名」表头，请使用下载的名单模板")
    if "name" not in columns:
        columns["name"] = 0

    students: list[Student] = []
    for row in rows[header_index + 1 :]:
        def value(key: str) -> str:
            position = columns.get(key)
            if position is None or position >= len(row):
                return ""
            cell = row[position]
            return "" if cell is None else str(cell).strip()

        name = value("name")
        if not name:
            continue
        students.append(
            Student(
                name=name,
                gender=_normalize_gender(value("gender")),
                height=_normalize_height(value("height")),
                talk=_normalize_talk(value("talk")),
                note=value("note"),
            )
        )
    return students


# --------------------------------------------------------------------------- #
# 页面
# --------------------------------------------------------------------------- #


class StudentsPage(QWidget):
    nextRequested = Signal()

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        self.header = PageHeader(
            "学生名单",
            "录入班级成员。性别决定同桌搭配，身高决定离黑板的远近。",
        )
        next_button = QPushButton("下一步：教室布局  →")
        next_button.setObjectName("Primary")
        next_button.setCursor(Qt.PointingHandCursor)
        next_button.clicked.connect(self.nextRequested.emit)
        self.header.add_action(next_button)
        root.addWidget(self.header)

        # -- 班级信息 + 统计 -------------------------------------------------
        info_card = Card(padding=18, spacing=14)
        top = QHBoxLayout()
        top.setSpacing(12)
        self.class_input = QLineEdit()
        self.class_input.setObjectName("ClassInput")
        self.class_input.setPlaceholderText("给班级起个名字，例如：示例班级")
        self.class_input.setMaximumWidth(360)
        self.class_input.editingFinished.connect(self._on_class_name)
        top.addWidget(self.class_input)

        self.total_pill = Pill("共 0 人", theme.ACCENT, theme.ACCENT_SOFT)
        self.gender_pill = Pill("男 0 · 女 0", theme.MUTED, theme.SURFACE_ALT)
        top.addWidget(self.total_pill)
        top.addWidget(self.gender_pill)
        self.chatty_pill = Pill("爱说话 0 人", theme.DANGER, theme.DANGER_SOFT)
        top.addWidget(self.chatty_pill)
        top.addStretch(1)

        self.relation_pill = Pill("特殊关系 0 组", theme.WARNING, theme.WARNING_SOFT)
        top.addWidget(self.relation_pill)
        info_card.body.addLayout(top)

        info_card.body.addWidget(HLine())

        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.stat_total = StatTile("0", "学生总数")
        self.stat_male = StatTile("0", "男生", theme.ACCENT)
        self.stat_female = StatTile("0", "女生", "#EC4899")
        self.stat_low = StatTile("0", "身高偏低")
        self.stat_mid = StatTile("0", "身高中等")
        self.stat_high = StatTile("0", "身高偏高")
        for widget in (
            self.stat_total, self.stat_male, self.stat_female,
            self.stat_low, self.stat_mid, self.stat_high,
        ):
            stats.addWidget(widget, 1)
        info_card.body.addLayout(stats)
        root.addWidget(info_card)

        # -- 名单表 ----------------------------------------------------------
        table_card = Card(padding=16, spacing=12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        add_button = QPushButton("＋ 添加学生")
        add_button.setObjectName("Ghost")
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.clicked.connect(self._add_student)
        toolbar.addWidget(add_button)

        import_button = QPushButton("导入 Excel")
        import_button.setObjectName("Ghost")
        import_button.setCursor(Qt.PointingHandCursor)
        menu = QMenu(import_button)
        menu.addAction("从名单模板导入…", self._import_roster)
        menu.addAction("从智学网成绩表导入姓名…", self._import_names_from_scores)
        import_button.setMenu(menu)
        toolbar.addWidget(import_button)

        template_button = QPushButton("下载模板")
        template_button.setObjectName("Ghost")
        template_button.setCursor(Qt.PointingHandCursor)
        template_button.clicked.connect(self._download_template)
        toolbar.addWidget(template_button)

        toolbar.addStretch(1)

        self.relation_button = QPushButton("特殊关系")
        self.relation_button.setObjectName("Ghost")
        self.relation_button.setCursor(Qt.PointingHandCursor)
        self.relation_button.clicked.connect(self._open_relations)
        toolbar.addWidget(self.relation_button)

        delete_button = QPushButton("删除选中")
        delete_button.setObjectName("DangerBtn")
        delete_button.setCursor(Qt.PointingHandCursor)
        delete_button.clicked.connect(self._delete_selected)
        toolbar.addWidget(delete_button)
        table_card.body.addLayout(toolbar)

        self.empty_hint = QLabel(
            "还没有学生。点「＋ 添加学生」逐个输入，或点「导入 Excel」用模板批量导入。"
        )
        self.empty_hint.setStyleSheet(
            f"background:{theme.ACCENT_SOFT}; color:{theme.ACCENT};"
            "border-radius:10px; padding:10px 14px; font-size:12px;"
        )
        table_card.body.addWidget(self.empty_hint)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["姓名", "性别", "身高档位", "爱说话程度", "备注"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        palette = self.table.palette()
        palette.setColor(QPalette.Base, QColor("#FFFFFF"))
        self.table.setPalette(palette)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 96)
        self.table.setColumnWidth(2, 112)
        self.table.setColumnWidth(3, 128)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.setItemDelegateForColumn(
            1, OptionDelegate([(g, g) for g in GENDERS], self.table)
        )
        self.table.setItemDelegateForColumn(
            2, OptionDelegate([(h, h) for h in HEIGHTS], self.table)
        )
        self.table.setItemDelegateForColumn(
            3, OptionDelegate([(t, t) for t in TALK_LEVELS], self.table)
        )
        table_card.body.addWidget(self.table, 1)

        hint = QLabel("提示：双击单元格修改；性别、身高直接点开下拉选择。所有修改会自动保存。")
        hint.setObjectName("Faint")
        table_card.body.addWidget(hint)
        root.addWidget(table_card, 1)

        self.refresh()

    # ------------------------------------------------------------------ #
    # 刷新
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        state = self.context.state
        self._loading = True
        self.class_input.setText(state.class_name)
        self.table.setRowCount(len(state.students))
        for row, student in enumerate(state.students):
            name_item = QTableWidgetItem(student.name)
            name_item.setData(Qt.UserRole, student.sid)
            gender_item = QTableWidgetItem(student.gender)
            gender_item.setData(Qt.UserRole, student.gender)
            height_item = QTableWidgetItem(student.height)
            height_item.setData(Qt.UserRole, student.height)
            talk_item = QTableWidgetItem(student.talk)
            talk_item.setData(Qt.UserRole, student.talk)
            note_item = QTableWidgetItem(student.note)
            for column, item in enumerate(
                (name_item, gender_item, height_item, talk_item, note_item)
            ):
                item.setTextAlignment(
                    Qt.AlignVCenter | (Qt.AlignLeft if column in (0, 4) else Qt.AlignHCenter)
                )
                if column == 3 and student.talk == TALK_CHATTY:
                    item.setForeground(QColor(theme.DANGER))
                if row % 2 == 1:
                    item.setBackground(QColor("#F8FAFF"))
                self.table.setItem(row, column, item)
        self._loading = False
        self._refresh_stats()
        self.empty_hint.setVisible(not state.students)

    def _refresh_stats(self) -> None:
        counts = self.context.state.counts()
        self.total_pill.setText(f"共 {counts['total']} 人")
        self.gender_pill.setText(f"男 {counts['male']} · 女 {counts['female']}")
        chatty = sum(1 for s in self.context.state.students if s.talk == TALK_CHATTY)
        self.chatty_pill.setText(f"爱说话 {chatty} 人")
        self.relation_pill.setText(f"特殊关系 {len(self.context.state.relations)} 组")
        self.stat_total.set_value(str(counts["total"]))
        self.stat_male.set_value(str(counts["male"]), theme.ACCENT)
        self.stat_female.set_value(str(counts["female"]), "#EC4899")
        self.stat_low.set_value(str(counts["low"]))
        self.stat_mid.set_value(str(counts["mid"]))
        self.stat_high.set_value(str(counts["high"]))

    # ------------------------------------------------------------------ #
    # 编辑
    # ------------------------------------------------------------------ #
    def _on_class_name(self) -> None:
        text = self.class_input.text().strip()
        if text == self.context.state.class_name:
            return
        self.context.state.class_name = text
        self.context.save()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        row = item.row()
        column = item.column()
        if not (0 <= row < len(self.context.state.students)):
            return
        student = self.context.state.students[row]
        text = item.text().strip()
        self._loading = True
        try:
            if column == 0:
                student.name = text
            elif column == 1:
                # 以单元格显示的文字为准（用户直接输入或下拉选择都走这里），
                # UserRole 只在文字非法时兜底，并在校验后同步回去。
                value = text if text in GENDERS else (item.data(Qt.UserRole) or student.gender)
                if value not in GENDERS:
                    value = student.gender
                student.gender = value
                if item.text() != value:
                    item.setText(value)
                if item.data(Qt.UserRole) != value:
                    item.setData(Qt.UserRole, value)
            elif column == 2:
                value = text if text in HEIGHTS else (item.data(Qt.UserRole) or student.height)
                if value not in HEIGHTS:
                    value = student.height
                student.height = value
                if item.text() != value:
                    item.setText(value)
                if item.data(Qt.UserRole) != value:
                    item.setData(Qt.UserRole, value)
            elif column == 3:
                value = text if text in TALK_LEVELS else (item.data(Qt.UserRole) or student.talk)
                if value not in TALK_LEVELS:
                    value = student.talk
                student.talk = value
                if item.text() != value:
                    item.setText(value)
                if item.data(Qt.UserRole) != value:
                    item.setData(Qt.UserRole, value)
                item.setForeground(QColor(theme.DANGER if value == TALK_CHATTY else theme.TEXT))
            elif column == 4:
                student.note = text
        finally:
            self._loading = False
        self.context.invalidate_plan()
        self.context.save()
        self._refresh_stats()

    def _add_student(self) -> None:
        self.context.state.students.append(Student(name="新同学"))
        self.context.invalidate_plan()
        self.context.save()
        self.refresh()
        row = self.table.rowCount() - 1
        self.table.scrollToBottom()
        index = self.table.model().index(row, 0)
        self.table.setCurrentIndex(index)
        self.table.edit(index)

    def _delete_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "删除学生", "请先在表格里选中要删除的行。")
            return
        names = [self.context.state.students[r].name for r in rows if r < len(self.context.state.students)]
        answer = QMessageBox.question(
            self,
            "删除学生",
            f"确定删除这 {len(rows)} 名学生吗？\n" + "、".join(names[:8]) + ("…" if len(names) > 8 else ""),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        for row in rows:
            if 0 <= row < len(self.context.state.students):
                del self.context.state.students[row]
        valid = {s.sid for s in self.context.state.students}
        self.context.state.relations = [
            r for r in self.context.state.relations if r.a in valid and r.b in valid
        ]
        self.context.invalidate_plan()
        self.context.save()
        self.refresh()

    # ------------------------------------------------------------------ #
    # 特殊关系
    # ------------------------------------------------------------------ #
    def _open_relations(self) -> None:
        if len(self.context.state.students) < 2:
            QMessageBox.information(self, "特殊关系", "至少需要 2 名学生才能建立关系。")
            return
        dialog = RelationsDialog(
            self.context.state.students,
            self.context.state.relations,
            self,
        )
        if dialog.exec():
            self.context.state.relations = dialog.relations
            self.context.invalidate_plan()
            self.context.save()
            self._refresh_stats()

    # ------------------------------------------------------------------ #
    # 导入
    # ------------------------------------------------------------------ #
    def _import_roster(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择名单 Excel", str(Path.home()), "Excel 文件 (*.xlsx *.xlsm)"
        )
        if not path:
            return
        try:
            students = read_roster(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        if not students:
            QMessageBox.warning(self, "导入失败", "表格里没有读到任何学生。")
            return
        self._apply_import(students, f"名单「{Path(path).name}」共 {len(students)} 人")

    def _import_names_from_scores(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择智学网成绩表", str(Path.home()), "Excel 文件 (*.xlsx *.xlsm)"
        )
        if not path:
            return
        try:
            result = auto_import(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        existing = {s.name.strip() for s in self.context.state.students}
        students = [
            Student(name=row.name)
            for row in result.rows
            if row.name.strip() and row.name.strip() not in existing
        ]
        if not students:
            QMessageBox.information(self, "导入姓名", "成绩表里的学生都已经在名单里了。")
            return
        self._apply_import(
            students,
            f"从成绩表补充了 {len(students)} 名学生（性别、身高请再核对）",
            append_only=True,
        )

    def _apply_import(self, students: list[Student], message: str, append_only: bool = False) -> None:
        if append_only:
            self.context.state.students.extend(students)
        else:
            box = QMessageBox(self)
            box.setWindowTitle("导入方式")
            box.setText(f"{message}\n\n要替换现有名单，还是追加到后面？")
            replace = box.addButton("替换现有名单", QMessageBox.AcceptRole)
            append = box.addButton("追加", QMessageBox.ActionRole)
            cancel = box.addButton("取消", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is cancel:
                return
            if box.clickedButton() is replace:
                self.context.state.students = students
                self.context.state.relations = []
            else:
                existing = {s.name.strip() for s in self.context.state.students}
                self.context.state.students.extend(
                    s for s in students if s.name.strip() not in existing
                )
        self.context.invalidate_plan()
        self.context.save()
        self.refresh()
        QMessageBox.information(self, "导入完成", message)

    def _download_template(self) -> None:
        default = str(storage.exports_dir() / "学生名单模板.xlsx")
        path, _ = QFileDialog.getSaveFileName(
            self, "保存名单模板", default, "Excel 文件 (*.xlsx)"
        )
        if not path:
            return
        try:
            write_roster_template(path)
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        QMessageBox.information(self, "模板已生成", f"已保存到：\n{path}\n\n填好后回到这里点「导入 Excel」。")
