"""项目资源管理器配套对话框：新建表格、数据处理（插值/平滑/微积分/寻峰…）。"""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from curviva.config.plot_config import DEFAULT_COLORS, CurveConfig
from curviva.ui.panels.form_utils import SchemaForm, fill_combo_with_names


class NewSheetDialog(QDialog):
    """新建空白表格：名称、行数、列数、归属文件夹。"""

    def __init__(self, folder_path: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建表格 / 工作簿")
        self.resize(380, 210)
        root = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QComboBox()
        self.name_edit.setEditable(True)
        self.name_edit.addItem("Book1")
        self.name_edit.setCurrentIndex(0)
        self.name_edit.setToolTip("表格名称即数据集名称，可在树上重命名")
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 100000)
        self.rows_spin.setValue(30)
        self.rows_spin.setKeyboardTracking(False)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 50)
        self.cols_spin.setValue(2)
        self.cols_spin.setKeyboardTracking(False)
        form.addRow("表格名称", self.name_edit)
        form.addRow("行数", self.rows_spin)
        form.addRow("列数", self.cols_spin)
        root.addLayout(form)

        tip = QLabel(f"归属：{folder_path or '项目根目录'}\n"
                     "默认列：X、Y（Y2、Y3…）；X 自动填充 0…N-1，其余为 0，"
                     "可在工作簿中直接编辑或用公式列填充。")
        tip.setObjectName("hintCard")
        tip.setWordWrap(True)
        root.addWidget(tip)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("创建")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> dict:
        return {
            "name": self.name_edit.currentText().strip() or "Book1",
            "rows": self.rows_spin.value(),
            "columns": self.cols_spin.value(),
        }


