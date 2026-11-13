"""菜单栏下方唯一一行工具栏：纯图标 + 悬停提示，随选中对象切换。

通用组（新建 / 打开 / 保存 / 撤销 / 重做 / 导入）始终显示；
后半段随工作区当前激活窗口类型自动切换：
表格 → 数据画图 / 批量 / 拟合 / 数据处理 / 行列 / 导出；
图形 → 鼠标编辑工具 / 尺寸与 DPI / 导出；
图片 → 缩放 / 适应窗口 / 显示尺寸 / 另存。
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QMenu,
    QSpinBox,
    QToolBar,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from curviva.graphs.model import SIZE_PRESETS
from curviva.ui import theme
from curviva.ui.workarea.graph_editor import MODES

ANALYSIS_OPS = [
    ("插值 / 重采样", "resample"), ("Savitzky–Golay 平滑", "savgol"),
    ("移动平均", "moving"), ("归一化", "normalize"), ("基线扣除", "baseline"),
    ("数值微分", "derivative"), ("累积积分", "integral"),
    ("FFT 幅度谱", "fft"), ("寻峰 / 峰面积", "find_peaks"),
    ("描述统计", "describe"),
]

FIT_MODELS = [
    ("线性 y = a + bx", "linear"), ("二次多项式", "poly2"),
    ("三次多项式", "poly3"), ("指数", "exp"), ("高斯", "gauss"),
    ("洛伦兹", "lorentz"), ("Sigmoid", "sigmoid"),
]


class ContextToolBar(QToolBar):
    """菜单栏下方唯一一行工具栏（纯图标，随选中对象切换动作集）。"""

    def __init__(self, ui, window, parent=None):
        super().__init__("工具栏", parent)
        self.ui = ui
        self.window = window
        self.app = ui.app
        self.kind = "none"
        self.doc_id = ""
        self.title = ""
        self.sw = None
        self.setObjectName("contextToolBar")
        self.setMovable(False)
        self.setFloatable(False)
        self.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.setIconSize(QSize(17, 17))
        self.groups = {k: [] for k in ("common", "sheet", "graph", "image", "none")}
        self._mode_actions = {}
        self._build()
        self.set_context("none", "", "", None)

    # ------------------------------------------------------------------
    def _act(self, group: str, text: str, slot, tooltip: str = "",
             icon: str = "") -> QAction:
        action = QAction(text, self)
        if icon:
            action.setIcon(theme.origin_icon(icon))
        action.setToolTip(tooltip or text)
        action.triggered.connect(slot)
        self.addAction(action)
        self.groups[group].append(action)
        return action

    def _widget(self, group: str, widget: QWidget) -> None:
        holder = QWidgetAction(self)
        holder.setDefaultWidget(widget)
        self.addAction(holder)
        self.groups[group].append(holder)

    def _sep(self, group: str) -> QAction:
        action = self.addSeparator()
        self.groups[group].append(action)
        return action

    def _menu_button(self, group: str, text: str, icon: str,
                     tooltip: str, items: list, slot) -> None:
        btn = QToolButton(self)
        btn.setIcon(theme.origin_icon(icon))
        btn.setToolTip(tooltip or text)
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setCursor(Qt.PointingHandCursor)
        menu = QMenu(btn)
        for label, key in items:
            menu.addAction(label, lambda k=key: slot(k))
        btn.setMenu(menu)
        self._widget(group, btn)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        w = self.window
        ui = self.ui

        # ---------- 通用（始终显示） ----------
        self._act("common", "新建项目", w._on_new_project,
                  "清空当前项目，新建空白项目 (Ctrl+N)", "project")
        self._act("common", "打开数据文件",
                  lambda: w.open_data_file(False),
                  "打开 CSV / TXT / DAT / Excel 数据文件 (Ctrl+Shift+O)", "import")
        self._act("common", "打开项目", w._on_open_project,
                  "打开 .cvproj 项目文件 (Ctrl+O)", "open")
        self._act("common", "保存项目", lambda: w._on_save_project(False),
                  "保存当前项目 (Ctrl+S)", "save")
        self._sep("common")
        self._act("common", "撤销", w._on_undo, "撤销上一步操作 (Ctrl+Z)", "undo")
        self._act("common", "重做", w._on_redo, "重做被撤销的操作 (Ctrl+Y)", "redo")
        self._sep("common")
        self._act("common", "新建表格", ui.panels.explorer.create_sheet_here,
                  "在当前文件夹新建空白工作表", "sheet")
        self._act("common", "新建图形", lambda: ui.workarea.new_graph(),
                  "新建一个图形窗口", "graph")
        self._act("common", "导入图片", lambda: ui.workarea.import_image(w),
                  "把 PNG / JPG 等图片导入为图片窗口", "image")
        self._sep("common")

        # ---------- 表格 ----------
        self._act("sheet", "数据画图", self._sheet_plot,
                  "把当前工作表的 X/Y 生成曲线并显示在图形窗口", "plot_linesymbol")
        self._act("sheet", "批量生成曲线", self._batch_curves,
                  "共享 X 列，为其余数值列各生成一条曲线", "batch")
        self._menu_button("sheet", "拟合", "plot_fit", "对当前表格做公式拟合",
                          FIT_MODELS, self._quick_fit)
        self._menu_button("sheet", "数据处理", "analysis",
                          "插值 / 平滑 / 微分 / 积分 / FFT / 寻峰等",
                          ANALYSIS_OPS, self._analysis)
        self._sep("sheet")
        self._act("sheet", "插入列", lambda: self._grid_do("insert_column"),
                  "在当前列位置插入一列", "insert_col")
        self._act("sheet", "插入行", lambda: self._grid_do("insert_row"),
                  "在当前行位置插入一行", "insert_row")
        self._act("sheet", "复制", lambda: self._grid_do("copy_selection"),
                  "复制选区到剪贴板 (Ctrl+C)", "copy")
        self._act("sheet", "粘贴", lambda: self._grid_do("paste_from_clipboard"),
                  "从剪贴板粘贴，自动扩展行列 (Ctrl+V)", "paste")
        self._act("sheet", "导出 CSV", self._sheet_export,
                  "把当前工作表导出为 CSV 文件", "export")
        self._act("sheet", "多表工作簿", lambda: ui.workarea.open_book(),
                  "打开包含全部工作表的多表工作簿窗口", "book")

        # ---------- 图形：鼠标编辑工具 ----------
        mode_group = QActionGroup(self)
        self.mode_group = mode_group          # 持有引用，避免构造期被 GC
        mode_group.setExclusive(True)
        mode_icons = {"select": "mode_select", "text": "mode_text",
                      "legend": "mode_legend", "data": "mode_data",
                      "pan": "mode_pan", "zoom": "mode_zoom"}
        for key, label, tip in MODES:
            act = QAction(theme.origin_icon(mode_icons.get(key, key)), label, self)
            act.setCheckable(True)
            act.setToolTip(tip)
            act.triggered.connect(lambda checked, k=key: self._set_mode(k))
            mode_group.addAction(act)
            self.addAction(act)
            self.groups["graph"].append(act)
            self._mode_actions[key] = act
        self._mode_actions["select"].setChecked(True)
        self._sep("graph")

        # ---------- 图形：尺寸 / DPI ----------
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.5, 60)
        self.width_spin.setDecimals(2)
        self.width_spin.setSingleStep(0.5)
        self.width_spin.setPrefix("宽 ")
        self.width_spin.setFixedWidth(84)
        self.width_spin.setToolTip("图形宽度")
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.5, 60)
        self.height_spin.setDecimals(2)
        self.height_spin.setSingleStep(0.5)
        self.height_spin.setPrefix("高 ")
        self.height_spin.setFixedWidth(84)
        self.height_spin.setToolTip("图形高度")
        self.unit_combo = QComboBox()
        for text, key in (("in", "inch"), ("cm", "cm"), ("mm", "mm"), ("px", "px")):
            self.unit_combo.addItem(text, key)
        self.unit_combo.setFixedWidth(56)
        self.unit_combo.setToolTip("尺寸单位")
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(50, 2400)
        self.dpi_spin.setSingleStep(50)
        self.dpi_spin.setPrefix("DPI ")
        self.dpi_spin.setFixedWidth(88)
        self.dpi_spin.setToolTip("导出分辨率")
        for widget in (self.width_spin, self.height_spin,
                       self.unit_combo, self.dpi_spin):
            self._widget("graph", widget)
        self._act("graph", "应用尺寸", self._apply_size,
                  "把宽 / 高 / DPI 应用到当前图形", "graph")
        self._menu_button("graph", "尺寸预设", "image_fit", "常用出版尺寸",
                          [(label, (w_, h_)) for label, w_, h_ in SIZE_PRESETS],
                          self._apply_preset)
        self._sep("graph")
        self._act("graph", "还原视图", self._graph_reset,
                  "还原图形的缩放与平移", "mode_zoom")
        self._act("graph", "复制到剪贴板", self._graph_copy,
                  "把当前图形复制到剪贴板", "copy")
        self._menu_button("graph", "导出图形", "export", "导出当前图形",
                          [("PNG 图片", "png"), ("SVG 矢量", "svg"),
                           ("PDF 矢量", "pdf"), ("EPS 矢量", "eps")],
                          lambda fmt: ui.workarea.export_graph(self.doc_id, fmt))
        self._act("graph", "清除标注", self._clear_overlays,
                  "清除图上文本标注并复位图例位置", "mode_text")

        # ---------- 图片 ----------
        self.image_zoom = QComboBox()
        for z in (25, 50, 75, 100, 150, 200, 300, 400):
            self.image_zoom.addItem(f"{z}%", z)
        self.image_zoom.setFixedWidth(80)
        self.image_zoom.setToolTip("显示缩放比例")
        self.image_zoom.currentIndexChanged.connect(self._image_zoom_changed)
        self._widget("image", self.image_zoom)
        self._act("image", "适应窗口", self._image_fit,
                  "缩放图片以适应窗口", "image_fit")
        self._act("image", "原始大小", self._image_original,
                  "按图片原始像素大小显示", "image_orig")
        self._sep("image")
        self._act("image", "导入图片…", lambda: ui.workarea.import_image(self.window),
                  "更换 / 导入图片文件", "import")
        self._act("image", "另存为…", self._image_save,
                  "把图片另存为新文件", "save")

    # ------------------------------------------------------------------
    # 上下文切换
    # ------------------------------------------------------------------

    def set_context(self, kind: str, doc_id: str, title: str, sw) -> None:
        self.kind = kind if kind in ("sheet", "graph", "image") else "none"
        self.doc_id = doc_id
        self.title = title
        self.sw = sw
        for group, actions in self.groups.items():
            show = group in ("common", self.kind)
            for act in actions:
                try:
                    act.setVisible(show)
                except RuntimeError:
                    # 构造期 Qt 可能短暂重建某个 separator / QWidgetAction，
                    # 单个失效包装不影响其余动作，下一轮切换会恢复。
                    continue
        if self.kind == "graph":
            self._load_graph_values()
        elif self.kind == "image":
            self._load_image_values()

    def sync_mode(self, mode: str) -> None:
        act = self._mode_actions.get(mode)
        if act is not None:
            act.blockSignals(True)
            act.setChecked(True)
            act.blockSignals(False)

    # ------------------------------------------------------------------
    # 表格动作
    # ------------------------------------------------------------------

    def _sheet_name(self) -> str:
        return self.ui.workarea.active_sheet_name() if self.sw else ""

    def _grid(self):
        return getattr(self.sw, "grid", None) if self.sw else None

    def _grid_do(self, method: str) -> None:
        grid = self._grid()
        if grid is None:
            return
        fn = getattr(grid, method, None)
        if callable(fn):
            fn()

    def _sheet_plot(self) -> None:
        name = self._sheet_name()
        if not name:
            return
        self.ui.worksheet.add_curve(name)
        self.ui.workarea.open_graph()

    def _batch_curves(self) -> None:
        name = self._sheet_name()
        if not name:
            return
        cols = self.ui.app.core.numeric_columns(name)
        if len(cols) < 2:
            return
        x = cols[0]
        self.app.checkpoint("工具栏：批量生成曲线")
        for y in cols[1:]:
            self.ui.worksheet.add_curve(name, y)
        self.ui.workarea.open_graph()
        self.app.status(f"已从「{name}」批量生成 {len(cols) - 1} 条曲线")

    def _quick_fit(self, key: str) -> None:
        self.ui.workarea.quick_fit(self._sheet_name(), key)

    def _analysis(self, key: str) -> None:
        self.ui.workarea.active_operation(key)

    def _sheet_export(self) -> None:
        name = self._sheet_name()
        if name:
            self.ui.worksheet.export_csv(name)

    # ------------------------------------------------------------------
    # 图形动作
    # ------------------------------------------------------------------

    def _graph_doc(self):
        return self.app.graphs.get(self.doc_id)

    def _graph_win(self):
        return self.ui.workarea.active_graph_window()

    def _load_graph_values(self) -> None:
        doc = self._graph_doc()
        if doc is None:
            return
        for spin, value in ((self.width_spin, doc.width),
                            (self.height_spin, doc.height)):
            spin.blockSignals(True)
            spin.setValue(float(value))
            spin.blockSignals(False)
        i = self.unit_combo.findData(doc.unit)
        self.unit_combo.blockSignals(True)
        self.unit_combo.setCurrentIndex(i if i >= 0 else 0)
        self.unit_combo.blockSignals(False)
        self.dpi_spin.blockSignals(True)
        self.dpi_spin.setValue(int(doc.dpi))
        self.dpi_spin.blockSignals(False)
        self.sync_mode(getattr(doc, "mode", "select"))

    def _set_mode(self, mode: str) -> None:
        self.ui.workarea.set_graph_mode(mode)

    def _apply_size(self) -> None:
        doc = self._graph_doc()
        if doc is None:
            return
        self.app.checkpoint("工具栏：修改图形尺寸")
        self.app.graphs.set_size(doc.id, self.width_spin.value(),
                                 self.height_spin.value(),
                                 self.unit_combo.currentData(),
                                 self.dpi_spin.value())

    def _apply_preset(self, value) -> None:
        doc = self._graph_doc()
        if doc is None:
            return
        self.width_spin.setValue(value[0])
        self.height_spin.setValue(value[1])
        i = self.unit_combo.findData("inch")
        self.unit_combo.setCurrentIndex(i if i >= 0 else 0)
        self._apply_size()

    def _graph_reset(self) -> None:
        win = self._graph_win()
        if win is not None:
            win.canvas.reset_view()

    def _graph_copy(self) -> None:
        win = self._graph_win()
        if win is not None:
            win.editor.copy_to_clipboard()

    def _clear_overlays(self) -> None:
        win = self._graph_win()
        if win is not None:
            win.editor._clear_overlays()

    # ------------------------------------------------------------------
    # 图片动作
    # ------------------------------------------------------------------

    def _image_win(self):
        return self.ui.workarea.active_image_window()

    def _load_image_values(self) -> None:
        doc = self._graph_doc()
        if doc is None:
            return
        i = self.image_zoom.findData(int(doc.zoom))
        self.image_zoom.blockSignals(True)
        self.image_zoom.setCurrentIndex(i if i >= 0 else 3)
        self.image_zoom.blockSignals(False)

    def _image_zoom_changed(self, *_args) -> None:
        if self.kind != "image":
            return
        z = self.image_zoom.currentData()
        doc = self._graph_doc()
        if doc and z:
            self.app.graphs.set_zoom(doc.id, z, fit=False)

    def _image_fit(self) -> None:
        win = self._image_win()
        if win is not None:
            win.fit_window()

    def _image_original(self) -> None:
        win = self._image_win()
        if win is not None:
            win.original_size()

    def _image_save(self) -> None:
        win = self._image_win()
        if win is not None:
            win._save_as()
