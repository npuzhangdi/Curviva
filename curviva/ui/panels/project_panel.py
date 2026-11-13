"""P0「项目」面板：项目文件、撤销重做、样式主题、Python 公式列、工作簿。"""

import os

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from curviva.project.project_io import PROJECT_FILTER
from curviva.ui.panels.form_utils import fill_combo_with_names
from curviva.ui.panels.sheet_dialog import SheetEditorDialog


class ProjectPanel(QWidget):
    """左侧「项目」选项卡。"""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._build_ui()
        self._connect()
        self.refresh_from_app()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        gb = QGroupBox("项目文件（.cvproj）")
        v = QVBoxLayout(gb)
        row = QHBoxLayout()
        self.new_btn = QPushButton("新建")
        self.open_btn = QPushButton("打开")
        self.save_btn = QPushButton("保存")
        self.save_btn.setProperty("accent", True)
        self.saveas_btn = QPushButton("另存为")
        self.saveas_btn.setProperty("tone", "cyan")
        for b in (self.new_btn, self.open_btn, self.save_btn, self.saveas_btn):
            row.addWidget(b)
        v.addLayout(row)
        self.path_label = QLabel("未保存的新项目")
        self.path_label.setObjectName("hintCard")
        self.path_label.setWordWrap(True)
        v.addWidget(self.path_label)
        root.addWidget(gb)

        gb2 = QGroupBox("历史记录")
        v2 = QVBoxLayout(gb2)
        row2 = QHBoxLayout()
        self.undo_btn = QPushButton("↶ 撤销")
        self.redo_btn = QPushButton("↷ 重做")
        self.undo_btn.setProperty("tone", "violet")
        self.redo_btn.setProperty("tone", "green")
        row2.addWidget(self.undo_btn)
        row2.addWidget(self.redo_btn)
        v2.addLayout(row2)
        self.history_label = QLabel("可记录：导入、曲线、样式、分析、拟合等全部状态")
        self.history_label.setObjectName("hintCard")
        self.history_label.setWordWrap(True)
        v2.addWidget(self.history_label)
        root.addWidget(gb2)

        gb3 = QGroupBox("样式主题")
        f3 = QFormLayout(gb3)
        self.style_combo = QComboBox()
        self.style_apply_btn = QPushButton("应用样式")
        self.style_apply_btn.setProperty("tone", "orange")
        f3.addRow("预设", self.style_combo)
        f3.addRow(self.style_apply_btn)
        root.addWidget(gb3)

        gb4 = QGroupBox("公式列（仅 Python 表达式）")
        f4 = QFormLayout(gb4)
        self.ds_combo = QComboBox()
        self.col_edit = QLineEdit()
        self.col_edit.setPlaceholderText("例如：归一化Y")
        self.expr_edit = QLineEdit()
        self.expr_edit.setPlaceholderText("例如：(B - np.min(B)) / (np.ptp(B) or 1)")
        self.formula_combo = QComboBox()
        f4.addRow("数据集", self.ds_combo)
        f4.addRow("新列名", self.col_edit)
        f4.addRow("表达式", self.expr_edit)
        f4.addRow("已有公式列", self.formula_combo)
        hint = QLabel("列引用：A/B/C… 或 c1/c2/c3…，任意列名用 col(\"列名\")；"
                      "可用 np、math、x、i。修改源数据后自动重算。")
        hint.setObjectName("hintCard")
        hint.setWordWrap(True)
        f4.addRow(hint)
        row4 = QHBoxLayout()
        self.add_formula_btn = QPushButton("添加 / 更新")
        self.add_formula_btn.setProperty("accent", True)
        self.recalc_btn = QPushButton("全部重算")
        self.del_formula_btn = QPushButton("删除公式列")
        self.del_formula_btn.setProperty("tone", "danger")
        for b in (self.add_formula_btn, self.recalc_btn, self.del_formula_btn):
            row4.addWidget(b)
        f4.addRow(row4)
        root.addWidget(gb4)

        gb5 = QGroupBox("工作簿")
        row5 = QHBoxLayout()
        self.sheet_btn = QPushButton("编辑数据")
        self.sheet_btn.setProperty("tone", "violet")
        self.csv_btn = QPushButton("导出 CSV")
        self.excel_btn = QPushButton("导出 Excel")
        for b in (self.sheet_btn, self.csv_btn, self.excel_btn):
            row5.addWidget(b)
        gb5.setLayout(row5)
        root.addWidget(gb5)

        self.status = QLabel("就绪")
        self.status.setObjectName("hintCard")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addStretch(1)

    def _connect(self) -> None:
        self.new_btn.clicked.connect(self._on_new)
        self.open_btn.clicked.connect(self._on_open)
        self.save_btn.clicked.connect(lambda: self._on_save(False))
        self.saveas_btn.clicked.connect(lambda: self._on_save(True))
        self.undo_btn.clicked.connect(self._on_undo)
        self.redo_btn.clicked.connect(self._on_redo)
        self.style_apply_btn.clicked.connect(self._on_style)
        self.add_formula_btn.clicked.connect(self._on_add_formula)
        self.recalc_btn.clicked.connect(self._on_recalc)
        self.del_formula_btn.clicked.connect(self._on_del_formula)
        self.ds_combo.currentIndexChanged.connect(self._refresh_formula_list)
        self.sheet_btn.clicked.connect(self._on_sheet)
        self.csv_btn.clicked.connect(self._on_export_csv)
        self.excel_btn.clicked.connect(self._on_export_excel)

    # ------------------------------------------------------------------
    def refresh_from_app(self) -> None:
        p = self.app.project
        self.path_label.setText(p.current_path or "未保存的新项目")
        self.undo_btn.setEnabled(p.history.can_undo())
        self.redo_btn.setEnabled(p.history.can_redo())
        self.undo_btn.setToolTip(p.history.undo_label())
        self.redo_btn.setToolTip(p.history.redo_label())
        names = self.app.project.styles()
        current = self.app.config.global_cfg.style_name
        fill_combo_with_names(self.style_combo, names, current)
        fill_combo_with_names(self.ds_combo, self.app.core.dataset_names())
        self._refresh_formula_list()

    def _refresh_formula_list(self) -> None:
        name = self.ds_combo.currentData()
        ds = self.app.core.get_dataset(name) if name else None
        fill_combo_with_names(self.formula_combo,
                              list(ds.formulas.keys()) if ds else [])

    def _status(self, text: str) -> None:
        self.status.setText(text)
        self.app.status(text)

    # ------------------------------------------------------------------
    def _on_new(self) -> None:
        self.app.project.new()
        self._status("已新建空白项目")
        self.refresh_from_app()

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开 Curviva 项目", "", PROJECT_FILTER)
        if not path:
            return
        try:
            self.app.project.open(path)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))
            return
        self._status(f"已打开：{os.path.basename(path)}")
        self.refresh_from_app()

    def _on_save(self, save_as: bool) -> None:
        path = ""
        if save_as or not self.app.project.current_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "保存项目", "untitled.cvproj", PROJECT_FILTER)
            if not path:
                return
        try:
            saved = self.app.project.save(path or None)
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return
        self._status(f"已保存：{os.path.basename(saved)}")
        self.refresh_from_app()

    def _on_undo(self) -> None:
        if self.app.project.undo():
            self._status("已撤销")
        self.refresh_from_app()

    def _on_redo(self) -> None:
        if self.app.project.redo():
            self._status("已重做")
        self.refresh_from_app()

    def _on_style(self) -> None:
        name = self.style_combo.currentData()
        if not name:
            return
        self.app.project.apply_style(name)
        self._status(f"已应用样式：{name}")

    # ------------------------------------------------------------------
    def _on_add_formula(self) -> None:
        ds = self.ds_combo.currentData()
        if not ds:
            QMessageBox.information(self, "提示", "请先导入或选择数据集。")
            return
        try:
            self.app.checkpoint(f"公式列：{self.col_edit.text()}")
            _, errors = self.app.core.add_formula_column(
                ds, self.col_edit.text(), self.expr_edit.text())
        except Exception as e:
            QMessageBox.warning(self, "公式错误", str(e))
            return
        if errors:
            QMessageBox.warning(self, "部分公式重算失败", "\n".join(errors[:6]))
        self.app.refresh("formula")
        self._status(f"公式列已添加：{self.col_edit.text()}")
        self._refresh_formula_list()

    def _on_recalc(self) -> None:
        errors = self.app.core.recompute_all()
        self.app.refresh("recalc")
        self._status("全部公式列已重算" + ("（有错误）" if errors else ""))

    def _on_del_formula(self) -> None:
        ds, col = self.ds_combo.currentData(), self.formula_combo.currentData()
        if not ds or not col:
            return
        self.app.checkpoint(f"删除公式列：{col}")
        self.app.core.remove_formula_column(ds, col)
        self.app.refresh("formula")
        self._status(f"已删除公式列：{col}")
        self._refresh_formula_list()

    # ------------------------------------------------------------------
    def _on_sheet(self) -> None:
        ds = self.ds_combo.currentData()
        if not ds:
            QMessageBox.information(self, "提示", "请先选择数据集。")
            return
        SheetEditorDialog(self.app.core, ds, self).exec()
        self.refresh_from_app()

    def _on_export_csv(self) -> None:
        ds = self.ds_combo.currentData()
        if not ds:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出数据集", f"{ds}.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            self.app.core.export_csv(ds, path)
            self._status(f"已导出：{os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _on_export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出全部工作簿", "curviva_data.xlsx", "Excel 工作簿 (*.xlsx)")
        if not path:
            return
        try:
            self.app.core.export_excel(path)
            self._status(f"已导出：{os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
