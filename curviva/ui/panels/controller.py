"""属性/工具面板集合「控制调用文件」。

PanelsController 统一创建、绑定、刷新所有面板；MainWindow 只与它交互，
不再逐个 import 面板类。新增面板只需在这里登记一次。
"""

from curviva.ui.panels.analysis_panel import AnalysisPanel
from curviva.ui.panels.axis_panel import AxisPanel
from curviva.ui.panels.curve_panel import CurvePanel
from curviva.ui.panels.data_panel import DataPanel
from curviva.ui.panels.explorer_panel import ExplorerPanel
from curviva.ui.panels.fitting_panel import FittingPanel
from curviva.ui.panels.frame_panel import FramePanel
from curviva.ui.panels.layout_panel import LayoutPanel
from curviva.ui.panels.legend_panel import LegendPanel
from curviva.ui.panels.project_panel import ProjectPanel
from curviva.ui.panels.workflow_panel import WorkflowPanel

# 面板色系（与 theme.TAB_COLORS 对应，供分组框着色）
PROPERTY_TONES = {
    "layout_panel": "blue", "curve_panel": "violet", "axis_panel": "cyan",
    "legend_panel": "orange", "frame_panel": "green",
}
TOOL_TONES = {
    "data_panel": "blue", "analysis_panel": "cyan", "fitting_panel": "violet",
    "project_panel": "green", "workflow_panel": "orange",
}


class PanelsController:
    def __init__(self, app):
        self.app = app

        # 最左侧独立窗口：Origin 风格项目 / 工作台资源树
        self.explorer = ExplorerPanel(app)

        # 左侧：数据与计算
        self.data_panel = DataPanel(app.core.data, app)
        self.analysis_panel = AnalysisPanel(app)
        self.fitting_panel = FittingPanel(app)
        self.project_panel = ProjectPanel(app)
        self.workflow_panel = WorkflowPanel(app)
        self.tool_panels = [
            ("data_panel", "数据", self.data_panel),
            ("analysis_panel", "数据分析", self.analysis_panel),
            ("fitting_panel", "曲线拟合", self.fitting_panel),
            ("project_panel", "项目", self.project_panel),
            ("workflow_panel", "工作台", self.workflow_panel),
        ]

        # 右侧：图形属性
        self.layout_panel = LayoutPanel()
        self.curve_panel = CurvePanel()
        self.axis_panel = AxisPanel()
        self.legend_panel = LegendPanel()
        self.frame_panel = FramePanel()
        self.property_panels = [
            ("layout_panel", "布局标题", self.layout_panel),
            ("curve_panel", "曲线", self.curve_panel),
            ("axis_panel", "坐标轴", self.axis_panel),
            ("legend_panel", "图例字体", self.legend_panel),
            ("frame_panel", "边框网格", self.frame_panel),
        ]
        self.bind_all()

    # ------------------------------------------------------------------
    def bind_all(self) -> None:
        """把当前配置对象重新绑定到全部属性面板。"""
        for _, _, panel in self.property_panels:
            panel.bind(self.app.config, self.app.core.data)

    def bind_signals(self, on_data_changed, on_config_changed, on_demo) -> None:
        self.data_panel.data_changed.connect(on_data_changed)
        self.data_panel.demo_requested.connect(on_demo)
        for _, _, panel in self.property_panels:
            panel.changed.connect(on_config_changed)

    def refresh_dynamic(self) -> None:
        for _, _, panel in self.property_panels:
            panel.refresh_dynamic()

    def rebind(self) -> None:
        """打开项目 / 撤销重做 / 脚本改动后：重绑配置 + 刷新全部面板状态。"""
        self.bind_all()
        self.explorer.refresh_from_app()
        for name, _, panel in self.tool_panels:
            if hasattr(panel, "refresh_from_app"):
                try:
                    panel.refresh_from_app()
                except Exception:                 # noqa: BLE001 - 单面板异常不阻断
                    pass
            if name == "data_panel":
                panel.refresh_tree()

    def panel(self, key: str):
        return getattr(self, key, None)
