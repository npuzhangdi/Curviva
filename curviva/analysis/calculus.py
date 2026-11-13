"""P2 数值微积分与插值（纯 numpy，对标 Origin 的 Mathematics / Interpolate）。"""

import numpy as np


def _sorted_xy(x, y) -> tuple:
    xv = np.asarray(x, dtype=float).ravel()
    yv = np.asarray(y, dtype=float).ravel()
    n = min(xv.size, yv.size)
    xv, yv = xv[:n], yv[:n]
    mask = np.isfinite(xv) & np.isfinite(yv)
    xv, yv = xv[mask], yv[mask]
    order = np.argsort(xv, kind="stable")
    xv, yv = xv[order], yv[order]
    # 合并重复 X（取均值），保证样条/差分可解
    ux, inv = np.unique(xv, return_inverse=True)
    if ux.size != xv.size:
        uy = np.zeros(ux.size)
        counts = np.zeros(ux.size)
        np.add.at(uy, inv, yv)
        np.add.at(counts, inv, 1.0)
        xv, yv = ux, uy / np.maximum(counts, 1.0)
    return xv, yv


def differentiate(x, y) -> tuple:
    """一阶数值微分（非等间距 X 用 np.gradient）。返回 (x, dy/dx)。"""
    xv, yv = _sorted_xy(x, y)
    if xv.size < 2:
        return xv, np.zeros_like(xv)
    return xv, np.gradient(yv, xv, edge_order=1)


def integrate(x, y) -> tuple:
    """累积梯形积分 ∫y dx。返回 (x, 累积积分)。"""
    xv, yv = _sorted_xy(x, y)
    if xv.size < 2:
        return xv, np.zeros_like(xv)
    inc = np.diff(xv) * (yv[:-1] + yv[1:]) / 2.0
    return xv, np.concatenate([[0.0], np.cumsum(inc)])


def natural_cubic(x, y, x_new) -> np.ndarray:
    """自然三次样条插值（边界二阶导为 0）。"""
    xv, yv = _sorted_xy(x, y)
    xn = np.asarray(x_new, dtype=float)
    if xv.size < 3:
        return np.interp(xn, xv, yv)
    h = np.diff(xv)
    n = xv.size
    A = np.zeros((n, n))
    rhs = np.zeros(n)
    A[0, 0] = A[-1, -1] = 1.0
    for i in range(1, n - 1):
        A[i, i - 1] = h[i - 1]
        A[i, i] = 2.0 * (h[i - 1] + h[i])
        A[i, i + 1] = h[i]
        rhs[i] = 3.0 * ((yv[i + 1] - yv[i]) / h[i] -
                         (yv[i] - yv[i - 1]) / h[i - 1])
    try:
        M = np.linalg.solve(A, rhs)
    except np.linalg.LinAlgError:
        return np.interp(xn, xv, yv)

    t = np.clip(xn, xv[0], xv[-1])
    idx = np.clip(np.searchsorted(xv, t, side="right") - 1, 0, n - 2)
    hi = h[idx]
    a = (xv[idx + 1] - t) / hi
    b = (t - xv[idx]) / hi
    return (a * yv[idx] + b * yv[idx + 1] +
            ((a ** 3 - a) * M[idx] + (b ** 3 - b) * M[idx + 1]) * hi ** 2 / 6.0)


def resample(x, y, n_points: int = 200, method: str = "linear") -> tuple:
    """等间距重采样：返回 (新X, 新Y)。"""
    xv, yv = _sorted_xy(x, y)
    if xv.size < 2:
        return xv, yv
    count = max(int(n_points), 2)
    xn = np.linspace(float(xv[0]), float(xv[-1]), count)
    yn = (np.interp(xn, xv, yv) if method == "linear"
          else natural_cubic(xv, yv, xn))
    return xn, yn