class OperationDialog(QDialog):
    """对某个表格直接执行数据处理；结果数据集自动挂回同一文件夹。

    与左侧「数据分析」面板共用同一套 analysis 操作注册表与参数 schema，
    因此在项目树上点「插值」与在面板里选「插值」完全等价。
    """

    def __init__(self, app, dataset_name: str = "", folder_id: str = None,
                 operation: str = "", parent=None):
        super().__init__(parent)
        self.app = app
        self.folder_id = folder_id
        self.result = None
        self.setWindowTitle("数据处理")
        self.resize(520, 520)

        root = QVBoxLayout(self)

        gb = QGroupBox("数据源")
        form = QFormLayout(gb)
        self.dataset_combo = QComboBox()
        self.x_combo = QComboBox()
        self.y_combo = QComboBox()
        form.addRow("表格", self.dataset_combo)
        form.addRow("X 列", self.x_combo)
        form.addRow("Y 数据列", self.y_combo)
        root.addWidget(gb)

        gb2 = QGroupBox("处理操作")
        v2 = QVBoxLayout(gb2)
        self.op_combo = QComboBox()
        for text, key in self.app.analysis.operations():
            self.op_combo.addItem(text, key)
        if operation:
            i = self.op_combo.findData(operation)
            if i >= 0:
                self.op_combo.setCurrentIndex(i)
        v2.addWidget(self.op_combo)
        self.hint = QLabel()
        self.hint.setObjectName("hintCard")
        self.hint.setWordWrap(True)
        v2.addWidget(self.hint)
        self.form_host = QWidget()
        self.form_layout = QVBoxLayout(self.form_host)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.params_form = None
        v2.addWidget(self.form_host)
        root.addWidget(gb2)

        row = QHBoxLayout()
        self.run_btn = QPushButton("执行处理")
        self.run_btn.setProperty("accent", True)
        self.plot_btn = QPushButton("结果生成曲线")
        self.plot_btn.setProperty("tone", "violet")
        self.close_btn = QPushButton("关闭")
        row.addWidget(self.run_btn)
        row.addWidget(self.plot_btn)
        row.addStretch(1)
        row.addWidget(self.close_btn)
        root.addLayout(row)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("执行结果、生成的新表格与摘要会显示在这里")
        self.output.setMinimumHeight(130)
        root.addWidget(self.output, 1)

        self.dataset_combo.currentIndexChanged.connect(self._fill_columns)
        self.op_combo.currentIndexChanged.connect(self._on_op_changed)
        self.run_btn.clicked.connect(self._on_run)
        self.plot_btn.clicked.connect(self._on_plot)
        self.close_btn.clicked.connect(self.accept)

        fill_combo_with_names(self.dataset_combo,
                              self.app.core.dataset_names(), dataset_name)
        self._fill_columns()
        self._on_op_changed()

    # ------------------------------------------------------------------
    def _fill_columns(self) -> None:
        name = self.dataset_combo.currentData()
        cols = self.app.core.columns(name) if name else []
        numeric = self.app.core.numeric_columns(name) if name else []
        fill_combo_with_names(self.x_combo, cols,
                              "X" if "X" in cols else (cols[0] if cols else ""))
        fill_combo_with_names(self.y_combo, numeric or cols)

    def _on_op_changed(self) -> None:
        key = self.op_combo.currentData()
        if not key:
            return
        self.hint.setText(self.app.analysis.description(key))
        if self.params_form is not None:
            self.form_layout.removeWidget(self.params_form)
            self.params_form.deleteLater()
        self.params_form = SchemaForm(self.app.analysis.schema(key))
        self.form_layout.addWidget(self.params_form)

    def _params(self) -> dict:
        p = {
            "dataset": self.dataset_combo.currentData(),
            "x_col": self.x_combo.currentData(),
            "y_col": self.y_combo.currentData(),
        }
        if self.params_form is not None:
            p.update(self.params_form.values())
        return p

    # ------------------------------------------------------------------
    def _on_run(self) -> None:
        key = self.op_combo.currentData()
        if not key:
            return
        try:
            self.result = self.app.analysis.run(key, self._params())
        except Exception as e:                       # noqa: BLE001
            QMessageBox.warning(self, "处理失败", str(e))
            return
        lines = [self.result.summary]
        if self.result.created_dataset:
            folder = self.folder_id
            self.app.workspace.attach_dataset(self.result.created_dataset, folder)
            path = self.app.workspace.path_of_dataset(self.result.created_dataset)
            lines.append(f"已生成新表格：{self.result.created_dataset}")
            lines.append(f"位置：{path}")
        if self.result.rows:
            lines.append("")
            lines.append("结果预览（前 12 行）：")
            lines.append(" | ".join(str(h) for h in self.result.headers))
            for row in self.result.preview_rows(12):
                lines.append(" | ".join(
                    f"{v:.6g}" if isinstance(v, float) else str(v) for v in row))
        self.output.setPlainText("\n".join(lines))
        self.app.refresh("explorer_operation")

    def _on_plot(self) -> None:
        if self.result is None or not self.result.created_dataset:
            QMessageBox.information(self, "提示", "请先执行会生成新表格的处理操作。")
            return
        name = self.result.created_dataset
        cols = self.app.core.columns(name)
        if len(cols) < 2:
            QMessageBox.information(self, "提示", "结果表格不足两列，无法绘图。")
            return
        x_col = "X" if "X" in cols else cols[0]
        y_cols = [c for c in cols if c != x_col and c != "原始Y"]
        y_col = y_cols[-1] if y_cols else cols[-1]
        self.app.checkpoint("处理结果生成曲线")
        n = len(self.app.config.curves)
        self.app.config.curves.append(CurveConfig(
            label=f"{self.result.name}·{y_col}", dataset_name=name,
            x_column=x_col, y_column=y_col, plot_type="line",
            color=DEFAULT_COLORS[n % len(DEFAULT_COLORS)],
            linestyle="--", linewidth=1.6))
        self.app.refresh("explorer_plot")
        self.output.appendPlainText(f"已把「{y_col}」加入绘图区。")
