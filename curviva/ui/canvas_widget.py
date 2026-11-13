"""画布组件：matplotlib Figure 嵌入 Qt 界面。

交互设计：
- 滚轮缩放：以光标为锚点，步进随滚动量平滑变化；光标所在子图优先缩放；
- 缩放/平移后自动按新窗口重新智能抽稀渲染（渐进细化），放大即见更多细节；
- 双击画布：恢复默认视图（配置范围）；
- 工具栏的框选缩放 / 平移 / 回退视图保持可用，且与视窗状态自动同步。
"""

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from curviva.config.plot_config import PlotConfig
from curviva.core.plot_builder import PlotBuilder


class PlotCanvas(FigureCanvasQTAgg):
    """持有 Figure 并提供 render() / export() / zoom 等入口。"""

    WHEEL_FACTOR = 1.15      # 每 120 格滚动量的缩放步长基数

    def __init__(self, parent=None, renderer=None):
        self.figure = Figure(figsize=(8, 6), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        # 渲染统一由核心域的控制调用文件提供（默认回退到绘图引擎）
        self._renderer = renderer

        self._view_state = {}      # {子图索引: ((x0,x1), (y0,y1))} 当前视窗
        self._last_args = None     # (config, datasets) 最近一次渲染入参
        self._refining = False     # 渐进细化重绘中（防止事件回环）
        # 工作区图形窗口注入的「渲染后叠加」（文本标注、图例位置、选中高亮等）
        self.post_render_callbacks = []
        # 双击钩子：返回 True 表示已由图上编辑器处理，不再执行「还原视图」
        self.double_click_hook = None

        self._refine_timer = QTimer(self)
        self._refine_timer.setSingleShot(True)
        self._refine_timer.setInterval(80)
        self._refine_timer.timeout.connect(self._refine)

        self.mpl_connect("draw_event", self._on_mpl_draw)

    # ------------------------------------------------------------------
    # 渲染 / 导出
    # ------------------------------------------------------------------

    def render(self, config: PlotConfig, datasets: list) -> None:
        """按配置重新渲染整张图（保留当前视窗状态）。"""
        self._last_args = (config, datasets)
        self._render_now()
        self.draw_idle()

    def _render_now(self) -> None:
        if self._renderer is not None:
            self._renderer(self.figure, view_state=self._view_state or None)
        elif self._last_args is not None:
            PlotBuilder.build(self.figure, *self._last_args,
                              view_state=self._view_state or None)
        for cb in list(self.post_render_callbacks):
            try:
                cb(self.figure)
            except Exception:                 # noqa: BLE001 - 叠加层异常不阻断绘图
                pass

    def export_image(self, path: str, dpi: float, size: tuple = None) -> None:
        """导出图片（PNG/SVG/EPS/PDF 等，由扩展名决定格式）。

        size=(宽, 高) 英寸时，按图形文档自身的出版尺寸导出，不改变界面显示。
        """
        old = None
        if size:
            old = tuple(self.figure.get_size_inches())
            self.figure.set_size_inches(float(size[0]), float(size[1]),
                                        forward=False)
        try:
            self.figure.savefig(path, dpi=dpi, bbox_inches="tight")
        finally:
            if old is not None:
                self.figure.set_size_inches(old[0], old[1], forward=False)

    # ------------------------------------------------------------------
    # 缩放
    # ------------------------------------------------------------------

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        delta = event.angleDelta().y()
        if delta == 0:
            return
        # 平滑步进：步长随滚动量连续变化，避免突兀跳变
        factor = self.WHEEL_FACTOR ** (abs(delta) / 120.0)
        factor = min(max(factor, 0.6), 1.8)
        factor = 1.0 / factor if delta > 0 else factor   # 上滚放大
        pos = event.position() * self.devicePixelRatioF()
        self.zoom_at(factor, pos.x(), pos.y())

    def _main_axes(self) -> list:
        """只取主子图（排除 twinx 双 Y 轴图层，避免视窗索引错位）。"""
        return [ax for ax in self.figure.axes
                if getattr(ax, "_curviva_index", None) is not None]

    def zoom_at(self, factor: float, px: float, py: float) -> None:
        """以显示坐标 (px, py) 为锚点缩放；factor>1 缩小，<1 放大。"""
        target = []
        for ax in self._main_axes():
            bbox = ax.get_window_extent()
            if bbox.x0 <= px <= bbox.x1 and bbox.y0 <= py <= bbox.y1:
                target = [ax]
                break
        if not target:
            target = self._main_axes()

        for ax in target:
            try:
                inv = ax.transData.inverted()
                (x_data, y_data), = inv.transform([(px, py)])
                x0, x1 = ax.get_xlim()
                y0, y1 = ax.get_ylim()
                ax.set_xlim(x_data - (x_data - x0) * factor,
                            x_data + (x1 - x_data) * factor)
                ax.set_ylim(y_data - (y_data - y0) * factor,
                            y_data + (y1 - y_data) * factor)
            except Exception:
                continue
        self.draw_idle()   # draw_event 将同步视窗并触发渐进细化

    def reset_view(self) -> None:
        """恢复默认视图（清除交互视窗，按配置范围重新渲染）。"""
        self._view_state = {}
        if self._last_args is not None:
            self.render(*self._last_args)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        # 工作区图形编辑器优先处理（双击曲线/文本/坐标轴进入属性设置）
        if self.double_click_hook is not None:
            try:
                if self.double_click_hook(event):
                    return
            except Exception:                 # noqa: BLE001
                pass
        self.reset_view()
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    # 视窗状态同步与渐进细化
    # ------------------------------------------------------------------

    def _on_mpl_draw(self, event) -> None:
        st = {ax._curviva_index: (ax.get_xlim(), ax.get_ylim())
              for ax in self._main_axes()}
        if self._refining:
            self._view_state = st     # 细化重绘期间仅同步状态
            return
        if st != self._view_state:
            self._view_state = st
            if self._last_args is not None:
                self._refine_timer.start()

    def _refine(self) -> None:
        """按当前视窗重新渲染（触发智能抽稀按新窗口重算）。"""
        if self._last_args is None:
            return
        self._refining = True
        try:
            self._render_now()
            self._view_state = {ax._curviva_index: (ax.get_xlim(), ax.get_ylim())
                                for ax in self._main_axes()}
            self.draw_idle()
        finally:
            QTimer.singleShot(200, self._end_refine)

    def _end_refine(self) -> None:
        self._refining = False


class PlotToolbar(NavigationToolbar2QT):
    """标准导航工具栏（缩放、平移、保存等）。"""

    def __init__(self, canvas: PlotCanvas, parent=None):
        super().__init__(canvas, parent)
        self.setIconSize(self.iconSize() * 0.8)
        self._tint_icons()

    def _tint_icons(self) -> None:
        """把工具栏图标统一着色为深蓝灰。

        matplotlib 3.11 在浅色主题下使用白色 symbolic 图标（供深色工具栏
        使用），与 Curviva 的浅色按钮背景叠加后图标完全不可见。此处按
        alpha 通道重新着色，保证在浅色玻璃风格下清晰可辨。
        """
        color = QColor("#4C5980")
        for action in self.actions():
            icon = action.icon()
            if icon.isNull():
                continue
            pm = icon.pixmap(28, 28)
            if pm.isNull():
                continue
            tinted = QPixmap(pm.size())
            tinted.fill(Qt.transparent)
            painter = QPainter(tinted)
            painter.drawPixmap(0, 0, pm)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(tinted.rect(), color)
            painter.end()
            action.setIcon(QIcon(tinted))
