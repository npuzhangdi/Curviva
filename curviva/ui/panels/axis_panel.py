"""坐标轴面板：范围、刻度模式（自动/个数/间隔）、小数位、对数、反向。"""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from curviva.config.plot_config import SCALES, TICK_MODES, AxisConfig
from curviva.ui.panels.panel_base import PanelBase
from curviva.ui.ui_utils import fill_combo, fill_options


class _AxisEditor(QGroupBox):
    """单个轴（X 或 Y）的编辑器，共用同一套控件逻辑。"""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        form = QFormLayout(self)
        self.auto_check = QCheckBox("自动范围")
        self.min_spin = QDoubleSpinBox(); self.min_spin.setRange(-1e9, 1e9); self.min_spin.setDecimals(4)
        self.max_spin = QDoubleSpinBox(); self.max_spin.setRange(-1e9, 1e9); self.max_spin.setDecimals(4)
        self.tick_mode_combo = QComboBox()
        for name, val in TICK_MODES:
            self.tick_mode_combo.addItem(name, val)
        self.num_ticks_spin = QSpinBox(); self.num_ticks_spin.setRange(2, 50)
        self.tick_step_spin = QDoubleSpinBox(); self.tick_step_spin.setRange(1e-6, 1e9); self.tick_step_spin.setDecimals(6)
        self.fixed_decimal_check = QCheckBox("固定小数位数")
        self.decimal_spin = QSpinBox(); self.decimal_spin.setRange(0, 8)
        self.scale_combo = QComboBox()
        for name, val in SCALES:
            self.scale_combo.addItem(name, val)
        self.invert_check = QCheckBox("坐标轴反向")

        form.addRow(self.auto_check)
        form.addRow("范围下限", self.min_spin)
        form.addRow("范围上限", self.max_spin)
        form.addRow("刻度模式", self.tick_mode_combo)
        form.addRow("刻度个数", self.num_ticks_spin)
        form.addRow("刻度间隔", self.tick_step_spin)
        form.addRow(self.fixed_decimal_check)
        form.addRow("小数位数", self.decimal_spin)
        form.addRow("坐标类型", self.scale_combo)
        form.addRow(self.invert_check)

        self.auto_check.toggled.connect(self._sync_range_enabled)
        self.fixed_decimal_check.toggled.connect(self._sync_decimal_enabled)
        self._sync_range_enabled()

    def _sync_range_enabled(self) -> None:
        on = not self.auto_check.isChecked()
        self.min_spin.setEnabled(on)
        self.max_spin.setEnabled(on)

    def _sync_decimal_enabled(self) -> None:
        self.decimal_spin.setEnabled(self.fixed_decimal_check.isChecked())

    # --- 界面 <-> 配置 ---
    def load(self, a: AxisConfig) -> None:
        self.auto_check.setChecked(a.auto_scale)
        self.min_spin.setValue(a.min_val)
        self.max_spin.setValue(a.max_val)
        fill_combo(self.tick_mode_combo, TICK_MODES, a.tick_mode)
        self.num_ticks_spin.setValue(a.num_ticks)
        self.tick_step_spin.setValue(a.tick_step)
        self.fixed_decimal_check.setChecked(a.decimal_places >= 0)
        self.decimal_spin.setValue(max(a.decimal_places, 0))
        fill_combo(self.scale_combo, SCALES, a.scale)
        self.invert_check.setChecked(a.invert)
        self._sync_range_enabled()
        self._sync_decimal_enabled()

    def save(self, a: AxisConfig) -> None:
        a.auto_scale = self.auto_check.isChecked()
        a.min_val = self.min_spin.value()
        a.max_val = self.max_spin.value()
        a.tick_mode = self.tick_mode_combo.currentData()
        a.num_ticks = self.num_ticks_spin.value()
        a.tick_step = self.tick_step_spin.value()
        a.decimal_places = self.decimal_spin.value() if self.fixed_decimal_check.isChecked() else -1
        a.scale = self.scale_combo.currentData()
        a.invert = self.invert_check.isChecked()


class AxisPanel(PanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._build_ui()
        self._connect()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.sub_combo = QComboBox()
        root.addWidget(self.sub_combo)
        self.x_editor = _AxisEditor("X 轴")
        self.y_editor = _AxisEditor("左 Y 轴")
        self.y2_editor = _AxisEditor("右 Y 轴（双 Y 图层）")
        y2_form = self.y2_editor.layout()
        self.show_y2_check = QCheckBox("启用右 Y 轴（曲线需选择「右 Y 轴」）")
        self.y2_label_edit = QLineEdit()
        self.y2_label_edit.setPlaceholderText("例如：温度 (°C)")
        y2_form.insertRow(0, self.show_y2_check)
        y2_form.insertRow(1, "右轴标签", self.y2_label_edit)
        root.addWidget(self.x_editor)
        root.addWidget(self.y_editor)
        root.addWidget(self.y2_editor)
        root.addStretch(1)

    def _connect(self) -> None:
        self.sub_combo.currentIndexChanged.connect(self._on_sub_changed)
        self.show_y2_check.toggled.connect(self._save_axes)
        self.y2_label_edit.textChanged.connect(self._save_axes)
        for editor in (self.x_editor, self.y_editor, self.y2_editor):
            for w in (editor.auto_check, editor.invert_check,
                      editor.fixed_decimal_check):
                w.toggled.connect(self._save_axes)
            editor.min_spin.valueChanged.connect(self._save_axes)
            editor.max_spin.valueChanged.connect(self._save_axes)
            editor.tick_mode_combo.currentIndexChanged.connect(self._save_axes)
            editor.num_ticks_spin.valueChanged.connect(self._save_axes)
            editor.tick_step_spin.valueChanged.connect(self._save_axes)
            editor.decimal_spin.valueChanged.connect(self._save_axes)
            editor.scale_combo.currentIndexChanged.connect(self._save_axes)

    # ------------------------------------------------------------------
    def _current_sub(self):
        i = self.sub_combo.currentIndex()
        if self._config and 0 <= i < len(self._config.subplots):
            return self._config.subplots[i]
        return None

    def _save_axes(self, *_) -> None:
        if self._updating:
            return
        sub = self._current_sub()
        if sub:
            self.x_editor.save(sub.x_axis)
            self.y_editor.save(sub.y_axis)
            self.y2_editor.save(sub.y2_axis)
            sub.show_y2 = self.show_y2_check.isChecked()
            sub.y2_axis.label = self.y2_label_edit.text()
            self.changed.emit()

    def _on_sub_changed(self) -> None:
        self.load_from_config()

    # ------------------------------------------------------------------
    def load_from_config(self) -> None:
        if self._config is None:
            return
        self._updating = True
        sub = self._current_sub()
        enabled = sub is not None
        self.x_editor.setEnabled(enabled)
        self.y_editor.setEnabled(enabled)
        self.y2_editor.setEnabled(enabled)
        if sub:
            self.x_editor.load(sub.x_axis)
            self.y_editor.load(sub.y_axis)
            self.y2_editor.load(sub.y2_axis)
            self.show_y2_check.setChecked(sub.show_y2)
            self.y2_label_edit.setText(sub.y2_axis.label)
        self._updating = False

    def refresh_dynamic(self) -> None:
        if self._config is None:
            return
        n = self._config.subplot_count()
        current = self.sub_combo.currentIndex()
        fill_options(self.sub_combo, [f"子图 {i + 1}" for i in range(n)], current)
        self.load_from_config()
