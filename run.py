"""启动入口（源码运行与打包后通用）。

把项目根目录加入 sys.path 后启动 Qt 界面。
如果启动失败，会把 traceback 写到程序目录的「启动错误.log」，方便排查。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return ROOT


def _write_crash() -> None:
    text = traceback.format_exc()
    for base in (_base_dir(), Path.home()):
        try:
            (base / "启动错误.log").write_text(text, encoding="utf-8")
            return
        except Exception:
            continue


try:
    from app.main import main  # noqa: E402
except BaseException:
    _write_crash()
    raise

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        try:
            from app.core import storage

            marker = storage.data_dir() / "selftest.txt"
            marker.write_text("ok", encoding="utf-8")
            if sys.stdout:
                print("selftest ok:", marker)
        except BaseException:
            _write_crash()
            sys.exit(2)
        sys.exit(0)
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        _write_crash()
        raise
