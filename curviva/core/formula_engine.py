"""安全 Python 表达式求值引擎（仅支持 Python，不引入任何脚本语言）。

用于两处：
1. P0 工作簿「公式列」：`np.sin(x) * 2 + c2` 这类表达式生成新列；
2. P1 自定义拟合模型：`a * np.exp(-b * x) + c`。

安全策略：
- 先用 ast 做节点白名单校验，禁止 import / lambda / 推导式 / 赋值 / 属性篡改；
- 禁止任何以 `_` 开头的名字或属性（封堵 `__builtins__`、`__import__` 等逃逸）；
- 属性访问的根只允许 numpy / np / math 等白名单模块；
- eval 时清空 builtins，仅注入少量纯函数。

列引用约定（兼容 Origin / Excel 习惯与任意中文列名）：
- `A`, `B`, `C` ... 按列顺序引用；`c1`, `c2` ... 等价；
- 合法 Python 标识符的列名可直接书写；
- 任意列名可用 `col("列名")` 引用。
"""

import ast
import math
import re

import numpy as np

# 允许的 AST 节点
_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load,
    ast.Constant, ast.Attribute, ast.Subscript, ast.Tuple, ast.List,
    ast.IfExp, ast.Compare, ast.BoolOp, ast.Slice,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.UAdd, ast.USub, ast.Not, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
    ast.Gt, ast.GtE, ast.And, ast.Or, ast.In, ast.NotIn, ast.keyword,
)

# 允许作为属性访问根的模块名
_ALLOWED_ROOTS = {"np", "numpy", "math"}

# 禁止直接调用的内建函数（即使 builtins 已被清空，也在语法层明确拦截）
_FORBIDDEN_CALLS = {
    "eval", "exec", "compile", "open", "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "input", "breakpoint",
}

_SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "sum": sum, "round": round,
    "len": len, "float": float, "int": int, "pow": pow,
    "range": range, "enumerate": enumerate, "zip": zip,
    "bool": bool, "str": str,
}


def validate_expression(expr: str) -> None:
    """校验表达式安全性；不安全时抛 ValueError。"""
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError("表达式不能为空。")
    if "__" in expr:
        raise ValueError("表达式中不允许使用双下划线（安全限制）。")
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Python 表达式语法错误：{e.msg}（第 {e.lineno} 行）") from e

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(
                f"表达式中使用了不允许的语法：{type(node).__name__}。"
                "仅支持算术运算、函数调用与数学模块访问。")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError("禁止访问以下划线开头的名称。")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ValueError("禁止访问以下划线开头的属性。")
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id not in _ALLOWED_ROOTS:
                raise ValueError(
                    f"只允许通过 np / numpy / math 访问模块属性，不能访问 {root.id}。")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id.startswith("_") or node.func.id in _FORBIDDEN_CALLS:
                raise ValueError(f"禁止调用函数「{node.func.id}」。")


def safe_eval(expr: str, env: dict):
    """在受限环境中求值 Python 表达式。"""
    validate_expression(expr)
    scope = dict(env)
    scope["__builtins__"] = _SAFE_BUILTINS.copy()
    scope.setdefault("np", np)
    scope.setdefault("numpy", np)
    scope.setdefault("math", math)
    scope.setdefault("pi", np.pi)
    scope.setdefault("e", np.e)
    try:
        return eval(compile(ast.parse(expr.strip(), mode="eval"), "<curviva>", "eval"),
                    scope, {})
    except Exception as e:
        raise ValueError(f"表达式求值失败：{e}") from e


def _column_letter(i: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA（Origin/Excel 风格列标）。"""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def dataset_environment(dataset, extra: dict = None) -> dict:
    """为一个数据集构造表达式求值环境。"""
    n = dataset.row_count()
    env = {
        "i": np.arange(n, dtype=float),
        "row": np.arange(n, dtype=float),
        "n": n,
        "N": n,
    }
    numeric_first = None
    for idx, name in enumerate(dataset.column_order):
        values = dataset.columns[name]
        try:
            arr = np.asarray(values, dtype=float)
        except (TypeError, ValueError):
            arr = None
        if arr is None:
            # 文本列仍可通过 col("名称") 取到原始值
            raw = list(values)
            env[f"c{idx + 1}"] = raw
            env[_column_letter(idx)] = raw
        else:
            env[f"c{idx + 1}"] = arr
            env[_column_letter(idx)] = arr
            if numeric_first is None:
                numeric_first = arr
            if re.fullmatch(r"[A-Za-z_]\w*", name) and name not in env:
                env[name] = arr
    if numeric_first is not None:
        env.setdefault("x", numeric_first)
    env["col"] = lambda name: (
        list(dataset.columns[name]) if name in dataset.columns
        else (_ for _ in ()).throw(KeyError(f"没有名为「{name}」的列"))
    )
    if extra:
        env.update(extra)
    return env


def evaluate_dataset_expression(expr: str, dataset, extra: dict = None) -> np.ndarray:
    """在数据集上求值表达式，返回长度为 row_count 的浮点数组。"""
    n = dataset.row_count()
    if n <= 0:
        raise ValueError("数据集没有数据行，无法计算公式列。")
    value = safe_eval(expr, dataset_environment(dataset, extra))
    arr = np.asarray(value, dtype=float)
    if arr.ndim == 0:
        arr = np.full(n, float(arr))
    else:
        arr = arr.ravel()
        if arr.size == 1:
            arr = np.full(n, float(arr[0]))
        elif arr.size != n:
            raise ValueError(f"表达式结果长度为 {arr.size}，与数据行数 {n} 不一致。")
    return np.asarray(arr, dtype=float)
