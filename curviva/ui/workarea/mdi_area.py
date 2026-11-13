"""中间工作区：QMdiArea 多文档容器（对标 Origin 的工作区窗口）。

每个表格 / 图形 / 图片是一个独立子窗口，支持最小化、最大化、还原、
关闭、拖动、层叠、平铺，以及通过「窗口管理」菜单单独显示或隐藏。
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QLabel, QMdiArea


class WorkareaMdiArea(QMdiArea):
    active_changed = Signal(object)          # 当前激活的子窗口（或 None）
    window_list_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workareaMdi")
        self.setViewMode(QMdiArea.SubWindowView)
        self.setTabsClosable(False)
        self.setTabsMovable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackground(QBrush(QColor("#8C8C8C")))
        self.setOption(QMdiArea.DontMaximizeSubWindowOnActivation, False)
        self.subWindowActivated.connect(self.active_changed.emit)

    # ------------------------------------------------------------------
    def resizeEvent(self, event):                    # noqa: N802 (Qt 命名)
        super().resizeEvent(event)

    def _sync_hint(self) -> None:
        """空工作区提示已按需求移除（打开时中间什么都不显示）。"""
        return

    # ------------------------------------------------------------------
    def windows(self) -> list:
        return list(self.subWindowList())

    def find(self, kind: str, doc_id: str):
        for sw in self.windows():
            if getattr(sw, "doc_kind", "") == kind and \
                    getattr(sw, "doc_id", "") == doc_id:
                return sw
        return None

    def active(self):
        return self.activeSubWindow()

    def activate(self, sw) -> None:
        if sw is None:
            return
        sw.show()
        if sw.isMinimized():
            sw.showNormal()
        self.setActiveSubWindow(sw)
        sw.raise_()

    def cascade_all(self) -> None:
        self.cascadeSubWindows()
        self.window_list_changed.emit()

    def tile_all(self) -> None:
        self.tileSubWindows()
        self.window_list_changed.emit()

    def minimize_all(self) -> None:
        for sw in self.windows():
            sw.showMinimized()
            if hasattr(sw, "document"):
                sw.document.minimized = True
        self.window_list_changed.emit()

    def restore_all(self) -> None:
        for sw in self.windows():
            sw.showNormal()
            sw.show()
            if hasattr(sw, "document"):
                sw.document.minimized = False
        self.window_list_changed.emit()

    def close_all(self) -> None:
        for sw in list(self.windows()):
            sw.close()
        self._sync_hint()
        self.window_list_changed.emit()

    def set_window_visible(self, sw, visible: bool) -> None:
        if sw is None:
            return
        sw.setVisible(bool(visible))
        if hasattr(sw, "document"):
            sw.document.visible = bool(visible)
        if visible:
            self.activate(sw)
        self._sync_hint()
        self.window_list_changed.emit()

    def add_window(self, sw):
        self.addSubWindow(sw)
        self._sync_hint()
        self.window_list_changed.emit()
        return sw
