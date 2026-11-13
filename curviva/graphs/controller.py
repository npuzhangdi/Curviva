"""图形 / 图片域「控制调用文件」。

GraphController 是图形文档对外的唯一入口：新建图形窗口 / 图片窗口、
尺寸与 DPI、图上文本标注与图例位置、图片路径与缩放、随 .cvproj 保存。
界面（工作区、上下文工具栏、项目树、菜单）与脚本都只调用这里。
"""

import os

from curviva.graphs.model import (
    IMAGE_EXTS,
    KIND_GRAPH,
    KIND_IMAGE,
    SIZE_PRESETS,
    DocumentLibrary,
)


class GraphController:
    def __init__(self, app=None):
        self.app = app
        self.library = DocumentLibrary()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def documents(self, kind: str = None) -> list:
        return self.library.all(kind)

    def get(self, doc_id: str):
        return self.library.get(doc_id)

    def primary(self):
        """主图形文档（没有时自动补建，保证工作区始终有一张图）。"""
        doc = self.library.first(KIND_GRAPH)
        if doc is None:
            doc = self.new_document(KIND_GRAPH, "图形 1", refresh=False)
        return doc

    def size_presets(self) -> list:
        return SIZE_PRESETS

    def to_dict(self) -> dict:
        return self.library.to_dict()

    def load_dict(self, data: dict) -> None:
        self.library.load_dict(data or {})
        if not self.library.first(KIND_GRAPH):
            self.new_document(KIND_GRAPH, "图形 1", refresh=False)
        self._sync_tree_nodes()

    def reset(self) -> None:
        self.library.reset()
        self.new_document(KIND_GRAPH, "图形 1", refresh=False)

    @property
    def workspace(self):
        return getattr(self.app, "workspace", None)

    # ------------------------------------------------------------------
    # 新建 / 删除
    # ------------------------------------------------------------------

    def new_document(self, kind: str = KIND_GRAPH, name: str = "",
                     parent: str = None, refresh: bool = True, **kwargs):
        doc = self.library.create(kind, name, **kwargs)
        ws = self.workspace
        if ws is not None:
            ws.attach_document(kind, doc.name, doc.id, parent)
        if refresh:
            self.app.refresh("new_document")
            self.app.status(f"已新建{'图形' if kind == KIND_GRAPH else '图片'}：{doc.name}")
        return doc

    def new_graph(self, name: str = "", parent: str = None, **kwargs):
        return self.new_document(KIND_GRAPH, name, parent, **kwargs)

    def new_image(self, name: str = "", parent: str = None, path: str = ""):
        return self.new_document(KIND_IMAGE, name, parent, image_path=path or "")

    def import_image(self, path: str, parent: str = None):
        if not path or not os.path.isfile(path):
            raise ValueError("图片文件不存在。")
        name = os.path.splitext(os.path.basename(path))[0]
        doc = self.new_image(name, parent, path=os.path.abspath(path))
        self.app.hook("open_document", doc.id)
        self.app.refresh("import_image")
        return doc

    def is_image_file(path: str) -> bool:
        return os.path.splitext(str(path or ""))[1].lower() in IMAGE_EXTS

    def remove(self, doc_id: str) -> bool:
        doc = self.library.remove(doc_id)
        if doc is None:
            return False
        ws = self.workspace
        if ws is not None:
            ws.remove_document(doc_id)
        self.app.hook("close_document", doc_id)
        self.app.refresh("remove_document")
        return True

    def rename(self, doc_id: str, name: str) -> str:
        final = self.library.rename(doc_id, name)
        if final:
            doc = self.library.get(doc_id)
            ws = self.workspace
            if ws is not None:
                ws.rename_document(doc_id, final)
            self.app.hook("rename_document", doc_id, final)
            self.app.refresh("rename_document")
        return final

    def path_of(self, doc_id: str) -> str:
        ws = self.workspace
        return ws.path_of_document(doc_id) if ws is not None else ""

    # ------------------------------------------------------------------
    # 属性修改（由上下文工具栏 / 图形尺寸对话框 / 图上编辑调用）
    # ------------------------------------------------------------------

    def set_size(self, doc_id: str, w: float, h: float,
                 unit: str = "inch", dpi: int = None) -> None:
        doc = self.library.get(doc_id)
        if doc is None:
            return
        doc.set_size(w, h, unit, dpi)
        self.app.hook("refresh_document", doc_id)
        self.app.refresh("document_size")

    def set_zoom(self, doc_id: str, zoom: int, fit: bool = False) -> None:
        doc = self.library.get(doc_id)
        if doc is None:
            return
        doc.zoom = max(10, min(int(zoom), 800))
        doc.fit_window = bool(fit)
        self.app.hook("refresh_document", doc_id)
        self.app.refresh("document_zoom")

    def set_image_path(self, doc_id: str, path: str) -> None:
        doc = self.library.get(doc_id)
        if doc is not None:
            doc.image_path = os.path.abspath(path) if path else ""
            self.app.hook("refresh_document", doc_id)
            self.app.refresh("document_image")

    def set_mode(self, doc_id: str, mode: str) -> None:
        doc = self.library.get(doc_id)
        if doc is not None:
            doc.mode = mode
            self.app.hook("graph_mode", doc_id, mode)

    def set_selected_curve(self, doc_id: str, index: int) -> None:
        doc = self.library.get(doc_id)
        if doc is not None:
            doc.selected_curve = int(index)

    def set_legend_anchor(self, doc_id: str, anchor) -> None:
        doc = self.library.get(doc_id)
        if doc is not None:
            doc.legend_anchor = [float(anchor[0]), float(anchor[1])] if anchor else None

    def add_text(self, doc_id: str, x: float, y: float, text: str, **kw) -> dict:
        doc = self.library.get(doc_id)
        return doc.add_text(x, y, text, **kw) if doc is not None else {}

    def remove_text(self, doc_id: str, index: int) -> bool:
        doc = self.library.get(doc_id)
        return doc.remove_text(index) if doc is not None else False

    def set_text(self, doc_id: str, index: int, **fields) -> None:
        doc = self.library.get(doc_id)
        if doc is not None and 0 <= index < len(doc.texts):
            doc.texts[index].update(fields)

    def clear_overlays(self, doc_id: str) -> None:
        doc = self.library.get(doc_id)
        if doc is not None:
            doc.texts = []
            doc.legend_anchor = None
            doc.selected_curve = -1
            self.app.hook("refresh_document", doc_id)
            self.app.refresh("document_clear")

    # ------------------------------------------------------------------
    def _sync_tree_nodes(self) -> None:
        """项目状态载入后，补齐文档对应的树节点、清理悬空文档节点。"""
        ws = self.workspace
        if ws is None:
            return
        valid = {d.id for d in self.library.all()}
        ws.prune_documents(valid)
        for doc in self.library.all():
            ws.attach_document(doc.kind, doc.name, doc.id, None)
