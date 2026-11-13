"""工作区（项目资源管理器）域「控制调用文件」。

WorkspaceController 是项目树对外的唯一入口：文件夹/表格的增删改名移动、
数据集与树节点的双向同步、以及随 .cvproj 保存与撤销重做。
界面、脚本、插件一律通过它操作树，不直接触碰 model.WorkspaceTree。
"""

from curviva.workspace.model import (
    DEFAULT_FOLDER_ID,
    DOCUMENT_KINDS,
    KIND_FOLDER,
    KIND_ROOT,
    KIND_SHEET,
    ROOT_ID,
    WorkspaceTree,
)


class WorkspaceController:
    def __init__(self, app=None):
        self.app = app
        self.tree = WorkspaceTree()
        self.active_folder_id = DEFAULT_FOLDER_ID   # 新建/导入/分析结果的默认归属

    # ------------------------------------------------------------------
    # 生命周期与序列化
    # ------------------------------------------------------------------

    def reset(self, project_name: str = "未命名项目") -> None:
        self.tree = WorkspaceTree(project_name)
        self.active_folder_id = DEFAULT_FOLDER_ID

    def to_dict(self) -> dict:
        return self.tree.to_dict()

    def load_dict(self, data: dict) -> None:
        self.tree.load_dict(data or {})
        if self.tree.find(self.active_folder_id) is None:
            self.active_folder_id = DEFAULT_FOLDER_ID

    @property
    def project_name(self) -> str:
        return self.tree.project_name

    def set_project_name(self, name: str) -> None:
        name = (name or "").strip() or "未命名项目"
        self.tree.project_name = name
        self.tree.root.name = name

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def node(self, node_id: str):
        return self.tree.find(node_id)

    def root(self):
        return self.tree.root

    def path(self, node_id: str) -> str:
        return self.tree.path_of(node_id)

    def set_active_folder(self, node_id: str) -> None:
        n = self.tree.find(node_id) if node_id else None
        if n is not None and n.is_folder():
            self.active_folder_id = n.id

    def active_folder(self):
        return (self.tree.find(self.active_folder_id)
                or self.tree.find(DEFAULT_FOLDER_ID)
                or self.tree.root)

    def folder_of_dataset(self, name: str):
        return self.tree.folder_for_ref(name)

    def path_of_dataset(self, name: str) -> str:
        node = self.tree.node_for_ref(name)
        return self.tree.path_of(node.id) if node is not None else ""

    # --- 图形 / 图片文档节点的树操作 ---------------------------------

    def attach_document(self, kind: str, name: str, doc_id: str,
                        parent_id: str = None):
        existing = self.tree.node_for_document(doc_id)
        if existing is not None:
            existing.name = name
            existing.kind = kind
            if parent_id:
                self.tree.move(existing.id, self._folder(parent_id).id)
            return existing
        return self.tree.add_document(self._folder(parent_id).id,
                                      name, kind, doc_id)

    def remove_document(self, doc_id: str) -> bool:
        node = self.tree.node_for_document(doc_id)
        if node is None:
            return False
        self.tree.remove(node.id)
        return True

    def rename_document(self, doc_id: str, name: str) -> None:
        node = self.tree.node_for_document(doc_id)
        if node is not None:
            node.name = name

    def prune_documents(self, valid_ids: set) -> None:
        self.tree.prune_documents(set(valid_ids or ()))

    def folder_of_document(self, doc_id: str):
        return self.tree.document_folder(doc_id)

    def path_of_document(self, doc_id: str) -> str:
        node = self.tree.node_for_document(doc_id)
        return self.tree.path_of(node.id) if node is not None else ""

    # ------------------------------------------------------------------
    # 节点操作（调用方负责在改动前 app.checkpoint()）
    # ------------------------------------------------------------------

    def new_folder(self, parent_id: str = None, name: str = "新建文件夹"):
        parent = self._folder(parent_id)
        return self.tree.add_folder(parent.id, name)

    def new_sheet(self, parent_id: str = None, name: str = "新建表格",
                  rows: int = 30, columns: int = 2):
        """新建一张空白表格：既创建数据集，也挂到项目树。"""
        parent = self._folder(parent_id)
        final_name = self.tree.unique_child_name(parent.id, name or "新建表格")
        ds = self.app.core.create_sheet(final_name, rows=int(rows), ncols=int(columns))
        return self.tree.add_sheet(parent.id, ds.name, ds.name)

    def add_dataset(self, ds, parent_id: str = None):
        return self.attach_dataset(ds.name, parent_id)

    def attach_dataset(self, name: str, parent_id: str = None):
        """把一个已存在的数据集挂到指定文件夹；已登记则只调整位置。"""
        existing = self.tree.node_for_ref(name)
        if existing is not None:
            if parent_id:
                self.tree.move(existing.id, self._folder(parent_id).id)
            return existing
        return self.tree.add_sheet(self._folder(parent_id).id, name, name)

    def rename(self, node_id: str, new_name: str) -> str:
        """重命名节点；表格会同步重命名数据集与所有引用它的曲线。"""
        node = self.tree.find(node_id)
        if node is None or node.kind == KIND_ROOT:
            raise ValueError("项目根节点不能重命名。")
        new_name = (new_name or "").strip()
        if not new_name:
            raise ValueError("名称不能为空。")
        final = self.tree.rename(node_id, new_name)
        if node.kind in DOCUMENT_KINDS and node.ref:
            graphs = getattr(self.app, "graphs", None)
            if graphs is not None:
                final = graphs.library.rename(node.ref, final) or final
            node.name = final
            return final
        if node.kind == KIND_SHEET and node.ref:
            old = node.ref
            renamed = self.app.core.rename_dataset(old, final)
            node.ref = renamed
            node.name = renamed
            for curve in self.app.config.curves:
                if curve.dataset_name == old:
                    curve.dataset_name = renamed
            return renamed
        return final

    def remove(self, node_id: str, delete_data: bool = True) -> list:
        """删除节点。delete_data=True 时同时删除数据集与引用它们的曲线。"""
        node = self.tree.find(node_id)
        if node is None or node.kind == KIND_ROOT:
            return []
        if node.kind in DOCUMENT_KINDS and node.ref:
            graphs = getattr(self.app, "graphs", None)
            if graphs is not None:
                graphs.remove(node.ref)
            return []
        refs = self.tree.remove(node_id)
        if delete_data and refs:
            ref_set = set(refs)
            for name in refs:
                self.app.core.remove_dataset(name)
            self.app.config.curves = [
                c for c in self.app.config.curves if c.dataset_name not in ref_set
            ]
        if self.tree.find(self.active_folder_id) is None:
            self.active_folder_id = DEFAULT_FOLDER_ID
        return refs

    def move(self, node_id: str, new_parent_id: str, index: int = None) -> bool:
        return self.tree.move(node_id, new_parent_id, index)

    def _folder(self, node_id):
        n = self.tree.find(node_id) if node_id else None
        if n is not None and n.is_folder():
            return n
        return self.active_folder()

    # ------------------------------------------------------------------
    # 同步与脚本 API
    # ------------------------------------------------------------------

    def sync(self, preferred_folder: str = None) -> list:
        """把当前全部数据集同步进树（自动补挂 / 清理悬空节点）。"""
        folder = preferred_folder or self.active_folder_id
        return self.tree.sync(self.app.core.dataset_names(), folder)

    def summary(self) -> dict:
        nodes = list(self.tree.root.walk())
        return {
            "project": self.tree.project_name,
            "folders": sum(1 for n in nodes if n.kind == KIND_FOLDER),
            "sheets": sum(1 for n in nodes if n.kind == KIND_SHEET),
            "active_folder": self.active_folder().name,
        }

    def outline(self, limit: int = 200) -> list:
        """返回 [(层级, 类型, 名称)]，供脚本 / 工作台视图使用。"""
        out = []

        def visit(node, depth):
            for child in node.children:
                out.append((depth, child.kind, child.name))
                visit(child, depth + 1)

        visit(self.tree.root, 0)
        return out[:limit]
