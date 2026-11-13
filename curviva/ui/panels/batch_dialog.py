"""批量生成曲线对话框：从同一数据集一次性生成多条曲线。

适用场景：一个 CSV 中有多列 Y 数据，共享同一 X 列——
勾选多个 Y 列即可一键生成多条曲线，自动分配默认配色，并以 Y 列名命名。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from curviva.config.plot_config import DEFAULT_COLORS, CurveConfig


class BatchCurveDialog(QDialog):
    """从数据集批量生成曲线。用法：

        dlg = BatchCurveDialog(data_manager, subplot_count, parent)
        if dlg.exec() == QDialog.Accepted:
            curves = dlg.get_curves()
    """

    def __init__(self, data_manager, subplot_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("从数据批量生成曲线")
        self.setMinimumWidth(420)
        self._data_manager = data_manager
        self._subplot_count = max(subplot_count, 1)
        self._result: list = []

        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "选择数据集与共享的 X 列，勾选一个或多个 Y 列，\n"
            "将按勾选顺序生成多条曲线（自动配色，以列名命名）。"))

        form = QFormLayout()
        self.dataset_combo = QComboBox()
        for ds in data_manager.datasets:
            self.dataset_combo.addItem(ds.name, ds.name)
        self.x_combo = QComboBox()
        self.y_list = QListWidget()
        self.y_list.setSelectionMode(QListWidget.MultiSelection)
        form.addRow("数据集", self.dataset_combo)
        form.addRow("共享 X 列", self.x_combo)
        form.addRow("Y 列（可多选）", self.y_list)
        root.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.ok_btn = QPushButton("生成曲线")
        self.ok_btn.setProperty("accent", True)
        cancel_btn = QPushButton("取消")
        btn_row.addWidget(self.ok_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        self.ok_btn.clicked.connect(self._on_accept)
        cancel_btn.clicked.connect(self.reject)
        self.dataset_combo.currentIndexChanged.connect(self._fill_columns)

        if self.dataset_combo.count() > 0:
            self._fill_columns()
        else:
            self.ok_btn.setEnabled(False)

    # ------------------------------------------------------------------
    def _current_dataset(self):
        name = self.dataset_combo.currentData()
        return self._data_manager.get_dataset(name) if name else None

    def _fill_columns(self, *_) -> None:
        ds = self._current_dataset()
        cols = ds.column_order if ds else []
        self.x_combo.blockSignals(True)
        self.x_combo.clear()
        self.x_combo.addItems(cols)
        if self.x_combo.count() > 1:
            self.x_combo.setCurrentIndex(0)
        self.x_combo.blockSignals(False)

        self.y_list.clear()
        for col in cols:
            self.y_list.addItem(col)
            item = self.y_list.item(self.y_list.count() - 1)
            # 默认勾选除 X 列之外的所有数值列，减少操作步骤
            if col != self.x_combo.currentText():
                item.setSelected(True)

    def _on_accept(self) -> None:
        ds = self._current_dataset()
        if ds is None:
            self.reject()
            return
        x_col = self.x_combo.currentText()
        y_cols = [it.text() for it in self.y_list.selectedItems() if it.text() != x_col]
        if not y_cols:
            self.reject()
            return

        curves = []
        for i, y_col in enumerate(y_cols):
            c = CurveConfig(
                label=y_col,
                dataset_name=ds.name,
                x_column=x_col,
                y_column=y_col,
                plot_type="line",
                color=DEFAULT_COLORS[len(curves) % len(DEFAULT_COLORS)],
                linestyle="-",
                marker="None",
                subplot_index=0,
            )
            curves.append(c)
        self._result = curves
        self.accept()

    def get_curves(self) -> list:
        return self._result
