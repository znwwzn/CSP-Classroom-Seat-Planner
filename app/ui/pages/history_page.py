"""历史记录页：每次排座自动存档，可回看、导出、删除。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core import storage
from ...core.excel_export import export_plan
from ...core.models import PlanRecord
from .. import theme
from ..context import AppContext
from ..widgets import Card, PageHeader, Pill


class HistoryPage(QWidget):
    viewRequested = Signal(object)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._checked: set[str] = set()
        self._cards: list[tuple[PlanRecord, QCheckBox]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.header = PageHeader(
            "历史记录",
            "每次生成座位都会自动存档，最多保留 80 次。",
        )
        root.addWidget(self.header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.batch_toggle = QCheckBox("批量选择")
        self.batch_toggle.setCursor(Qt.PointingHandCursor)
        self.batch_toggle.toggled.connect(self._on_batch_toggled)
        toolbar.addWidget(self.batch_toggle)
        toolbar.addSpacing(8)

        self.select_all_button = QPushButton("全选")
        self.select_all_button.setObjectName("Ghost")
        self.select_all_button.setCursor(Qt.PointingHandCursor)
        self.select_all_button.clicked.connect(self._toggle_all)
        self.select_all_button.setVisible(False)
        toolbar.addWidget(self.select_all_button)

        self.batch_count = QLabel("")
        self.batch_count.setObjectName("Muted")
        toolbar.addWidget(self.batch_count)
        toolbar.addStretch(1)

        self.batch_export_button = QPushButton("导出选中")
        self.batch_export_button.setObjectName("Ghost")
        self.batch_export_button.setCursor(Qt.PointingHandCursor)
        self.batch_export_button.clicked.connect(self._export_selected)
        self.batch_export_button.setVisible(False)
        toolbar.addWidget(self.batch_export_button)

        self.batch_delete_button = QPushButton("删除选中")
        self.batch_delete_button.setObjectName("DangerBtn")
        self.batch_delete_button.setCursor(Qt.PointingHandCursor)
        self.batch_delete_button.clicked.connect(self._delete_selected)
        self.batch_delete_button.setVisible(False)
        toolbar.addWidget(self.batch_delete_button)
        root.addLayout(toolbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        holder = QWidget()
        self.list_layout = QVBoxLayout(holder)
        self.list_layout.setContentsMargins(0, 0, 6, 0)
        self.list_layout.setSpacing(10)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(holder)
        root.addWidget(self.scroll, 1)

        self.empty = QLabel("还没有排座记录。到「开始排座」生成一次后，这里就会留下存档。")
        self.empty.setObjectName("Muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setMinimumHeight(200)
        root.addWidget(self.empty)

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        records = storage.load_history()
        self._cards.clear()
        self._checked &= {record.pid for record in records}
        self.empty.setVisible(not records)
        self.scroll.setVisible(bool(records))
        for record in records:
            card, check = self._make_card(record)
            self._cards.append((record, check))
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)
        self.batch_toggle.setEnabled(bool(records))
        if not records and self.batch_toggle.isChecked():
            self.batch_toggle.setChecked(False)
        self._update_batch_state()

    # ------------------------------------------------------------------ #
    # 批量选择
    # ------------------------------------------------------------------ #
    def _on_batch_toggled(self, checked: bool) -> None:
        self.select_all_button.setVisible(checked)
        self.batch_export_button.setVisible(checked)
        self.batch_delete_button.setVisible(checked)
        for _, check in self._cards:
            check.setVisible(checked)
        if not checked:
            for _, check in self._cards:
                check.blockSignals(True)
                check.setChecked(False)
                check.blockSignals(False)
            self._checked.clear()
        self._update_batch_state()

    def _on_check(self, pid: str, checked: bool) -> None:
        if checked:
            self._checked.add(pid)
        else:
            self._checked.discard(pid)
        self._update_batch_state()

    def _update_batch_state(self) -> None:
        batch = self.batch_toggle.isChecked()
        count = len(self._checked)
        self.batch_count.setText(f"已选 {count} 条" if batch else "")
        self.batch_export_button.setEnabled(count > 0)
        self.batch_delete_button.setEnabled(count > 0)
        all_checked = bool(self._cards) and count == len(self._cards)
        self.select_all_button.setText("取消全选" if all_checked else "全选")

    def _toggle_all(self) -> None:
        target = not (bool(self._cards) and len(self._checked) == len(self._cards))
        for _, check in self._cards:
            check.setChecked(target)
        self._checked = {record.pid for record, _ in self._cards} if target else set()
        self._update_batch_state()

    def _export_selected(self) -> None:
        records = [record for record, _ in self._cards if record.pid in self._checked]
        if not records:
            QMessageBox.information(self, "导出选中", "请先勾选要导出的记录。")
            return
        directory = QFileDialog.getExistingDirectory(
            self, "选择导出文件夹", str(storage.exports_dir())
        )
        if not directory:
            return
        folder = Path(directory)
        exported = 0
        failed: list[str] = []
        for record in records:
            safe = "".join(
                ch for ch in f"{record.class_name or '班级'}座位表_{record.created_at}"
                if ch not in '\\/:*?"<>|'
            ).strip() or "座位表"
            path = folder / f"{safe}.xlsx"
            index = 2
            while path.exists():
                path = folder / f"{safe}_{index}.xlsx"
                index += 1
            try:
                export_plan(record, path)
                exported += 1
            except OSError:
                failed.append(record.created_at)
        message = f"已导出 {exported} 份到：\n{folder}"
        if failed:
            message += "\n\n失败：" + "、".join(failed)
        QMessageBox.information(self, "批量导出", message)

    def _delete_selected(self) -> None:
        records = [record for record, _ in self._cards if record.pid in self._checked]
        if not records:
            QMessageBox.information(self, "删除选中", "请先勾选要删除的记录。")
            return
        answer = QMessageBox.question(
            self,
            "删除选中",
            f"确定删除选中的 {len(records)} 条排座记录吗？删除后无法恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        remaining = [record for record in storage.load_history() if record.pid not in self._checked]
        storage.save_history(remaining)
        self._checked.clear()
        self.refresh()

    def _make_card(self, record: PlanRecord) -> tuple[QWidget, QCheckBox]:
        card = QFrame()
        card.setObjectName("Card")
        row = QHBoxLayout(card)
        row.setContentsMargins(18, 14, 16, 14)
        row.setSpacing(14)

        check = QCheckBox()
        check.setCursor(Qt.PointingHandCursor)
        check.setChecked(record.pid in self._checked)
        check.setVisible(self.batch_toggle.isChecked())
        check.setToolTip("勾选后可批量导出或删除")
        check.toggled.connect(lambda checked, pid=record.pid: self._on_check(pid, checked))
        row.addWidget(check)

        color_bar = QLabel()
        color_bar.setFixedSize(4, 44)
        color_bar.setStyleSheet(f"background:{theme.ACCENT}; border-radius:2px;")
        row.addWidget(color_bar)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        title = QLabel(record.created_at or "未记录时间")
        title.setStyleSheet(f"font-size:14px; font-weight:700; color:{theme.TEXT};")
        text_col.addWidget(title)

        stats = record.stats or {}
        bits = [record.class_name or "班级"]
        bits.append(f"{len(record.students)} 人")
        bits.append(f"{len(record.groups)} 组")
        if stats.get("height_ok") is not None:
            bits.append(f"身高匹配 {stats['height_ok']:.0%}")
        if stats.get("gender_ok") is not None:
            bits.append(f"同桌搭配 {stats['gender_ok']:.0%}")
        conflicts = int(
            stats.get("conflicts")
            if stats.get("conflicts") is not None
            else int(stats.get("must_conflicts", 0)) + int(stats.get("prefer_conflicts", 0))
        )
        bits.append("无冲突" if conflicts == 0 else f"{conflicts} 处冲突")
        if record.source_file:
            source = record.source_file
            bits.append(source if len(source) <= 24 else source[:22] + "…")
        subtitle = QLabel("　·　".join(bits))
        subtitle.setObjectName("Faint")
        subtitle.setToolTip("　·　".join(bits))
        subtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        text_col.addWidget(subtitle)
        row.addLayout(text_col, 1)

        if conflicts == 0:
            row.addWidget(Pill("无冲突", theme.SUCCESS, theme.SUCCESS_SOFT))
        else:
            row.addWidget(Pill(f"{conflicts} 处冲突", theme.WARNING, theme.WARNING_SOFT))

        view_button = QPushButton("查看")
        view_button.setObjectName("Ghost")
        view_button.setCursor(Qt.PointingHandCursor)
        view_button.clicked.connect(lambda _=False, r=record: self.viewRequested.emit(r))
        row.addWidget(view_button)

        export_button = QPushButton("导出")
        export_button.setObjectName("Ghost")
        export_button.setCursor(Qt.PointingHandCursor)
        export_button.clicked.connect(lambda _=False, r=record: self._export(r))
        row.addWidget(export_button)

        delete_button = QPushButton("删除")
        delete_button.setObjectName("DangerBtn")
        delete_button.setCursor(Qt.PointingHandCursor)
        delete_button.clicked.connect(lambda _=False, r=record: self._delete(r))
        row.addWidget(delete_button)
        return card, check

    def _export(self, record: PlanRecord) -> None:
        base = f"{record.class_name or '班级'}座位表_{record.created_at.replace(':', '').replace(' ', '_')}"
        default = str(storage.exports_dir() / f"{base}.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "导出座位表", default, "Excel 文件 (*.xlsx)")
        if not path:
            return
        try:
            export_plan(record, path)
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出成功", f"已导出到：\n{path}")

    def _delete(self, record: PlanRecord) -> None:
        answer = QMessageBox.question(
            self,
            "删除记录",
            f"确定删除 {record.created_at} 的这次排座记录吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        storage.delete_history(record.pid)
        self.refresh()
