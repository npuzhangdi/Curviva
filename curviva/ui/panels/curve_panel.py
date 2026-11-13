"""曲线面板：曲线列表管理 + 逐曲线细节编辑。

每条曲线在列表中以颜色色块图标展示，勾选状态即显示/隐藏；
选中某条曲线后，可在下方编辑其全部细节：颜色、线型、线宽、
标记样式与大小、不透明度、柱宽、所属子图等。
"""

from copy import deepcopy

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from curviva.config.plot_config import (
    DEFAULT_COLORS,
    LINESTYLES,
    MARKERS,
    PLOT_TYPES,
    Y_AXIS_SIDES,
    CurveConfig,
)
from curviva.ui.panels.batch_dialog import BatchCurveDialog
from curviva.ui.panels.panel_base import PanelBase
from curviva.ui.ui_utils import fill_combo, fill_options


def _color_icon(hex_color: str, size: int = 12) -> QIcon:
    """生成圆角色块图标，用于曲线列表。"""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#7d8a99"), 1))
    painter.setBrush(QColor(hex_color))
    painter.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
    painter.end()
    return QIcon(pix)


class CurvePanel(PanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._build_ui()
        self._connect()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- 曲线列表 ---
        gb0 = QGroupBox("曲线列表（勾选 = 显示）")
        v0 = QVBoxLayout(gb0)
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("＋ 新建")
        self.add_btn.setProperty("accent", True)
        self.batch_btn = QPushButton("批量生成")
        self.batch_btn.setProperty("tone", "violet")
        self.dup_btn = QPushButton("复制")
        self.dup_btn.setProperty("tone", "cyan")
        self.del_btn = QPushButton("删除")
        self.del_btn.setProperty("tone", "danger")
        for b in (self.add_btn, self.batch_btn, self.dup_btn, self.del_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        v0.addLayout(btn_row)
        self.curve_list = QListWidget()
        self.curve_list.setIconSize(QSize(14, 14))
        self.curve_list.setFixedHeight(130)
        v0.addWidget(self.curve_list)
        root.addWidget(gb0)

        # --- 数据来源 ---
        gb1 = QGroupBox("数据来源")
        form1 = QFormLayout(gb1)
        self.label_edit = QLineEdit()
        self.dataset_combo = QComboBox()
        self.x_combo = QComboBox()
        self.y_combo = QComboBox()
        form1.addRow("曲线名称(图例)", self.label_edit)
        self.label_edit.setPlaceholderText("例如：样品A（显示在图例中）")
        form1.addRow("数据集", self.dataset_combo)
        form1.addRow("X 列", self.x_combo)
        form1.addRow("Y 列", self.y_combo)
        root.addWidget(gb1)

        # --- 图形细节 ---
        gb2 = QGroupBox("图形细节（仅作用于当前选中曲线）")
        form2 = QFormLayout(gb2)
        self.type_combo = QComboBox()
        for name, val in PLOT_TYPES:
            self.type_combo.addItem(name, val)

        color_row = QHBoxLayout()
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(46, 22)
        self.color_btn.setCursor(Qt.PointingHandCursor)
        self.color_label = QLabel("#1f77b4")
        color_row.addWidget(self.color_btn)
        color_row.addWidget(self.color_label)
        color_row.addStretch(1)

        self.linestyle_combo = QComboBox()
        for name, val in LINESTYLES:
            self.linestyle_combo.addItem(name, val)
        self.linewidth_spin = QDoubleSpinBox(); self.linewidth_spin.setRange(0.1, 10.0); self.linewidth_spin.setSingleStep(0.25)
        self.marker_combo = QComboBox()
        for name, val in MARKERS:
            self.marker_combo.addItem(name, val)
        self.markersize_spin = QDoubleSpinBox(); self.markersize_spin.setRange(1.0, 30.0)
        self.alpha_spin = QDoubleSpinBox(); self.alpha_spin.setRange(0.0, 1.0); self.alpha_spin.setSingleStep(0.05)
        self.barwidth_spin = QDoubleSpinBox(); self.barwidth_spin.setRange(0.05, 1.0); self.barwidth_spin.setSingleStep(0.05)
        self.barwidth_spin.setToolTip("柱形图：一组柱的总宽度占类目间距的比例")

        form2.addRow("图形类型", self.type_combo)
        form2.addRow("颜色", color_row)
        form2.addRow("线型", self.linestyle_combo)
        form2.addRow("线宽", self.linewidth_spin)
        form2.addRow("标记样式", self.marker_combo)
        form2.addRow("标记大小", self.markersize_spin)
        form2.addRow("不透明度", self.alpha_spin)
        form2.addRow("柱宽", self.barwidth_spin)
        root.addWidget(gb2)

        # --- 归属与图层 ---
        gb3 = QGroupBox("归属与图层")
        form3 = QFormLayout(gb3)
        self.subplot_combo = QComboBox()
        self.yaxis_combo = QComboBox()
        for name, val in Y_AXIS_SIDES:
            self.yaxis_combo.addItem(name, val)
        self.error_combo = QComboBox()
        self.error_cap_spin = QDoubleSpinBox()
        self.error_cap_spin.setRange(0.0, 20.0)
        self.error_cap_spin.setSingleStep(0.5)
        self.error_cap_spin.setToolTip("误差棒端帽大小；Y 误差列留空则不绘制误差棒")
        form3.addRow("所属子图", self.subplot_combo)
        form3.addRow("绘制在", self.yaxis_combo)
        form3.addRow("Y 误差列", self.error_combo)
        form3.addRow("误差棒端帽", self.error_cap_spin)
        root.addWidget(gb3)
        root.addStretch(1)

        self._apply_color_button("#1f77b4")

    def _connect(self) -> None:
        self.add_btn.clicked.connect(self._on_add_curve)
        self.batch_btn.clicked.connect(self._on_batch_create)
        self.dup_btn.clicked.connect(self._on_dup_curve)
        self.del_btn.clicked.connect(self._on_del_curve)
        self.curve_list.itemChanged.connect(self._on_item_changed)
        self.curve_list.currentRowChanged.connect(self._on_row_changed)
        self.label_edit.textChanged.connect(self._on_label_changed)
        self.dataset_combo.currentIndexChanged.connect(self._on_dataset_changed)
        self.x_combo.currentIndexChanged.connect(self._on_col_changed)
        self.y_combo.currentIndexChanged.connect(self._on_col_changed)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.color_btn.clicked.connect(self._on_pick_color)
        self.linestyle_combo.currentIndexChanged.connect(self._on_style_changed)
        self.linewidth_spin.valueChanged.connect(self._on_style_changed)
        self.marker_combo.currentIndexChanged.connect(self._on_style_changed)
        self.markersize_spin.valueChanged.connect(self._on_style_changed)
        self.alpha_spin.valueChanged.connect(self._on_style_changed)
        self.barwidth_spin.valueChanged.connect(self._on_style_changed)
        self.subplot_combo.currentIndexChanged.connect(self._on_subplot_changed)
        self.yaxis_combo.currentIndexChanged.connect(self._on_axis_changed)
        self.error_combo.currentIndexChanged.connect(self._on_axis_changed)
        self.error_cap_spin.valueChanged.connect(self._on_axis_changed)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _apply_color_button(self, hex_color: str) -> None:
        self.color_btn.setStyleSheet(
            f"QPushButton {{ background-color: {hex_color}; border: 1px solid #9aa5b1;"
            f"border-radius: 5px; min-width: 40px; }}")
        self.color_label.setText(hex_color)

    def _current_curve(self):
        if self._config is None:
            return None
        i = self.curve_list.currentRow()
        if 0 <= i < len(self._config.curves):
            return self._config.curves[i]
        return None

    def _sync_list_item(self, i: int) -> None:
        """把曲线的名称与颜色同步到列表项（不触发 itemChanged）。"""
        if not (0 <= i < len(self._config.curves)):
            return
        c = self._config.curves[i]
        item = self.curve_list.item(i)
        if item is None:
            return
        self.curve_list.blockSignals(True)
        item.setIcon(_color_icon(c.color))
        item.setText(c.label or "未命名")
        item.setCheckState(Qt.Checked if c.visible else Qt.Unchecked)
        self.curve_list.blockSignals(False)

    # ------------------------------------------------------------------
    # 列表操作
    # ------------------------------------------------------------------

    def _on_add_curve(self) -> None:
        if self._config is None:
            return
        colors = DEFAULT_COLORS
        c = CurveConfig(
            label=f"曲线{len(self._config.curves) + 1}",
            color=colors[len(self._config.curves) % len(colors)],
        )
        # 若有可用数据，默认映射前两个数值列，并以 Y 列名命名
        if self._data_manager and self._data_manager.datasets:
            ds = self._data_manager.datasets[0]
            c.dataset_name = ds.name
            numeric = ds.numeric_columns()
            if numeric:
                c.x_column = numeric[0]
                c.y_column = numeric[1] if len(numeric) > 1 else numeric[0]
                c.label = c.y_column
            else:
                c.x_column = ds.column_order[0]
                c.y_column = ds.column_order[-1]
        c.subplot_index = min(self._config.subplot_count() - 1,
                              self._config.curves[-1].subplot_index if self._config.curves else 0)
        self._config.curves.append(c)
        self.refresh_dynamic()
        self.curve_list.setCurrentRow(len(self._config.curves) - 1)
        self.changed.emit()

    def _on_batch_create(self) -> None:
        """从数据集批量生成多条曲线。"""
        if self._config is None or self._data_manager is None:
            return
        if not self._data_manager.datasets:
            return
        dlg = BatchCurveDialog(self._data_manager,
                               self._config.subplot_count(), self)
        if dlg.exec() != BatchCurveDialog.Accepted:
            return
        new_curves = dlg.get_curves()
        if not new_curves:
            return
        start = len(self._config.curves)
        for k, c in enumerate(new_curves):
            c.color = DEFAULT_COLORS[(start + k) % len(DEFAULT_COLORS)]
            c.subplot_index = 0
            self._config.curves.append(c)
        self.refresh_dynamic()
        self.curve_list.setCurrentRow(start)
        self.changed.emit()

    def _on_dup_curve(self) -> None:
        c = self._current_curve()
        if c is None:
            return
        copy_c = deepcopy(c)
        copy_c.label = (c.label or "曲线") + " 副本"
        i = self.curve_list.currentRow()
        self._config.curves.insert(i + 1, copy_c)
        self.refresh_dynamic()
        self.curve_list.setCurrentRow(i + 1)
        self.changed.emit()

    def _on_del_curve(self) -> None:
        if self._config is None or not self._config.curves:
            return
        i = self.curve_list.currentRow()
        if 0 <= i < len(self._config.curves):
            del self._config.curves[i]
            self.refresh_dynamic()
            self.changed.emit()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """勾选/取消勾选 = 显示/隐藏曲线。"""
        if self._updating:
            return
        i = self.curve_list.row(item)
        if 0 <= i < len(self._config.curves):
            self._config.curves[i].visible = (item.checkState() == Qt.Checked)
            self.changed.emit()

    def _on_row_changed(self, *_):
        self.load_from_config()

    # ------------------------------------------------------------------
    # 字段联动
    # ------------------------------------------------------------------

    def _on_label_changed(self, text: str) -> None:
        if self._updating:
            return
        c = self._current_curve()
        if c:
            c.label = text
            self._sync_list_item(self.curve_list.currentRow())
            self.changed.emit()

    def _on_dataset_changed(self) -> None:
        if self._updating:
            return
        c = self._current_curve()
        if not c:
            return
        # 用文本而非 currentData()，避免填充方式差异导致取不到值
        c.dataset_name = self.dataset_combo.currentText()
        ds = self._data_manager.get_dataset(c.dataset_name) if self._data_manager else None
        if ds:
            numeric = ds.numeric_columns()
            if numeric:
                c.x_column = numeric[0]
                c.y_column = numeric[1] if len(numeric) > 1 else numeric[0]
            else:
                c.x_column = ds.column_order[0]
                c.y_column = ds.column_order[-1]
        self._updating = True
        self._fill_columns(c, keep=True)   # 此时 c 的列名必在新数据集内
        self._updating = False
        self.changed.emit()

    def _on_col_changed(self) -> None:
        if self._updating:
            return
        c = self._current_curve()
        if c:
            c.x_column = self.x_combo.currentText()
            c.y_column = self.y_combo.currentText()
            self.changed.emit()

    def _on_type_changed(self) -> None:
        if self._updating:
            return
        c = self._current_curve()
        if c:
            c.plot_type = self.type_combo.currentData()
            self.changed.emit()

    def _on_style_changed(self, *_) -> None:
        if self._updating:
            return
        c = self._current_curve()
        if c:
            c.linestyle = self.linestyle_combo.currentData()
            c.linewidth = self.linewidth_spin.value()
            c.marker = self.marker_combo.currentData()
            c.markersize = self.markersize_spin.value()
            c.alpha = self.alpha_spin.value()
            c.bar_width = self.barwidth_spin.value()
            self.changed.emit()

    def _on_subplot_changed(self) -> None:
        if self._updating:
            return
        c = self._current_curve()
        if c and self.subplot_combo.currentIndex() >= 0:
            c.subplot_index = self.subplot_combo.currentIndex()
            self.changed.emit()

    def _on_axis_changed(self) -> None:
        """双 Y 轴图层与误差棒设置。"""
        if self._updating:
            return
        c = self._current_curve()
        if c:
            c.y_axis = self.yaxis_combo.currentData() or "left"
            c.error_y_column = self.error_combo.currentData() or ""
            c.error_cap_size = self.error_cap_spin.value()
            self.changed.emit()

    def _on_pick_color(self) -> None:
        c = self._current_curve()
        if not c:
            return
        from PySide6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(QColor(c.color), self, "选择曲线颜色")
        if color.isValid():
            c.color = color.name()
            self._apply_color_button(c.color)
            self._sync_list_item(self.curve_list.currentRow())
            self.changed.emit()

    def _fill_columns(self, c: CurveConfig, keep: bool = True) -> None:
        """按曲线所属数据集填充 X/Y/误差列下拉框。"""
        ds = self._data_manager.get_dataset(c.dataset_name) if self._data_manager else None
        cols = ds.column_order if ds else []
        fill_options(self.x_combo, cols, cols.index(c.x_column) if keep and c.x_column in cols else 0)
        fill_options(self.y_combo, cols, cols.index(c.y_column) if keep and c.y_column in cols else 0)
        self.error_combo.blockSignals(True)
        self.error_combo.clear()
        self.error_combo.addItem("(无)", "")
        for col in cols:
            self.error_combo.addItem(col, col)
        i = self.error_combo.findData(c.error_y_column or "")
        self.error_combo.setCurrentIndex(i if i >= 0 else 0)
        self.error_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # 对外：界面 <-> 配置同步
    # ------------------------------------------------------------------

    def load_from_config(self) -> None:
        if self._config is None:
            return
        self._updating = True
        c = self._current_curve()
        enabled = c is not None
        for w in (self.label_edit, self.dataset_combo, self.x_combo, self.y_combo,
                  self.type_combo, self.color_btn, self.linestyle_combo,
                  self.linewidth_spin, self.marker_combo, self.markersize_spin,
                  self.alpha_spin, self.barwidth_spin, self.subplot_combo,
                  self.yaxis_combo, self.error_combo, self.error_cap_spin):
            w.setEnabled(enabled)
        self.dup_btn.setEnabled(enabled)
        self.del_btn.setEnabled(enabled)
        if c:
            self.label_edit.setText(c.label)
            names = [d.name for d in self._data_manager.datasets] if self._data_manager else []
            fill_options(self.dataset_combo, names,
                         names.index(c.dataset_name) if c.dataset_name in names else 0)
            self._fill_columns(c)
            fill_combo(self.type_combo, PLOT_TYPES, c.plot_type)
            self._apply_color_button(c.color)
            fill_combo(self.linestyle_combo, LINESTYLES, c.linestyle)
            self.linewidth_spin.setValue(c.linewidth)
            fill_combo(self.marker_combo, MARKERS, c.marker)
            self.markersize_spin.setValue(c.markersize)
            self.alpha_spin.setValue(c.alpha)
            self.barwidth_spin.setValue(c.bar_width)
            n = self._config.subplot_count()
            fill_options(self.subplot_combo, [f"子图 {i + 1}" for i in range(n)],
                         c.subplot_index)
            fill_combo(self.yaxis_combo, Y_AXIS_SIDES, c.y_axis)
            self.error_cap_spin.setValue(getattr(c, "error_cap_size", 3.0))
        self._updating = False

    def refresh_dynamic(self) -> None:
        if self._config is None:
            return
        # 重建曲线列表（保留选中行与勾选状态）
        current = self.curve_list.currentRow()
        self.curve_list.blockSignals(True)
        self.curve_list.clear()
        for c in self._config.curves:
            item = QListWidgetItem(_color_icon(c.color), c.label or "未命名")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if c.visible else Qt.Unchecked)
            self.curve_list.addItem(item)
        n_items = len(self._config.curves)
        if n_items > 0:
            self.curve_list.setCurrentRow(max(0, min(current, n_items - 1)))
        self.curve_list.blockSignals(False)

        self.load_from_config()
