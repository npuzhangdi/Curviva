"""P3 自动化扩展：**仅支持 Python**（对标 Origin 的 LabTalk / X-Function / Origin C）。

Curviva 明确只提供 Python 一种扩展语言：
- 内置「Python 脚本」编辑器，通过 `api` 对象操作数据、配置、分析、拟合与导出；
- 插件就是 `.py` 文件，声明 `NAME` / `DESCRIPTION` / `run(api)` 即可被自动发现；
- 不提供也不计划支持 LabTalk、Origin C、R、MATLAB、JavaScript 等其它语言。

安全说明：脚本在主进程内执行，ast 层做导入白名单与危险名字过滤，
但 Python 沙箱不等于操作系统级隔离——请只运行自己编写或可信来源的脚本。
"""

import ast
import contextlib
import importlib.util
import io
import json
import math
import os
import sys

import numpy as np

from curviva.config.plot_config import CurveConfig

ALLOWED_IMPORTS = {
    "numpy", "math", "json", "csv", "io", "statistics", "cmath",
    "itertools", "functools", "collections", "re", "datetime", "dataclasses",
}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "open", "__import__",
                   "globals", "locals", "vars", "getattr", "setattr", "delattr"}

_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "int": int,
    "len": len, "list": list, "map": map, "max": max, "min": min,
    "print": print, "range": range, "round": round, "set": set,
    "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "zip": zip,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "True": True, "False": False, "None": None,
}


class AppScriptAPI:
    """脚本/插件唯一允许操作的门面（不暴露底层实现模块）。"""

    def __init__(self, app):
        self.app = app
        self.lines: list = []
        self.np = np
        self.numpy = np
        self.math = math
        self.json = json

    # --- 输出 ---
    def log(self, *args) -> None:
        self.lines.append(" ".join(str(a) for a in args))

    # --- 配置对象（高级用法）---
    @property
    def config(self):
        return self.app.config

    # --- 数据集 ---
    def datasets(self) -> list:
        return self.app.core.dataset_names()

    def columns(self, dataset: str) -> list:
        return self.app.core.columns(dataset)

    def numeric_columns(self, dataset: str) -> list:
        return self.app.core.numeric_columns(dataset)

    def values(self, dataset: str, column: str):
        return self.app.core.column_values(dataset, column)

    def add_dataset(self, name: str, columns: dict):
        return self.app.core.add_result_dataset(name, columns)

    def add_formula_column(self, dataset: str, column: str, expression: str):
        return self.app.core.add_formula_column(dataset, column, expression)

    def open_data_file(self, path: str, **options) -> list:
        """打开 CSV/TXT/DAT/Excel 数据文件，返回新建数据集名列表。"""
        names = [ds.name for ds in self.app.core.open_data_file(path, options)]
        self.app.refresh("script_open_data")
        return names

    # --- 图形 / 图片文档（工作区）---
    def documents(self) -> list:
        return [(d.id, d.kind, d.name) for d in self.app.graphs.documents()]

    def new_graph(self, name: str = "", width: float = 8.0,
                  height: float = 6.0, dpi: int = 300):
        doc = self.app.graphs.new_graph(name, width=width, height=height, dpi=dpi)
        self.app.hook("open_document", doc.id)
        return doc.id

    def new_image(self, path: str = "", name: str = ""):
        doc = self.app.graphs.new_image(name, path=path)
        self.app.hook("open_document", doc.id)
        return doc.id

    def graph_size(self, doc: str, width: float, height: float,
                   unit: str = "inch", dpi: int = 300):
        return self.app.graphs.set_size(doc, width, height, unit, dpi)

    def annotate(self, doc: str, x: float, y: float, text: str):
        self.app.graphs.add_text(doc, x, y, text)
        self.app.hook("refresh_document", doc)
        self.app.refresh("script_annotate")

    def open_document(self, doc: str):
        return self.app.hook("open_document", doc)

    def examples(self) -> list:
        return [(i["name"], i["description"])
                for i in self.app.examples.list_examples()]

    def open_example(self, name: str):
        for item in self.app.examples.list_examples():
            if item["name"] == name or item["path"] == name:
                return self.app.examples.open(item["path"])[0]
        raise ValueError(f"未找到示例「{name}」。")

    # --- 曲线与图形 ---
    def curves(self) -> list:
        return [c.label for c in self.app.config.curves]

    def add_curve(self, dataset: str = "", x: str = "", y: str = "",
                  label: str = "", **kwargs):
        c = CurveConfig(label=label or y, dataset_name=dataset,
                        x_column=x, y_column=y)
        for k, v in kwargs.items():
            if hasattr(c, k):
                setattr(c, k, v)
        self.app.config.curves.append(c)
        self.app.refresh("script")
        return c

    def set_title(self, text: str) -> None:
        self.app.config.global_cfg.title = text
        self.app.refresh("script")

    def set_labels(self, x: str = "", y: str = "", subplot: int = 0) -> None:
        subs = self.app.config.subplots
        if 0 <= subplot < len(subs):
            subs[subplot].x_axis.label = x
            subs[subplot].y_axis.label = y
            self.app.refresh("script")

    # --- 项目资源管理器（仅 Python）---
    def workspace_outline(self) -> list:
        return self.app.workspace.outline()

    def new_folder(self, name: str = "新建文件夹", parent: str = None) -> str:
        self.app.checkpoint("脚本：新建文件夹")
        node = self.app.workspace.new_folder(parent, name)
        self.app.refresh("script_folder")
        return node.name

    def new_sheet(self, name: str = "新建表格", rows: int = 30,
                  columns: int = 2, parent: str = None) -> str:
        self.app.checkpoint("脚本：新建表格")
        node = self.app.workspace.new_sheet(parent, name, rows, columns)
        self.app.refresh("script_sheet")
        return node.ref

    def rename_node(self, node: str, name: str) -> str:
        self.app.checkpoint("脚本：重命名节点")
        final = self.app.workspace.rename(node, name)
        self.app.refresh("script_rename")
        return final

    def active_folder(self) -> str:
        return self.app.workspace.active_folder().name

    # --- 功能域 ---
    def analyze(self, op: str, **params):
        return self.app.analysis.run(op, params)

    def fit(self, **spec):
        return self.app.fitting.fit(spec)

    def fit_report(self) -> str:
        return self.app.fitting.report()

    def styles(self) -> list:
        return self.app.project.styles()

    def apply_style(self, name: str) -> None:
        self.app.project.apply_style(name)

    def templates(self) -> list:
        return [t["name"] for t in self.app.templates.templates()]

    def apply_template(self, name: str) -> None:
        self.app.templates.apply_template(name)

    def save_project(self, path: str) -> str:
        return self.app.project.save(path)

    def open_project(self, path: str):
        return self.app.project.open(path)

    def export(self, path: str, fmt: str = "png") -> bool:
        return bool(self.app.hook("export", path, fmt))

    def refresh(self) -> None:
        self.app.refresh("script")


