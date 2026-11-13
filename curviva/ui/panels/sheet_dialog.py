"""工作簿编辑对话框：像 Origin Worksheet 一样改单元格与表格结构。

支持：单元格编辑、增删列、重命名列、增删行、Python 公式列。
所有结构操作都经 CoreController，保证项目树与曲线引用同步刷新。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

MAX_ROWS = 500


class SheetEditorDialog(QDialog):
    """编辑一个数据集（最多显示前 500 行）。"""

    def __init__(self, core, dataset_name: str, parent=None):
        super().__init__(parent)
        self.core = core
        self.dataset_name = dataset_name
        self.setWindowTitle(f"工作簿 - {dataset_name}")
        self.resize(720, 520)

        root = QVBoxLayout(self)
        tip = QLabel("双击单元格即可编辑；列/行结构操作立即生效，单元格需点「保存修改」。"
                     "（最多显示前 500 行；公式列用 Python 表达式）")
        tip.setObjectName("hintCard")
        tip.setWordWrap(True)
        root.addWidget(tip)

        bar = QHBoxLayout()
        self.add_col_btn = QPushButton("新增列")
        self.rename_col_btn = QPushButton("重命名列")
        self.del_col_btn = QPushButton("删除列")
        self.add_row_btn = QPushButton("添加行")
        self.del_row_btn = QPushButton("删除行")
        for b, tone in ((self.add_col_btn, "cyan"), (self.rename_col_btn, "violet"),
                        (self.del_col_btn, "danger"), (self.add_row_btn, "green"),
                        (self.del_row_btn, "danger")):
            b.setProperty("tone", tone)
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableWidget()
        root.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("hintCard")
        self.save_btn = QPushButton("保存修改")
        self.save_btn.setProperty("accent", True)
        self.close_btn = QPushButton("关闭")
        row.addWidget(self.status, 1)
        row.addWidget(self.save_btn)
        row.addWidget(self.close_btn)
        root.addLayout(row)

        self.add_col_btn.clicked.connect(self._on_add_col)
        self.rename_col_btn.clicked.connect(self._on_rename_col)
        self.del_col_btn.clicked.connect(self._on_del_col)
        self.add_row_btn.clicked.connect(self._on_add_rows)
        self.del_row_btn.clicked.connect(self._on_del_rows)
        self.save_btn.clicked.connect(self._on_save)
        self.close_btn.clicked.connect(self.reject)
        self._load()

    # ------------------------------------------------------------------
    def _checkpoint(self, label: str) -> None:
        app = getattr(self.core, "app", None)
        if app is not None:
            app.checkpoint(label)

    def _refresh_app(self, reason: str = "worksheet") -> None:
        app = getattr(self.core, "app", None)
        if app is not None:
            app.refresh(reason)

    def _load(self) -> None:
        ds = self.core.get_dataset(self.dataset_name)
        if ds is None:
            self.status.setText("表格不存在，可能已被删除")
            return
        cols = list(ds.column_order)
        n = min(ds.row_count(), MAX_ROWS)
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setRowCount(n)
        for r in range(n):
            for j, col in enumerate(cols):
                value = ds.columns[col][r]
                text = f"{value:.10g}" if isinstance(value, float) else str(value)
                item = QTableWidgetItem(text)
                if col in ds.formulas:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, j, item)
        self.status.setText(f"{ds.name}　·　{ds.row_count()} 行 × {len(cols)} 列")

    def _current_col(self) -> str:
        ds = self.core.get_dataset(self.dataset_name)
        if ds is None:
            return ""
        j = self.table.currentColumn()
        if j < 0 or j >= len(ds.column_order):
            return ""
        return ds.column_order[j]

    # ------------------------------------------------------------------
    def _on_add_col(self) -> None:
        name, ok = QInputDialog.getText(self, "新增列", "列名：", text="Y2")
        if not ok or not name.strip():
            return
        expr, ok2 = QInputDialog.getText(
            self, "列内容（可选）",
            "Python 表达式，留空则填 0：\n"
            "列引用 A/B/C… 或 col(\"列名\")，可用 np、math、x、i",
            text="")
        if not ok2:
            return
        try:
            self._checkpoint("工作簿：新增列")
            if expr.strip():
                self.core.add_formula_column(
                    self.dataset_name, name.strip(), expr.strip())[0]
            else:
                self.core.add_column(self.dataset_name, name.strip())
        except Exception as e:                        # noqa: BLE001
            QMessageBox.warning(self, "新增列失败", str(e))
            return
        self._refresh_app("worksheet_col")
        self._load()

    def _on_rename_col(self) -> None:
        old = self._current_col()
        if not old:
            QMessageBox.information(self, "提示", "请先点选一个列。")
            return
        name, ok = QInputDialog.getText(self, "重命名列", "新列名：", text=old)
        if not ok or not name.strip():
            return
        try:
            self._checkpoint("工作簿：重命名列")
            final = self.core.rename_column(self.dataset_name, old, name.strip())
        except Exception as e:                        # noqa: BLE001
            QMessageBox.warning(self, "重命名失败", str(e))
            return
        self._sync_curve_columns(old, final)
        self._refresh_app("worksheet_rename")
        self._load()

    def _sync_curve_columns(self, old: str, new: str) -> None:
        app = getattr(self.core, "app", None)
        if app is None or old == new:
            return
        for c in app.config.curves:
            if c.dataset_name != self.dataset_name:
                continue
            if c.x_column == old:
                c.x_column = new
            if c.y_column == old:
                c.y_column = new

    def _on_del_col(self) -> None:
        col = self._current_col()
        if not col:
            QMessageBox.information(self, "提示", "请先点选一个列。")
            return
        if QMessageBox.question(self, "删除列", f"确定删除列「{col}」吗？",
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self._checkpoint("工作簿：删除列")
            self.core.remove_column(self.dataset_name, col)
        except Exception as e:                        # noqa: BLE001
            QMessageBox.warning(self, "删除列失败", str(e))
            return
        self._refresh_app("worksheet_delcol")
        self._load()

    def _on_add_rows(self) -> None:
        count, ok = QInputDialog.getInt(self, "添加行", "添加行数：",
                                        10, 1, 100000, 10)
        if not ok:
            return
        self._checkpoint("工作簿：添加行")
        self.core.add_rows(self.dataset_name, count)
        self._refresh_app("worksheet_addrow")
        self._load()

    def _on_del_rows(self) -> None:
        start = self.table.currentRow()
        if start < 0:
            QMessageBox.information(self, "提示", "请先点选要删除的起始行。")
            return
        count, ok = QInputDialog.getInt(
            self, "删除行", f"从第 {start + 1} 行起删除的行数：", 1, 1, 100000, 1)
        if not ok:
            return
        self._checkpoint("工作簿：删除行")
        self.core.remove_rows(self.dataset_name, start, count)
        self._refresh_app("worksheet_delrow")
        self._load()

    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        ds = self.core.get_dataset(self.dataset_name)
        if ds is None:
            return
        changed = 0
        for r in range(self.table.rowCount()):
            for j, col in enumerate(ds.column_order):
                item = self.table.item(r, j)
                if item is None or col in ds.formulas:
                    continue
                if self.core.set_cell(self.dataset_name, col, r, item.text()):
                    changed += 1
        errors = self.core.recompute_all()
        if errors:
            QMessageBox.warning(self, "公式列重算提示", "\n".join(errors[:8]))
        self._refresh_app("worksheet")
        self.status.setText(f"已写入 {changed} 个单元格")
        QMessageBox.information(self, "已保存", f"已写入 {changed} 个单元格。")
