"""排座页：导入成绩 → 自动分组 → 指定区域 → 生成座位。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...core import storage
from ...core.excel_import import auto_import, import_with_mapping, match_to_students
from ...core.grouping import build_groups, default_area_map
from ...core.models import (
    GENDER_MODES,
    TALK_CHATTY,
    TALK_QUIET,
    Layout,
    PlanRecord,
    Preferences,
    Relation,
    Student,
)
from ...core.seating import solve
from .. import theme
from ..context import AppContext
from ..dialogs import ScoreMappingDialog
from ..widgets import (
    Card,
    ComboBox,
    HLine,
    PageHeader,
    Pill,
    SegmentedControl,
    StatTile,
)


class SeatPage(QWidget):
    generated = Signal(object)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._building = False
        self._area_combos: dict[str, QComboBox] = {}
        self._group_cards: list[QWidget] = []
        self.focus_checks: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.header = PageHeader(
            "开始排座",
            "导入本次智学网成绩，软件会按班排分组，再由你决定每组坐哪个区域。",
        )
        root.addWidget(self.header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 6, 0)
        self.content_layout.setSpacing(14)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.content_layout.addWidget(self._build_score_card())
        self.content_layout.addWidget(self._build_focus_card())
        self.content_layout.addWidget(self._build_group_card())
        self.content_layout.addWidget(self._build_area_card())
        self.content_layout.addWidget(self._build_pref_card())
        self.content_layout.addStretch(1)

        # 底部操作条
        footer = QFrame()
        footer.setObjectName("Card")
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(18, 12, 18, 12)
        footer_row.setSpacing(12)
        self.footer_hint = QLabel("")
        self.footer_hint.setObjectName("Muted")
        footer_row.addWidget(self.footer_hint, 1)
        self.generate_button = QPushButton("生成座位  →")
        self.generate_button.setObjectName("Primary")
        self.generate_button.setCursor(Qt.PointingHandCursor)
        self.generate_button.setMinimumWidth(160)
        self.generate_button.clicked.connect(lambda: self.generate())
        footer_row.addWidget(self.generate_button)
        root.addWidget(footer)

        self.refresh_prefs()

    # ------------------------------------------------------------------ #
    # 构建界面
    # ------------------------------------------------------------------ #
    def _build_score_card(self) -> QWidget:
        card = Card(padding=20, spacing=12)
        head = QHBoxLayout()
        step = QLabel("1")
        step.setObjectName("StepNo")
        step.setFixedSize(22, 22)
        step.setAlignment(Qt.AlignCenter)
        head.addWidget(step)
        title = QLabel("导入本次考试成绩")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.score_pill = Pill("未导入", theme.MUTED, theme.SURFACE_ALT)
        head.addWidget(self.score_pill)
        card.body.addLayout(head)

        self.score_empty = QWidget()
        empty_col = QVBoxLayout(self.score_empty)
        empty_col.setContentsMargins(0, 4, 0, 4)
        empty_col.setSpacing(8)
        hint = QLabel("支持智学网导出的 .xlsx 汇总表；会自动识别「姓名 / 总分 / 班次」列。")
        hint.setObjectName("Muted")
        empty_col.addWidget(hint)
        import_button = QPushButton("选择成绩表…")
        import_button.setObjectName("Ghost")
        import_button.setCursor(Qt.PointingHandCursor)
        import_button.setMaximumWidth(180)
        import_button.clicked.connect(self._import_scores)
        empty_col.addWidget(import_button)
        card.body.addWidget(self.score_empty)

        self.score_info = QWidget()
        info_col = QVBoxLayout(self.score_info)
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.score_file = QLabel("")
        self.score_file.setStyleSheet(f"font-size:13px; font-weight:600; color:{theme.TEXT};")
        row.addWidget(self.score_file, 1)
        self.score_desc = QLabel("")
        self.score_desc.setObjectName("Faint")
        row.addWidget(self.score_desc)
        reimport = QPushButton("重新导入")
        reimport.setObjectName("Ghost")
        reimport.setCursor(Qt.PointingHandCursor)
        reimport.clicked.connect(self._import_scores)
        row.addWidget(reimport)
        mapping = QPushButton("手动指定列")
        mapping.setObjectName("LinkBtn")
        mapping.setCursor(Qt.PointingHandCursor)
        mapping.clicked.connect(self._manual_mapping)
        row.addWidget(mapping)
        info_col.addLayout(row)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        self.stat_matched = StatTile("0", "已匹配学生")
        self.stat_missing = StatTile("0", "名单中缺成绩")
        self.stat_absent = StatTile("0", "缺考/无排名")
        self.stat_class_avg = StatTile("—", "班级平均分")
        for widget in (self.stat_matched, self.stat_missing, self.stat_absent, self.stat_class_avg):
            stats.addWidget(widget, 1)
        info_col.addLayout(stats)
        card.body.addWidget(self.score_info)
        self.score_info.setVisible(False)
        return card

    def _build_group_card(self) -> QWidget:
        card = Card(padding=20, spacing=10)
        head = QHBoxLayout()
        step = QLabel("3")
        step.setObjectName("StepNo")
        step.setFixedSize(22, 22)
        step.setAlignment(Qt.AlignCenter)
        head.addWidget(step)
        title = QLabel("自动分组")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        self.group_pill = Pill("等待成绩", theme.MUTED, theme.SURFACE_ALT)
        head.addWidget(self.group_pill)
        head.addStretch(1)
        hint = QLabel("第 1、2 组为班排最前的尖子组，其余组平均分自动拉平")
        hint.setObjectName("Faint")
        head.addWidget(hint)
        card.body.addLayout(head)

        self.group_scroll = QScrollArea()
        self.group_scroll.setWidgetResizable(True)
        self.group_scroll.setFrameShape(QFrame.NoFrame)
        self.group_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.group_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.group_scroll.setFixedHeight(190)
        self.group_holder = QWidget()
        self.group_row = QHBoxLayout(self.group_holder)
        self.group_row.setContentsMargins(0, 2, 0, 4)
        self.group_row.setSpacing(10)
        self.group_row.addStretch(1)
        self.group_scroll.setWidget(self.group_holder)
        card.body.addWidget(self.group_scroll)

        self.group_empty = QLabel("导入成绩后，这里会显示每个小组的成员和平均分。")
        self.group_empty.setObjectName("Faint")
        self.group_empty.setAlignment(Qt.AlignCenter)
        self.group_empty.setMinimumHeight(120)
        card.body.addWidget(self.group_empty)
        self.group_scroll.setVisible(False)
        return card

    def _build_area_card(self) -> QWidget:
        card = Card(padding=20, spacing=10)
        head = QHBoxLayout()
        step = QLabel("4")
        step.setObjectName("StepNo")
        step.setFixedSize(22, 22)
        step.setAlignment(Qt.AlignCenter)
        head.addWidget(step)
        title = QLabel("指定每个区域坐第几组")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.area_pill = Pill("", theme.MUTED, theme.SURFACE_ALT)
        head.addWidget(self.area_pill)
        card.body.addLayout(head)

        hint = QLabel("下拉框只列出人数不超过该区域座位数的小组；默认按区域顺序一一对应。")
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        card.body.addWidget(hint)

        self.area_container = QWidget()
        self.area_form = QGridLayout(self.area_container)
        self.area_form.setContentsMargins(0, 4, 0, 0)
        self.area_form.setHorizontalSpacing(22)
        self.area_form.setVerticalSpacing(6)
        self.area_form.setColumnStretch(0, 1)
        self.area_form.setColumnStretch(1, 1)
        card.body.addWidget(self.area_container)

        self.area_empty = QLabel("还没有可用的区域，请先到「教室布局」里画课桌并分组。")
        self.area_empty.setObjectName("Faint")
        card.body.addWidget(self.area_empty)
        return card

    def _build_focus_card(self) -> QWidget:
        card = Card(padding=20, spacing=10)
        head = QHBoxLayout()
        step = QLabel("2")
        step.setObjectName("StepNo")
        step.setFixedSize(22, 22)
        step.setAlignment(Qt.AlignCenter)
        head.addWidget(step)
        title = QLabel("关照爱说话的学生")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.focus_pill = Pill("", theme.MUTED, theme.SURFACE_ALT)
        head.addWidget(self.focus_pill)
        card.body.addLayout(head)

        hint = QLabel(
            "勾选的同学，排座时会尽量让他前后左右都是「异性」或「不爱说话」的同学"
            "（斜角不算；同桌也算相邻）。"
        )
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        card.body.addWidget(hint)

        self.focus_container = QWidget()
        self.focus_form = QGridLayout(self.focus_container)
        self.focus_form.setContentsMargins(0, 4, 0, 0)
        self.focus_form.setHorizontalSpacing(16)
        self.focus_form.setVerticalSpacing(6)
        for column in range(3):
            self.focus_form.setColumnStretch(column, 1)
        card.body.addWidget(self.focus_container)

        self.focus_empty = QLabel(
            "名单里还没有「爱说话」的学生。可以到学生名单把对应同学的“爱说话程度”改成“爱说话”。"
        )
        self.focus_empty.setObjectName("Faint")
        self.focus_empty.setWordWrap(True)
        card.body.addWidget(self.focus_empty)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        select_all = QPushButton("全选")
        select_all.setObjectName("LinkBtn")
        select_all.setCursor(Qt.PointingHandCursor)
        select_all.clicked.connect(lambda: self._select_all_focus(True))
        buttons.addWidget(select_all)
        clear_all = QPushButton("全不选")
        clear_all.setObjectName("LinkBtn")
        clear_all.setCursor(Qt.PointingHandCursor)
        clear_all.clicked.connect(lambda: self._select_all_focus(False))
        buttons.addWidget(clear_all)
        buttons.addStretch(1)
        self.focus_apply_button = QPushButton("应用并重新分组")
        self.focus_apply_button.setObjectName("Ghost")
        self.focus_apply_button.setCursor(Qt.PointingHandCursor)
        self.focus_apply_button.setEnabled(False)
        self.focus_apply_button.clicked.connect(self._apply_focus)
        buttons.addWidget(self.focus_apply_button)
        card.body.addLayout(buttons)
        return card

    def _build_pref_card(self) -> QWidget:
        card = Card(padding=20, spacing=12)
        head = QHBoxLayout()
        step = QLabel("5")
        step.setObjectName("StepNo")
        step.setFixedSize(22, 22)
        step.setAlignment(Qt.AlignCenter)
        head.addWidget(step)
        title = QLabel("排座偏好")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        head.addStretch(1)
        hint = QLabel("调整权重，决定冲突时优先保哪一项")
        hint.setObjectName("Faint")
        head.addWidget(hint)
        card.body.addLayout(head)

        gender_row = QHBoxLayout()
        gender_row.setSpacing(12)
        gender_label = QLabel("同桌性别")
        gender_label.setMinimumWidth(70)
        gender_row.addWidget(gender_label)
        self.gender_seg = SegmentedControl(list(GENDER_MODES), self.context.preferences.gender_mode)
        self.gender_seg.changed.connect(self._on_gender_mode)
        gender_row.addWidget(self.gender_seg, 1)
        card.body.addLayout(gender_row)

        card.body.addWidget(HLine())
        self.sliders: dict[str, QSlider] = {}
        self.slider_labels: dict[str, QLabel] = {}
        specs = [
            ("height_weight", "身高：前低后高", "靠近黑板坐矮个，远离黑板坐高个"),
            ("gender_weight", "性别：同桌搭配", "同桌同性/异性不符合时扣分"),
            ("relation_weight", "关系：分开坐", "情侣、好友等尽量不坐在一起"),
            ("talk_weight", "爱说话：周围安排", "四周尽量是异性或不爱说话的同学"),
        ]
        for key, title_text, hint_text in specs:
            row = QHBoxLayout()
            row.setSpacing(14)
            text_col = QVBoxLayout()
            text_col.setSpacing(1)
            label = QLabel(title_text)
            label.setStyleSheet(f"font-size:13px; font-weight:600; color:{theme.TEXT};")
            text_col.addWidget(label)
            sub = QLabel(hint_text)
            sub.setObjectName("Faint")
            text_col.addWidget(sub)
            text_col_widget = QWidget()
            text_col_widget.setLayout(text_col)
            text_col_widget.setMinimumWidth(210)
            row.addWidget(text_col_widget)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(getattr(self.context.preferences, key))
            slider.setCursor(Qt.PointingHandCursor)
            slider.valueChanged.connect(lambda value, k=key: self._on_slider(k, value))
            row.addWidget(slider, 1)

            value_label = QLabel(f"{getattr(self.context.preferences, key)}%")
            value_label.setMinimumWidth(42)
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_label.setStyleSheet(f"color:{theme.ACCENT}; font-weight:700;")
            row.addWidget(value_label)
            self.sliders[key] = slider
            self.slider_labels[key] = value_label
            card.body.addLayout(row)
        return card

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def on_show(self) -> None:
        self.refresh_from_runtime()

    def refresh_from_runtime(self) -> None:
        runtime = self.context.runtime
        if runtime.import_result:
            self._show_score_info(runtime.import_result)
        else:
            self._show_score_empty()
        self._refresh_focus_list()
        if runtime.import_result and runtime.plan is None:
            self._rebuild_plan()
        else:
            self._refresh_groups()
            self._refresh_area_mapping()
        self._refresh_footer()

    # ------------------------------------------------------------------ #
    # 成绩导入
    # ------------------------------------------------------------------ #
    def _show_score_empty(self) -> None:
        self.score_empty.setVisible(True)
        self.score_info.setVisible(False)
        self.score_pill.setText("未导入")
        self.score_pill.setStyleSheet(
            f"background:{theme.SURFACE_ALT}; color:{theme.MUTED}; border-radius:10px; padding:3px 10px; font-size:12px; font-weight:600;"
        )

    def _show_score_info(self, result) -> None:
        self.score_empty.setVisible(False)
        self.score_info.setVisible(True)
        self.score_file.setText(Path(result.path).name)
        self.score_desc.setText(result.description())
        self.score_pill.setText("已导入")
        self.score_pill.setStyleSheet(
            f"background:{theme.SUCCESS_SOFT}; color:{theme.SUCCESS}; border-radius:10px; padding:3px 10px; font-size:12px; font-weight:600;"
        )
        runtime = self.context.runtime
        match = runtime.match
        if match:
            self.stat_matched.set_value(str(len(match.mapping)), theme.SUCCESS)
            self.stat_missing.set_value(str(len(match.missing_students)))
            total_scores = [row.total for row in result.rows if row.total is not None]
            self.stat_class_avg.set_value(
                f"{sum(total_scores) / len(total_scores):.0f}" if total_scores else "—"
            )
        self.stat_absent.set_value(str(sum(1 for row in result.rows if row.rank is None)))

    def _import_scores(self) -> None:
        if not self.context.students:
            QMessageBox.information(self, "还没有学生", "请先到「学生名单」录入学生，再导入成绩。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择智学网成绩表", str(Path.home()), "Excel 文件 (*.xlsx *.xlsm);;CSV 文件 (*.csv)"
        )
        if not path:
            return
        try:
            result = auto_import(path)
        except (OSError, ValueError) as exc:
            answer = QMessageBox.question(
                self,
                "自动识别失败",
                f"{exc}\n\n要手动指定工作表、表头行和列吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes:
                self._manual_mapping(path)
            return
        self._apply_result(result)

    def _manual_mapping(self, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择成绩表", str(Path.home()), "Excel 文件 (*.xlsx *.xlsm)"
            )
            if not path:
                return
        dialog = ScoreMappingDialog(path, self)
        if not dialog.exec():
            return
        mapping = dialog.mapping()
        if mapping["name_col"] is None:
            QMessageBox.warning(self, "缺少姓名列", "请至少指定「姓名列」。")
            return
        try:
            result = import_with_mapping(
                path,
                mapping["sheet"],
                mapping["header_row"],
                mapping["name_col"],
                mapping["total_col"],
                mapping["rank_col"],
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self._apply_result(result)

    def _apply_result(self, result) -> None:
        match = match_to_students(self.context.students, result)
        if not match.mapping:
            QMessageBox.warning(
                self,
                "没有匹配到学生",
                "成绩表里的姓名和班级名单完全对不上。请检查名单是否已录入，或成绩表是否选错。",
            )
            return
        self.context.runtime.import_result = result
        self.context.runtime.match = match
        self.context.state.last_score_file = str(result.path)
        self.context.invalidate_plan()
        self.context.save()
        self._show_score_info(result)
        if match.missing_students or match.unmatched_rows:
            lines = []
            if match.missing_students:
                lines.append(
                    f"名单里有 {len(match.missing_students)} 人没有成绩，将按缺考处理：\n"
                    + "、".join(match.missing_students[:10])
                    + ("…" if len(match.missing_students) > 10 else "")
                )
            if match.unmatched_rows:
                lines.append(
                    f"成绩表里有 {len(match.unmatched_rows)} 人不在名单中，已忽略：\n"
                    + "、".join(match.unmatched_rows[:10])
                    + ("…" if len(match.unmatched_rows) > 10 else "")
                )
            QMessageBox.information(self, "匹配提示", "\n\n".join(lines))
        self._rebuild_plan()
        self._refresh_footer()

    # ------------------------------------------------------------------ #
    # 分组
    # ------------------------------------------------------------------ #
    def _rebuild_plan(self, preserve_mapping: bool = False) -> None:
        runtime = self.context.runtime
        if runtime.import_result is None or runtime.match is None:
            return
        self._refresh_focus_list()
        layout = self.context.layout
        if not layout.areas or not layout.desks():
            runtime.plan = None
            self._refresh_groups()
            self._refresh_area_mapping()
            return
        old_map = dict(runtime.area_map)
        runtime.plan = build_groups(
            self.context.students,
            runtime.match.mapping,
            layout,
            self.context.state.relations,
            seed=runtime.generation,
            focus_sids=runtime.focus_sids,
        )
        group_count = len(runtime.plan.groups)
        if preserve_mapping and old_map:
            valid_aids = {area.aid for area in layout.areas}
            runtime.area_map = {
                aid: gid
                for aid, gid in old_map.items()
                if aid in valid_aids and 1 <= gid <= group_count
            }
            for aid, gid in default_area_map(layout, group_count).items():
                runtime.area_map.setdefault(aid, gid)
        else:
            runtime.area_map = default_area_map(layout, group_count)
        runtime.focus_dirty = False
        self._update_focus_pill()
        self._refresh_groups()
        self._refresh_area_mapping()
        self._refresh_footer()

    def _refresh_groups(self) -> None:
        self._group_cards.clear()
        while self.group_row.count():
            item = self.group_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.group_row.addStretch(1)

        plan = self.context.runtime.plan
        if plan is None or not plan.groups:
            self.group_scroll.setVisible(False)
            self.group_empty.setVisible(True)
            self.group_pill.setText("等待成绩")
            return

        self.group_scroll.setVisible(True)
        self.group_empty.setVisible(False)
        self.group_pill.setText(f"{len(plan.groups)} 组")
        match = self.context.runtime.match
        mapping = match.mapping if match else {}
        area_colors = {a.aid: a.color_hex for a in self.context.layout.areas}

        for group in plan.groups:
            card = self._make_group_card(group, mapping, plan, area_colors)
            self._group_cards.append(card)
            self.group_row.insertWidget(self.group_row.count() - 1, card)

    def _make_group_card(self, group, mapping, plan, area_colors) -> QWidget:
        card = QFrame()
        card.setObjectName("SoftCard")
        card.setFixedWidth(196)
        card.setMinimumHeight(120 + ((len(group.members) + 1) // 2) * 26)
        col = QVBoxLayout(card)
        col.setContentsMargins(12, 10, 12, 10)
        col.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel(f"第 {group.gid} 组")
        title.setStyleSheet(f"font-size:13px; font-weight:700; color:{theme.TEXT};")
        head.addWidget(title)
        head.addStretch(1)
        count = Pill(f"{len(group.members)} 人", theme.MUTED, theme.SURFACE)
        head.addWidget(count)
        col.addLayout(head)

        scores = [
            mapping[m.sid].total
            for m in group.members
            if m.sid in mapping and mapping[m.sid].total is not None
        ]
        avg = sum(scores) / len(scores) if scores else 0.0
        avg_label = QLabel(f"均分 {avg:.1f}" if scores else "无成绩")
        avg_label.setStyleSheet(f"font-size:11px; color:{theme.MUTED};")
        col.addWidget(avg_label)

        if group.gid <= 2:
            tag = Pill("尖子组", theme.ACCENT, theme.ACCENT_SOFT)
            tag.setMaximumWidth(58)
            col.addWidget(tag)

        chips = QWidget()
        grid = QGridLayout(chips)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        for index, member in enumerate(group.members):
            chip = QLabel(member.name)
            chip.setStyleSheet(
                f"background:white; border:1px solid {theme.BORDER}; border-radius:8px;"
                f"padding:2px 6px; font-size:11px; color:{theme.TEXT};"
            )
            chip.setAlignment(Qt.AlignCenter)
            chip.setToolTip(f"{member.name} · {member.gender} · 身高{member.height}")
            grid.addWidget(chip, index // 2, index % 2)
        col.addWidget(chips, 1)

        if group.gid <= 2:
            card.setStyleSheet(
                f"QFrame#SoftCard{{background:{theme.ACCENT_SOFT}; border:1px solid #CBDCFB; border-radius:12px;}}"
            )
        return card

    # ------------------------------------------------------------------ #
    # 区域映射
    # ------------------------------------------------------------------ #
    def _refresh_area_mapping(self) -> None:
        while self.area_form.count():
            item = self.area_form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._area_combos.clear()

        layout = self.context.layout
        areas = [a for a in layout.areas if layout.seats_of(a)]
        plan = self.context.runtime.plan

        if plan is None:
            self.area_container.setVisible(False)
            self.area_pill.setVisible(False)
            self.area_empty.setText("导入成绩并完成分组后，这里会列出每个区域，供你指定它坐第几组。")
            self.area_empty.setVisible(True)
            return

        if not areas:
            self.area_container.setVisible(False)
            self.area_pill.setVisible(False)
            self.area_empty.setText("还没有可用的区域，请先到「教室布局」里画课桌并分组。")
            self.area_empty.setVisible(True)
            return

        self.area_container.setVisible(True)
        self.area_empty.setVisible(False)
        self.area_pill.setVisible(True)
        self.area_pill.setText(f"{len(areas)} 个区域")
        groups = plan.groups
        current = self.context.runtime.area_map

        for index, area in enumerate(areas):
            seats = len(layout.seats_of(area))
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(10)

            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background:{area.color_hex}; border-radius:3px;")
            row.addWidget(dot)
            name = QLabel(area.name)
            name.setMinimumWidth(90)
            name.setStyleSheet(f"font-size:13px; font-weight:600; color:{theme.TEXT};")
            row.addWidget(name)
            chips = Pill(f"{seats} 座", theme.MUTED, theme.SURFACE_ALT)
            row.addWidget(chips)
            row.addStretch(1)

            combo = ComboBox()
            combo.setMinimumWidth(200)
            valid = False
            for group in groups:
                if group.capacity > seats:
                    continue
                label = f"第 {group.gid} 组"
                if group.capacity < seats:
                    label += f"（{group.capacity} 人，空 {seats - group.capacity} 位）"
                combo.addItem(label, group.gid)
            default_gid = current.get(area.aid)
            if default_gid is None:
                default_gid = groups[index].gid if index < len(groups) else None
            position = combo.findData(default_gid)
            if position >= 0:
                combo.setCurrentIndex(position)
                valid = True
            if combo.count() == 0:
                combo.addItem("没有人数匹配的小组", None)
                combo.setEnabled(False)
            combo.currentIndexChanged.connect(lambda _=0, aid=area.aid: self._on_area_changed(aid))
            row.addWidget(combo)
            self._area_combos[area.aid] = combo
            self.area_form.addWidget(row_widget, index // 2, index % 2)
            if not valid:
                self.context.runtime.area_map.pop(area.aid, None)

        self._sync_area_map()

    def _on_area_changed(self, aid: str) -> None:
        self._sync_area_map()
        self._refresh_footer()

    def _sync_area_map(self) -> None:
        mapping: dict[str, int] = {}
        duplicates = False
        used: set[int] = set()
        for aid, combo in self._area_combos.items():
            gid = combo.currentData()
            if gid is None:
                continue
            if gid in used:
                duplicates = True
            used.add(gid)
            mapping[aid] = gid
        self.context.runtime.area_map = mapping
        self._duplicate_groups = duplicates

    # ------------------------------------------------------------------ #
    # 爱说话学生关照名单
    # ------------------------------------------------------------------ #
    def _refresh_focus_list(self) -> None:
        runtime = self.context.runtime
        chatty = [s for s in self.context.students if s.talk == TALK_CHATTY]
        valid = {s.sid for s in chatty}
        if runtime.focus_touched:
            runtime.focus_sids &= valid
        else:
            runtime.focus_sids = set(valid)

        while self.focus_form.count():
            item = self.focus_form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.focus_checks.clear()

        self.focus_container.setVisible(bool(chatty))
        self.focus_empty.setVisible(not chatty)
        for index, student in enumerate(chatty):
            check = QCheckBox(student.name)
            check.setCursor(Qt.PointingHandCursor)
            check.setChecked(student.sid in runtime.focus_sids)
            check.setToolTip(f"{student.gender} · 身高{student.height} · 爱说话")
            check.toggled.connect(
                lambda checked, sid=student.sid: self._on_focus_toggle(sid, checked)
            )
            self.focus_form.addWidget(check, index // 3, index % 3)
            self.focus_checks[student.sid] = check
        self._update_focus_pill()

    def _on_focus_toggle(self, sid: str, checked: bool) -> None:
        runtime = self.context.runtime
        runtime.focus_touched = True
        if checked:
            runtime.focus_sids.add(sid)
        else:
            runtime.focus_sids.discard(sid)
        runtime.focus_dirty = True
        self._update_focus_pill()
        self._refresh_footer()

    def _select_all_focus(self, checked: bool) -> None:
        runtime = self.context.runtime
        runtime.focus_touched = True
        for sid, check in self.focus_checks.items():
            check.blockSignals(True)
            check.setChecked(checked)
            check.blockSignals(False)
        runtime.focus_sids = set(self.focus_checks) if checked else set()
        runtime.focus_dirty = True
        self._update_focus_pill()
        self._refresh_footer()

    def _apply_focus(self) -> None:
        if not self.context.runtime.focus_dirty:
            return
        self._rebuild_plan(preserve_mapping=True)

    def _update_focus_pill(self) -> None:
        total = len(self.focus_checks)
        chosen = len(self.context.runtime.focus_sids & set(self.focus_checks))
        self.focus_pill.setText(f"已选 {chosen} / {total}" if total else "暂无")
        color = theme.DANGER if chosen else theme.MUTED
        background = theme.DANGER_SOFT if chosen else theme.SURFACE_ALT
        self.focus_pill.setStyleSheet(
            f"background:{background}; color:{color}; border-radius:10px;"
            "padding:3px 10px; font-size:12px; font-weight:600;"
        )
        button = getattr(self, "focus_apply_button", None)
        if button is not None:
            button.setEnabled(self.context.runtime.focus_dirty)

    # ------------------------------------------------------------------ #
    # 偏好
    # ------------------------------------------------------------------ #
    def _on_gender_mode(self, mode: str) -> None:
        self.context.preferences.gender_mode = mode
        self.context.save()

    def _on_slider(self, key: str, value: int) -> None:
        setattr(self.context.preferences, key, value)
        self.slider_labels[key].setText(f"{value}%")
        self.context.save()

    def refresh_prefs(self) -> None:
        self.gender_seg.set_current(self.context.preferences.gender_mode)
        for key, slider in self.sliders.items():
            slider.blockSignals(True)
            slider.setValue(getattr(self.context.preferences, key))
            slider.blockSignals(False)
            self.slider_labels[key].setText(f"{slider.value()}%")

    # ------------------------------------------------------------------ #
    # 底部状态
    # ------------------------------------------------------------------ #
    def _refresh_footer(self) -> None:
        runtime = self.context.runtime
        ready = True
        messages: list[str] = []
        if not self.context.students:
            ready = False
            messages.append("还没有学生")
        if not self.context.layout.areas or not self.context.layout.desks():
            ready = False
            messages.append("还没有教室布局")
        if runtime.import_result is None:
            ready = False
            messages.append("还没有导入成绩")
        elif runtime.plan is None:
            ready = False
            messages.append("请先检查分组")
        elif getattr(self, "_duplicate_groups", False):
            ready = False
            messages.append("有区域重复选择了同一个小组")
        elif runtime.plan.waiting:
            messages.append(f"座位不足，{len(runtime.plan.waiting)} 人将没有座位")
        if runtime.focus_dirty:
            messages.append("关照名单有改动，生成时会自动重新分组")
        if ready and runtime.plan:
            seated = sum(len(g.members) for g in runtime.plan.groups)
            messages.append(
                f"{seated} 人 · {len(runtime.plan.groups)} 组 · {len([a for a in self.context.layout.areas if self.context.layout.seats_of(a)])} 个区域"
            )
        self.footer_hint.setText("　·　".join(messages) if messages else "")
        self.generate_button.setEnabled(ready)

    # ------------------------------------------------------------------ #
    # 生成
    # ------------------------------------------------------------------ #
    def generate(self, seed: int | None = None) -> PlanRecord | None:
        runtime = self.context.runtime
        if runtime.plan is None or runtime.match is None:
            return None
        if runtime.focus_dirty:
            self._rebuild_plan(preserve_mapping=True)
            if runtime.plan is None:
                return None
        if getattr(self, "_duplicate_groups", False):
            QMessageBox.warning(self, "区域重复", "有多个区域选择了同一个小组，请先改成不重复。")
            return None

        layout = self.context.layout
        missing = [a for a in layout.areas if layout.seats_of(a) and a.aid not in runtime.area_map]
        if missing:
            QMessageBox.warning(
                self,
                "还有区域没指定小组",
                "这些区域还没有选择小组：" + "、".join(a.name for a in missing[:5]),
            )
            return None

        seed_value = runtime.generation if seed is None else seed
        solution = solve(
            layout,
            runtime.plan.groups,
            runtime.area_map,
            self.context.students,
            runtime.match.mapping,
            self.context.state.relations,
            self.context.preferences,
            seed=seed_value,
            focus_sids=runtime.focus_sids,
        )
        record = PlanRecord(
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            class_name=self.context.state.class_name,
            source_file=Path(runtime.import_result.path).name if runtime.import_result else "",
            students=[Student.from_dict(s.to_dict()) for s in self.context.students],
            layout=Layout.from_dict(layout.to_dict()),
            preferences=Preferences.from_dict(self.context.preferences.to_dict()),
            relations=[
                Relation.from_dict(r.to_dict())
                for r in self.context.state.relations
            ],
            scores={
                sid: {"total": row.total, "rank": row.rank}
                for sid, row in runtime.match.mapping.items()
            },
            groups=[
                {
                    "gid": g.gid,
                    "capacity": g.capacity,
                    "members": [m.sid for m in g.members],
                }
                for g in runtime.plan.groups
            ],
            area_group=dict(runtime.area_map),
            seats=dict(solution.assignment),
            focus_sids=sorted(runtime.focus_sids),
            stats={
                "height_ok": solution.analysis.height_ok,
                "gender_ok": solution.analysis.gender_ok,
                "must_conflicts": solution.analysis.must_conflicts,
                "prefer_conflicts": solution.analysis.prefer_conflicts,
                "conflicts": len(solution.analysis.conflicts),
                "chatty_total": solution.analysis.chatty_total,
                "chatty_ok": solution.analysis.chatty_ok,
                "warnings": solution.warnings,
            },
        )
        runtime.record = record
        self.generated.emit(record)
        return record
