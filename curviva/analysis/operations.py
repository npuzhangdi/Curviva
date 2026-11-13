"""P2 分析操作注册表（数据驱动，界面按 schema 自动生成参数表单）。

新增一个分析功能只需：写一个数值处理函数 + 在 OPERATIONS 里注册一条
OperationSpec（含参数 schema 与 handler），UI 会自动出现对应控件与结果表。
"""

from dataclasses import dataclass, field

import numpy as np

from curviva.analysis import calculus, peaks, signal_processing, statistics


@dataclass
class AnalysisResult:
    name: str = "分析结果"
    summary: str = ""
    columns: dict = field(default_factory=dict)   # 列名 -> 数组（用于生成数据集）
    headers: list = field(default_factory=list)   # 结果表表头
    rows: list = field(default_factory=list)      # 结果表数据
    dataset: bool = True                         # 是否生成可绘图的结果数据集
    created_dataset: str = ""                    # 实际生成的数据集名（供 UI 提示）

    def preview_rows(self, limit: int = 200) -> list:
        return self.rows[:limit]


@dataclass
class OperationSpec:
    key: str
    name: str
    category: str
    description: str
    params: list = field(default_factory=list)
    handler: object = None


# ------------------------------------------------------------------
# 参数 schema 辅助
# ------------------------------------------------------------------

def P(key, label, kind, default=None, **kw) -> dict:   # noqa: N802
    return {"key": key, "label": label, "type": kind, "default": default, **kw}


# ------------------------------------------------------------------
# 公共数据读取
# ------------------------------------------------------------------

def _xy(core, p: dict) -> tuple:
    ds_name, y_col = p.get("dataset"), p.get("y_col")
    ds = core.get_dataset(ds_name)
    if ds is None or not y_col:
        raise ValueError("请先选择数据集与 Y 数据列。")
    y = np.asarray(ds.columns[y_col], dtype=float).ravel()
    x_col = p.get("x_col")
    if x_col and x_col in ds.columns:
        try:
            x = np.asarray(ds.columns[x_col], dtype=float).ravel()
        except (TypeError, ValueError):
            x = np.arange(y.size, dtype=float)
    else:
        x = np.arange(y.size, dtype=float)
    n = min(x.size, y.size)
    x, y = x[:n], y[:n]
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 2:
        raise ValueError("所选数据列的有效数值点不足 2 个。")
    return x[mask], y[mask], x_col, y_col


def _table_result(name, summary, columns, ds_name, y_col, extra: str = "") -> AnalysisResult:
    headers = list(columns)
    rows = [[columns[h][i] if i < len(columns[h]) else "" for h in headers]
            for i in range(max((len(v) for v in columns.values()), default=0))]
    dataset_name = f"{name}-{y_col}"
    return AnalysisResult(name=dataset_name, summary=f"{summary}{extra}",
                          columns=columns, headers=headers, rows=rows, dataset=True)


# ------------------------------------------------------------------
# 各操作 handler（统一签名：handler(core, params) -> AnalysisResult）
# ------------------------------------------------------------------

def _describe(core, p):
    ds = core.get_dataset(p.get("dataset"))
    if ds is None:
        raise ValueError("请先选择数据集。")
    numeric = ds.numeric_columns()
    if p.get("all_columns"):
        cols = numeric
    else:
        cols = [p.get("y_col") or (numeric[0] if numeric else "")]
    cols = [c for c in cols if c in ds.columns]
    if not cols:
        raise ValueError("数据集里没有可统计的数值列。")
    headers, rows = statistics.columns_table(core, ds.name, cols)
    return AnalysisResult(name=f"描述统计-{ds.name}",
                          summary=f"对 {len(cols)} 个数值列完成描述统计：{', '.join(cols)}",
                          columns={}, headers=headers, rows=rows, dataset=False)


