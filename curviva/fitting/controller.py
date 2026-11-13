"""拟合域「控制调用文件」。

FittingController 对外提供：模型清单、执行拟合、把拟合曲线/残差加到图上、
生成与导出报告。界面与脚本都只调用这里，不接触拟合引擎内部。
"""

import numpy as np

from curviva.config.plot_config import CurveConfig, DEFAULT_COLORS
from curviva.fitting import models as model_lib
from curviva.fitting.engine import fit_curve
from curviva.fitting.report import report_text

WEIGHT_MODES = [
    ("无权重（等权）", "none"),
    ("统计权重 1/y", "inv_y"),
    ("统计权重 1/y²", "inv_y2"),
    ("自定义误差列 σ（权重 1/σ²）", "sigma_col"),
    ("自定义权重列 w（直接作权重）", "weight_col"),
]


class FittingController:
    def __init__(self, app=None):
        self.app = app
        self.results: list = []
        self.last = None

    # ------------------------------------------------------------------
    # 模型库
    # ------------------------------------------------------------------

    def models(self) -> list:
        return model_lib.model_menu()

    def model_info(self, key: str) -> dict:
        m = model_lib.get_model(key)
        return {"key": m.key, "name": m.name, "category": m.category,
                "expression": m.expression, "params": list(m.params),
                "description": m.description}

    def infer_params(self, expression: str) -> list:
        return model_lib.infer_params(expression)

    def weight_modes(self) -> list:
        return WEIGHT_MODES

    # ------------------------------------------------------------------
    # 拟合
    # ------------------------------------------------------------------

    def fit(self, spec: dict):
        core = self.app.core
        ds_name = spec.get("dataset") or (core.dataset_names() or [""])[0]
        x_col, y_col = spec.get("x_col"), spec.get("y_col")
        x = core.column_values(ds_name, x_col)
        y = core.column_values(ds_name, y_col)

        key = spec.get("model_key", "linear")
        if key == "custom":
            expression = (spec.get("expression") or "").strip()
            if not expression:
                raise ValueError("请填写自定义 Python 拟合表达式。")
            m = model_lib.custom_model(expression)
        else:
            m = model_lib.get_model(key)

        # 权重
        mode = spec.get("weight_mode", "none")
        w = None
        if mode == "inv_y":
            w = np.where(y != 0, 1.0 / np.abs(y), 1.0)
        elif mode == "inv_y2":
            w = np.where(y != 0, 1.0 / (y * y), 1.0)
        elif mode in ("sigma_col", "weight_col"):
            col = spec.get("weight_column")
            if not col:
                raise ValueError("请选择用于权重的误差/权重列。")
            v = core.column_values(ds_name, col)
            v = v[:len(y)]
            if mode == "sigma_col":
                w = np.where(v != 0, 1.0 / (v * v), 1.0)
            else:
                w = v

        result = fit_curve(
            x, y, m.expression, m.params,
            p0=spec.get("p0") or {}, estimate=m.estimate, weights=w,
            bounds=m.bounds,
            x_min=spec.get("x_min"), x_max=spec.get("x_max"),
            max_iter=int(spec.get("max_iter", 250)),
            key=m.key, name=m.name,
        )
        result.dataset_name = ds_name
        result.x_column, result.y_column = x_col, y_col
        result.weight_mode = dict(WEIGHT_MODES).get(mode, mode)
        self.last = result
        self.results.append(result)
        del self.results[:-10]
        if result.success:
            self.app.project.workspace.setdefault("fit_summary", []).append(
                f"{result.name}｜{result.dataset_name}.{y_col}｜{result.message}")
            del self.app.project.workspace["fit_summary"][:-20]
        return result

    # ------------------------------------------------------------------
    # 结果上图
    # ------------------------------------------------------------------

    def _replace_dataset(self, name: str, columns: dict):
        """幂等：先清理同名结果数据集与引用它的曲线，再重建。"""
        cfg = self.app.config
        cfg.curves = [c for c in cfg.curves if c.dataset_name != name]
        if any(d.name == name for d in self.app.datasets):
            self.app.core.remove_dataset(name)
        return self.app.core.add_result_dataset(name, columns)

    def add_fit_curve(self, result=None, subplot_index: int = 0,
                      with_band: bool = False) -> str:
        """把拟合曲线作为普通曲线加入图中（含可选 95% 置信带）。"""
        r = result or self.last
        if r is None or not r.success:
            raise ValueError("没有可用的拟合结果。")
        self.app.checkpoint("拟合曲线上图")
        safe_name = "".join(ch for ch in r.name if ch not in "\\/:*?\"<>|")[:14]
        name = f"拟合-{safe_name}"
        cols = {"X": r.x_curve, "Y": r.y_curve}
        if with_band and r.band.size:
            cols["下限"] = r.y_curve - r.band
            cols["上限"] = r.y_curve + r.band
        self._replace_dataset(name, cols)

        c = CurveConfig(label=f"拟合：{r.name}", dataset_name=name,
                        x_column="X", y_column="Y", plot_type="line",
                        color="#EE6A73", linestyle="-", linewidth=2.0,
                        subplot_index=int(subplot_index))
        self.app.config.curves.append(c)
        if with_band:
            # 置信带用 ax.fill_between 需专用渲染；这里以两条虚线近似表达上下限
            for label, col, color in (("95% 下限", "下限", "#EE6A73"),
                                      ("95% 上限", "上限", "#EE6A73")):
                self.app.config.curves.append(CurveConfig(
                    label=label, dataset_name=name, x_column="X", y_column=col,
                    plot_type="line", color=color, linestyle="--",
                    linewidth=1.0, alpha=0.6, subplot_index=int(subplot_index)))
        self.app.refresh("fit_curve")
        return name

    def add_residuals(self, result=None, subplot_index: int = 0) -> str:
        r = result or self.last
        if r is None or not r.success:
            raise ValueError("没有可用的拟合结果。")
        self.app.checkpoint("残差上图")
        name = "残差-" + "".join(ch for ch in r.name if ch not in "\\/:*?\"<>|")[:14]
        self._replace_dataset(name, {"X": r.x, "残差": r.residuals,
                                     "拟合值": r.y_fit})
        self.app.config.curves.append(CurveConfig(
            label="残差", dataset_name=name, x_column="X", y_column="残差",
            plot_type="scatter", marker="o", color=DEFAULT_COLORS[4],
            subplot_index=int(subplot_index)))
        self.app.refresh("residuals")
        return name

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------

    def report(self, result=None) -> str:
        r = result or self.last
        if r is None:
            return "尚无拟合结果。"
        return report_text(r)

    def export_report(self, path: str, result=None) -> str:
        text = self.report(result)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path
