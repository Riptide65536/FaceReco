from __future__ import annotations

import importlib.util
import sys


def _require(module: str, install_hint: str) -> None:
    if importlib.util.find_spec(module) is None:
        raise SystemExit(
            f"缺少依赖 {module}。\n"
            f"请先安装依赖：{install_hint}\n"
            "推荐使用 Python 3.8-3.10 的虚拟环境。"
        )


def main() -> None:
    if not (sys.version_info.major == 3 and 8 <= sys.version_info.minor <= 10):
        print(
            "警告：当前 Python 版本不是 3.8-3.10，PySide2/OpenCV 可能无法正常安装或运行。\n"
            f"当前解释器：{sys.executable}"
        )
    _require("PySide2", "pip install -r requirements.txt")
    _require("cv2", "pip install -r requirements.txt")
    import main as app_main  # noqa: F401 - main.py starts the Qt application.


if __name__ == "__main__":
    main()
