"""P1 拟合函数库（对标 Origin 的 Fitting Function Library）。

所有模型统一用 **Python 表达式** 描述，参数即表达式中的自由变量，`x` 为自变量。
内置模型与用户自定义表达式走完全相同的求值/拟合路径，扩展模型只需写一个
Python 字符串，不需要编译 C / 写 LabTalk / 引入其它语言。
"""

import ast
from dataclasses import dataclass, field

import numpy as np

# 表达式中视为「非参数」的名字（自变量、模块、数学函数与常量）
RESERVED_NAMES = {
    "x", "i", "row", "n", "N", "np", "numpy", "math", "pi", "e",
    "col", "abs", "min", "max", "sum", "round", "len", "float", "int",
    "pow", "range", "enumerate", "zip", "bool", "str", "True", "False", "None",
} | set(dir(np)) | set(dir(__import__("math")))


@dataclass
class FitModel:
    key: str
    name: str
    category: str
    expression: str
    params: list = field(default_factory=list)
    estimate: object = None       # callable(x, y) -> dict
    bounds: dict = None           # {param: (lo, hi)}，None 表示不限制
    description: str = ""


def _lin_est(x, y):
    b, a = np.polyfit(x, y, 1) if len(x) > 1 else (1.0, 0.0)
    return {"a": float(a), "b": float(b)}


def _poly_est(degree):
    def est(x, y):
        d = min(degree, max(len(x) - 1, 1))
        coef = np.polyfit(x, y, d)
        p = [0.0] * (degree + 1)
        for i, v in enumerate(coef[::-1]):
            p[i] = float(v)
        return {f"p{i}": v for i, v in enumerate(p)}
    return est


def _peak_est(x, y, kind="gauss"):
    ymin, ymax = float(np.min(y)), float(np.max(y))
    xc = float(x[int(np.argmax(y))])
    span = float(np.ptp(x)) or 1.0
    base = {"y0": ymin, "A": (ymax - ymin) or 1.0,
            "xc": xc, "w": max(span / 6.0, 1e-6)}
    return base


def _exp_est(x, y):
    ymin, ymax = float(np.min(y)), float(np.max(y))
    span = float(np.ptp(x)) or 1.0
    return {"y0": ymin, "A": (ymax - ymin) or 1.0, "t": max(span / 3.0, 1e-6)}


