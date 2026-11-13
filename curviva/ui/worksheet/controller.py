"""工作表域「控制调用文件」。

WorksheetController 是工作表对外的唯一入口：打开/关闭工作表、单元格与
结构编辑后的刷新策略、生成曲线、导出、数据处理对话框、新建与粘贴建表。
界面其余部分（主窗口菜单、项目树、数据面板、示例域）只调用这里或
AppController 注入的 hook("open_sheet")。
"""

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMessageBox

from curviva.config.plot_config import DEFAULT_COLORS, CurveConfig


class WorksheetController:
    def __init__(self, app, ui=None):
        self.app = app
        self.ui = ui
        self.book = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    @property
    def core(self):
        return self.app.core

    def attach(self, book) -> None:
        self.book = book

    def open_sheet(self, name: str, show: bool = True):
        """优先在中间 MDI 工作区打开该表格的独立窗口。"""
        if not name:
            return None
        hook = self.app.hooks.get("open_sheet_window")
        if callable(hook):
            return hook(name)
        if self.book is None:
            return None
        grid = self.book.open_sheet(name)
        if show:
            self.show()
        return grid

    def show(self) -> None:
        """显示「多表工作簿」工作区窗口；无工作区时回退到内嵌 Book。"""
        hook = self.app.hooks.get("open_book_window")
        if callable(hook):
            hook()
            return
        if self.book is not None:
            self.book.show()
            self.book.raise_()

    def active_name(self) -> str:
        return self.book.active_name() if self.book else ""

    def sync_from_app(self) -> None:
        if self.book is not None:
            self.book.sync_from_app()

    def refresh_all(self) -> None:
        self.sync_from_app()
        self.status("工作表已刷新")

    # ------------------------------------------------------------------
    # 刷新策略：单元格/元数据改动只重绘，结构改动才整体刷新
    # ------------------------------------------------------------------

    def status(self, text: str) -> None:
        self.app.status(str(text))

    def checkpoint(self, label: str = "工作表：修改") -> None:
        self.app.checkpoint(label)

    def quiet_changed(self, name: str, message: str = "") -> None:
        self.app.hook("redraw")
        if message:
            self.status(message)

    def structural_changed(self, name: str, message: str = "") -> None:
        self.app.refresh("worksheet")
        if message:
            self.status(message)

    # ------------------------------------------------------------------
    # 结构编辑（曲线引用同步）
    # ------------------------------------------------------------------

    def rename_column(self, name: str, old: str, new: str) -> str:
        final = self.core.rename_column(name, old, new)
        for c in self.app.config.curves:
            if c.dataset_name != name:
                continue
            if c.x_column == old:
                c.x_column = final
            if c.y_column == old:
                c.y_column = final
            if c.error_y_column == old:
                c.error_y_column = final
        return final

    def delete_column(self, name: str, col: str) -> None:
        self.core.remove_column(name, col)
        self.app.config.curves = [
            c for c in self.app.config.curves
            if not (c.dataset_name == name and col in
                    (c.x_column, c.y_column, c.error_y_column))
        ]

    def rename_dataset(self, old: str, new: str) -> str:
        node = self.app.workspace.tree.node_for_ref(old)
        if node is None:
            return self.core.rename_dataset(old, new)
        return self.app.workspace.rename(node.id, new)

    def duplicate(self, name: str) -> str:
        ds = self.core.get_dataset(name)
        if ds is None:
            return ""
        cols = {c: ds.columns[c] for c in ds.column_order}
        clone = self.core.add_result_dataset(f"{name} 副本", cols, ds.formulas)
        for c in ds.column_order:
            clone.set_meta(c, **ds.meta(c))
        folder = self.app.workspace.folder_of_dataset(name)
        self.app.workspace.attach_dataset(clone.name,
                                          folder.id if folder else None)
        self.app.refresh("worksheet_duplicate")
        return clone.name

    # ------------------------------------------------------------------
    # 新建 / 粘贴 / 打开
    # ------------------------------------------------------------------

    def new_sheet(self, parent=None) -> str:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            parent or self.book, "新建工作表", "工作表名称：", text="新建表格")
        if not ok or not name.strip():
            return ""
        self.app.checkpoint("工作表：新建表格")
        node = self.app.workspace.new_sheet(None, name.strip(), 30, 2)
        self.app.refresh("worksheet_new_sheet")
        self.open_sheet(node.ref)
        return node.ref

    def new_from_clipboard(self, parent=None) -> str:
        text = QGuiApplication.clipboard().text()
        if not text or not text.strip():
            QMessageBox.information(parent or self.book, "提示",
                                    "剪贴板中没有文本数据。\n"
                                    "可从 Excel / Origin / 记事本复制几行后再试。")
            return ""
        try:
            self.app.checkpoint("工作表：从剪贴板新建")
            ds = self.core.import_clipboard(text)
            self.app.workspace.attach_dataset(ds.name)
        except Exception as e:                        # noqa: BLE001
            QMessageBox.warning(parent or self.book, "粘贴失败", str(e))
            return ""
        self.app.refresh("worksheet_paste_new")
        self.open_sheet(ds.name)
        return ds.name

    def open_data_file(self, parent=None, wizard: bool = False) -> list:
        from curviva.ui.panels.import_dialog import open_data_file
        return open_data_file(parent or self.book, self.app, wizard=wizard)

    # ------------------------------------------------------------------
    # 绘图 / 分析 / 导出
    # ------------------------------------------------------------------

    def add_curve(self, name: str, y_col: str = "",
                  plot_type: str = "line") -> None:
        cols = self.core.columns(name)
        numeric = self.core.numeric_columns(name)
        if not cols:
            return
        meta = self.core.column_meta(name)
        ds = self.core.get_dataset(name)

        def _usable(col: str) -> bool:
            """列有实际数值（非空且不是恒定值）。"""
            if ds is None:
                return False
            import numpy as _np
            v = ds.columns.get(col)
            if not isinstance(v, _np.ndarray):
                return False
            v = v[_np.isfinite(v)]
            return v.size > 0 and float(_np.ptp(v)) > 0

        usable = [c for c in numeric if _usable(c)]
        x_candidates = [c for c in cols if meta.get(c, {}).get("designation") == "X"]
        if x_candidates and _usable(x_candidates[0]):
            x = x_candidates[0]
        elif usable:
            x = usable[0]
        else:
            x = x_candidates[0] if x_candidates else (
                "X" if "X" in cols else (numeric[0] if numeric else cols[0]))
        y = y_col if y_col in cols else ""
        if not y:
            y = next((c for c in usable if c != x
                      and meta.get(c, {}).get("designation") == "Y"), "")
        if not y:
            y = next((c for c in usable if c != x), "")
        if not y:
            y = next((c for c in numeric if c != x),
                     cols[-1] if len(cols) > 1 else cols[0])
        self.app.checkpoint("工作表：生成曲线")
        n = len(self.app.config.curves)
        self.app.config.curves.append(CurveConfig(
            label=f"{name}·{y}", dataset_name=name, x_column=x, y_column=y,
            plot_type=plot_type,
            color=DEFAULT_COLORS[n % len(DEFAULT_COLORS)]))
        self.app.refresh("worksheet_curve")
        self.status(f"已把「{name}.{y}」加入绘图区")

    def open_operation(self, name: str, key: str = "") -> None:
        from curviva.ui.panels.workspace_dialogs import OperationDialog
        folder = self.app.workspace.folder_of_dataset(name)
        dlg = OperationDialog(self.app, name,
                              folder.id if folder else None, key,
                              self.book)
        dlg.exec()
        self.app.refresh("worksheet_operation")

    def export_csv(self, name: str, include_meta: bool = True) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self.book, "导出工作表 CSV", f"{name}.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            self.core.export_csv(name, path, include_meta)
        except Exception as e:                        # noqa: BLE001
            QMessageBox.warning(self.book, "导出失败", str(e))
            return
        self.status(f"已导出：{path}")

    def export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self.book, "导出全部工作簿", "curviva_workbook.xlsx",
            "Excel 工作簿 (*.xlsx)")
        if not path:
            return
        try:
            self.core.export_excel(path)
        except Exception as e:                        # noqa: BLE001
            QMessageBox.warning(self.book, "导出失败", str(e))
            return
        self.status(f"已导出全部工作簿：{path}")
