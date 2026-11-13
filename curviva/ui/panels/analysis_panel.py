"""P2「数据分析」面板：操作注册表驱动的动态参数表单 + 结果表格。"""

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from curviva.config.plot_config import CurveConfig, DEFAULT_COLORS
from curviva.ui.panels.form_utils import SchemaForm, fill_combo_with_names


class AnalysisPanel(QWidget):
    """左侧「数据分析」选项卡。"""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.result = None
        self._build_ui()
        self._connect()
        self.refresh_from_app()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        gb = QGroupBox("数据源")
        form = QFormLayout(gb)
        self.dataset_combo = QComboBox()
        self.x_combo = QComboBox()
        self.y_combo = QComboBox()
        form.addRow("数据集", self.dataset_combo)
        form.addRow("X 列（可选）", self.x_combo)
        form.addRow("Y 数据列", self.y_combo)
        root.addWidget(gb)

        gb2 = QGroupBox("分析操作")
        v2 = QVBoxLayout(gb2)
        self.op_combo = QComboBox()
        for text, key in self.app.analysis.operations():
            self.op_combo.addItem(text, key)
        v2.addWidget(self.op_combo)
        self.op_hint = QLabel()
        self.op_hint.setObjectName("hintCard")
        self.op_hint.setWordWrap(True)
        v2.addWidget(self.op_hint)
        self.form_host = QWidget()
        self.form_layout = QVBoxLayout(self.form_host)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.params_form = None
        v2.addWidget(self.form_host)
        btns = QHBoxLayout()
        self.run_btn = QPushButton("执行分析")
        self.run_btn.setProperty("accent", True)
        self.plot_btn = QPushButton("结果生成曲线")
        self.plot_btn.setProperty("tone", "violet")
        self.export_btn = QPushButton("导出结果 CSV")
        self.export_btn.setProperty("tone", "cyan")
        for b in (self.run_btn, self.plot_btn, self.export_btn):
            btns.addWidget(b)
        v2.addLayout(btns)
        root.addWidget(gb2)

        self.summary = QLabel("选择操作后点击「执行分析」，结果会自动生成新的数据集。")
        self.summary.setObjectName("hintCard")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMinimumHeight(150)
        root.addWidget(self.table, 1)

    def _connect(self) -> None:
        self.dataset_combo.currentIndexChanged.connect(self._on_dataset_changed)
        self.op_combo.currentIndexChanged.connect(self._on_op_changed)
        self.run_btn.clicked.connect(self._on_run)
        self.plot_btn.clicked.connect(self._on_plot)
        self.export_btn.clicked.connect(self._on_export)

    # ------------------------------------------------------------------
    def refresh_from_app(self) -> None:
        names = self.app.core.dataset_names()
        fill_combo_with_names(self.dataset_combo, names)
        self._fill_columns()
        self._on_op_changed()

    def _fill_columns(self) -> None:
        name = self.dataset_combo.currentData()
        cols = self.app.core.columns(name) if name else []
        numeric = self.app.core.numeric_columns(name) if name else []
        fill_combo_with_names(self.x_combo, cols)
        fill_combo_with_names(self.y_combo, numeric or cols)

    def _on_dataset_changed(self) -> None:
        self._fill_columns()

    def _on_op_changed(self) -> None:
        key = self.op_combo.currentData()
        if not key:
            return
        self.op_hint.setText(self.app.analysis.description(key))
        if self.params_form is not None:
            self.form_layout.removeWidget(self.params_form)
            self.params_form.deleteLater()
        self.params_form = SchemaForm(self.app.analysis.schema(key))
        self.form_layout.addWidget(self.params_form)

    # ------------------------------------------------------------------
    def _params(self) -> dict:
        p = {
            "dataset": self.dataset_combo.currentData(),
            "x_col": self.x_combo.currentData(),
            "y_col": self.y_combo.currentData(),
        }
        if self.params_form is not None:
            p.update(self.params_form.values())
        return p

    def _on_run(self) -> None:
        key = self.op_combo.currentData()
        if not key:
            return
        try:
            self.result = self.app.analysis.run(key, self._params())
        except Exception as e:
            QMessageBox.warning(self, "分析失败", str(e))
            return
        extra = (f"　新数据集：{self.result.created_dataset}"
                 if self.result.created_dataset else "")
        self.summary.setText(self.result.summary + extra)
        self._show_table(self.result)

    def _show_table(self, result) -> None:
        headers = result.headers
        rows = result.preview_rows(200)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels([str(h) for h in headers])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                text = (f"{value:.6g}" if isinstance(value, float) else str(value))
                self.table.setItem(i, j, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()

    def _on_plot(self) -> None:
        if self.result is None or not self.result.created_dataset:
            QMessageBox.information(self, "提示", "请先执行会生成数据集的分析操作。")
            return
        name = self.result.created_dataset
        cols = self.app.core.columns(name)
        if len(cols) < 2:
            return
        self.app.checkpoint("分析结果生成曲线")
        x_col = "X" if "X" in cols else cols[0]
        y_cols = [c for c in cols if c != x_col and c != "原始Y"]
        y_col = y_cols[-1] if y_cols else cols[-1]
        n = len(self.app.config.curves)
        self.app.config.curves.append(CurveConfig(
            label=f"{self.result.name}·{y_col}", dataset_name=name,
            x_column=x_col, y_column=y_col, plot_type="line",
            color=DEFAULT_COLORS[n % len(DEFAULT_COLORS)],
            linestyle="--", linewidth=1.6))
        self.app.refresh("analysis_plot")
        self.summary.setText(f"已把「{y_col}」加入绘图区。")

    def _on_export(self) -> None:
        if self.result is None:
            QMessageBox.information(self, "提示", "请先执行分析。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出分析结果", "analysis_result.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            self.app.analysis.export_result(self.result, path)
            self.summary.setText(f"结果已导出：{path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
