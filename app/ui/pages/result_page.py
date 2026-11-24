"""排座结果页：座位图、拖拽微调、冲突提示、导出。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core import storage
from ...core.excel_export import export_plan
from ...core.models import PlanRecord, Student, fits_neighbor
from ...core.seating import SeatingModel, analyze, reassign
from .. import theme
from ..context import AppContext
from ..seat_canvas import SeatCanvas
from ..widgets import Card, HLine, PageHeader, Pill, StatTile


class ResultPage(QWidget):
    backRequested = Signal()
    regenerateRequested = Signal()

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.record: PlanRecord | None = None
        self.model: SeatingModel | None = None
        self.readonly = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.header = PageHeader("排座结果", "")
        back_button = QPushButton("← 返回调整")
        back_button.setObjectName("Ghost")
        back_button.setCursor(Qt.PointingHandCursor)
        back_button.clicked.connect(self.backRequested.emit)
        self.header.add_action(back_button)

        self.regenerate_button = QPushButton("换一版")
        self.regenerate_button.setObjectName("Ghost")
        self.regenerate_button.setCursor(Qt.PointingHandCursor)
        self.regenerate_button.clicked.connect(self.regenerateRequested.emit)
        self.header.add_action(self.regenerate_button)

        self.optimize_button = QPushButton("优化爱说话周围")
        self.optimize_button.setObjectName("Ghost")
        self.optimize_button.setCursor(Qt.PointingHandCursor)
        self.optimize_button.setToolTip("把爱说话同学周围不合格的同桌/邻座换走，可能轻微影响小组均分")
        self.optimize_button.clicked.connect(self._optimize_chatty)
        self.header.add_action(self.optimize_button)
        self.optimize_button.setVisible(False)

        export_button = QPushButton("导出 Excel")
        export_button.setObjectName("Primary")
        export_button.setCursor(Qt.PointingHandCursor)
        export_button.clicked.connect(self._export)
        self.header.add_action(export_button)
        root.addWidget(self.header)

        body = QHBoxLayout()
        body.setSpacing(14)

        # -- 座位图 ---------------------------------------------------------
        canvas_card = Card(padding=14, spacing=8)
        title_row = QHBoxLayout()
        title = QLabel("座位图")
        title.setObjectName("CardTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.readonly_pill = Pill("历史记录", theme.WARNING, theme.WARNING_SOFT)
        self.readonly_pill.setVisible(False)
        title_row.addWidget(self.readonly_pill)
        self.canvas_hint = QLabel("拖动姓名到另一个座位即可交换；红色边框表示该座位存在冲突。")
        self.canvas_hint.setObjectName("Faint")
        title_row.addWidget(self.canvas_hint)
        canvas_card.body.addLayout(title_row)

        self.canvas = SeatCanvas(self.context.layout)
        self.canvas.swapRequested.connect(self._on_swap)
        canvas_card.body.addWidget(self.canvas, 1)
        body.addWidget(canvas_card, 1)

        # -- 右侧信息 -------------------------------------------------------
        side = QWidget()
        side.setFixedWidth(320)
        side_col = QVBoxLayout(side)
        side_col.setContentsMargins(0, 0, 0, 0)
        side_col.setSpacing(12)

        stats_card = Card(padding=16, spacing=10)
        title = QLabel("本版质量")
        title.setObjectName("CardTitle")
        stats_card.body.addWidget(title)
        stat_grid = QHBoxLayout()
        stat_grid.setSpacing(6)
        self.stat_seated = StatTile("0", "已安排")
        self.stat_height = StatTile("0%", "身高匹配")
        self.stat_gender = StatTile("—", "同桌搭配")
        self.stat_conflict = StatTile("0", "冲突", theme.SUCCESS)
        for widget in (self.stat_seated, self.stat_height, self.stat_gender, self.stat_conflict):
            stat_grid.addWidget(widget, 1)
        stats_card.body.addLayout(stat_grid)
        stats_card.body.addWidget(HLine())
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(f"color:{theme.MUTED}; font-size:12px;")
        stats_card.body.addWidget(self.summary_label)
        side_col.addWidget(stats_card)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        info_content = QWidget()
        info_col = QVBoxLayout(info_content)
        info_col.setContentsMargins(0, 0, 4, 0)
        info_col.setSpacing(12)

        warn_card = Card(padding=16, spacing=8)
        warn_title = QLabel("提示")
        warn_title.setObjectName("CardTitle")
        warn_card.body.addWidget(warn_title)
        self.warn_label = QLabel("")
        self.warn_label.setWordWrap(True)
        self.warn_label.setStyleSheet(f"color:{theme.WARNING}; font-size:12px; line-height:150%;")
        warn_card.body.addWidget(self.warn_label)
        info_col.addWidget(warn_card)

        conflict_card = Card(padding=16, spacing=8)
        conflict_title = QLabel("需要留意")
        conflict_title.setObjectName("CardTitle")
        conflict_card.body.addWidget(conflict_title)
        self.conflict_label = QLabel("")
        self.conflict_label.setWordWrap(True)
        self.conflict_label.setStyleSheet(f"color:{theme.MUTED}; font-size:12px; line-height:160%;")
        conflict_card.body.addWidget(self.conflict_label)
        info_col.addWidget(conflict_card)

        legend_card = Card(padding=16, spacing=8)
        legend_title = QLabel("区域图例")
        legend_title.setObjectName("CardTitle")
        legend_card.body.addWidget(legend_title)
        self.legend_box = QVBoxLayout()
        self.legend_box.setSpacing(5)
        legend_card.body.addLayout(self.legend_box)
        info_col.addWidget(legend_card)
        info_col.addStretch(1)
        scroll.setWidget(info_content)
        side_col.addWidget(scroll, 1)

        body.addWidget(side)
        root.addLayout(body, 1)

    # ------------------------------------------------------------------ #
    # 载入
    # ------------------------------------------------------------------ #
    def load(self, record: PlanRecord, readonly: bool = False) -> None:
        self.record = record
        self.readonly = readonly
        self.readonly_pill.setVisible(readonly)
        self.regenerate_button.setVisible(not readonly)
        self.canvas_hint.setVisible(not readonly)
        self.model = SeatingModel(record.layout)
        self.header.title.setText("排座结果")
        subtitle = f"{record.class_name or '班级'}　·　{record.created_at}"
        if record.source_file:
            subtitle += f"　·　成绩来源：{record.source_file}"
        self.header.set_subtitle(subtitle)
        self.canvas.set_layout(record.layout)
        self._recompute()
        self._build_legend()

    def _build_legend(self) -> None:
        while self.legend_box.count():
            item = self.legend_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        assert self.record is not None
        layout = self.record.layout
        for area in layout.areas:
            seats = layout.seats_of(area)
            if not seats:
                continue
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background:{area.color_hex}; border-radius:3px;")
            row.addWidget(dot)
            label = QLabel(area.name)
            label.setStyleSheet(f"color:{theme.TEXT}; font-size:12px;")
            row.addWidget(label, 1)
            gid = self.record.area_group.get(area.aid)
            tag = QLabel(f"第 {gid} 组" if gid else "未指定")
            tag.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")
            row.addWidget(tag)
            count = QLabel(f"{len(seats)} 座")
            count.setStyleSheet(f"color:{theme.FAINT}; font-size:11px;")
            row.addWidget(count)
            self.legend_box.addWidget(row_widget)

    # ------------------------------------------------------------------ #
    def _recompute(self) -> None:
        if self.record is None or self.model is None:
            return
        record = self.record
        students = {s.sid: s for s in record.students}
        analysis = analyze(
            self.model,
            record.seats,
            students,
            record.relations,
            record.preferences,
            focus_sids=set(record.focus_sids),
        )
        group_of: dict[str, int] = {}
        for key, sid in record.seats.items():
            if not sid:
                continue
            seat = self.model.seats.get(key)
            if not seat or not seat.area_id:
                continue
            gid = record.area_group.get(seat.area_id)
            if gid:
                group_of[sid] = gid
        self.canvas.set_data(record.seats, students, analysis.seat_flags, group_of)

        total_seats = len(self.model.seats)
        self.stat_seated.set_value(f"{analysis.seated}/{total_seats}")
        self.stat_height.set_value(f"{analysis.height_ok:.0%}")
        if analysis.gender_ok is None:
            self.stat_gender.set_value("—")
        else:
            self.stat_gender.set_value(f"{analysis.gender_ok:.0%}")
        conflicts = len(analysis.conflicts)
        self.stat_conflict.set_value(
            str(conflicts), theme.SUCCESS if conflicts == 0 else theme.DANGER
        )
        has_focus = bool(record.focus_sids)
        self.optimize_button.setVisible(has_focus)
        bad_chatty = analysis.chatty_total - analysis.chatty_ok
        self.optimize_button.setEnabled(bad_chatty > 0)
        self.optimize_button.setText(
            f"优化爱说话周围 ({bad_chatty})" if bad_chatty else "爱说话周围已合格"
        )

        overall = [v["total"] for v in record.scores.values() if v.get("total") is not None]
        summary = [
            f"学生 {len(record.students)} 人　·　座位 {total_seats} 个",
            f"分组 {len(record.groups)} 组",
        ]
        if analysis.chatty_total:
            summary.append(
                f"爱说话关照 {analysis.chatty_ok}/{analysis.chatty_total} 人"
            )
        if overall:
            summary.append(f"班级均分 {sum(overall) / len(overall):.1f}")
        if analysis.unseated:
            names = [students[sid].name for sid in analysis.unseated if sid in students]
            summary.append(f"未安排 {len(names)} 人：" + "、".join(names[:6]))
        self.summary_label.setText("\n".join(summary))

        warnings = list(record.stats.get("warnings", [])) + analysis.group_notes
        deduped: list[str] = []
        for warning in warnings:
            if warning and warning not in deduped:
                deduped.append(warning)
        warnings = deduped
        self.warn_label.setText("\n".join("· " + w for w in warnings[:8]) if warnings else "没有需要注意的布局问题。")
        self.warn_label.setStyleSheet(
            f"color:{theme.WARNING}; font-size:12px; line-height:150%;"
            if warnings
            else f"color:{theme.SUCCESS}; font-size:12px;"
        )

        if analysis.conflicts:
            lines = []
            for conflict in analysis.conflicts[:8]:
                mark = "⛔" if conflict.severity == "hard" else "·"
                lines.append(f"{mark} {conflict.text}")
            if len(analysis.conflicts) > 8:
                lines.append(f"…… 还有 {len(analysis.conflicts) - 8} 条")
            self.conflict_label.setText("\n".join(lines))
            self.conflict_label.setStyleSheet(f"color:{theme.MUTED}; font-size:12px; line-height:160%;")
        elif warnings:
            self.conflict_label.setText("没有硬性冲突，按提示微调即可。")
        else:
            self.conflict_label.setText("所有约束都满足了，可以直接导出。")

    # ------------------------------------------------------------------ #
    def _on_swap(self, source: str, target: str) -> None:
        if self.record is None or self.model is None:
            return
        self.record.seats = reassign(self.model, self.record.seats, source, target)
        self._recompute()

    # ------------------------------------------------------------------ #
    # 爱说话学生：主动调整周围
    # ------------------------------------------------------------------ #
    def _chatty_bad(self, assignment: dict[str, str], students: dict[str, Student]):
        if self.record is None or self.model is None:
            return []
        seat_of = {sid: key for key, sid in assignment.items() if sid in students}
        bad = []
        for sid in self.record.focus_sids:
            target = students.get(sid)
            seat = seat_of.get(sid)
            if target is None or seat is None:
                continue
            for neighbor in self.model.orthogonal.get(seat, []):
                occupant = assignment.get(neighbor)
                if not occupant or occupant == sid:
                    continue
                other = students.get(occupant)
                if other is not None and not fits_neighbor(other, target):
                    bad.append((sid, seat, neighbor, occupant))
        return bad

    def _optimize_chatty(self) -> None:
        if self.record is None or self.model is None:
            return
        students = {s.sid: s for s in self.record.students}
        assignment = dict(self.record.seats)
        before = len(self._chatty_bad(assignment, students))
        if before == 0:
            QMessageBox.information(self, "爱说话关照", "所有勾选的同学，周围已经都是异性或“不爱说话”的同学了。")
            return

        seats = list(assignment.keys())
        for _ in range(200):
            pairs = self._chatty_bad(assignment, students)
            if not pairs:
                break
            improved = False
            for _sid, seat, neighbor, _occupant in pairs:
                best: tuple[int, dict[str, str]] | None = None
                for other in seats:
                    if other in (seat, neighbor):
                        continue
                    trial = dict(assignment)
                    trial[neighbor], trial[other] = trial.get(other), trial.get(neighbor)
                    bad = len(self._chatty_bad(trial, students))
                    if bad < len(pairs) and (best is None or bad < best[0]):
                        best = (bad, trial)
                if best is not None:
                    assignment = best[1]
                    improved = True
                    break
            if not improved:
                break

        after = len(self._chatty_bad(assignment, students))
        if after >= before:
            QMessageBox.information(
                self,
                "无法继续优化",
                "在当前的教室布局和小组安排下，已经换不出更合适的位置了。\n"
                "可以点「换一版」重新生成，或直接拖动学生手动调整。",
            )
            return
        self.record.seats = assignment
        self._recompute()
        QMessageBox.information(
            self,
            "已调整周围",
            f"不合格的邻座从 {before} 处降到 {after} 处。\n\n"
            "为了让周围坐满异性/不爱说话的同学，个别学生可能跨组交换，小组均分会有轻微变化。",
        )

    # ------------------------------------------------------------------ #
    def _export(self) -> None:
        if self.record is None:
            return
        base = f"{self.record.class_name or '班级'}座位表"
        default = str(storage.unique_export_path(base))
        path, _ = QFileDialog.getSaveFileName(self, "导出座位表", default, "Excel 文件 (*.xlsx)")
        if not path:
            return
        try:
            export_plan(self.record, path)
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        box = QMessageBox(self)
        box.setWindowTitle("导出成功")
        box.setText(f"已导出到：\n{path}")
        open_button = box.addButton("打开文件夹", QMessageBox.ActionRole)
        box.addButton("好", QMessageBox.AcceptRole)
        box.exec()
        if box.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))
