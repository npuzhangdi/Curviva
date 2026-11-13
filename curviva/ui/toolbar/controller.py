"""上下文工具栏域「控制调用文件」。

ToolbarController 是顶部非菜单栏工具栏对外的唯一入口：创建工具栏、
转发工作区「当前选中对象」、提供显示隐藏开关供窗口管理菜单使用。
"""

from curviva.ui.toolbar.context_toolbar import ContextToolBar


class ToolbarController:
    def __init__(self, app, ui, window):
        self.app = app
        self.ui = ui
        self.window = window
        self.bar = ContextToolBar(ui, window)
        window.addToolBar(self.bar)

    # ------------------------------------------------------------------
    def set_context(self, kind: str, doc_id: str, title: str, sw) -> None:
        self.bar.set_context(kind, doc_id, title, sw)

    def sync_mode(self, mode: str) -> None:
        self.bar.sync_mode(mode)

    def toggle_action(self):
        action = self.bar.toggleViewAction()
        action.setText("上下文工具栏")
        action.setToolTip("显示 / 隐藏随选中对象切换的工具栏")
        return action

    def set_visible(self, visible: bool) -> None:
        self.bar.setVisible(bool(visible))

    def is_visible(self) -> bool:
        return self.bar.isVisible()
