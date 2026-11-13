"""Curviva 启动入口。

用法：
    python main.py
"""

import sys

# --- 兼容性预加载（必须位于任何 PySide6 导入之前）---
# 根因：Python 3.12 下，PySide6 安装的 shiboken 签名特性钩子会在处理
# six 虚拟模块时抛出 AttributeError('_SixMetaPathImporter' object has
# no attribute '_path')。先导入 matplotlib.dates（连带加载 dateutil/six），
# 使其在钩子安装前完成加载，即可完全规避。
try:
    import matplotlib.dates  # noqa: F401
except Exception:  # pragma: no cover - 缺依赖时由后续正式导入给出明确报错
    pass

from PySide6.QtWidgets import QApplication

from curviva import __app_name__, __version__
from curviva.controller import AppController
from curviva.ui import theme
from curviva.ui.controller import UIController
from curviva.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationDisplayName(f"{__app_name__} v{__version__}")

    # 先应用主题（圆角 + 玻璃质感），再创建总控与界面控制器
    theme.apply_theme(app)

    controller = AppController()          # 总控：组合各功能域 controller
    ui = UIController(controller)         # 界面域：装配面板与主题
    window = MainWindow(controller, ui)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