# ------------------------------------------------------------------
# 脚本校验与执行
# ------------------------------------------------------------------

def validate_script(code: str) -> None:
    if not isinstance(code, str) or not code.strip():
        raise ValueError("脚本内容为空。")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Python 语法错误：{e.msg}（第 {e.lineno} 行）") from e
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = ([a.name.split(".")[0] for a in node.names]
                     if isinstance(node, ast.Import)
                     else [(node.module or "").split(".")[0]])
            for n in names:
                if n not in ALLOWED_IMPORTS:
                    raise ValueError(f"脚本只允许导入 Python 标准数学库与 numpy，禁止导入「{n}」。")
        if isinstance(node, ast.Name) and (node.id.startswith("__") or
                                           node.id in FORBIDDEN_CALLS):
            raise ValueError(f"脚本中禁止使用「{node.id}」。")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("脚本中禁止访问双下划线属性。")


def run_script(code: str, api: AppScriptAPI) -> tuple:
    """执行 Python 脚本，返回 (是否成功, 输出文本)。"""
    try:
        validate_script(code)
    except ValueError as e:
        return False, str(e)
    buffer = io.StringIO()
    scope = {
        "__builtins__": _SAFE_BUILTINS,
        "api": api, "np": np, "numpy": np, "math": math, "json": json,
    }
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            exec(compile(code, "<curviva-script>", "exec"), scope, scope)  # noqa: S102
        ok = True
    except Exception as e:                       # noqa: BLE001
        buffer.write(f"\n[脚本异常] {type(e).__name__}: {e}")
        ok = False
    parts = [buffer.getvalue().strip(), "\n".join(api.lines).strip()]
    return ok, "\n".join(p for p in parts if p).strip()


# ------------------------------------------------------------------
# 插件发现（只认 .py）
# ------------------------------------------------------------------

def plugin_dirs() -> list:
    builtin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
    user = os.path.join(os.path.expanduser("~"), ".curviva", "plugins")
    os.makedirs(user, exist_ok=True)
    return [builtin, user]


def _load_module(path: str):
    mod_name = "_curviva_plugin_" + str(abs(hash(path)))
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ValueError("无法加载插件模块。")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def discover_plugins() -> list:
    """扫描插件目录，返回 [{name,description,path,source,error}]。"""
    found, seen = [], set()
    for folder in plugin_dirs():
        if not os.path.isdir(folder):
            continue
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".py") or fn.startswith("_"):
                continue
            path = os.path.join(folder, fn)
            key = os.path.basename(path)
            if key in seen:
                continue
            seen.add(key)
            item = {"name": os.path.splitext(fn)[0], "description": "",
                    "path": path, "source": "内置" if folder == plugin_dirs()[0] else "用户",
                    "error": ""}
            try:
                module = _load_module(path)
                item["name"] = getattr(module, "NAME", item["name"])
                item["description"] = getattr(module, "DESCRIPTION", "")
                if not callable(getattr(module, "run", None)):
                    item["error"] = "缺少 run(api) 函数"
            except Exception as e:                # noqa: BLE001
                item["error"] = str(e)
            found.append(item)
    return found


def run_plugin(path: str, api: AppScriptAPI) -> tuple:
    try:
        module = _load_module(path)
        fn = getattr(module, "run", None)
        if not callable(fn):
            return False, "插件缺少 run(api) 函数。"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            fn(api)
        parts = [buffer.getvalue().strip(), "\n".join(api.lines).strip()]
        return True, "\n".join(p for p in parts if p).strip() or "插件执行完成。"
    except Exception as e:                       # noqa: BLE001
        return False, f"插件执行失败：{type(e).__name__}: {e}"
