"""跨页共享的应用状态。"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from ..core import storage
from ..core.excel_import import ImportResult, MatchResult
from ..core.grouping import GroupPlan
from ..core.models import AppState, PlanRecord


@dataclass
class Runtime:
    import_result: ImportResult | None = None
    match: MatchResult | None = None
    plan: GroupPlan | None = None
    area_map: dict[str, int] = field(default_factory=dict)
    record: PlanRecord | None = None
    generation: int = 0
    focus_sids: set[str] = field(default_factory=set)
    focus_touched: bool = False
    focus_dirty: bool = False


class AppContext(QObject):
    saved = Signal(bool)

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self.runtime = Runtime()

    # -- 持久化 -------------------------------------------------------------
    def save(self) -> bool:
        try:
            storage.save_state(self.state)
        except OSError:
            self.saved.emit(False)
            return False
        self.saved.emit(True)
        return True

    # -- 便捷访问 -----------------------------------------------------------
    @property
    def students(self):
        return self.state.students

    @property
    def layout(self):
        return self.state.layout

    @property
    def preferences(self):
        return self.state.preferences

    def student_by_id(self, sid: str):
        return self.state.student_by_id(sid)

    def invalidate_plan(self) -> None:
        self.runtime.plan = None
        self.runtime.area_map = {}
        self.runtime.record = None

    def clear_scores(self) -> None:
        self.runtime.import_result = None
        self.runtime.match = None
        self.invalidate_plan()
