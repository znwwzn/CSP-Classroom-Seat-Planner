"""本地配置与历史记录的持久化。

数据默认保存在程序目录下的 ``data`` 文件夹（便携式），
可用环境变量 ``SEATPLANNER_DATA`` 覆盖，方便测试与多份配置。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    CELL_BOARD,
    CELL_DESK,
    AppState,
    Layout,
    PlanRecord,
    cell_key,
)

HISTORY_LIMIT = 80


# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #


def app_dir() -> Path:
    """程序所在目录（打包后是 exe 所在目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    override = os.environ.get("SEATPLANNER_DATA")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path

    candidates = [app_dir() / "data"]
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "班级排座助手")

    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return path
        except OSError:
            continue

    # 最后兜底到用户目录
    fallback = Path.home() / ".班级排座助手"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def exports_dir() -> Path:
    path = data_dir() / "导出"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return data_dir() / "config.json"


def history_path() -> Path:
    return data_dir() / "history.json"


# --------------------------------------------------------------------------- #
# 默认布局
# --------------------------------------------------------------------------- #


def demo_layout() -> Layout:
    """一个 48 座、12 个 4 人区域的示例教室，方便第一次打开就有东西可看。"""
    layout = Layout(rows=9, cols=8)
    for c in range(8):
        layout.set_cell(0, c, CELL_BOARD)

    seat_cols = [0, 1, 3, 4, 6, 7]
    for r in range(1, 9):
        for c in seat_cols:
            layout.set_cell(r, c, CELL_DESK)

    index = 0
    for band in range(4):  # 四条横带
        for col_band in range(3):  # 三条竖带
            area = layout.add_area(f"区域 {index + 1}")
            c0 = seat_cols[col_band * 2]
            c1 = seat_cols[col_band * 2 + 1]
            r0 = 1 + band * 2
            for r in (r0, r0 + 1):
                for c in (c0, c1):
                    layout.assign_to_area(area, r, c)
            index += 1
    return layout


# --------------------------------------------------------------------------- #
# 读写
# --------------------------------------------------------------------------- #


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _backup_broken(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        shutil.copy2(path, path.with_name(f"{path.stem}.broken.{stamp}{path.suffix}"))
    except OSError:
        pass


def load_state() -> AppState:
    path = config_path()
    if not path.exists():
        state = AppState(class_name="我的班级", layout=demo_layout())
        save_state(state)
        return state
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppState.from_dict(data)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        _backup_broken(path)
        state = AppState(class_name="我的班级", layout=demo_layout())
        save_state(state)
        return state


def save_state(state: AppState) -> None:
    _atomic_write(
        config_path(),
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
    )


def load_history() -> list[PlanRecord]:
    path = history_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _backup_broken(path)
        return []
    records: list[PlanRecord] = []
    for item in data.get("plans", []):
        try:
            records.append(PlanRecord.from_dict(item))
        except (ValueError, TypeError, KeyError):
            continue
    records.sort(key=lambda p: p.created_at, reverse=True)
    return records


def save_history(records: list[PlanRecord]) -> None:
    payload = {"plans": [r.to_dict() for r in records[:HISTORY_LIMIT]]}
    _atomic_write(
        history_path(),
        json.dumps(payload, ensure_ascii=False, indent=2),
    )


def append_history(record: PlanRecord) -> list[PlanRecord]:
    records = load_history()
    records.insert(0, record)
    records = records[:HISTORY_LIMIT]
    save_history(records)
    return records


def delete_history(pid: str) -> list[PlanRecord]:
    records = [r for r in load_history() if r.pid != pid]
    save_history(records)
    return records


def unique_export_path(name: str) -> Path:
    """在导出目录里生成不重名的文件路径。"""
    safe = "".join(ch for ch in name if ch not in '\\/:*?"<>|').strip() or "座位表"
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = exports_dir() / f"{safe}_{stamp}.xlsx"
    index = 2
    while path.exists():
        path = exports_dir() / f"{safe}_{stamp}_{index}.xlsx"
        index += 1
    return path


def today_text() -> str:
    return datetime.now().strftime("%Y年%m月%d日 %H:%M")
