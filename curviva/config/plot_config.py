"""配置数据模型模块。

Curviva 采用"配置驱动"架构：
- UI 层只负责修改 PlotConfig 对象；
- 绘图引擎 (PlotBuilder) 只负责按 PlotConfig 渲染；
- 两者通过配置对象解耦，便于后期扩展（如配置导入导出、撤销重做等）。
"""

from dataclasses import dataclass, field

# ------------------------------------------------------------------
# 选项常量：均为 (显示名, 内部值) 二元组列表，供界面下拉框直接使用
# ------------------------------------------------------------------

PLOT_TYPES = [("折线图", "line"), ("散点图", "scatter"), ("点线图", "line_point"), ("柱形图", "bar")]

LINESTYLES = [("实线", "-"), ("虚线", "--"), ("点线", ":"), ("点划线", "-."), ("无线条", "None")]

MARKERS = [
    ("无", "None"), ("圆点", "o"), ("方块", "s"), ("上三角", "^"),
    ("下三角", "v"), ("菱形", "D"), ("星形", "*"), ("加号", "+"),
    ("叉号", "x"), ("小点", "."),
]

LEGEND_LOCS = [
    ("自动", "best"), ("右上", "upper right"), ("左上", "upper left"),
    ("右下", "lower right"), ("左下", "lower left"), ("上方居中", "upper center"),
    ("下方居中", "lower center"), ("右侧居中", "center right"), ("左侧居中", "center left"),
]

TICK_MODES = [("自动刻度", "auto"), ("指定刻度个数", "num"), ("指定刻度间隔", "step")]

SCALES = [("线性", "linear"), ("对数", "log")]

# 双 Y 轴（图层）：曲线可绘制在左轴或右轴（Origin 的 Layer / Right Y）
Y_AXIS_SIDES = [("左 Y 轴", "left"), ("右 Y 轴", "right")]

GRID_AXES = [("两个方向", "both"), ("仅X轴", "x"), ("仅Y轴", "y")]

FONT_FAMILIES = [
    ("Arial", "Arial"),
    ("Times New Roman", "Times New Roman"),
    ("宋体 (SimSun)", "SimSun"),
    ("黑体 (SimHei)", "SimHei"),
    ("微软雅黑", "Microsoft YaHei"),
    ("楷体 (KaiTi)", "KaiTi"),
    ("Consolas", "Consolas"),
]

DEFAULT_COLORS = [
    "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


# ------------------------------------------------------------------
# 数据类
# ------------------------------------------------------------------

@dataclass
class CurveConfig:
    """单条曲线的配置。"""

    label: str = "曲线"
    dataset_name: str = ""          # 引用 DataManager 中的数据集名
    x_column: str = ""
    y_column: str = ""
    plot_type: str = "line"         # line / scatter / line_point / bar
    color: str = "#1f77b4"
    linestyle: str = "-"
    linewidth: float = 1.5
    marker: str = "None"
    markersize: float = 6.0
    alpha: float = 1.0
    bar_width: float = 0.8          # 柱形图：柱组总宽度占类目间距的比例
    subplot_index: int = 0          # 所属子图编号（从 0 开始）
    visible: bool = True            # 是否显示（图例中同步隐藏）
    # --- P3 图层 ---
    y_axis: str = "left"            # left / right，右轴曲线绘制在 twinx 图层上
    # --- P1 误差棒 ---
    error_y_column: str = ""        # Y 误差列（留空则不绘制误差棒）
    error_cap_size: float = 3.0     # 误差棒端帽大小


@dataclass
class AxisConfig:
    """单个坐标轴（X 或 Y）的配置。"""

    label: str = ""                 # 轴标签（显示在轴旁）
    auto_scale: bool = True         # 是否自动范围
    min_val: float = 0.0            # 手动范围下限
    max_val: float = 10.0           # 手动范围上限
    tick_mode: str = "auto"         # auto / num / step
    num_ticks: int = 5              # tick_mode=num 时刻度个数
    tick_step: float = 1.0          # tick_mode=step 时刻度间隔
    decimal_places: int = -1        # 刻度小数位数，-1 表示自动
    scale: str = "linear"           # linear / log
    invert: bool = False            # 是否反向


@dataclass
class SubplotConfig:
    """单个子图的配置。"""

    title: str = ""
    x_axis: AxisConfig = field(default_factory=lambda: AxisConfig(label="X"))
    y_axis: AxisConfig = field(default_factory=lambda: AxisConfig(label="Y"))
    # P3 双 Y 轴：右侧坐标轴（仅当存在 y_axis="right" 的曲线时生效）
    y2_axis: AxisConfig = field(default_factory=lambda: AxisConfig(label="Y2"))
    show_y2: bool = True
    # 图例
    show_legend: bool = True
    legend_loc: str = "best"
    legend_fontsize: float = 10.0
    legend_frame: bool = True
    # 边框封闭：上下左右四条边是否显示
    show_top: bool = True
    show_bottom: bool = True
    show_left: bool = True
    show_right: bool = True
    # 网格
    grid_show: bool = False
    grid_axis: str = "both"         # both / x / y
    grid_linestyle: str = "--"
    grid_alpha: float = 0.5


@dataclass
class GlobalConfig:
    """全局（整张图）配置。"""

    title: str = ""                 # 总标题（suptitle）
    title_fontsize: float = 14.0
    font_family: str = "Arial"
    base_fontsize: float = 10.0     # 全局基准字号
    rows: int = 1                   # 子图行数
    cols: int = 1                   # 子图列数
    figsize_w: float = 8.0          # 图宽（英寸）
    figsize_h: float = 6.0          # 图高（英寸）
    dpi: float = 100.0
    face_color: str = "white"
    # 智能抽稀：大数据量时按可视窗口做 LTTB 保形降采样（非等间距，保留峰谷形态），
    # 缩放/平移时自动按新窗口重新抽稀，放大即可看到更多细节
    smart_render: bool = True
    target_points: int = 500        # 每条曲线在当前视口内渲染的目标点数上限
    style_name: str = "默认"         # 当前样式主题名（P0）


@dataclass
class PlotConfig:
    """整张图的完整配置，是 UI 与绘图引擎之间的唯一数据契约。"""

    global_cfg: GlobalConfig = field(default_factory=GlobalConfig)
    subplots: list = field(default_factory=list)   # SubplotConfig 列表
    curves: list = field(default_factory=list)     # CurveConfig 列表

    def subplot_count(self) -> int:
        return self.global_cfg.rows * self.global_cfg.cols

    def ensure_subplots(self) -> None:
        """使子图配置列表长度与 rows*cols 一致（新增用默认配置，多余的丢弃）。"""
        n = self.subplot_count()
        while len(self.subplots) < n:
            self.subplots.append(SubplotConfig())
        del self.subplots[n:]

    def clamp_curve_indices(self) -> None:
        """防止曲线引用不存在的子图。"""
        n = max(self.subplot_count(), 1)
        for c in self.curves:
            if not (0 <= c.subplot_index < n):
                c.subplot_index = 0
