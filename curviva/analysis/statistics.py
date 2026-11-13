"""P2 描述统计（对标 Origin 的 Statistics on Columns / Rows）。"""

import math

import numpy as np


def describe(values) -> dict:
    """计算一列数值的常用描述统计量，返回有序字典。"""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    n = v.size
    if n == 0:
        return {"N": 0}
    mean = float(np.mean(v))
    std = float(np.std(v, ddof=1)) if n > 1 else 0.0
    q1, median, q3 = (float(t) for t in np.percentile(v, [25, 50, 75]))
    m2 = float(np.mean((v - mean) ** 2))
    m3 = float(np.mean((v - mean) ** 3))
    m4 = float(np.mean((v - mean) ** 4))
    skew = m3 / (m2 ** 1.5) if m2 > 0 else 0.0
    kurt = m4 / (m2 ** 2) - 3.0 if m2 > 0 else 0.0
    sem = std / math.sqrt(n) if n else 0.0
    return {
        "N": n,
        "缺失数": int(np.asarray(values, dtype=float).size - n),
        "均值": mean,
        "标准差 (SD)": std,
        "标准误 (SE)": sem,
        "方差": float(np.var(v, ddof=1)) if n > 1 else 0.0,
        "最小值": float(np.min(v)),
        "最大值": float(np.max(v)),
        "极差": float(np.ptp(v)),
        "中位数": median,
        "Q1 (25%)": q1,
        "Q3 (75%)": q3,
        "IQR": q3 - q1,
        "求和": float(np.sum(v)),
        "均方根 RMS": float(np.sqrt(np.mean(v ** 2))),
        "变异系数 CV(%)": (std / mean * 100.0) if mean else float("nan"),
        "偏度": skew,
        "峰度 (超额)": kurt,
        "95% 置信半宽": 1.96 * sem,
    }


def columns_table(core, dataset_name: str, columns: list) -> tuple:
    """多列统计表：返回 (表头, 二维数据)。"""
    keys = ["N", "均值", "标准差 (SD)", "标准误 (SE)", "最小值", "最大值",
            "中位数", "Q1 (25%)", "Q3 (75%)", "求和", "方差", "极差",
            "偏度", "峰度 (超额)"]
    headers = ["统计量"] + list(columns)
    rows = []
    for key in keys:
        row = [key]
        for col in columns:
            values = np.asarray(core.get_dataset(dataset_name).columns[col], dtype=float)
            row.append(describe(values).get(key, float("nan")))
        rows.append(row)
    return headers, rows
