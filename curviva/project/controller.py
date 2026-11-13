"""项目域「控制调用文件」。

ProjectController 统一管理：新建 / 打开 / 保存 .cvproj、撤销重做、
工作区文本（脚本、日志、拟合摘要）与最近文件。
"""

import os

from curviva.project import project_io
from curviva.project.history import History
from curviva.project.style_presets import style_names


class ProjectController:
    def __init__(self, app=None):
        self.app = app
        self.history = History(limit=60)
        self.current_path = ""
        self.recent_files: list = []
        self.workspace = project_io.blank_workspace()

    # ------------------------------------------------------------------
    # 状态快照
    # ------------------------------------------------------------------

    def state(self) -> dict:
        # 项目树作为工作区的一部分一起入快照，撤销重做与 .cvproj 都能还原结构
        ws = dict(self.workspace)
        if getattr(self.app, "workspace", None) is not None:
            ws["tree"] = self.app.workspace.to_dict()
        if getattr(self.app, "graphs", None) is not None:
            ws["documents"] = self.app.graphs.to_dict()
        return project_io.make_state(
            self.app.config_ctrl.to_dict(),
            self.app.core.to_dict(),
            ws,
        )

    def apply_state(self, state: dict) -> None:
        self.app.config_ctrl.from_dict(state.get("config", {}))
        self.app.core.load_dict(state.get("datasets", []))
        self.workspace = {**project_io.blank_workspace(),
                          **(state.get("workspace") or {})}
        if getattr(self.app, "workspace", None) is not None:
            self.app.workspace.load_dict(self.workspace.get("tree"))
            self.app.workspace.sync()
        if getattr(self.app, "graphs", None) is not None:
            self.app.graphs.load_dict(self.workspace.get("documents"))
        self.app.notify("state")

    # ------------------------------------------------------------------
    # 新建 / 打开 / 保存
    # ------------------------------------------------------------------

    def new(self) -> None:
        self.app.config_ctrl.new()
        self.app.core.clear()
        self.workspace = project_io.blank_workspace()
        if getattr(self.app, "workspace", None) is not None:
            self.app.workspace.reset()
        if getattr(self.app, "graphs", None) is not None:
            self.app.graphs.reset()
        self.history.clear()
        self.current_path = ""
        self.app.notify("new")

    def open(self, path: str) -> dict:
        state = project_io.load_state(path)
        self.history.push(self.state(), f"打开项目：{os.path.basename(path)}")
        self.apply_state(state)
        self.current_path = path
        self._remember(path)
        return state

    def save(self, path: str = None) -> str:
        target = path or self.current_path
        if not target:
            raise ValueError("尚未指定项目文件路径，请使用「另存为」。")
        saved = project_io.save_state(target, self.state())
        self.current_path = saved
        self.workspace = self.state()["workspace"]
        self._remember(saved)
        return saved

    def save_as(self, path: str) -> str:
        return self.save(path)

    def _remember(self, path: str) -> None:
        path = os.path.abspath(path)
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        del self.recent_files[8:]

    # ------------------------------------------------------------------
    # 撤销 / 重做
    # ------------------------------------------------------------------

    def checkpoint(self, label: str = "修改") -> bool:
        """在改动「之前」记录一个快照；状态未变化时不重复入栈。"""
        state = self.state()
        last = self.history.last_state()
        if last is not None and last == state:
            return False
        self.history.push(state, label)
        return True

    def undo(self) -> bool:
        state = self.history.undo(self.state())
        if state is None:
            return False
        self.apply_state(state)
        return True

    def redo(self) -> bool:
        state = self.history.redo(self.state())
        if state is None:
            return False
        self.apply_state(state)
        return True

    # ------------------------------------------------------------------
    # 样式主题
    # ------------------------------------------------------------------

    def styles(self) -> list:
        return style_names()

    def apply_style(self, name: str) -> None:
        self.checkpoint(f"应用样式：{name}")
        self.app.config_ctrl.apply_style(name)
        self.app.notify("style")

    # ------------------------------------------------------------------
    # 工作区文本
    # ------------------------------------------------------------------

    def set_workspace(self, key: str, value) -> None:
        self.workspace[key] = value

    def log(self, text: str) -> None:
        lines = self.workspace.setdefault("analysis_log", [])
        lines.append(text)
        del lines[:-200]
