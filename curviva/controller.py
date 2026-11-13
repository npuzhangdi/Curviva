"""Curviva 总控「控制调用文件」（Application Facade）。

架构约定（模块化 + 每个功能域一个控制调用文件）：

    curviva/controller.py          总控 AppController
    ├── config/controller.py      配置域
    ├── core/controller.py        数据与绘图引擎域
    ├── project/controller.py     项目 / 撤销重做 / 样式域
    ├── workspace/controller.py   项目资源管理器域（文件夹 / 表格 / 图形树）
    ├── graphs/controller.py      图形 / 图片文档域（尺寸、标注、图片）
    ├── analysis/controller.py    数据处理与分析域
    ├── fitting/controller.py     公式拟合域
    ├── templates/controller.py   模板 / 批处理 / Python 扩展域
    ├── examples/controller.py    示例资源域（位于项目根 examples/）
    └── ui/controller.py          界面域（窗口、工作表与面板装配）

所有跨模块调用一律通过 AppController 或各域 controller，界面不直接
触碰底层实现文件。扩展能力（公式列、自定义拟合、脚本、插件）**仅支持
Python**，不引入 LabTalk / Origin C / R / MATLAB 等其它语言。
"""

from curviva.config.controller import ConfigController
from curviva.core.controller import CoreController
from curviva.project.controller import ProjectController


class AppController:
    """组合所有功能域，提供统一调度入口。"""

    def __init__(self):
        self._listeners = []
        self.hooks = {}                # UI 注入的可选能力：refresh / export / status

        self.config_ctrl = ConfigController(self)
        self.core = CoreController(self)
        self.project = ProjectController(self)

        # 延迟到构造时导入，避免各域互相 import 形成环
        from curviva.analysis.controller import AnalysisController
        from curviva.fitting.controller import FittingController
        from curviva.templates.controller import TemplateController
        from curviva.workspace.controller import WorkspaceController
        from curviva.graphs.controller import GraphController
        self.workspace = WorkspaceController(self)
        self.graphs = GraphController(self)
        self.analysis = AnalysisController(self)
        self.fitting = FittingController(self)
        self.templates = TemplateController(self)

        # 示例域是项目根的独立文件夹 examples/，同样带一个 controller.py
        import os
        import sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        from examples.controller import ExamplesController
        self.examples = ExamplesController(self)

    # ------------------------------------------------------------------
    # 便捷属性（始终取当前对象，撤销/打开项目后引用不会失效）
    # ------------------------------------------------------------------

    @property
    def config(self):
        return self.config_ctrl.config

    @property
    def data_manager(self):
        return self.core.data

    @property
    def datasets(self) -> list:
        return self.core.datasets()

    # ------------------------------------------------------------------
    # 事件与钩子
    # ------------------------------------------------------------------

    def add_listener(self, callback) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def notify(self, reason: str = "changed") -> None:
        for cb in list(self._listeners):
            try:
                cb(reason)
            except Exception:                  # noqa: BLE001 - 单个监听者异常不影响全局
                pass

    def hook(self, name: str, *args, **kwargs):
        fn = self.hooks.get(name)
        return fn(*args, **kwargs) if callable(fn) else None

    def status(self, text: str) -> None:
        self.hook("status", text)

    # ------------------------------------------------------------------
    # 通用调度
    # ------------------------------------------------------------------

    def render(self, figure, view_state=None) -> None:
        self.core.render(figure, self.config, view_state)

    def checkpoint(self, label: str = "修改") -> bool:
        return self.project.checkpoint(label)

    def undo(self) -> bool:
        return self.project.undo()

    def redo(self) -> bool:
        return self.project.redo()

    def refresh(self, reason: str = "changed") -> None:
        """请求界面整体刷新（面板重新绑定 + 重绘），由 UI 监听器统一处理。"""
        self.notify(reason)

    # 需要在改动前记录撤销点的项目树动作
    WORKSPACE_ACTIONS = {
        "new_folder", "new_sheet", "rename_node", "remove_node", "move_node",
        "set_project_name", "new_graph", "new_image", "remove_document",
        "set_document_size",
    }

    def execute(self, action: str, **kwargs):
        """统一命令分发：脚本 / 插件 / 菜单共用同一套动作名。"""
        table = {
            "new_project": lambda: self.project.new(),
            "open_project": lambda: self.project.open(kwargs["path"]),
            "save_project": lambda: self.project.save(kwargs.get("path")),
            "undo": lambda: self.undo(),
            "redo": lambda: self.redo(),
            "import_csv": lambda: self.core.import_csv(kwargs["path"]),
            "import_excel": lambda: self.core.import_excel(
                kwargs["path"], kwargs.get("sheets")),
            "open_data": lambda: self.core.open_data_file(
                kwargs["path"], kwargs.get("options"), kwargs.get("sheets"),
                kwargs.get("folder")),
            "open_example": lambda: self.examples.open(kwargs["path"]),
            "paste": lambda: self.core.import_clipboard(kwargs["text"]),
            "demo": lambda: self.core.load_demo(),
            "apply_style": lambda: self.project.apply_style(kwargs["name"]),
            "new_folder": lambda: self.workspace.new_folder(
                kwargs.get("parent"), kwargs.get("name", "新建文件夹")),
            "new_sheet": lambda: self.workspace.new_sheet(
                kwargs.get("parent"), kwargs.get("name", "新建表格"),
                kwargs.get("rows", 30), kwargs.get("columns", 2)),
            "rename_node": lambda: self.workspace.rename(
                kwargs["node"], kwargs["name"]),
            "remove_node": lambda: self.workspace.remove(kwargs["node"]),
            "move_node": lambda: self.workspace.move(
                kwargs["node"], kwargs["parent"]),
            "set_project_name": lambda: self.workspace.set_project_name(kwargs["name"]),
            "new_graph": lambda: self.graphs.new_graph(
                kwargs.get("name", ""), kwargs.get("parent")),
            "new_image": lambda: self.graphs.new_image(
                kwargs.get("name", ""), kwargs.get("parent"),
                kwargs.get("path", "")),
            "remove_document": lambda: self.graphs.remove(kwargs["doc"]),
            "open_document": lambda: self.hook("open_document", kwargs["doc"]),
            "set_document_size": lambda: self.graphs.set_size(
                kwargs["doc"], kwargs["width"], kwargs["height"],
                kwargs.get("unit", "inch"), kwargs.get("dpi")),
            "analyze": lambda: self.analysis.run(kwargs["op"], kwargs),
            "fit": lambda: self.fitting.fit(kwargs),
            "fit_curve": lambda: self.fitting.add_fit_curve(kwargs.get("result")),
            "apply_template": lambda: self.templates.apply_template(kwargs["name"]),
            "save_template": lambda: self.templates.save_template(kwargs["name"]),
            "batch": lambda: self.templates.batch_export(**kwargs),
            "run_script": lambda: self.templates.run_script(kwargs["code"]),
            "export": lambda: self.hook("export", kwargs["path"],
                                        kwargs.get("fmt", "png")),
            "refresh": lambda: self.refresh(),
        }
        if action not in table:
            raise ValueError(f"未知动作：{action}（可用：{', '.join(sorted(table))}）")
        if action in self.WORKSPACE_ACTIONS:
            self.checkpoint(f"项目树：{action}")
        result = table[action]()
        if action not in ("undo", "redo", "refresh", "export"):
            self.refresh(action)
        return result
