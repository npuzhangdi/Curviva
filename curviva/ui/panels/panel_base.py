"""属性面板基类：统一约定 changed 信号与 bind 接口。"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class PanelBase(QWidget):
    """所有属性面板的基类。

    约定：
    - 面板不自行渲染，只修改 PlotConfig 并发出 changed 信号；
    - MainWindow 统一接收信号后调用画布重绘并刷新其他面板的动态选项。
    """

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = None
        self._data_manager = None

    def bind(self, config, data_manager) -> None:
        """绑定配置对象与数据管理器。"""
        self._config = config
        self._data_manager = data_manager
        self.refresh_dynamic()

    def refresh_dynamic(self) -> None:
        """刷新依赖数据集/子图数量的动态选项（子类按需覆写）。"""
        pass
