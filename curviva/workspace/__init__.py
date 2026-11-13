"""workspace —— 项目资源管理器域（对标 Origin 的 Project Explorer）。

    model.py       root / folder / sheet 树模型（纯数据、可序列化）
    controller.py  域「控制调用文件」：WorkspaceController 统一对外 API

树节点引用 DataManager 中的数据集名，随 .cvproj 一起保存、撤销与重做。
"""

from curviva.workspace.controller import WorkspaceController

__all__ = ["WorkspaceController"]
