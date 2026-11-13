"""P3 批处理（对标 Origin 的 Batch Processing / Analysis Template）。

对一批 CSV / Excel 文件套用同一份绘图配置，自动挑选 X/Y 列并批量导出
PNG / SVG / PDF / EPS。全程使用 matplotlib Agg 后端，不依赖 Qt 界面，
因此可被脚本、插件或无界面环境直接调用。
"""

import os
from copy import deepcopy

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from curviva.config.controller import ConfigController
from curviva.config.plot_config import DEFAULT_COLORS, CurveConfig, GlobalConfig
from curviva.core.data_manager import DataManager
from curviva.core.plot_builder import PlotBuilder

SUPPORTED_INPUT = (".csv", ".xlsx", ".xlsm")
SUPPORTED_OUTPUT = ("png", "svg", "pdf", "eps")


def _import(path: str) -> list:
    dm = DataManager()
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return [dm.import_csv(path)]
    if ext in (".xlsx", ".xlsm"):
        return dm.import_excel(path)
    raise ValueError(f"不支持的输入格式：{ext}")


def _build_config(template: dict, ds, columns_rule: dict):
    ctrl = ConfigController()
    if template:
        ctrl.from_dict(deepcopy(template))
    else:
        ctrl.config.global_cfg = GlobalConfig()
    cfg = ctrl.config
    cfg.global_cfg.rows = 1
    cfg.global_cfg.cols = 1
    cfg.ensure_subplots()

    style = None
    if cfg.curves:
        style = deepcopy(cfg.curves[0])
    cfg.curves = []

    numeric = ds.numeric_columns()
    all_cols = list(ds.column_order)
    x_col = columns_rule.get("x_column") or ""
    if x_col not in all_cols:
        x_col = numeric[0] if numeric else (all_cols[0] if all_cols else "")
    requested = columns_rule.get("y_columns") or []
    y_cols = [c for c in requested if c in all_cols and c != x_col]
    if not y_cols:
        y_cols = [c for c in numeric if c != x_col][:8] or [x_col]

    ptype = columns_rule.get("plot_type", "line")
    for i, y_col in enumerate(y_cols):
        c = deepcopy(style) if style else CurveConfig()
        c.dataset_name = ds.name
        c.x_column = x_col
        c.y_column = y_col
        c.label = y_col
        c.plot_type = ptype
        c.subplot_index = 0
        c.visible = True
        c.color = columns_rule.get("color") or DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
        c.error_y_column = ""
        cfg.curves.append(c)
    return cfg


def batch_export(files: list, template: dict, out_dir: str, fmt: str = "png",
                 dpi: int = 300, x_column: str = "", y_columns: list = None,
                 plot_type: str = "line", title_from_file: bool = True,
                 progress=None) -> dict:
    """批量导出。返回 {'total', 'ok', 'failed', 'items': [(输入, 输出, 错误)]}。"""
    fmt = (fmt or "png").lower().lstrip(".")
    if fmt not in SUPPORTED_OUTPUT:
        raise ValueError(f"不支持的导出格式：{fmt}")
    os.makedirs(out_dir, exist_ok=True)
    rule = {"x_column": x_column, "y_columns": y_columns or [],
            "plot_type": plot_type}
    items = []
    jobs = []
    for path in files:
        if os.path.splitext(path)[1].lower() not in SUPPORTED_INPUT:
            items.append((path, "", "不支持的文件类型"))
            continue
        jobs.append(path)
    total = len(jobs)
    ok = 0

    for idx, path in enumerate(jobs, 1):
        stem = os.path.splitext(os.path.basename(path))[0]
        try:
            datasets = _import(path)
        except Exception as e:                    # noqa: BLE001
            items.append((path, "", f"导入失败：{e}"))
            if progress:
                progress(idx, total, f"{stem}：导入失败")
            continue
        for ds in datasets:
            figure = None
            try:
                cfg = _build_config(template, ds, rule)
                if title_from_file:
                    suffix = f" · {ds.name}" if len(datasets) > 1 else ""
                    cfg.global_cfg.title = stem + suffix
                figure = Figure()
                FigureCanvasAgg(figure)
                PlotBuilder.build(figure, cfg, [ds])
                base = "".join(ch if ch not in '\\/:*?"<>|' else "_"
                               for ch in f"{stem}-{ds.name}")
                out = os.path.join(out_dir, f"{base}.{fmt}")
                figure.savefig(out, dpi=max(int(dpi), 72), format=fmt,
                               bbox_inches="tight")
                items.append((path, out, ""))
                ok += 1
            except Exception as e:                # noqa: BLE001
                items.append((path, "", f"绘图/导出失败：{e}"))
            finally:
                if figure is not None:
                    try:
                        import matplotlib.pyplot as plt
                        plt.close(figure)
                    except Exception:             # noqa: BLE001
                        pass
        if progress:
            progress(idx, total, f"{stem}：已处理")
    return {"total": len(files), "ok": ok,
            "failed": sum(1 for it in items if it[2]), "items": items}
