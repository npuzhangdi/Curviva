"""多工作表标签窗口（Origin 的 Book 概念）+ 常用工具栏。

每张表是一个 WorksheetGrid，标签可关闭、重命名、复制；窗口本身是普通
QDockWidget 的内容，因此「窗口管理」可单独设置显示 / 停靠 / 浮动 / 尺寸。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from curviva.ui.worksheet.worksheet_grid import WorksheetGrid


class WorksheetBook(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctl = controller
        self.setObjectName("worksheetBook")
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        # ---------- 工具栏第一行 ----------
        row1 = QHBoxLayout()
        row1.setSpacing(5)
        row1.addWidget(self._btn("新建表格", "accent", self._on_new_sheet))
        row1.addWidget(self._btn("打开数据文件…", "cyan",
                                 lambda: self.ctl.open_data_file(self)))
        row1.addWidget(self._btn("文本导入向导…", "violet",
                                 lambda: self.ctl.open_data_file(self, wizard=True)))
        row1.addWidget(self._btn("从剪贴板新建", "green",
                                 lambda: self.ctl.new_from_clipboard(self)))
        row1.addSpacing(8)
        row1.addWidget(self._btn("复制", "", self._on_copy))
        row1.addWidget(self._btn("粘贴", "", self._on_paste))
        row1.addWidget(self._btn("清空", "danger", self._on_clear))
        row1.addStretch(1)
        row1.addWidget(self._btn("刷新", "orange", self.ctl.refresh_all))
        root.addLayout(row1)

        # ---------- 工具栏第二行 ----------
        row2 = QHBoxLayout()
        row2.setSpacing(5)
        row2.addWidget(self._btn("插入列", "", self._on_insert_col))
        row2.addWidget(self._btn("插入行", "", self._on_insert_row))
        row2.addWidget(self._btn("删除列", "danger", self._on_delete_col))
        row2.addWidget(self._btn("删除行", "danger", self._on_delete_row))
        row2.addSpacing(8)
        self.meta_cb = QCheckBox("显示列头信息（长名称 / 单位 / 注释 / 公式）")
        self.meta_cb.setChecked(True)
        self.meta_cb.toggled.connect(self._on_meta_toggled)
        row2.addWidget(self.meta_cb)
        self.header_cb = QCheckBox("粘贴首行作列名")
        self.header_cb.setToolTip("勾选后，从 Excel 粘贴时第一行会写成列名")
        self.header_cb.toggled.connect(self._on_header_toggled)
        row2.addWidget(self.header_cb)
        row2.addStretch(1)
        row2.addWidget(self._btn("导出 CSV", "", self._on_export_csv))
        row2.addWidget(self._btn("导出 Excel", "", self.ctl.export_excel))
        root.addLayout(row2)

        # ---------- 标签页 ----------
        self.empty = QLabel(
            "尚未打开工作表　·　双击左侧项目树的表格，或用「打开数据文件 / 从剪贴板新建」开始\n"
            "支持 CSV / TXT / DAT / TSV / Excel；可直接从 Excel 复制后按 Ctrl+V 粘贴进表格")
        self.empty.setObjectName("hintCard")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        root.addWidget(self.empty, 1)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self._on_tab_menu)
        root.addWidget(self.tabs, 1)

        self.info = QLabel("就绪")
        self.info.setObjectName("hintCard")
        root.addWidget(self.info)
        self._sync_empty()

    # ------------------------------------------------------------------
    def _btn(self, text: str, tone: str, slot, checkable: bool = False) -> QPushButton:
        btn = QPushButton(text)
        if tone == "accent":
            btn.setProperty("accent", True)
        elif tone:
            btn.setProperty("tone", tone)
        btn.setCheckable(checkable)
        btn.clicked.connect(slot)
        return btn

    def _sync_empty(self) -> None:
        has = self.tabs.count() > 0
        self.tabs.setVisible(has)
        self.empty.setVisible(not has)

    # ------------------------------------------------------------------
    # 标签管理
    # ------------------------------------------------------------------

    def open_sheet(self, name: str):
        if self.ctl.core.get_dataset(name) is None:
            return None
        for i in range(self.tabs.count()):
            grid = self.tabs.widget(i)
            if getattr(grid, "dataset_name", "") == name:
                self.tabs.setCurrentIndex(i)
                return grid
        grid = WorksheetGrid(self.ctl, name)
        grid.set_show_meta(self.meta_cb.isChecked())
        grid.set_paste_header(self.header_cb.isChecked())
        grid.selection_info_changed.connect(self.info.setText)
        i = self.tabs.addTab(grid, name)
        self.tabs.setCurrentIndex(i)
        self._sync_empty()
        return grid

    def close_tab(self, index: int) -> None:
        if 0 <= index < self.tabs.count():
            self.tabs.removeTab(index)
            self._sync_empty()

    def active_name(self) -> str:
        grid = self.current_grid()
        return grid.dataset_name if grid else ""

    def current_grid(self):
        return self.tabs.currentWidget()

    def sync_from_app(self) -> None:
        names = set(self.ctl.app.core.dataset_names())
        for i in reversed(range(self.tabs.count())):
            grid = self.tabs.widget(i)
            if grid.dataset_name not in names:
                self.tabs.removeTab(i)
                continue
            grid.refresh()
            self.tabs.setTabText(i, grid.dataset_name)
        self._sync_empty()
        grid = self.current_grid()
        if grid is not None:
            self.info.setText(getattr(grid, "_status", grid.dataset_name))

    def _on_tab_changed(self, _index: int) -> None:
        grid = self.current_grid()
        if grid is not None:
            self.info.setText(getattr(grid, "_status", grid.dataset_name))

    def _on_tab_menu(self, pos) -> None:
        index = self.tabs.tabBar().tabAt(pos)
        if index < 0:
            return
        grid = self.tabs.widget(index)
        name = grid.dataset_name
        menu = QMenu(self)
        menu.addAction("重命名工作表…", lambda: self._rename_tab(index, name))
        menu.addAction("复制工作表", lambda: self._duplicate_tab(name))
        menu.addSeparator()
        menu.addAction("关闭", lambda: self.close_tab(index))
        menu.addAction("关闭其它工作表", lambda: self._close_others(index))
        menu.exec(self.tabs.tabBar().mapToGlobal(pos))

    def _rename_tab(self, index: int, name: str) -> None:
        new, ok = QInputDialog.getText(self, "重命名工作表", "新名称：", text=name)
        if not ok or not new.strip() or new.strip() == name:
            return
        self.ctl.checkpoint("工作表：重命名表格")
        final = self.ctl.rename_dataset(name, new.strip())
        self.ctl.app.refresh("worksheet_rename")
        self.open_sheet(final)

    def _duplicate_tab(self, name: str) -> None:
        self.ctl.checkpoint("工作表：复制表格")
        final = self.ctl.duplicate(name)
        if final:
            self.open_sheet(final)

    def _close_others(self, keep: int) -> None:
        for i in reversed(range(self.tabs.count())):
            if i != keep:
                self.tabs.removeTab(i)
        self._sync_empty()

    # ------------------------------------------------------------------
    # 工具栏动作
    # ------------------------------------------------------------------

    def _need_grid(self, message: str = "请先打开一张工作表。"):
        grid = self.current_grid()
        if grid is None:
            QMessageBox.information(self, "提示", message)
        return grid

    def _on_new_sheet(self) -> None:
        self.ctl.new_sheet(self)

    def _on_copy(self) -> None:
        grid = self._need_grid()
        if grid:
            grid.copy_selection(False)

    def _on_paste(self) -> None:
        grid = self._need_grid("请先打开一张工作表，再按粘贴。")
        if grid:
            grid.paste_from_clipboard()

    def _on_clear(self) -> None:
        grid = self._need_grid()
        if grid:
            grid.clear_selection()

    def _on_insert_col(self) -> None:
        grid = self._need_grid()
        if grid:
            grid.insert_column()

    def _on_insert_row(self) -> None:
        grid = self._need_grid()
        if grid:
            grid.insert_row()

    def _on_delete_col(self) -> None:
        grid = self._need_grid()
        if grid:
            grid.delete_column()

    def _on_delete_row(self) -> None:
        grid = self._need_grid()
        if grid:
            grid.delete_row()

    def _on_meta_toggled(self, checked: bool) -> None:
        for i in range(self.tabs.count()):
            self.tabs.widget(i).set_show_meta(checked)

    def _on_header_toggled(self, checked: bool) -> None:
        for i in range(self.tabs.count()):
            self.tabs.widget(i).set_paste_header(checked)

    def _on_export_csv(self) -> None:
        name = self.active_name()
        if name:
            self.ctl.export_csv(name)
        else:
            QMessageBox.information(self, "提示", "请先打开一张工作表。")
