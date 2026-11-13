"""边框与网格面板：四边封闭控制与网格样式。"""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QVBoxLayout,
    QWidget,
)

from curviva.config.plot_config import GRID_AXES, LINESTYLES
from curviva.ui.panels.panel_base import PanelBase
from curviva.ui.ui_utils import fill_combo, fill_options


class FramePanel(PanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._build_ui()
        self._connect()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.sub_combo = QComboBox()
        root.addWidget(self.sub_combo)

        gb1 = QGroupBox("图框封闭（四条边）")
        grid = QGridLayout(gb1)
        self.top_check = QCheckBox("上边框")
        self.bottom_check = QCheckBox("下边框")
        self.left_check = QCheckBox("左边框")
        self.right_check = QCheckBox("右边框")
        grid.addWidget(self.top_check, 0, 0)
        grid.addWidget(self.bottom_check, 0, 1)
        grid.addWidget(self.left_check, 1, 0)
        grid.addWidget(self.right_check, 1, 1)
        root.addWidget(gb1)

        gb2 = QGroupBox("网格线")
        form = QFormLayout(gb2)
        self.grid_check = QCheckBox("显示网格")
        self.grid_axis_combo = QComboBox()
        for name, val in GRID_AXES:
            self.grid_axis_combo.addItem(name, val)
        self.grid_ls_combo = QComboBox()
        for name, val in LINESTYLES[:-1]:  # 网格不需要"无线条"
            self.grid_ls_combo.addItem(name, val)
        self.grid_alpha_spin = QDoubleSpinBox()
        self.grid_alpha_spin.setRange(0.0, 1.0)
        self.grid_alpha_spin.setSingleStep(0.05)
        form.addRow(self.grid_check)
        form.addRow("网格方向", self.grid_axis_combo)
        form.addRow("网格线型", self.grid_ls_combo)
        form.addRow("网格透明度", self.grid_alpha_spin)
        root.addWidget(gb2)
        root.addStretch(1)

    def _connect(self) -> None:
        self.sub_combo.currentIndexChanged.connect(self._on_sub_changed)
        self.top_check.toggled.connect(self._save)
        self.bottom_check.toggled.connect(self._save)
        self.left_check.toggled.connect(self._save)
        self.right_check.toggled.connect(self._save)
        self.grid_check.toggled.connect(self._save)
        self.grid_axis_combo.currentIndexChanged.connect(self._save)
        self.grid_ls_combo.currentIndexChanged.connect(self._save)
        self.grid_alpha_spin.valueChanged.connect(self._save)

    # ------------------------------------------------------------------
    def _current_sub(self):
        i = self.sub_combo.currentIndex()
        if self._config and 0 <= i < len(self._config.subplots):
            return self._config.subplots[i]
        return None

    def _save(self, *_) -> None:
        if self._updating:
            return
        sub = self._current_sub()
        if sub:
            sub.show_top = self.top_check.isChecked()
            sub.show_bottom = self.bottom_check.isChecked()
            sub.show_left = self.left_check.isChecked()
            sub.show_right = self.right_check.isChecked()
            sub.grid_show = self.grid_check.isChecked()
            sub.grid_axis = self.grid_axis_combo.currentData()
            sub.grid_linestyle = self.grid_ls_combo.currentData()
            sub.grid_alpha = self.grid_alpha_spin.value()
            self.changed.emit()

    def _on_sub_changed(self) -> None:
        self.load_from_config()

    # ------------------------------------------------------------------
    def load_from_config(self) -> None:
        if self._config is None:
            return
        self._updating = True
        sub = self._current_sub()
        if sub:
            self.top_check.setChecked(sub.show_top)
            self.bottom_check.setChecked(sub.show_bottom)
            self.left_check.setChecked(sub.show_left)
            self.right_check.setChecked(sub.show_right)
            self.grid_check.setChecked(sub.grid_show)
            fill_combo(self.grid_axis_combo, GRID_AXES, sub.grid_axis)
            fill_combo(self.grid_ls_combo, LINESTYLES[:-1], sub.grid_linestyle)
            self.grid_alpha_spin.setValue(sub.grid_alpha)
        self._updating = False

    def refresh_dynamic(self) -> None:
        if self._config is None:
            return
        n = self._config.subplot_count()
        current = self.sub_combo.currentIndex()
        fill_options(self.sub_combo, [f"子图 {i + 1}" for i in range(n)], current)
        self.load_from_config()
