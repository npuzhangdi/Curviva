"""图例与字体面板：子图图例设置 + 全局字体设置。"""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QVBoxLayout,
    QWidget,
)

from curviva.config.plot_config import FONT_FAMILIES, LEGEND_LOCS
from curviva.ui.panels.panel_base import PanelBase
from curviva.ui.ui_utils import fill_combo, fill_options


class LegendPanel(PanelBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._build_ui()
        self._connect()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self.sub_combo = QComboBox()
        root.addWidget(self.sub_combo)

        gb1 = QGroupBox("图例设置（当前子图）")
        form1 = QFormLayout(gb1)
        self.show_check = QCheckBox("显示图例")
        self.loc_combo = QComboBox()
        for name, val in LEGEND_LOCS:
            self.loc_combo.addItem(name, val)
        self.legend_size_spin = QDoubleSpinBox(); self.legend_size_spin.setRange(4.0, 40.0); self.legend_size_spin.setSuffix(" pt")
        self.legend_frame_check = QCheckBox("显示图例边框")
        form1.addRow(self.show_check)
        form1.addRow("图例位置", self.loc_combo)
        form1.addRow("图例字号", self.legend_size_spin)
        form1.addRow(self.legend_frame_check)
        root.addWidget(gb1)

        gb2 = QGroupBox("全局字体")
        form2 = QFormLayout(gb2)
        self.font_combo = QComboBox()
        for name, val in FONT_FAMILIES:
            self.font_combo.addItem(name, val)
        self.base_size_spin = QDoubleSpinBox(); self.base_size_spin.setRange(4.0, 40.0); self.base_size_spin.setSuffix(" pt")
        form2.addRow("字体", self.font_combo)
        form2.addRow("基准字号（轴刻度/标签）", self.base_size_spin)
        root.addWidget(gb2)
        root.addStretch(1)

    def _connect(self) -> None:
        self.sub_combo.currentIndexChanged.connect(self._on_sub_changed)
        self.show_check.toggled.connect(self._save)
        self.loc_combo.currentIndexChanged.connect(self._save)
        self.legend_size_spin.valueChanged.connect(self._save)
        self.legend_frame_check.toggled.connect(self._save)
        self.font_combo.currentIndexChanged.connect(self._save_global)
        self.base_size_spin.valueChanged.connect(self._save_global)

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
            sub.show_legend = self.show_check.isChecked()
            sub.legend_loc = self.loc_combo.currentData()
            sub.legend_fontsize = self.legend_size_spin.value()
            sub.legend_frame = self.legend_frame_check.isChecked()
            self.changed.emit()

    def _save_global(self, *_) -> None:
        if self._updating:
            return
        g = self._config.global_cfg
        g.font_family = self.font_combo.currentData()
        g.base_fontsize = self.base_size_spin.value()
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
            self.show_check.setChecked(sub.show_legend)
            fill_combo(self.loc_combo, LEGEND_LOCS, sub.legend_loc)
            self.legend_size_spin.setValue(sub.legend_fontsize)
            self.legend_frame_check.setChecked(sub.legend_frame)
        g = self._config.global_cfg
        fill_combo(self.font_combo, FONT_FAMILIES, g.font_family)
        self.base_size_spin.setValue(g.base_fontsize)
        self._updating = False

    def refresh_dynamic(self) -> None:
        if self._config is None:
            return
        n = self._config.subplot_count()
        current = self.sub_combo.currentIndex()
        fill_options(self.sub_combo, [f"子图 {i + 1}" for i in range(n)], current)
        self.load_from_config()
