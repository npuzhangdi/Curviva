"""P1 拟合引擎：Levenberg–Marquardt 非线性最小二乘（纯 numpy，无 scipy 依赖）。

支持：
- 任意 Python 表达式模型（内置模型库与自定义表达式共用同一执行路径）；
- 数值雅可比 + 阻尼迭代 + 参数边界裁剪；
- 权重（无 / 1/y / 1/y² / 自定义误差列 / 自定义权重列）；
- 拟合区间、参数初值覆盖、最大迭代次数；
- 参数标准误、R² / 调整 R² / 约化 χ² / RMSE / AIC、95% 置信带、残差。
"""

import ast
import math
from dataclasses import dataclass, field

import numpy as np

from curviva.core.formula_engine import safe_eval, validate_expression


@dataclass
class FitResult:
    key: str = ""
    name: str = ""
    expression: str = ""
    params: dict = field(default_factory=dict)
    stderr: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    x: np.ndarray = field(default_factory=lambda: np.array([]))
    y: np.ndarray = field(default_factory=lambda: np.array([]))
    weights: np.ndarray = field(default_factory=lambda: np.array([]))
    y_fit: np.ndarray = field(default_factory=lambda: np.array([]))
    residuals: np.ndarray = field(default_factory=lambda: np.array([]))
    x_curve: np.ndarray = field(default_factory=lambda: np.array([]))
    y_curve: np.ndarray = field(default_factory=lambda: np.array([]))
    band: np.ndarray = field(default_factory=lambda: np.array([]))
    dataset_name: str = ""
    x_column: str = ""
    y_column: str = ""
    weight_mode: str = "none"
    success: bool = False
    message: str = ""
    iterations: int = 0

    def summary(self) -> str:
        return (f"{self.name} | R²={self.stats.get('r2', float('nan')):.6f} | "
                f"参数：{', '.join(f'{k}={v:.6g}' for k, v in self.params.items())}")


def compile_expression(expression: str):
    """校验并编译 Python 表达式（一次校验，多次求值）。"""
    validate_expression(expression)
    return compile(ast.parse(expression.strip(), mode="eval"), "<curviva-fit>", "eval")


def predict(expression_or_code, params: dict, x) -> np.ndarray:
    """按参数计算模型值；自动把标量广播到 x 长度。"""
    code = (expression_or_code if hasattr(expression_or_code, "co_code")
            else compile_expression(expression_or_code))
    xv = np.asarray(x, dtype=float)
    scope = {
        "x": xv, "np": np, "numpy": np, "math": math,
        "pi": np.pi, "e": np.e,
        "__builtins__": {"abs": abs, "min": min, "max": max, "sum": sum,
                         "float": float, "int": int, "pow": pow, "len": len,
                         "round": round, "range": range},
    }
    scope.update({k: float(v) for k, v in params.items()})
    with np.errstate(all="ignore"):
        value = eval(code, scope, {})            # noqa: S307 - 已通过 ast 白名单校验
    arr = np.asarray(value, dtype=float)
    if arr.ndim == 0:
        arr = np.full(xv.shape, float(arr))
    else:
        arr = np.broadcast_to(arr, xv.shape).astype(float, copy=True)
    return arr


