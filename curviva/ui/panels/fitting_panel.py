"""P1「公式拟合」面板：模型库 / 自定义 Python 表达式 / 权重 / 结果报告。"""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from curviva.ui.panels.form_utils import fill_combo_with_names


class FittingPanel(QWidget):
    """左侧「公式拟合」选项卡。"""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._build_ui()
        self._connect()
        self.refresh_from_app()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        gb = QGroupBox("拟合数据")
        form = QFormLayout(gb)
        self.dataset_combo = QComboBox()
        self.x_combo = QComboBox()
        self.y_combo = QComboBox()
        form.addRow("数据集", self.dataset_combo)
        form.addRow("X 列", self.x_combo)
        form.addRow("Y 列", self.y_combo)
        root.addWidget(gb)

        gb2 = QGroupBox("拟合模型（全部使用 Python 表达式）")
        f2 = QFormLayout(gb2)
        self.model_combo = QComboBox()
        for text, key in self.app.fitting.models():
            self.model_combo.addItem(text, key)
        self.expr_edit = QLineEdit()
        self.expr_edit.setPlaceholderText("例如：y0 + A * np.exp(-x / t)")
        self.expr_edit.setEnabled(False)
        self.param_hint = QLabel("参数：—")
        self.param_hint.setWordWrap(True)
        f2.addRow("模型", self.model_combo)
        f2.addRow("自定义表达式", self.expr_edit)
        f2.addRow(self.param_hint)
        root.addWidget(gb2)

        gb3 = QGroupBox("拟合设置")
        f3 = QFormLayout(gb3)
        self.weight_combo = QComboBox()
        for text, key in self.app.fitting.weight_modes():
            self.weight_combo.addItem(text, key)
        self.weight_col_combo = QComboBox()
        self.xmin_edit = QLineEdit(); self.xmin_edit.setPlaceholderText("留空 = 全部数据")
        self.xmax_edit = QLineEdit(); self.xmax_edit.setPlaceholderText("留空 = 全部数据")
        self.iter_spin = QSpinBox(); self.iter_spin.setRange(10, 5000)
        self.iter_spin.setValue(250); self.iter_spin.setKeyboardTracking(False)
        self.subplot_combo = QComboBox()
        f3.addRow("权重", self.weight_combo)
        f3.addRow("误差/权重列", self.weight_col_combo)
        f3.addRow("X 下限", self.xmin_edit)
        f3.addRow("X 上限", self.xmax_edit)
        f3.addRow("最大迭代", self.iter_spin)
        f3.addRow("结果加入子图", self.subplot_combo)
        root.addWidget(gb3)

        gb4 = QGroupBox("参数初值（留空 = 自动估计）")
        v4 = QVBoxLayout(gb4)
        self.param_table = QTableWidget(0, 2)
        self.param_table.setHorizontalHeaderLabels(["参数", "初值"])
        self.param_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.param_table.setMaximumHeight(140)
        v4.addWidget(self.param_table)
        root.addWidget(gb4)

        btns = QHBoxLayout()
        self.fit_btn = QPushButton("执行拟合")
        self.fit_btn.setProperty("accent", True)
        self.curve_btn = QPushButton("拟合曲线上图")
        self.curve_btn.setProperty("tone", "green")
        self.res_btn = QPushButton("残差上图")
        self.res_btn.setProperty("tone", "violet")
        self.report_btn = QPushButton("导出报告")
        self.report_btn.setProperty("tone", "cyan")
        for b in (self.fit_btn, self.curve_btn, self.res_btn, self.report_btn):
            btns.addWidget(b)
        root.addLayout(btns)

        self.band_check = QCheckBox("拟合曲线同时绘制 95% 置信带")
        root.addWidget(self.band_check)
        self.status = QLabel("选择数据与模型后点击「执行拟合」。")
        self.status.setObjectName("hintCard")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.stats_table = QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels(["统计量", "数值"])
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.setMaximumHeight(140)
        root.addWidget(self.stats_table)

        self.report_edit = QPlainTextEdit()
        self.report_edit.setReadOnly(True)
        self.report_edit.setPlaceholderText("拟合报告将在这里生成，可直接复制。")
        self.report_edit.setMinimumHeight(160)
        root.addWidget(self.report_edit, 1)

    def _connect(self) -> None:
        self.dataset_combo.currentIndexChanged.connect(self._fill_columns)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self.expr_edit.textChanged.connect(self._on_expr_changed)
        self.weight_combo.currentIndexChanged.connect(self._sync_weight_col)
        self.fit_btn.clicked.connect(self._on_fit)
        self.curve_btn.clicked.connect(self._on_add_curve)
        self.res_btn.clicked.connect(self._on_add_residuals)
        self.report_btn.clicked.connect(self._on_export_report)

    # ------------------------------------------------------------------
    def refresh_from_app(self) -> None:
        fill_combo_with_names(self.dataset_combo, self.app.core.dataset_names())
        self._fill_columns()
        n = self.app.config.subplot_count()
        fill_combo_with_names(self.subplot_combo,
                              [f"子图 {i + 1}" for i in range(n)])
        self._on_model_changed()

    def _fill_columns(self) -> None:
        name = self.dataset_combo.currentData()
        cols = self.app.core.columns(name) if name else []
        numeric = self.app.core.numeric_columns(name) if name else []
        fill_combo_with_names(self.x_combo, numeric or cols)
        fill_combo_with_names(self.y_combo, numeric or cols)
        if self.y_combo.count() > 1:
            self.y_combo.setCurrentIndex(1)
        fill_combo_with_names(self.weight_col_combo, numeric or cols)
        self._sync_weight_col()

    def _sync_weight_col(self) -> None:
        mode = self.weight_combo.currentData()
        self.weight_col_combo.setEnabled(mode in ("sigma_col", "weight_col"))

    def _current_params(self) -> list:
        key = self.model_combo.currentData()
        if key == "custom":
            expr = self.expr_edit.text().strip()
            try:
                return self.app.fitting.infer_params(expr) if expr else []
            except Exception:
                return []
        return list(self.app.fitting.model_info(key)["params"])

    def _on_expr_changed(self) -> None:
        if self.model_combo.currentData() == "custom":
            self._rebuild_param_table()

    def _on_model_changed(self) -> None:
        key = self.model_combo.currentData()
        custom = key == "custom"
        self.expr_edit.setEnabled(custom)
        if not custom and key:
            info = self.app.fitting.model_info(key)
            self.expr_edit.setText(info["expression"])
        elif custom and not self.expr_edit.text().strip():
            self.expr_edit.setText("a * np.exp(-b * x) + c")
        self.param_hint.setText("参数：" + (", ".join(self._current_params()) or "—"))
        self._rebuild_param_table()
        self._sync_weight_col()

    def _rebuild_param_table(self) -> None:
        params = self._current_params()
        self.param_table.setRowCount(len(params))
        for i, name in enumerate(params):
            self.param_table.setItem(i, 0, QTableWidgetItem(name))
            self.param_table.setItem(i, 1, QTableWidgetItem(""))

    # ------------------------------------------------------------------
    def _spec(self) -> dict:
        def _num(text):
            text = (text or "").strip()
            return float(text) if text else None
        p0 = {}
        for row in range(self.param_table.rowCount()):
            name_item = self.param_table.item(row, 0)
            value_item = self.param_table.item(row, 1)
            if name_item and value_item and value_item.text().strip():
                try:
                    p0[name_item.text().strip()] = float(value_item.text())
                except ValueError:
                    pass
        return {
            "dataset": self.dataset_combo.currentData(),
            "x_col": self.x_combo.currentData(),
            "y_col": self.y_combo.currentData(),
            "model_key": self.model_combo.currentData(),
            "expression": self.expr_edit.text().strip(),
            "p0": p0,
            "weight_mode": self.weight_combo.currentData(),
            "weight_column": self.weight_col_combo.currentData(),
            "x_min": _num(self.xmin_edit.text()),
            "x_max": _num(self.xmax_edit.text()),
            "max_iter": self.iter_spin.value(),
        }

    def _subplot(self) -> int:
        return max(self.subplot_combo.currentIndex(), 0)

    def _on_fit(self) -> None:
        try:
            result = self.app.fitting.fit(self._spec())
        except Exception as e:
            QMessageBox.warning(self, "拟合失败", str(e))
            return
        self.status.setText(result.message)
        self.param_table.setRowCount(0)
        self.param_table.setRowCount(len(result.params))
        for i, (name, value) in enumerate(result.params.items()):
            self.param_table.setItem(i, 0, QTableWidgetItem(name))
            se = result.stderr.get(name, float("nan"))
            self.param_table.setItem(i, 1, QTableWidgetItem(
                f"{value:.8g}  ± {se:.3g}"))
        from curviva.fitting.report import statistic_table
        stats = statistic_table(result)
        self.stats_table.setRowCount(len(stats))
        for i, (label, value) in enumerate(stats):
            self.stats_table.setItem(i, 0, QTableWidgetItem(label))
            self.stats_table.setItem(i, 1, QTableWidgetItem(value))
        self.report_edit.setPlainText(self.app.fitting.report(result))
        if not result.success:
            QMessageBox.warning(self, "拟合未成功", result.message)

    def _on_add_curve(self) -> None:
        try:
            name = self.app.fitting.add_fit_curve(
                subplot_index=self._subplot(),
                with_band=self.band_check.isChecked())
            self.status.setText(f"已生成拟合曲线数据集：{name}")
        except Exception as e:
            QMessageBox.warning(self, "操作失败", str(e))

    def _on_add_residuals(self) -> None:
        try:
            name = self.app.fitting.add_residuals(subplot_index=self._subplot())
            self.status.setText(f"已生成残差数据集：{name}")
        except Exception as e:
            QMessageBox.warning(self, "操作失败", str(e))

    def _on_export_report(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出拟合报告", "fit_report.md",
            "Markdown / 文本 (*.md *.txt);;所有文件 (*.*)")
        if not path:
            return
        try:
            self.app.fitting.export_report(path)
            self.status.setText(f"报告已导出：{path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