def _smooth(core, p, kind):
    x, y, _, y_col = _xy(core, p)
    if kind == "moving":
        out = signal_processing.moving_average(y, p.get("window", 5))
        label, summary = "移动平均", f"移动平均（窗口 {p.get('window', 5)}）"
    elif kind == "savgol":
        out = signal_processing.savitzky_golay(
            y, p.get("window", 9), p.get("polyorder", 2))
        label, summary = "SG平滑", (f"Savitzky–Golay 平滑（窗口 {p.get('window', 9)}，"
                              f"阶数 {p.get('polyorder', 2)}）")
    elif kind == "median":
        out = signal_processing.median_filter(y, p.get("window", 5))
        label, summary = "中值滤波", f"中值滤波（窗口 {p.get('window', 5)}）"
    else:
        out = signal_processing.gaussian_filter(y, p.get("sigma", 2.0))
        label, summary = "高斯平滑", f"高斯平滑（σ={p.get('sigma', 2.0)}）"
    return _table_result(label, f"{summary}；共 {y.size} 点。",
                         {"X": x, "原始Y": y, label: out},
                         p.get("dataset", ""), y_col)


def _normalize(core, p):
    x, y, _, y_col = _xy(core, p)
    out = signal_processing.normalize(y, p.get("mode", "minmax"))
    return _table_result("归一化", f"归一化（{p.get('mode', 'minmax')}）；共 {y.size} 点。",
                         {"X": x, "原始Y": y, "归一化": out},
                         p.get("dataset", ""), y_col)


def _baseline(core, p):
    x, y, _, y_col = _xy(core, p)
    b = signal_processing.baseline(x, y, p.get("mode", "linear"),
                                   p.get("degree", 1))
    return _table_result("基线校正", f"基线扣除（{p.get('mode', 'linear')}）；共 {y.size} 点。",
                         {"X": x, "原始Y": y, "基线": b, "扣除后": y - b},
                         p.get("dataset", ""), y_col)


def _fft(core, p):
    x, y, _, y_col = _xy(core, p)
    dx = float(np.median(np.diff(x))) if x.size > 1 else 1.0
    if abs(dx) < 1e-15:
        dx = 1.0
    freq, amp = signal_processing.fft_spectrum(y, abs(dx))
    return _table_result("FFT频谱", f"FFT 单侧幅度谱（Δx≈{dx:.6g}，{freq.size} 个频点）。",
                         {"频率": freq, "幅度": amp},
                         p.get("dataset", ""), y_col)


def _derivative(core, p):
    x, y, _, y_col = _xy(core, p)
    xs, d = calculus.differentiate(x, y)
    return _table_result("数值微分", f"一阶数值微分 dy/dx；共 {xs.size} 点。",
                         {"X": xs, "dy/dx": d}, p.get("dataset", ""), y_col)


def _integral(core, p):
    x, y, _, y_col = _xy(core, p)
    xs, s = calculus.integrate(x, y)
    return _table_result("数值积分",
                         f"累积梯形积分；末端积分值 = {s[-1]:.6g}，共 {xs.size} 点。",
                         {"X": xs, "累积积分": s}, p.get("dataset", ""), y_col)


def _resample(core, p):
    x, y, _, y_col = _xy(core, p)
    xn, yn = calculus.resample(x, y, p.get("n_points", 200),
                               p.get("method", "linear"))
    return _table_result("插值重采样",
                         f"{p.get('method', 'linear')} 插值：{x.size} → {xn.size} 点。",
                         {"X": xn, "插值Y": yn}, p.get("dataset", ""), y_col)


def _find_peaks(core, p):
    x, y, _, y_col = _xy(core, p)
    found = peaks.find_peaks(
        x, y,
        height=p.get("height") if p.get("height") not in (None, "") else None,
        prominence=p.get("prominence") if p.get("prominence") not in (None, "") else None,
        distance=p.get("distance", 1),
        min_width=p.get("min_width", 0.0))
    cols = peaks.peaks_to_columns(found)
    if not found:
        cols = {k: [] for k in cols}
    table_cols = {k: (v if v else []) for k, v in cols.items()}
    result = _table_result("寻峰",
                           f"检出 {len(found)} 个峰（阈值/突出度/最小间距过滤后）。",
                           table_cols, p.get("dataset", ""), y_col)
    result.name = f"寻峰结果-{y_col}"
    return result


# ------------------------------------------------------------------
# 注册表
# ------------------------------------------------------------------

