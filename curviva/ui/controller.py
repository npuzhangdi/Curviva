"""界面域「控制调用文件」。

UIController 负责装配界面：应用主题、创建面板集合、构建中间 MDI 工作区、
上下文工具栏、三个可独立设置的停靠窗口与窗口管理、布局持久化。
MainWindow 只做菜单与信号调度，不直接触碰具体面板类或工作区实现。
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from curviva.ui import theme
from curviva.ui.panels.controller import PROPERTY_TONES, TOOL_TONES, PanelsController
from curviva.ui.window_manager import WindowManager
from curviva.ui.worksheet.controller import WorksheetController
from curviva.ui.worksheet.worksheet_book import WorksheetBook

LEFT_TAB_COLORS = [theme.C_BLUE, theme.C_CYAN, theme.C_VIOLET,
                   theme.C_GREEN, theme.C_ORANGE]


class UIController:
    def __init__(self, app):
        self.app = app
        self.panels = PanelsController(app)
        self.left_tabs = None
        self.right_tabs = None
        self.left_dock = None
        self.right_dock = None
        self.explorer_dock = None
        self.window_manager = None
        self.summary = None

        # 工作表域（多表工作簿作为工作区的一个子窗口，不再是底部 Dock）
        self.worksheet = WorksheetController(app, self)
        self.worksheet_book = WorksheetBook(self.worksheet)
        self.worksheet.attach(self.worksheet_book)

        # 中间工作区与上下文工具栏在 build_center 中创建
        self.workarea = None
        self.toolbar = None

    # ------------------------------------------------------------------
    def apply_theme(self, qapp) -> None:
        theme.apply_theme(qapp)

    def polish(self, window) -> None:
        theme.polish_window(window)

    def brand_logo(self, size: int = 40):
        return theme.brand_logo(size)

    # ------------------------------------------------------------------
    # 中间工作区（必须在菜单构建之前执行）
    # ------------------------------------------------------------------

    def build_center(self, window) -> None:
        from curviva.ui.workarea.controller import WorkareaController
        from curviva.ui.toolbar.controller import ToolbarController
        self.workarea = WorkareaController(self.app, self)
        self.workarea.attach(window)
        self.toolbar = ToolbarController(self.app, self, window)

    def primary_canvas(self):
        return self.workarea.primary_canvas() if self.workarea else None

    def render_graphs(self) -> None:
        if self.workarea is not None:
            self.workarea.render_graphs()

    def sync_from_app(self) -> None:
        try:
            self.worksheet.sync_from_app()
        except Exception:                  # noqa: BLE001
            pass
        if self.workarea is not None:
            self.workarea.sync_from_app()

    # ------------------------------------------------------------------
    def attach(self, window) -> None:
        """把面板信号接到主窗口，并装配停靠区与窗口管理。"""
        self.panels.bind_signals(
            window._on_data_changed, window._on_config_changed, window._load_demo)
        self.window_manager = WindowManager(window, self)
        self.build_docks(window)
        self._register_hooks(window)
        # 布局恢复与初始宽度在窗口显示后执行（此时布局引擎才可用）
        QTimer.singleShot(0, self._after_show)

    def _register_hooks(self, window) -> None:
        """向总控注入 UI 能力，供示例域 / 工作表域 / 脚本调用。"""
        hooks = self.app.hooks
        hooks["open_sheet"] = self.open_sheet
        hooks["load_script"] = self.load_script
        hooks["redraw"] = self.render_graphs
        hooks["open_data_dialog"] = lambda: window.open_data_file()
        hooks["status"] = lambda text: window.statusBar().showMessage(text, 8000)
        hooks["export"] = window._export_hook

    def _after_show(self) -> None:
        if self.window_manager is not None and self.window_manager.has_saved_layout():
            self.window_manager.restore_layout()
        else:
            self._apply_default_widths()

    def _apply_default_widths(self) -> None:
        wm = self.window_manager
        if wm is None:
            return
        for key, e in wm.entries.items():
            wm.set_width(key, e["default_width"])

    @staticmethod
    def _scroll(widget: QWidget, min_height: int = 0) -> QScrollArea:
        if min_height:
            widget.setMinimumHeight(min_height)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(widget)
        sa.setFrameShape(QFrame.NoFrame)
        return sa

    @staticmethod
    def _dock(title: str, obj_name: str, widget: QWidget, window) -> QDockWidget:
        dock = QDockWidget(title, window)
        dock.setObjectName(obj_name)
        dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetMovable |
                         QDockWidget.DockWidgetFloatable |
                         QDockWidget.DockWidgetClosable)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea |
                             Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)
        return dock

    def build_docks(self, window) -> None:
        # ---- 最左侧：项目管理器（Origin 式上树下内容，窄栏）----
        explorer = self.panels.explorer
        ex_dock = self._dock("项目管理器", "explorerDock", explorer, window)
        ex_dock.setMinimumWidth(150)
        ex_dock.setMaximumWidth(340)          # 防止被窗口拉伸占掉工作区
        window.addDockWidget(Qt.LeftDockWidgetArea, ex_dock)

        # ---- 右侧：属性窗口（选中对象摘要 + 属性/工具选项卡合并）----
        from curviva.ui.panels.summary_panel import SelectionSummaryPanel
        self.summary = SelectionSummaryPanel(self.app)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        # 属性选项卡（随选中图形生效）
        for key, title, panel in self.panels.property_panels:
            tabs.addTab(self._scroll(panel), title)
            theme.colorize_groups(panel, PROPERTY_TONES.get(key, "blue"))
        # 工具选项卡（数据分析 / 拟合 / 项目 / 工作台并入属性窗口）
        for key, title, panel in self.panels.tool_panels:
            if key == "data_panel":
                continue          # 数据面板的职能已由项目管理器 + 工作表承担
            tabs.addTab(self._scroll(panel, 620), title)
            theme.colorize_groups(panel, TOOL_TONES.get(key, "blue"))

        holder = QWidget()
        v = QVBoxLayout(holder)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)
        v.addWidget(self.summary)
        v.addWidget(tabs, 1)

        right = self._dock("属性窗口", "rightDock", holder, window)
        right.setMinimumWidth(240)
        right.setMaximumWidth(460)
        window.addDockWidget(Qt.RightDockWidgetArea, right)
        theme.colorize_tabs(tabs)

        self.right_tabs = tabs
        self.left_tabs = tabs          # 兼容旧调用：合并后统一走右侧
        self.right_dock = right
        self.left_dock = None
        self.explorer_dock = ex_dock
        window.left_dock, window.right_dock = None, right
        window.explorer_dock = ex_dock
        window.tabs = tabs

        wm = self.window_manager
        wm.register("explorer", ex_dock, "项目管理器",
                    tabs=None, tab_labels=[],
                    area=Qt.LeftDockWidgetArea, width=200)
        wm.register("properties", right, "属性窗口",
                    tabs=tabs,
                    tab_labels=[t for _, t, _ in self.panels.property_panels] +
                               [t for k, t, _ in self.panels.tool_panels
                                if k != "data_panel"],
                    area=Qt.RightDockWidgetArea, width=260)

    # ------------------------------------------------------------------
    def open_sheet(self, name: str, show: bool = True):
        """hook：任何模块都可以通过 app.hook("open_sheet", name) 打开表格窗口。"""
        if self.workarea is not None:
            return self.workarea.open_sheet(name)
        return self.worksheet.open_sheet(name, show)

    def load_script(self, code: str) -> None:
        """hook：把示例脚本载入「工作台 → Python 脚本」编辑器。"""
        self.focus_tool("workflow_panel")
        panel = self.panels.workflow_panel
        if hasattr(panel, "tabs"):
            panel.tabs.setCurrentIndex(1)
        if hasattr(panel, "script_edit"):
            panel.script_edit.setPlainText(code)

    # ------------------------------------------------------------------
    def _show_tab(self, tabs, index: int) -> None:
        if (hasattr(tabs, "setTabVisible")
                and hasattr(tabs, "isTabVisible")
                and not tabs.isTabVisible(index)):
            tabs.setTabVisible(index, True)
        tabs.setCurrentIndex(index)

    def focus_tool(self, key: str, sub_index: int = None) -> None:
        """菜单快捷入口：切到属性窗口中指定的工具选项卡。"""
        tabs = self.right_tabs
        if tabs is not None:
            offset = len(self.panels.property_panels)
            tool_keys = [k for k, _, _ in self.panels.tool_panels
                         if k != "data_panel"]
            if key in tool_keys:
                self._show_tab(tabs, offset + tool_keys.index(key))
        if self.right_dock is not None:
            self.right_dock.show()
            self.right_dock.raise_()

    def focus_property(self, key: str) -> None:
        tabs = self.right_tabs
        if tabs is not None:
            for i, (k, _, _) in enumerate(self.panels.property_panels):
                if k == key:
                    self._show_tab(tabs, i)
                    break
        if self.right_dock is not None:
            self.right_dock.show()
            self.right_dock.raise_()
