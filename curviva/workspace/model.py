"""Origin 风格「项目资源管理器」树模型（纯数据、可 JSON 序列化）。

树由三种节点组成：

    root    项目根（唯一）
    folder  文件夹，可任意层级嵌套，可包含文件夹与表格
    sheet   表格 / 工作簿，ref 指向 DataManager 里的数据集名

模型不依赖 Qt，也不直接持有 DataSet；界面通过 workspace/controller.py
统一操作，保证项目文件、撤销重做、脚本都能复用同一份结构。
"""

import uuid
from dataclasses import dataclass, field

ROOT_ID = "root"
DEFAULT_FOLDER_ID = "folder_data"
KIND_ROOT = "root"
KIND_FOLDER = "folder"
KIND_SHEET = "sheet"
KIND_GRAPH = "graph"            # 图形窗口文档
KIND_IMAGE = "image"            # 图片窗口文档

DOCUMENT_KINDS = (KIND_GRAPH, KIND_IMAGE)


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class WorkspaceNode:
    name: str
    kind: str = KIND_FOLDER
    id: str = field(default_factory=_new_id)
    ref: str = ""                 # sheet: 对应数据集名
    note: str = ""
    expanded: bool = True
    children: list = field(default_factory=list)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "kind": self.kind,
            "ref": self.ref, "note": self.note, "expanded": self.expanded,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkspaceNode":
        if not isinstance(data, dict):
            return cls("节点")
        return cls(
            name=str(data.get("name", "节点")),
            kind=str(data.get("kind", KIND_FOLDER)),
            id=str(data.get("id") or _new_id()),
            ref=str(data.get("ref", "")),
            note=str(data.get("note", "")),
            expanded=bool(data.get("expanded", True)),
            children=[cls.from_dict(c) for c in data.get("children", []) or []],
        )

    # ------------------------------------------------------------------
    def walk(self, include_self: bool = True):
        if include_self:
            yield self
        for child in self.children:
            yield from child.walk()

    def find(self, node_id: str):
        for node in self.walk():
            if node.id == node_id:
                return node
        return None

    def parent_of(self, node_id: str):
        """返回 (父节点, 在父节点 children 中的索引)。"""
        for node in self.walk():
            for i, child in enumerate(node.children):
                if child.id == node_id:
                    return node, i
        return None, -1

    def is_folder(self) -> bool:
        return self.kind in (KIND_ROOT, KIND_FOLDER)


