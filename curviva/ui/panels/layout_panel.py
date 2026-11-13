"""布局与标题面板：子图行列数、图尺寸、总标题、子图标题与轴标签。"""

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QVBoxLayout,
    QWidget,
)

from curviva.config.plot_config import SubplotConfig
from curviva.ui.panels.panel_base import PanelBase
from curviva.ui.ui_utils import fill_options


class LayoutPanel(PanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._build_ui()
        self._connect()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- 全局布局 ---
        gb = QGroupBox("图布局与尺寸")
        form = QFormLayout(gb)
        self.rows_spin = QSpinBox(); self.rows_spin.setRange(1, 10)
        self.cols_spin = QSpinBox(); self.cols_spin.setRange(1, 10)
        self.fig_w_spin = QDoubleSpinBox(); self.fig_w_spin.setRange(2.0, 40.0); self.fig_w_spin.setSuffix(" 英寸")
        self.fig_h_spin = QDoubleSpinBox(); self.fig_h_spin.setRange(2.0, 40.0); self.fig_h_spin.setSuffix(" 英寸")
        self.dpi_spin = QDoubleSpinBox(); self.dpi_spin.setRange(50.0, 600.0)
        form.addRow("子图行数", self.rows_spin)
        form.addRow("子图列数", self.cols_spin)
        form.addRow("图宽", self.fig_w_spin)
        form.addRow("图高", self.fig_h_spin)
        form.addRow("分辨率 DPI", self.dpi_spin)
        self.smart_check = QCheckBox("智能抽稀（大数据量保形降采样，缩放自动细化）")
        self.target_spin = QSpinBox(); self.target_spin.setRange(3, 20000); self.target_spin.setSingleStep(10)
        self.target_spin.setKeyboardTracking(False)   # 避免输入过程中每敲一位就重渲染
        self.target_spin.setToolTip("每条曲线在当前视口内渲染的目标点数上限（最小 3）")
        form.addRow(self.smart_check)
        form.addRow("目标点数", self.target_spin)
        root.addWidget(gb)

        # --- 总标题 ---
        gb2 = QGroupBox("总标题（整图上方）")
        form2 = QFormLayout(gb2)
        self.suptitle_edit = QLineEdit()
        self.suptitle_edit.setPlaceholderText("例如：不同样品的拉伸性能对比")
        self.suptitle_size = QDoubleSpinBox(); self.suptitle_size.setRange(6.0, 60.0); self.suptitle_size.setSuffix(" pt")
        form2.addRow("标题文字", self.suptitle_edit)
        form2.addRow("标题字号", self.suptitle_size)
        root.addWidget(gb2)

        # --- 子图标题与轴标签 ---
        gb3 = QGroupBox("子图标题与轴标签")
        form3 = QFormLayout(gb3)
        self.sub_combo = QComboBox()
        self.sub_title_edit = QLineEdit()
        self.sub_title_edit.setPlaceholderText("例如：图1 温度随时间变化")
        self.x_label_edit = QLineEdit()
        self.x_label_edit.setPlaceholderText("例如：时间 (s)")
        self.y_label_edit = QLineEdit()
        self.y_label_edit.setPlaceholderText("例如：温度 (°C)")
        form3.addRow("选择子图", self.sub_combo)
        form3.addRow("子图标题", self.sub_title_edit)
        form3.addRow("X 轴标签", self.x_label_edit)
        form3.addRow("Y 轴标签", self.y_label_edit)
        root.addWidget(gb3)
        root.addStretch(1)

    def _connect(self) -> None:
        self.rows_spin.valueChanged.connect(self._on_layout_count_changed)
        self.cols_spin.valueChanged.connect(self._on_layout_count_changed)
        self.fig_w_spin.valueChanged.connect(self._emit)
        self.fig_h_spin.valueChanged.connect(self._emit)
        self.dpi_spin.valueChanged.connect(self._emit)
        self.suptitle_size.valueChanged.connect(self._emit)
        self.sub_combo.currentIndexChanged.connect(self._on_sub_changed)
        self.suptitle_edit.textChanged.connect(self._emit)
        self.sub_title_edit.textChanged.connect(self._on_sub_title_changed)
        self.x_label_edit.textChanged.connect(self._on_x_label_changed)
        self.y_label_edit.textChanged.connect(self._on_y_label_changed)
        self.smart_check.toggled.connect(self._emit)
        self.target_spin.valueChanged.connect(self._emit)

    # ------------------------------------------------------------------
    def _emit(self, *_) -> None:
        if self._updating or self._config is None:
            return
        g = self._config.global_cfg
        g.figsize_w = self.fig_w_spin.value()
        g.figsize_h = self.fig_h_spin.value()
        g.dpi = self.dpi_spin.value()
        g.title = self.suptitle_edit.text()
        g.title_fontsize = self.suptitle_size.value()
        g.smart_render = self.smart_check.isChecked()
        g.target_points = self.target_spin.value()
        self.changed.emit()

    def _on_layout_count_changed(self) -> None:
        """行列数变化：调整子图配置数量并刷新子图下拉框。"""
        if self._updating or self._config is None:
            return
        g = self._config.global_cfg
        g.rows = self.rows_spin.value()
        g.cols = self.cols_spin.value()
        self._config.ensure_subplots()
        self._config.clamp_curve_indices()
        self.refresh_dynamic()
        self.changed.emit()

    def _current_sub(self):
        i = self.sub_combo.currentIndex()
        if 0 <= i < len(self._config.subplots):
            return self._config.subplots[i]
        return None

    def _on_sub_changed(self) -> None:
        """切换子图：从配置回填该子图的标题与轴标签，不触发渲染。"""
        self.load_from_config()

    def _on_sub_title_changed(self, text: str) -> None:
        if not self._updating and (sub := self._current_sub()):
            sub.title = text
            self.changed.emit()

    def _on_x_label_changed(self, text: str) -> None:
        if not self._updating and (sub := self._current_sub()):
            sub.x_axis.label = text
            self.changed.emit()

    def _on_y_label_changed(self, text: str) -> None:
        if not self._updating and (sub := self._current_sub()):
            sub.y_axis.label = text
            self.changed.emit()

    # ------------------------------------------------------------------
    def load_from_config(self) -> None:
        """把配置同步到界面控件（渲染后由 MainWindow 调用）。"""
        if self._config is None:
            return
        self._updating = True
        g = self._config.global_cfg
        self.rows_spin.setValue(g.rows)
        self.cols_spin.setValue(g.cols)
        self.fig_w_spin.setValue(g.figsize_w)
        self.fig_h_spin.setValue(g.figsize_h)
        self.dpi_spin.setValue(g.dpi)
        self.suptitle_edit.setText(g.title)
        self.suptitle_size.setValue(g.title_fontsize)
        self.smart_check.setChecked(g.smart_render)
        self.target_spin.setValue(g.target_points)
        sub = self._current_sub()
        if sub:
            self.sub_title_edit.setText(sub.title)
            self.x_label_edit.setText(sub.x_axis.label)
            self.y_label_edit.setText(sub.y_axis.label)
        self._updating = False

    def refresh_dynamic(self) -> None:
        if self._config is None:
            return
        n = self._config.subplot_count()
        current = self.sub_combo.currentIndex()
        fill_options(self.sub_combo, [f"子图 {i + 1}" for i in range(n)], current)
        self.load_from_config()
