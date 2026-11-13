"""中间工作区域「控制调用文件」。

WorkareaController 是工作区对外的唯一入口：把表格 / 图形 / 图片 /
多表工作簿作为 MDI 子窗口打开、激活、显示隐藏、最小化、层叠平铺、
重绘与导出；同时把「当前选中对象」通知上下文工具栏。

界面其它部分（项目树、菜单、示例域、脚本）只调用这里或 AppController
注入的 hook，不直接创建子窗口。
"""

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from curviva.graphs.model import KIND_GRAPH, KIND_IMAGE
from curviva.ui.workarea.mdi_area import WorkareaMdiArea
from curviva.ui.workarea.graph_dialogs import GraphSizeDialog
from curviva.ui.workarea.windows import (
    BookSubWindow,
    GraphSubWindow,
    ImageSubWindow,
    SheetSubWindow,
)

EXPORT_FILTERS = {
    "png": "PNG 图片 (*.png)", "svg": "SVG 矢量图 (*.svg)",
    "eps": "EPS 矢量图 (*.eps)", "pdf": "PDF 矢量文档 (*.pdf)",
    "jpg": "JPEG 图片 (*.jpg)",
}


class WorkareaController:
    def __init__(self, app, ui=None):
        self.app = app
        self.ui = ui
        self.area = WorkareaMdiArea()
        self.windows = {}                 # (kind, id) -> 子窗口
        self.active = None
        self._windows_menu = None
        self.area.active_changed.connect(self._on_active_changed)
        self.area.window_list_changed.connect(self._on_window_list_changed)

    # ------------------------------------------------------------------
    # 装配
    # ------------------------------------------------------------------

    @property
    def sheet_controller(self):
        return getattr(self.ui, "worksheet", None) if self.ui else None

    def attach(self, window) -> None:
        window.setCentralWidget(self.area)
        hooks = self.app.hooks
        hooks["open_sheet"] = self.open_sheet
        hooks["open_sheet_window"] = self.open_sheet
        hooks["open_document"] = self.open_document
        hooks["close_document"] = self.close_document
        hooks["rename_document"] = self.rename_document
        hooks["refresh_document"] = self.refresh_document
        hooks["open_book_window"] = self.open_book
        hooks["graph_mode"] = self.set_graph_mode_hook
        hooks["redraw"] = self.render_graphs
        hooks["active_document"] = self.active_info
        hooks["workarea"] = lambda: self
        # Origin 行为：默认工作区为空，不自动打开任何窗口

    # ------------------------------------------------------------------
    # 打开 / 查找
    # ------------------------------------------------------------------

    def _key(self, kind: str, doc_id: str):
        return (kind, doc_id)

    def _alive(self, sw) -> bool:
        return sw is not None and sw in self.area.windows()

    def find(self, kind: str, doc_id: str):
        return self.area.find(kind, doc_id)

    def open_sheet(self, name: str):
        if not name or self.app.core.get_dataset(name) is None:
            return None
        key = self._key("sheet", name)
        sw = self.windows.get(key)
        if not self._alive(sw):
            if self.sheet_controller is None:
                return None
            sw = SheetSubWindow(self, name)
            self.area.add_window(sw)
            self.windows[key] = sw
        sw.show()
        self.area.activate(sw)
        return sw

    def open_graph(self, doc_id: str = None):
        doc = self.app.graphs.get(doc_id) if doc_id else None
        if doc is None:
            doc = self.app.graphs.primary()
        key = self._key(KIND_GRAPH, doc.id)
        sw = self.windows.get(key)
        if not self._alive(sw):
            sw = GraphSubWindow(self, doc)
            self.area.add_window(sw)
            self.windows[key] = sw
        sw.show()
        self.area.activate(sw)
        return sw

    def open_image(self, doc_id: str = None):
        doc = self.app.graphs.get(doc_id) if doc_id else None
        if doc is None or doc.kind != KIND_IMAGE:
            docs = self.app.graphs.documents(KIND_IMAGE)
            doc = docs[0] if docs else None
        if doc is None:
            return None
        key = self._key(KIND_IMAGE, doc.id)
        sw = self.windows.get(key)
        if not self._alive(sw):
            sw = ImageSubWindow(self, doc)
            self.area.add_window(sw)
            self.windows[key] = sw
        sw.show()
        self.area.activate(sw)
        return sw

    def open_document(self, doc_id: str):
        doc = self.app.graphs.get(doc_id)
        if doc is None:
            return None
        return (self.open_graph(doc_id) if doc.kind == KIND_GRAPH
                else self.open_image(doc_id))

    def open_book(self):
        book = getattr(self.ui, "worksheet_book", None) if self.ui else None
        if book is None:
            return None
        key = self._key("book", "book")
        sw = self.windows.get(key)
        if not self._alive(sw):
            sw = BookSubWindow(self, book)
            self.area.add_window(sw)
            self.windows[key] = sw
        sw.show()
        self.area.activate(sw)
        return sw

    def ensure_primary(self):
        """按需打开主图形窗口（绘图 / 导出等需要画布时才调用）。"""
        doc = self.app.graphs.primary()
        return self.open_graph(doc.id)

    # ------------------------------------------------------------------
    # 关闭 / 刷新 / 同步
    # ------------------------------------------------------------------

    def on_window_closed(self, sw) -> None:
        for key, value in list(self.windows.items()):
            if value is sw:
                self.windows.pop(key, None)
        if self.active is sw:
            self.active = None
            self._notify_context(None)

    def close_document(self, doc_id: str = None) -> None:
        for key, sw in list(self.windows.items()):
            if key[1] == doc_id or (doc_id is None and key[0] != "book"):
                sw.close()
                self.windows.pop(key, None)

    def refresh_document(self, doc_id: str) -> None:
        for (kind, did), sw in list(self.windows.items()):
            if did == doc_id and self._alive(sw):
                sw.refresh_document()

    def rename_document(self, doc_id: str, name: str) -> None:
        for (kind, did), sw in list(self.windows.items()):
            if did == doc_id and self._alive(sw):
                sw.setWindowTitle(name)
                if kind == "sheet":
                    sw.doc.name = name

    def render_graphs(self) -> None:
        for (kind, _), sw in list(self.windows.items()):
            if kind == KIND_GRAPH and self._alive(sw):
                sw.render()

    def sync_from_app(self) -> None:
        """项目状态被替换（打开/撤销/脚本/新建）后同步全部子窗口。"""
        valid_docs = {d.id for d in self.app.graphs.documents()}
        valid_ds = set(self.app.core.dataset_names())
        for key, sw in list(self.windows.items()):
            kind, did = key
            stale = ((kind == "sheet" and did not in valid_ds) or
                     (kind in (KIND_GRAPH, KIND_IMAGE) and did not in valid_docs))
            if stale or not self._alive(sw):
                self.windows.pop(key, None)
                if self._alive(sw):
                    sw.close()
                continue
            if kind != KIND_GRAPH:
                try:
                    sw.refresh_document()
                except Exception:             # noqa: BLE001
                    pass
        self.render_graphs()
        self._notify_context(self.active)

    def primary_canvas(self):
        """返回任一已打开图形窗口的画布；工作区为空时返回 None。"""
        for (kind, _), sw in self.windows.items():
            if kind == KIND_GRAPH and self._alive(sw):
                return sw.canvas
        return None

    # ------------------------------------------------------------------
    # 当前对象与上下文
    # ------------------------------------------------------------------

    def _on_active_changed(self, sw) -> None:
        self.active = sw
        if sw is not None and hasattr(sw, "on_activated"):
            try:
                sw.on_activated()
            except Exception:                 # noqa: BLE001
                pass
        self._notify_context(sw)
        self.area._sync_hint()

    def _on_window_list_changed(self) -> None:
        # 菜单通过 aboutToShow 自行刷新；此处若直接 clear() 会在
        # QAction.toggled 发射途中销毁自身，故只通知上下文工具栏。
        self._notify_context(self.active)

    def _notify_context(self, sw) -> None:
        kind = getattr(sw, "doc_kind", "") if sw is not None else ""
        doc_id = getattr(sw, "doc_id", "") if sw is not None else ""
        title = sw.windowTitle() if sw is not None else ""
        summary = getattr(self.ui, "summary", None) if self.ui else None
        if summary is not None:
            try:
                summary.set_context(kind, doc_id, title)
            except Exception:                  # noqa: BLE001 - 摘要异常不阻断
                pass
        toolbar = getattr(self.ui, "toolbar", None) if self.ui else None
        if toolbar is None:
            return
        if sw is None:
            toolbar.set_context("none", "", "未选中文档", None)
        else:
            toolbar.set_context(kind, doc_id, title, sw)

    def active_info(self) -> dict:
        sw = self.active or self.area.active()
        return {"kind": getattr(sw, "doc_kind", ""),
                "id": getattr(sw, "doc_id", ""),
                "title": sw.windowTitle() if sw else ""}

    def active_sheet_name(self) -> str:
        sw = self.active or self.area.active()
        if sw is None:
            return ""
        if getattr(sw, "doc_kind", "") == "sheet":
            return getattr(sw, "dataset_name", sw.doc_id)
        if getattr(sw, "doc_kind", "") == "book" and hasattr(sw, "book"):
            return sw.book.active_name()
        return ""

    def active_graph_window(self):
        sw = self.active or self.area.active()
        if sw is not None and getattr(sw, "doc_kind", "") == KIND_GRAPH:
            return sw
        for (kind, _), w in self.windows.items():
            if kind == KIND_GRAPH and self._alive(w):
                return w
        return None

    def active_image_window(self):
        sw = self.active or self.area.active()
        return sw if sw is not None and getattr(sw, "doc_kind", "") == KIND_IMAGE else None

    # ------------------------------------------------------------------
    # 新建 / 尺寸 / 导出 / 快速拟合
    # ------------------------------------------------------------------

    def new_graph(self, name: str = ""):
        self.app.checkpoint("工作区：新建图形")
        doc = self.app.graphs.new_graph(name)
        self.open_graph(doc.id)
        return doc

    def new_image(self, name: str = "", path: str = ""):
        self.app.checkpoint("工作区：新建图片")
        doc = self.app.graphs.new_image(name, path=path)
        self.open_image(doc.id)
        return doc

    def import_image(self, parent=None) -> None:
        path, _ = QFileDialog.getOpenFileName(
            parent or self.area, "导入图片文件", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp *.svg);;"
            "所有文件 (*.*)")
        if path:
            self.app.checkpoint("工作区：导入图片")
            doc = self.app.graphs.import_image(path)
            self.open_image(doc.id)

    def open_size_dialog(self, doc_id: str = None) -> None:
        doc = self.app.graphs.get(doc_id) or self.app.graphs.primary()
        dlg = GraphSizeDialog(doc, self.area)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        self.app.checkpoint("图形：修改尺寸")
        self.app.graphs.set_size(doc.id, **v)
        self.app.status(f"「{doc.name}」尺寸已设为 {doc.display_size()} @ {doc.dpi} dpi")

    def export_graph(self, doc_id: str = None, fmt: str = "png") -> None:
        sw = self.active_graph_window()
        doc = self.app.graphs.get(doc_id) if doc_id else None
        if doc is not None:
            target = self.find(KIND_GRAPH, doc.id)
            if target is not None:
                sw = target
        if sw is None:
            if not self.app.graphs.documents(KIND_GRAPH):
                QMessageBox.information(
                    self.area, "导出图形", "工作区中没有图形窗口。\n"
                    "请先选中表格并使用「绘图」菜单生成图形。")
                return
            sw = self.ensure_primary()
        path, _ = QFileDialog.getSaveFileName(
            self.area, "导出当前图形", f"{sw.doc.name}.{fmt}",
            EXPORT_FILTERS.get(fmt, EXPORT_FILTERS["png"]))
        if not path:
            return
        try:
            sw.export(path, fmt)
        except Exception as e:                 # noqa: BLE001
            QMessageBox.warning(self.area, "导出失败", str(e))
            return
        self.app.status(f"已导出图形：{path}（{sw.doc.display_size()}）")

    def set_graph_mode(self, mode: str) -> None:
        sw = self.active_graph_window()
        if sw is not None:
            sw.set_mode(mode)

    def set_graph_mode_hook(self, doc_id: str, mode: str) -> None:
        sw = self.find(KIND_GRAPH, doc_id)
        if sw is not None and hasattr(sw, "editor"):
            sw.editor.set_mode(mode)
        toolbar = getattr(self.ui, "toolbar", None) if self.ui else None
        if toolbar is not None:
            toolbar.sync_mode(mode)

    def quick_fit(self, dataset_name: str = "", model_key: str = "linear") -> None:
        name = dataset_name or self.active_sheet_name() or \
            (self.app.core.dataset_names() or [""])[0]
        if not name:
            QMessageBox.information(self.area, "提示", "请先打开一张工作表。")
            return
        cols = self.app.core.numeric_columns(name)
        if len(cols) < 2:
            QMessageBox.information(self.area, "提示", "该表格至少需要两列数值数据。")
            return
        meta = self.app.core.column_meta(name)
        x_col = next((c for c in cols if meta.get(c, {}).get("designation") == "X"),
                     cols[0])
        y_col = next((c for c in cols if c != x_col), cols[-1])
        try:
            self.app.checkpoint("工具栏：快速拟合")
            result = self.app.fitting.fit({
                "dataset": name, "x_col": x_col, "y_col": y_col,
                "model_key": model_key})
            self.app.fitting.add_fit_curve(result)
            self.app.refresh("quick_fit")
            self.open_graph()
            self.app.status(
                f"{result.name} 拟合完成：R² = {getattr(result, 'r2', float('nan')):.6g}")
        except Exception as e:                 # noqa: BLE001
            QMessageBox.warning(self.area, "拟合失败", str(e))

    def active_operation(self, key: str = "") -> None:
        name = self.active_sheet_name()
        if not name:
            QMessageBox.information(self.area, "提示", "请先选中一张工作表。")
            return
        if self.sheet_controller is not None:
            self.sheet_controller.open_operation(name, key)

    # ------------------------------------------------------------------
    # 窗口管理菜单
    # ------------------------------------------------------------------

    def windows_info(self) -> list:
        out = []
        for sw in self.area.windows():
            out.append({"kind": getattr(sw, "doc_kind", ""),
                        "id": getattr(sw, "doc_id", ""),
                        "title": sw.windowTitle(),
                        "visible": sw.isVisible(),
                        "minimized": sw.isMinimized()})
        return out

    def build_windows_menu(self, menu) -> None:
        menu.addSeparator()
        sub = menu.addMenu("工作区文档窗口")
        self._windows_menu = sub
        sub.aboutToShow.connect(self._fill_windows_menu)
        menu.addAction("层叠排列", self.area.cascade_all)
        menu.addAction("平铺排列", self.area.tile_all)
        menu.addAction("最小化全部文档", self.area.minimize_all)
        menu.addAction("还原全部文档", self.area.restore_all)
        menu.addAction("关闭全部文档", self.area.close_all)
        menu.addSeparator()
        menu.addAction("打开多表工作簿", self.open_book)
        menu.addAction("新建图形窗口", lambda: self.new_graph())
        menu.addAction("新建图片窗口", lambda: self.new_image())
        self._fill_windows_menu()

    def _fill_windows_menu(self) -> None:
        sub = self._windows_menu
        if sub is None:
            return
        sub.clear()
        wins = self.area.windows()
        if not wins:
            act = sub.addAction("（暂无打开的文档窗口）")
            act.setEnabled(False)
            return
        for sw in wins:
            title = sw.windowTitle()
            act = QAction(title, sub)
            act.setCheckable(True)
            act.setChecked(sw.isVisible())
            act.setToolTip("勾选显示 / 取消勾选隐藏该文档窗口")
            act.toggled.connect(
                lambda checked, w=sw: self.area.set_window_visible(w, checked))
            sub.addAction(act)
            ops = sub.addMenu(f"{title} · 操作")
            ops.addAction("激活 / 前置", lambda w=sw: self.area.activate(w))
            ops.addAction("最小化", lambda w=sw: w.showMinimized())
            ops.addAction("还原", lambda w=sw: (w.showNormal(), w.show()))
            ops.addAction("关闭", lambda w=sw: w.close())
        sub.addSeparator()
        sub.addAction("全部显示", lambda: [self.area.set_window_visible(w, True)
                                          for w in self.area.windows()])
        sub.addAction("全部隐藏", lambda: [self.area.set_window_visible(w, False)
                                          for w in self.area.windows()])
