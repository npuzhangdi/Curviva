"""P2 寻峰与峰分析（对标 Origin 的 Peak Analyzer 基础能力）。"""

import numpy as np


def _crossing(x, y, i, level, direction: int) -> float:
    """从峰位向左右线性插值寻找与 level 的交点 X。"""
    j = i
    n = len(y)
    step = -1 if direction < 0 else 1
    while 0 <= j + step < n:
        k = j + step
        if (y[j] - level) * (y[k] - level) <= 0 and y[j] != y[k]:
            ratio = (level - y[j]) / (y[k] - y[j])
            return float(x[j] + ratio * (x[k] - x[j]))
        j = k
    return float(x[0] if direction < 0 else x[-1])


def find_peaks(x, y, height: float = None, prominence: float = None,
               distance: int = 1, min_width: float = 0.0) -> list:
    """寻找局部极大峰，返回 [{index,x,height,prominence,fwhm,area,left,right}]。"""
    xv = np.asarray(x, dtype=float).ravel()
    yv = np.asarray(y, dtype=float).ravel()
    n = min(xv.size, yv.size)
    xv, yv = xv[:n], yv[:n]
    mask = np.isfinite(xv) & np.isfinite(yv)
    xv, yv = xv[mask], yv[mask]
    n = yv.size
    if n < 3:
        return []

    candidates = [i for i in range(1, n - 1)
                  if yv[i] >= yv[i - 1] and yv[i] > yv[i + 1]]

    raw = []
    for i in candidates:
        # 向两侧寻找更高点之前的谷底，计算突出度
        lmin, rmin = yv[i], yv[i]
        j = i - 1
        while j >= 0 and yv[j] <= yv[i]:
            lmin = min(lmin, yv[j]); j -= 1
        j = i + 1
        while j < n and yv[j] <= yv[i]:
            rmin = min(rmin, yv[j]); j += 1
        base = max(lmin, rmin)
        prom = yv[i] - base
        raw.append({"index": i, "x": float(xv[i]), "height": float(yv[i]),
                    "prominence": float(prom), "base": float(base)})

    if height is not None:
        raw = [p for p in raw if p["height"] >= float(height)]
    if prominence is not None:
        raw = [p for p in raw if p["prominence"] >= float(prominence)]

    # 最小间距：按峰高降序贪心保留
    dist = max(int(distance), 1)
    kept = []
    for p in sorted(raw, key=lambda d: -d["height"]):
        if all(abs(p["index"] - q["index"]) >= dist for q in kept):
            kept.append(p)
    kept.sort(key=lambda d: d["index"])

    peaks = []
    for p in kept:
        i = p["index"]
        half = p["base"] + p["prominence"] / 2.0
        left = _crossing(xv, yv, i, half, -1)
        right = _crossing(xv, yv, i, half, 1)
        width = max(right - left, 0.0)
        if min_width and width < float(min_width):
            continue
        sel = (xv >= left) & (xv <= right)
        trapz = getattr(np, "trapezoid", None) or np.trapz
        area = float(trapz(yv[sel] - half, xv[sel])) if sel.sum() > 1 else 0.0
        peaks.append({
            "index": i, "x": p["x"], "height": p["height"],
            "prominence": p["prominence"], "fwhm": width,
            "area": max(area, 0.0), "left": left, "right": right,
        })
    return peaks


def peaks_to_columns(peaks: list) -> dict:
    """寻峰结果转成可写入结果数据集的列字典。"""
    return {
        "峰序号": [f"P{i + 1}" for i in range(len(peaks))],
        "峰位 X": [p["x"] for p in peaks],
        "峰高": [p["height"] for p in peaks],
        "突出度": [p["prominence"] for p in peaks],
        "半高宽 FWHM": [p["fwhm"] for p in peaks],
        "峰面积": [p["area"] for p in peaks],
        "左边界": [p["left"] for p in peaks],
        "右边界": [p["right"] for p in peaks],
    }
