"""Excel 工作表选择对话框 + 数据预览对话框。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
)

MAX_PREVIEW_ROWS = 200


class ExcelSheetDialog(QDialog):
    """展示工作簿中的全部工作表，点选（高亮）要导入的表。

    交互语义：选中几行就导入几行，未选中不导入；默认全部未选中。
    """

    def __init__(self, sheet_names: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择要导入的工作表")
        self.setMinimumWidth(320)

        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "在列表中点选要导入的工作表（可按住 Ctrl 多选），\n"
            "每个选中表将生成一个独立数据集。未选中不导入："))

        self.sheet_list = QListWidget()
        self.sheet_list.setSelectionMode(QListWidget.MultiSelection)
        for name in sheet_names:
            self.sheet_list.addItem(name)
        if len(sheet_names) == 1:
            self.sheet_list.setCurrentRow(0)   # 单表工作簿默认选中
        root.addWidget(self.sheet_list)

        sel_row = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_none_btn = QPushButton("全不选")
        select_all_btn.clicked.connect(self._select_all)
        select_none_btn.clicked.connect(self._select_none)
        sel_row.addWidget(select_all_btn)
        sel_row.addWidget(select_none_btn)
        sel_row.addStretch(1)
        root.addLayout(sel_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        ok_btn = QPushButton("导入")
        ok_btn.setProperty("accent", True)
        cancel_btn = QPushButton("取消")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

    def _select_all(self) -> None:
        self.sheet_list.selectAll()

    def _select_none(self) -> None:
        self.sheet_list.clearSelection()

    def selected_sheets(self) -> list:
        return [it.text() for it in self.sheet_list.selectedItems()]


class DataPreviewDialog(QDialog):
    """以表格形式查看数据集内容（最多展示前 200 行）。"""

    def __init__(self, dataset, parent=None):
        super().__init__(parent)
        n = dataset.row_count()
        shown = min(n, MAX_PREVIEW_ROWS)
        self.setWindowTitle(f"数据预览 — {dataset.name}（前 {shown} 行 / 共 {n} 行）")
        self.resize(640, 480)

        root = QVBoxLayout(self)
        table = QTableWidget(shown, len(dataset.column_order), self)
        table.setHorizontalHeaderLabels(dataset.column_order)
        table.setEditTriggers(QTableWidget.NoEditTriggers)

        for r in range(shown):
            for c, col in enumerate(dataset.column_order):
                table.setItem(r, c, _make_item(dataset.columns[col][r]))

        root.addWidget(table)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.setProperty("accent", True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)


def _make_item(value):
    from PySide6.QtWidgets import QTableWidgetItem
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value)
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item
