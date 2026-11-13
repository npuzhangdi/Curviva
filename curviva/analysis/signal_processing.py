"""P2 信号与数据处理：平滑、归一化、基线扣除、FFT 频谱（纯 numpy）。"""

import numpy as np


def _odd(window: int) -> int:
    w = max(3, int(window))
    return w if w % 2 else w + 1


def moving_average(y, window: int = 5) -> np.ndarray:
    w = _odd(window)
    pad = w // 2
    v = np.pad(np.asarray(y, dtype=float), pad, mode="edge")
    return np.convolve(v, np.ones(w) / w, mode="valid")


def savitzky_golay(y, window: int = 9, polyorder: int = 2) -> np.ndarray:
    """Savitzky–Golay 平滑：由 Vandermonde 伪逆预计算卷积核。"""
    w = _odd(window)
    order = min(max(int(polyorder), 1), w - 1)
    half = w // 2
    t = np.arange(-half, half + 1, dtype=float)
    V = np.vander(t, order + 1, increasing=True)
    kernel = np.linalg.pinv(V)[0]           # t=0 处的滤波系数
    v = np.pad(np.asarray(y, dtype=float), half, mode="edge")
    return np.convolve(v, kernel[::-1], mode="valid")


def median_filter(y, window: int = 5) -> np.ndarray:
    w = _odd(window)
    pad = w // 2
    v = np.pad(np.asarray(y, dtype=float), pad, mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(v, w)
    return np.median(view, axis=1)


def gaussian_filter(y, sigma: float = 2.0) -> np.ndarray:
    sigma = max(float(sigma), 0.2)
    radius = max(1, int(3 * sigma))
    t = np.arange(-radius, radius + 1)
    kernel = np.exp(-0.5 * (t / sigma) ** 2)
    kernel /= kernel.sum()
    v = np.pad(np.asarray(y, dtype=float), radius, mode="edge")
    return np.convolve(v, kernel, mode="valid")


def normalize(y, mode: str = "minmax") -> np.ndarray:
    v = np.asarray(y, dtype=float)
    lo, hi = float(np.nanmin(v)), float(np.nanmax(v))
    if mode == "zscore":
        sd = float(np.nanstd(v))
        return (v - float(np.nanmean(v))) / (sd or 1.0)
    if mode == "max":
        return v / (hi or 1.0)
    if mode == "sum":
        return v / (float(np.nansum(v)) or 1.0)
    if mode == "mean":
        return v / (float(np.nanmean(v)) or 1.0)
    return (v - lo) / ((hi - lo) or 1.0)    # minmax


def baseline(x, y, mode: str = "linear", degree: int = 1) -> np.ndarray:
    """估计基线：constant=最小值；linear=首末均值连线；poly=多项式拟合。"""
    xv, yv = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if mode == "constant":
        return np.full_like(yv, float(np.min(yv)))
    if mode == "poly":
        coef = np.polyfit(xv, yv, min(max(int(degree), 1), max(len(xv) - 1, 1)))
        return np.polyval(coef, xv)
    n = max(len(yv) // 10, 1)
    left = float(np.mean(yv[:n]))
    right = float(np.mean(yv[-n:]))
    return np.linspace(left, right, len(yv))


def fft_spectrum(y, dx: float = 1.0) -> tuple:
    """单侧幅度谱，返回 (频率, 幅度)；自动去均值、加 Hann 窗。"""
    v = np.asarray(y, dtype=float)
    n = v.size
    if n < 2:
        return np.array([0.0]), np.array([0.0])
    v = v - np.mean(v)
    window = np.hanning(n)
    amp = np.abs(np.fft.rfft(v * window)) * 2.0 / max(window.sum(), 1e-12)
    freq = np.fft.rfftfreq(n, d=abs(dx) or 1.0)
    return freq, amp