class WorkspaceTree:
    """项目树：负责节点增删查改与序列化，不涉及数据集内容。"""

    def __init__(self, project_name: str = "未命名项目"):
        self.project_name = project_name
        self.root = WorkspaceNode(
            name=project_name, kind=KIND_ROOT, id=ROOT_ID,
            children=[WorkspaceNode(name="数据表", kind=KIND_FOLDER,
                                    id=DEFAULT_FOLDER_ID, expanded=True)],
        )

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"project_name": self.project_name, "root": self.root.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "WorkspaceTree":
        obj = cls(str((data or {}).get("project_name") or "未命名项目"))
        root = (data or {}).get("root")
        if isinstance(root, dict):
            obj.root = WorkspaceNode.from_dict(root)
            if obj.root.id != ROOT_ID:
                obj.root.id = ROOT_ID
            obj.root.kind = KIND_ROOT
        obj._ensure_ids()
        return obj

    def load_dict(self, data: dict) -> None:
        other = WorkspaceTree.from_dict(data)
        self.project_name = other.project_name
        self.root = other.root

    def _ensure_ids(self) -> None:
        seen = set()
        for node in self.root.walk():
            if not node.id or node.id in seen:
                node.id = (_new_id() if node.kind != KIND_ROOT else ROOT_ID)
            seen.add(node.id)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def find(self, node_id: str):
        return self.root.find(node_id or ROOT_ID)

    def parent_of(self, node_id: str):
        return self.root.parent_of(node_id)

    def path_of(self, node_id: str) -> str:
        parts, cur = [], node_id
        while cur and cur != ROOT_ID:
            node = self.find(cur)
            if node is None:
                break
            parts.append(node.name)
            parent, _ = self.root.parent_of(cur)
            cur = parent.id if parent else ""
        return " / ".join(reversed(parts)) or self.project_name

    def refs(self) -> set:
        return {n.ref for n in self.root.walk() if n.kind == KIND_SHEET and n.ref}

    def node_for_ref(self, ref: str):
        for node in self.root.walk():
            if node.kind == KIND_SHEET and node.ref == ref:
                return node
        return None

    def folder_for_ref(self, ref: str):
        node = self.node_for_ref(ref)
        if node is None:
            return self.root
        parent, _ = self.root.parent_of(node.id)
        return parent or self.root

    # --- 图形 / 图片文档节点（ref = 文档 id） -------------------------

    def node_for_document(self, doc_id: str):
        for node in self.root.walk():
            if node.kind in DOCUMENT_KINDS and node.ref == doc_id:
                return node
        return None

    def document_folder(self, doc_id: str):
        node = self.node_for_document(doc_id)
        if node is None:
            return self.root
        parent, _ = self.root.parent_of(node.id)
        return parent or self.root

    def add_document(self, parent_id: str, name: str, kind: str,
                     doc_id: str) -> WorkspaceNode:
        parent = self.find(parent_id) if parent_id else self.root
        if parent is None or not parent.is_folder():
            parent = self.root
        node = WorkspaceNode(
            name=self.unique_child_name(parent.id, name or "图形"),
            kind=kind, ref=doc_id)
        parent.children.append(node)
        parent.expanded = True
        return node

    def prune_documents(self, valid_ids: set) -> None:
        """清理指向已删除文档的树节点。"""
        for parent in list(self.root.walk()):
            parent.children[:] = [
                c for c in parent.children
                if not (c.kind in DOCUMENT_KINDS and c.ref not in valid_ids)
            ]

    # ------------------------------------------------------------------
    # 名称与增删改
    # ------------------------------------------------------------------

    def unique_child_name(self, parent_id: str, base: str) -> str:
        parent = self.find(parent_id) or self.root
        used = {c.name for c in parent.children}
        if base not in used:
            return base
        i = 2
        while f"{base} {i}" in used:
            i += 1
        return f"{base} {i}"

    def add_folder(self, parent_id: str = None, name: str = "新建文件夹") -> WorkspaceNode:
        parent = self.find(parent_id) if parent_id else self.root
        if parent is None or not parent.is_folder():
            parent = self.root
        node = WorkspaceNode(
            name=self.unique_child_name(parent.id, name or "新建文件夹"),
            kind=KIND_FOLDER, expanded=True)
        parent.children.append(node)
        parent.expanded = True
        return node

    def add_sheet(self, parent_id: str, name: str, ref: str) -> WorkspaceNode:
        parent = self.find(parent_id) if parent_id else self.root
        if parent is None or not parent.is_folder():
            parent = self.root
        node = WorkspaceNode(
            name=self.unique_child_name(parent.id, name or ref or "新建表格"),
            kind=KIND_SHEET, ref=ref)
        parent.children.append(node)
        parent.expanded = True
        return node

    def rename(self, node_id: str, name: str) -> str:
        node = self.find(node_id)
        if node is None or node.kind == KIND_ROOT:
            return ""
        parent, _ = self.root.parent_of(node_id)
        siblings = {c.name for c in parent.children if c.id != node_id} if parent else set()
        final = name
        i = 2
        while final in siblings:
            final = f"{name} {i}"
            i += 1
        node.name = final
        return final

    def remove(self, node_id: str) -> list:
        """删除节点（含子树）；返回被移除的 sheet 引用名列表。"""
        parent, index = self.root.parent_of(node_id)
        if parent is None:
            return []
        node = parent.children.pop(index)
        return [n.ref for n in node.walk() if n.kind == KIND_SHEET and n.ref]

    def move(self, node_id: str, new_parent_id: str, index: int = None) -> bool:
        """把节点移动到另一个文件夹下；禁止移动到自身子树内。"""
        target = self.find(new_parent_id)
        if target is None or not target.is_folder() or node_id == ROOT_ID:
            return False
        source_parent, old_index = self.root.parent_of(node_id)
        if source_parent is None:
            return False
        node = source_parent.children[old_index]
        if target is node or any(c is target for c in node.walk(include_self=False)):
            return False
        same_parent = target is source_parent
        source_parent.children.pop(old_index)
        pos = len(target.children) if index is None else max(0, min(int(index), len(target.children)))
        if same_parent and pos > old_index:
            pos -= 1
        target.children.insert(pos, node)
        target.expanded = True
        return True

    # ------------------------------------------------------------------
    # 与数据集同步
    # ------------------------------------------------------------------

    def sync(self, dataset_names: list, preferred_folder: str = None) -> list:
        """补齐未登记的数据集、清理已删除数据集的悬空节点。

        返回新挂入树的数据集名列表。任何来源（导入 / 分析 / 拟合 / 脚本）
        产生的数据集都会自动出现在项目树中，无需各自维护树结构。
        """
        names = [str(n) for n in (dataset_names or [])]
        valid = set(names)
        # 清理悬空 sheet 节点（只遍历容器节点，直接过滤其 children）
        for parent in list(self.root.walk()):
            parent.children[:] = [
                c for c in parent.children
                if not (c.kind == KIND_SHEET and c.ref not in valid)
            ]
        existing = self.refs()
        pending = [n for n in names if n not in existing]
        folder = self.find(preferred_folder) if preferred_folder else self.find(DEFAULT_FOLDER_ID)
        if folder is None or not folder.is_folder():
            folder = self.find(DEFAULT_FOLDER_ID) or self.root
        for name in pending:
            self.add_sheet(folder.id, name, name)
        return pending