WINDOW = lambda: P("window", "窗口点数", "int", 5, min=3, max=999, step=2)  # noqa: E731

OPERATIONS: list = [
    OperationSpec("describe", "描述统计", "统计",
                  "N / 均值 / SD / SE / 分位数 / 偏度峰度等，支持一次统计多列",
                  [P("all_columns", "统计全部数值列", "bool", True)], _describe),
    OperationSpec("moving", "移动平均", "平滑与变换",
                  "滑动窗口均值平滑（边缘采用边界延拓）", [WINDOW()],
                  lambda c, p: _smooth(c, p, "moving")),
    OperationSpec("savgol", "Savitzky–Golay 平滑", "平滑与变换",
                  "保峰形多项式平滑，适合谱图",
                  [WINDOW(), P("polyorder", "多项式阶数", "int", 2, min=1, max=9)],
                  lambda c, p: _smooth(c, p, "savgol")),
    OperationSpec("median", "中值滤波", "平滑与变换",
                  "去除脉冲尖峰噪声", [WINDOW()],
                  lambda c, p: _smooth(c, p, "median")),
    OperationSpec("gaussian", "高斯平滑", "平滑与变换",
                  "高斯核卷积平滑",
                  [P("sigma", "σ（点数）", "float", 2.0, min=0.2, max=100.0, decimals=2)],
                  lambda c, p: _smooth(c, p, "gaussian")),
    OperationSpec("normalize", "归一化", "平滑与变换",
                  "最小-最大 / Z-score / 最大值 / 求和 / 均值",
                  [P("mode", "方式", "combo", "minmax",
                     options=[("最小-最大 [0,1]", "minmax"), ("Z-score 标准化", "zscore"),
                              ("除以最大值", "max"), ("除以总和", "sum"), ("除以均值", "mean")])],
                  _normalize),
    OperationSpec("baseline", "基线扣除", "平滑与变换",
                  "常量 / 线性 / 多项式基线估计与扣除",
                  [P("mode", "基线类型", "combo", "linear",
                     options=[("线性两端连线", "linear"), ("常量（最小值）", "constant"),
                              ("多项式拟合", "poly")]),
                   P("degree", "多项式次数（poly 时）", "int", 1, min=1, max=6)],
                  _baseline),
    OperationSpec("fft", "FFT 幅度谱", "平滑与变换",
                  "去均值 + Hann 窗的单侧幅度谱",
                  [], _fft),
    OperationSpec("derivative", "数值微分", "数学运算",
                  "一阶导数 dy/dx（支持非等间距 X）", [], _derivative),
    OperationSpec("integral", "累积积分", "数学运算",
                  "梯形法累积积分 ∫y dx", [], _integral),
    OperationSpec("resample", "插值 / 等间距重采样", "数学运算",
                  "线性插值或自然三次样条，把曲线重采样到指定点数",
                  [P("n_points", "目标点数", "int", 200, min=2, max=20000),
                   P("method", "插值方法", "combo", "linear",
                     options=[("线性插值", "linear"), ("自然三次样条", "cubic")])],
                  _resample),
    OperationSpec("find_peaks", "寻峰 / 峰面积", "峰分析",
                  "局部极大值检出：峰高阈值、突出度、最小间距、半高宽与峰面积",
                  [P("height", "最小峰高（可空）", "float", None, optional=True, decimals=4),
                   P("prominence", "最小突出度（可空）", "float", None,
                     optional=True, decimals=4),
                   P("distance", "最小峰间距（点数）", "int", 1, min=1, max=1000),
                   P("min_width", "最小半高宽（可空）", "float", 0.0,
                     optional=True, decimals=4)],
                  _find_peaks),
]


def get_operation(key: str) -> OperationSpec:
    for op in OPERATIONS:
        if op.key == key:
            return op
    raise ValueError(f"未知分析操作：{key}")


def operation_menu() -> list:
    return [(f"[{op.category}] {op.name}", op.key) for op in OPERATIONS]


def run(core, key: str, params: dict) -> AnalysisResult:
    op = get_operation(key)
    return op.handler(core, params)