def fit_curve(x, y, expression: str, param_names: list,
              p0: dict = None, estimate=None, weights=None,
              bounds: dict = None, x_min=None, x_max=None,
              max_iter: int = 250, n_curve: int = 300,
              key: str = "", name: str = "", label: str = "") -> FitResult:
    """执行拟合并返回 FitResult。异常统一转成 success=False 的友好消息。"""
    result = FitResult(key=key, name=name or label or "拟合", expression=expression)
    try:
        xv = np.asarray(x, dtype=float).ravel()
        yv = np.asarray(y, dtype=float).ravel()
        n = min(xv.size, yv.size)
        xv, yv = xv[:n], yv[:n]

        # 拟合区间与有限值过滤
        mask = np.isfinite(xv) & np.isfinite(yv)
        if x_min is not None:
            mask &= xv >= float(x_min)
        if x_max is not None:
            mask &= xv <= float(x_max)
        xv, yv = xv[mask], yv[mask]
        if xv.size < max(len(param_names) + 1, 3):
            raise ValueError("拟合区间内有效数据点太少（至少需要参数个数 + 1 个点）。")

        w = (np.ones_like(yv) if weights is None
             else np.asarray(weights, dtype=float).ravel()[:n][mask])
        w = np.where(np.isfinite(w) & (w > 0), w, 1.0)
        sw = np.sqrt(w)

        # 初值
        init = {}
        if callable(estimate):
            try:
                init = {k: float(v) for k, v in (estimate(xv, yv) or {}).items()}
            except Exception:                    # noqa: BLE001
                init = {}
        if p0:
            init.update({k: float(v) for k, v in p0.items() if v is not None})
        p = np.array([init.get(k, 1.0) for k in param_names], dtype=float)
        p = np.where(np.isfinite(p), p, 1.0)

        code = compile_expression(expression)

        def model_values(params_vec, xs=None):
            d = dict(zip(param_names, params_vec))
            return predict(code, d, xv if xs is None else xs)

        def residual(params_vec):
            diff = yv - model_values(params_vec)
            if not np.all(np.isfinite(diff)):
                diff = np.nan_to_num(diff, nan=1e12, posinf=1e12, neginf=-1e12)
            return diff * sw

        def jacobian(params_vec, xs=None):
            """数值偏导 df/dp（中心差分）。"""
            xs = xv if xs is None else xs
            J = np.empty((xs.size, len(params_vec)))
            for j, val in enumerate(params_vec):
                h = 1e-6 * max(abs(val), 1.0)
                pp = params_vec.copy(); pp[j] += h
                pm = params_vec.copy(); pm[j] -= h
                with np.errstate(all="ignore"):
                    J[:, j] = (predict(code, dict(zip(param_names, pp)), xs) -
                               predict(code, dict(zip(param_names, pm)), xs)) / (2 * h)
            return np.nan_to_num(J, nan=0.0, posinf=0.0, neginf=0.0)

        r = residual(p)
        cost = float(r @ r)
        if not np.isfinite(cost):
            raise ValueError("模型在初值处无法求值，请检查表达式、初值或数据范围（如 log(x) 需要 x>0）。")

        lam = 1e-3
        iters = 0
        for it in range(max(1, int(max_iter))):
            iters = it + 1
            Jf = jacobian(p)                      # df/dp
            J = -Jf * sw[:, None]                # d(加权残差)/dp
            JTJ = J.T @ J
            g = J.T @ r
            diag = np.diag(JTJ).copy()
            diag[diag <= 0] = 1e-8
            H = JTJ + lam * np.diag(diag)
            try:
                step = np.linalg.solve(H, -g)
            except np.linalg.LinAlgError:
                step = np.linalg.lstsq(H, -g, rcond=None)[0]
            if not np.all(np.isfinite(step)):
                lam *= 10
                continue
            candidate = p + step
            if bounds:
                for j, pname in enumerate(param_names):
                    lim = bounds.get(pname)
                    if lim:
                        lo, hi = lim
                        if lo is not None:
                            candidate[j] = max(candidate[j], float(lo))
                        if hi is not None:
                            candidate[j] = min(candidate[j], float(hi))
            rc = residual(candidate)
            new_cost = float(rc @ rc)
            if np.isfinite(new_cost) and new_cost < cost:
                improvement = cost - new_cost
                p, r, cost = candidate, rc, new_cost
                lam = max(lam / 3.0, 1e-12)
                if improvement < 1e-12 * (cost + 1e-12):
                    break
            else:
                lam = min(lam * 10.0, 1e12)
                if lam > 1e10:
                    break

        # ---- 结果 ----
        params = {k: float(v) for k, v in zip(param_names, p)}
        y_fit = model_values(p)
        residuals = yv - y_fit
        k = len(param_names)
        dof = max(xv.size - k, 1)
        rss_w = float(np.sum(w * residuals ** 2))
        mean_w = float(np.sum(w * yv) / np.sum(w))
        tss_w = float(np.sum(w * (yv - mean_w) ** 2))
        r2 = 1.0 - rss_w / tss_w if tss_w > 0 else float("nan")
        adj_r2 = (1.0 - (1.0 - r2) * (xv.size - 1) / max(xv.size - k - 1, 1)
                  if np.isfinite(r2) else float("nan"))
        rmse = float(np.sqrt(np.mean(residuals ** 2)))
        chi2 = rss_w / dof
        aic = xv.size * math.log(max(np.mean(residuals ** 2), 1e-300)) + 2 * k

        # 参数标准误（协方差 = χ² · (JᵀJ)⁻¹）
        stderr = {name_: float("nan") for name_ in param_names}
        cov = None
        try:
            Jw = -jacobian(p) * sw[:, None]
            cov = chi2 * np.linalg.pinv(Jw.T @ Jw)
            diag_cov = np.diag(cov)
            for j, name_ in enumerate(param_names):
                stderr[name_] = float(np.sqrt(abs(diag_cov[j])))
        except Exception:                        # noqa: BLE001
            pass

        # 拟合曲线与 95% 置信带
        x_curve = np.linspace(float(xv.min()), float(xv.max()), max(int(n_curve), 10))
        y_curve = predict(code, params, x_curve)
        band = np.zeros_like(x_curve)
        if cov is not None:
            try:
                Jc = jacobian(p, x_curve)
                se = np.sqrt(np.abs(np.einsum("ij,jk,ik->i", Jc, cov, Jc)))
                band = 1.96 * se
            except Exception:                    # noqa: BLE001
                band = np.zeros_like(x_curve)

        result.params = params
        result.stderr = stderr
        result.stats = {
            "n": int(xv.size), "k": k, "dof": int(dof),
            "r2": r2, "adj_r2": adj_r2, "rmse": rmse,
            "reduced_chi2": chi2, "rss": rss_w, "aic": aic,
        }
        result.x, result.y, result.weights = xv, yv, w
        result.y_fit, result.residuals = y_fit, residuals
        result.x_curve, result.y_curve, result.band = x_curve, y_curve, band
        result.iterations = iters
        result.success = True
        result.message = (f"拟合完成：{xv.size} 个数据点 / {k} 个参数 / "
                          f"{iters} 次迭代，R² = {r2:.6f}")
    except Exception as e:                       # noqa: BLE001 - 统一转成结果对象
        result.success = False
        result.message = f"拟合失败：{e}"
    return result