def _sigmoid_est(x, y):
    ymin, ymax = float(np.min(y)), float(np.max(y))
    xmid = float(x[len(x) // 2])
    span = float(np.ptp(x)) or 1.0
    return {"A1": ymax, "A2": ymin, "x0": xmid, "dx": max(span / 10.0, 1e-6)}


def _sine_est(x, y):
    span = float(np.ptp(x)) or 1.0
    return {"y0": float(np.mean(y)), "A": float(np.ptp(y) / 2 or 1.0),
            "T": max(span, 1e-6), "phi": 0.0}


MODELS: list = [
    FitModel("linear", "线性 y = a + b·x", "线性/多项式", "a + b * x",
             ["a", "b"], _lin_est, description="最小二乘直线，a 截距、b 斜率"),
    FitModel("poly2", "二次多项式", "线性/多项式",
             "p0 + p1 * x + p2 * x**2", ["p0", "p1", "p2"], _poly_est(2)),
    FitModel("poly3", "三次多项式", "线性/多项式",
             "p0 + p1 * x + p2 * x**2 + p3 * x**3",
             ["p0", "p1", "p2", "p3"], _poly_est(3)),
    FitModel("poly4", "四次多项式", "线性/多项式",
             "p0 + p1 * x + p2 * x**2 + p3 * x**3 + p4 * x**4",
             ["p0", "p1", "p2", "p3", "p4"], _poly_est(4)),
    FitModel("poly5", "五次多项式", "线性/多项式",
             " + ".join(f"p{i} * x**{i}" if i else "p0" for i in range(6)),
             [f"p{i}" for i in range(6)], _poly_est(5)),
    FitModel("exp_decay", "单指数衰减（含基线）", "指数/增长",
             "y0 + A * np.exp(-x / t)", ["y0", "A", "t"], _exp_est,
             bounds={"t": (1e-9, None)}, description="弛豫 / 荧光寿命常用"),
    FitModel("exp_growth", "单指数增长（含基线）", "指数/增长",
             "y0 + A * np.exp(x / t)", ["y0", "A", "t"], _exp_est,
             bounds={"t": (1e-9, None)}),
    FitModel("biexp", "双指数衰减", "指数/增长",
             "y0 + A1 * np.exp(-x / t1) + A2 * np.exp(-x / t2)",
             ["y0", "A1", "t1", "A2", "t2"],
             lambda x, y: {**_exp_est(x, y), "A1": _exp_est(x, y)["A"] / 2,
                           "A2": _exp_est(x, y)["A"] / 2,
                           "t1": _exp_est(x, y)["t"] / 2,
                           "t2": _exp_est(x, y)["t"] * 2},
             bounds={"t1": (1e-9, None), "t2": (1e-9, None)}),
    FitModel("logarithm", "对数 y = a + b·ln(x)", "指数/增长",
             "a + b * np.log(x)", ["a", "b"],
             lambda x, y: {"a": float(np.mean(y)), "b": 1.0},
             description="要求 x > 0"),
    FitModel("power", "幂函数 y = a·x^b", "指数/增长",
             "a * np.power(x, b)", ["a", "b"],
             lambda x, y: {"a": 1.0, "b": 1.0}, description="要求 x > 0"),
    FitModel("mm", "Michaelis-Menten", "生化/药代",
             "Vmax * x / (K + x)", ["Vmax", "K"],
             lambda x, y: {"Vmax": float(np.max(y) * 1.2 or 1.0),
                           "K": float(np.median(x) or 1.0)},
             bounds={"K": (1e-9, None)}),
    FitModel("gauss", "Gaussian 高斯峰", "峰/波谱",
             "y0 + A * np.exp(-0.5 * ((x - xc) / w) ** 2)",
             ["y0", "A", "xc", "w"], lambda x, y: _peak_est(x, y),
             bounds={"w": (1e-9, None)}),
    FitModel("lorentz", "Lorentzian 洛伦兹峰", "峰/波谱",
             "y0 + A / (1 + ((x - xc) / w) ** 2)",
             ["y0", "A", "xc", "w"], lambda x, y: _peak_est(x, y),
             bounds={"w": (1e-9, None)}),
    FitModel("sigmoid", "Boltzmann / S 型", "生化/药代",
             "A2 + (A1 - A2) / (1 + np.exp((x - x0) / dx))",
             ["A1", "A2", "x0", "dx"], _sigmoid_est,
             bounds={"dx": (1e-9, None)}),
    FitModel("sine", "正弦 y0 + A·sin(2πx/T + φ)", "周期信号",
             "y0 + A * np.sin(2 * np.pi * x / T + phi)",
             ["y0", "A", "T", "phi"], _sine_est,
             bounds={"T": (1e-9, None)}),
]


def get_model(key: str) -> FitModel:
    for m in MODELS:
        if m.key == key:
            return m
    return MODELS[0]


def infer_params(expression: str) -> list:
    """从任意 Python 表达式推断自由参数名（排除 x / 数学函数 / 模块）。"""
    tree = ast.parse(expression, mode="eval")
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
            continue
        if node.id in RESERVED_NAMES or node.id.startswith("_"):
            continue
        if node.id not in names:
            names.append(node.id)
    return names


def custom_model(expression: str, name: str = "自定义 Python 表达式") -> FitModel:
    params = infer_params(expression)
    if not params:
        raise ValueError("表达式中没有识别到自由参数（除 x 外至少需要一个参数名）。")
    return FitModel(key="custom", name=name, category="自定义", expression=expression,
                    params=params, description="用户以 Python 表达式定义的模型")


def model_menu() -> list:
    """供界面使用的 (显示名, key) 列表。"""
    return [(f"[{m.category}] {m.name}", m.key) for m in MODELS] + \
           [("[自定义] Python 表达式…", "custom")]
