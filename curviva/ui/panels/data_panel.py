"""数据面板：数据集导入（CSV / Excel / 剪贴板粘贴）、浏览与预览。"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import numpy as np

from curviva.core.data_manager import DataManager
from curviva.ui import theme
from curviva.ui.panels.data_dialogs import DataPreviewDialog, ExcelSheetDialog


class DataPanel(QWidget):
    """左侧数据管理面板。data_changed 信号通知主窗口刷新全局。

    demo_requested：请求载入完整示例（数据 + 示例曲线），由主窗口响应。
    """

    data_changed = Signal()
    demo_requested = Signal()

    def __init__(self, data_manager: DataManager, app=None, parent=None):
        super().__init__(parent)
        self._data_manager = data_manager
        self._app = app            # 可选：接入总控后使用统一的数据文件打开流程
        self._build_ui()
        self._connect()
        self.refresh_tree()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        grid = QGridLayout()
        grid.setSpacing(4)
        self.import_btn = QPushButton("导入 CSV")
        self.excel_btn = QPushButton("导入 Excel")
        self.paste_btn = QPushButton("粘贴数据")
        self.demo_btn = QPushButton("示例数据")
        self.preview_btn = QPushButton("预览数据")
        self.del_btn = QPushButton("删除选中")
        self.open_btn = QPushButton("打开数据")
        self.sheet_btn = QPushButton("工作表")
        self.paste_sheet_btn = QPushButton("粘贴到新表")
        # 按操作语义着色：导入青色、Excel 品牌渐变、粘贴绿色、
        # 示例紫色、预览橙色、删除红色
        self.import_btn.setProperty("tone", "cyan")
        self.excel_btn.setProperty("accent", True)
        self.paste_btn.setProperty("tone", "green")
        self.demo_btn.setProperty("tone", "violet")
        self.preview_btn.setProperty("tone", "orange")
        self.del_btn.setProperty("tone", "danger")
        self.open_btn.setProperty("accent", True)
        self.sheet_btn.setProperty("tone", "cyan")
        self.paste_sheet_btn.setProperty("tone", "green")
        grid.addWidget(self.import_btn, 0, 0)
        grid.addWidget(self.excel_btn, 0, 1)
        grid.addWidget(self.paste_btn, 0, 2)
        grid.addWidget(self.demo_btn, 1, 0)
        grid.addWidget(self.preview_btn, 1, 1)
        grid.addWidget(self.del_btn, 1, 2)
        grid.addWidget(self.open_btn, 2, 0)
        grid.addWidget(self.sheet_btn, 2, 1)
        grid.addWidget(self.paste_sheet_btn, 2, 2)
        root.addLayout(grid)

        hint = QLabel("双击数据集可预览；「工作表」在底部 Origin 式表格中打开；\n"
                      "支持 CSV/TXT/DAT/Excel，也可把文件拖进窗口或从 Excel 直接粘贴。")
        hint.setObjectName("hintCard")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["数据集 / 数据列", "类型"])
        self.tree.setColumnWidth(0, 130)
        self.tree.setIconSize(QSize(12, 12))
        self.tree.setAlternatingRowColors(True)
        root.addWidget(self.tree)

    def _connect(self) -> None:
        self.import_btn.clicked.connect(self._on_import)
        self.excel_btn.clicked.connect(self._on_import_excel)
        self.paste_btn.clicked.connect(self._on_paste)
        self.demo_btn.clicked.connect(self.demo_requested.emit)
        self.preview_btn.clicked.connect(self._on_preview)
        self.del_btn.clicked.connect(self._on_delete)
        self.open_btn.clicked.connect(self._on_open_file)
        self.sheet_btn.clicked.connect(self._on_open_sheet)
        self.paste_sheet_btn.clicked.connect(self._on_paste_sheet)
        self.tree.itemDoubleClicked.connect(lambda *_: self._on_preview())

    # ------------------------------------------------------------------
    def _status(self, text: str) -> None:
        """在主窗口状态栏显示提示（若可用）。"""
        win = self.window()
        if hasattr(win, "statusBar"):
            win.statusBar().showMessage(text, 8000)

    def _selected_name(self):
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item is not None else None

    def _on_open_file(self) -> None:
        """统一打开入口：CSV / TXT / DAT / TSV / ASC / Excel。"""
        if self._app is None:
            self._on_import()
            return
        from curviva.ui.panels.import_dialog import open_data_file
        open_data_file(self, self._app)
        self.refresh_tree()

    def _on_open_sheet(self) -> None:
        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "提示", "请先选中一个数据集。")
            return
        ui = getattr(self.window(), "ui", None)
        if ui is not None and hasattr(ui, "open_sheet"):
            ui.open_sheet(name)
        else:
            self._on_preview()

    def _on_paste_sheet(self) -> None:
        ui = getattr(self.window(), "ui", None)
        if ui is not None and getattr(ui, "worksheet", None) is not None:
            ui.worksheet.new_from_clipboard(self)
        else:
            self._on_paste()
        self.refresh_tree()

    def _on_import(self) -> None:
        if self._app is not None:
            self._on_open_file()
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 CSV 数据", "", "CSV 文件 (*.csv);;所有文件 (*.*)")
        if not path:
            return
        try:
            ds = self._data_manager.import_csv(path)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"无法导入该文件：\n{e}")
            return
        self.refresh_tree()
        self.data_changed.emit()
        self._status(f"已导入数据集「{ds.name}」")

    def _on_import_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 Excel 工作簿", "",
            "Excel 工作簿 (*.xlsx *.xlsm);;所有文件 (*.*)")
        if not path:
            return
        try:
            sheets = self._data_manager.read_excel_sheets(path)
        except Exception as e:
            QMessageBox.warning(self, "读取失败", f"无法读取该工作簿：\n{e}")
            return
        dlg = ExcelSheetDialog(sheets, self)
        if dlg.exec() != ExcelSheetDialog.Accepted:
            return
        selected = dlg.selected_sheets()
        if not selected:
            return
        try:
            imported = self._data_manager.import_excel(path, selected)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"导入工作表时出错：\n{e}")
            return
        self.refresh_tree()
        self.data_changed.emit()
        self._status(f"已导入 {len(imported)} 个工作表："
                     + "、".join(d.name for d in imported))

    def _on_paste(self) -> None:
        text = QGuiApplication.clipboard().text()
        try:
            ds = self._data_manager.import_clipboard(text)
        except Exception as e:
            QMessageBox.warning(self, "粘贴失败", f"无法从剪贴板创建数据集：\n{e}")
            return
        self.refresh_tree()
        self.data_changed.emit()
        self._status(f"已从剪贴板创建数据集「{ds.name}」"
                     f"（{ds.row_count()} 行 × {len(ds.column_order)} 列）")

    def _on_demo(self) -> None:
        self._data_manager.load_demo_data()
        self.refresh_tree()
        self.data_changed.emit()

    def _on_preview(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        # 数据集名存在条目的 UserRole 中（顶层项与其列子项均可定位）
        name = item.data(0, Qt.UserRole)
        ds = self._data_manager.get_dataset(name) if name else None
        if ds is None:
            return
        DataPreviewDialog(ds, self).exec()

    def _on_delete(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        name = item.data(0, Qt.UserRole)
        if not name:
            return
        self._data_manager.remove_dataset(name)
        self.refresh_tree()
        self.data_changed.emit()

    # ------------------------------------------------------------------
    def refresh_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        for ds in self._data_manager.datasets:
            top = QTreeWidgetItem([ds.name, "数据集"])
            top.setData(0, Qt.UserRole, ds.name)   # 记录数据集名（供预览/删除定位）
            top.setIcon(0, theme.dot_icon(theme.C_VIOLET))
            for col in ds.column_order:
                numeric = isinstance(ds.columns[col], np.ndarray)
                kind = "数值" if numeric else "文本"
                child = QTreeWidgetItem(top, [col, kind])
                child.setData(0, Qt.UserRole, ds.name)
                child.setIcon(0, theme.dot_icon(theme.C_BLUE if numeric else theme.C_ORANGE, 10))
            self.tree.addTopLevelItem(top)
        self.tree.expandAll()
        self.tree.blockSignals(False)
