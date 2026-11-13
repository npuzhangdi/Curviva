"""绘图引擎模块（配置 -> 图形的唯一转换器）。

能力：
- 多子图、折线/散点/点线/柱形、多曲线、边框四边独立开关、刻度与小数位；
- P3 双 Y 轴图层：每条曲线可指定 left / right，右轴用 twinx 独立渲染；
- P1 误差棒：曲线可指定 Y 误差列；
- 智能抽稀：LTTB 保形降采样（非等间距），按当前视窗渐进细化。

约定：主子图 ax 会打上 `_curviva_index` 标记，twin 图层没有该标记，
画布据此维护视窗状态，避免双 Y 轴导致子图索引错位。
"""

import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import FormatStrFormatter, MaxNLocator, MultipleLocator

from curviva.config.plot_config import PlotConfig


def lttb_indices(x: np.ndarray, y: np.ndarray, n: int) -> np.ndarray:
    """LTTB 保形降采样：从 N 个点中选出 n 个（保留首尾端点）。"""
    N = len(x)
    if n >= N or n < 3:
        return np.arange(N)
    indices = np.empty(n, dtype=int)
    indices[0] = 0
    indices[-1] = N - 1
    bucket = (N - 2) / (n - 2)
    a = 0
    for i in range(1, n - 1):
        s = int(np.floor((i - 1) * bucket)) + 1
        e = min(int(np.floor(i * bucket)) + 1, N - 1)
        ns = int(np.floor(i * bucket)) + 1
        ne = min(int(np.floor((i + 1) * bucket)) + 1, N)
        if e <= s or ne <= ns:
            j = min(s, N - 2)
            indices[i] = j
            a = j
            continue
        avg_x = float(np.mean(x[ns:ne]))
        avg_y = float(np.mean(y[ns:ne]))
        ax_, ay_ = x[a], y[a]
        rx, ry = x[s:e], y[s:e]
        areas = np.abs((ax_ - avg_x) * (ry - ay_) - (ax_ - rx) * (avg_y - ay_))
        j = s + int(np.argmax(areas))
        indices[i] = j
        a = j
    return indices


class PlotBuilder:
    """按 PlotConfig 在 Figure 上渲染整张图。"""

    # ------------------------------------------------------------------
    @staticmethod
    def build(figure: Figure, config: PlotConfig, datasets: list,
              view_state=None) -> None:
        g = config.global_cfg
        figure.clear()
        figure.set_facecolor(g.face_color)
        figure.set_size_inches(g.figsize_w, g.figsize_h, forward=True)
        figure.dpi = g.dpi

        import matplotlib as mpl
        with mpl.rc_context({
            "font.family": [g.font_family, "Microsoft YaHei", "SimHei", "Arial"],
            "font.size": g.base_fontsize,
            "axes.unicode_minus": False,
        }):
            n = config.subplot_count()
            config.ensure_subplots()
            config.clamp_curve_indices()

            if not any(c.visible for c in config.curves):
                figure.text(0.5, 0.52,
                            "空白的画布期待数据\n\n"
                            "左侧面板：导入 CSV / Excel / 粘贴数据 / 示例数据\n"
                            "数据分析 · 公式拟合 · 项目与模板\n"
                            "右侧面板：新建曲线或批量生成曲线",
                            ha="center", va="center",
                            fontsize=g.base_fontsize + 2, color="#9aa4b1")
            else:
                for idx in range(n):
                    ax = figure.add_subplot(g.rows, g.cols, idx + 1)
                    ax._curviva_index = idx
                    PlotBuilder._render_subplot(ax, config.subplots[idx],
                                                config, datasets, idx, view_state)

            if g.title and config.curves:
                figure.suptitle(g.title, fontsize=g.title_fontsize)
            try:
                rect = (0, 0, 1, 0.95) if g.title and config.curves else None
                figure.tight_layout(rect=rect)
            except Exception:
                pass

    # ------------------------------------------------------------------
    @staticmethod
    def _render_subplot(ax, sub, config: PlotConfig, datasets: list,
                        idx: int, view_state) -> None:
        g = config.global_cfg
        curves = [c for c in config.curves
                  if c.subplot_index == idx and c.visible]
        left = [c for c in curves if c.y_axis != "right"]
        right = [c for c in curves if c.y_axis == "right"]
        if not sub.show_y2:                  # 关闭右轴时降级到左轴绘制
            left = curves
            right = []

        resolved = [(c, r) for c in curves
                    for r in [PlotBuilder._resolve_data(c, datasets)] if r is not None]
        line_resolved = [(c, r) for c, r in resolved if c.plot_type != "bar"]
        bar_resolved = [(c, r) for c, r in resolved if c.plot_type == "bar"]

        # ---- 视窗与 X 范围 ----
        view = view_state.get(idx) if view_state else None
        if view is not None:
            (x0, x1), _ = view
        elif not sub.x_axis.auto_scale:
            x0, x1 = sub.x_axis.min_val, sub.x_axis.max_val
        else:
            x0, x1 = PlotBuilder._auto_x_range(line_resolved, bar_resolved)

        if sub.x_axis.scale == "log":
            try:
                ax.set_xscale("log")
            except Exception:
                pass
        if sub.y_axis.scale == "log":
            try:
                ax.set_yscale("log")
            except Exception:
                pass
        try:
            ax.set_xlim(x0, x1)
        except Exception:
            pass

        # ---- 左轴曲线组 ----
        PlotBuilder._draw_group(ax, left, g, datasets, x0, x1,
                                view, sub.y_axis, config)

        # ---- 右轴图层 ----
        ax2 = None
        if right:
            ax2 = ax.twinx()
            ax2._curviva_twin = True
            if sub.y2_axis.scale == "log":
                try:
                    ax2.set_yscale("log")
                except Exception:
                    pass
            PlotBuilder._draw_group(ax2, right, g, datasets, x0, x1,
                                    view, sub.y2_axis, config)
            if sub.y2_axis.label:
                ax2.set_ylabel(sub.y2_axis.label)
            PlotBuilder._apply_ticks(ax2, sub.y2_axis, is_x=False)
            ax2.spines["top"].set_visible(sub.show_top)
            ax2.spines["right"].set_visible(True)
            ax2.spines["left"].set_visible(False)
            ax2.spines["bottom"].set_visible(False)

        # ---- 标题与轴标签 ----
        if sub.title:
            ax.set_title(sub.title)
        if sub.x_axis.label:
            ax.set_xlabel(sub.x_axis.label)
        if sub.y_axis.label:
            ax.set_ylabel(sub.y_axis.label)

        if view is None:
            if sub.x_axis.invert:
                ax.invert_xaxis()
            if sub.y_axis.invert:
                ax.invert_yaxis()
            if ax2 is not None and sub.y2_axis.invert:
                ax2.invert_yaxis()

        PlotBuilder._apply_ticks(ax, sub.x_axis, is_x=True)
        PlotBuilder._apply_ticks(ax, sub.y_axis, is_x=False)

        for spine, visible in (
            ("top", sub.show_top), ("bottom", sub.show_bottom),
            ("left", sub.show_left), ("right", sub.show_right and ax2 is None),
        ):
            ax.spines[spine].set_visible(visible)

        if sub.grid_show:
            ax.grid(True, axis=sub.grid_axis, linestyle=sub.grid_linestyle,
                    alpha=sub.grid_alpha, color="gray")

        if sub.show_legend and any(c.label for c in curves):
            handles, labels = ax.get_legend_handles_labels()
            if ax2 is not None:
                h2, l2 = ax2.get_legend_handles_labels()
                handles, labels = list(handles) + list(h2), list(labels) + list(l2)
            if handles:
                ax.legend(handles, labels, loc=sub.legend_loc,
                          fontsize=sub.legend_fontsize, frameon=sub.legend_frame)

    # ------------------------------------------------------------------
    @staticmethod
    def _draw_group(ax, curves, g, datasets, x0, x1, view, axis_cfg,
                    config=None) -> None:
        """在一个坐标轴（左轴或右轴）上绘制一组曲线，并处理自动 Y 范围。"""
        resolved = [(c, r) for c in curves
                    for r in [PlotBuilder._resolve_data(c, datasets)] if r is not None]
        lines = [(c, r) for c, r in resolved if c.plot_type != "bar"]
        bars = [(c, r) for c, r in resolved if c.plot_type == "bar"]

        if view is None and not axis_cfg.auto_scale:
            try:
                ax.set_ylim(axis_cfg.min_val, axis_cfg.max_val)
            except Exception:
                pass

        smart = g.smart_render
        target = max(int(g.target_points), 3)
        y_for_range = []
        for c, (x, y, x_labels, yerr) in lines:
            xs, ys, xls, es = PlotBuilder._slice_window(x, y, x_labels, x0, x1, yerr)
            if smart and len(ys) > target:
                sel = lttb_indices(np.asarray(xs, dtype=float),
                                   np.asarray(ys, dtype=float), target)
                xs = [xs[i] for i in sel]
                ys = [ys[i] for i in sel]
                xls = [xls[i] for i in sel] if xls is not None else None
                es = es[sel] if es is not None else None
            y_for_range.append(np.asarray(ys, dtype=float))
            idx = next((i for i, cc in enumerate(config.curves) if cc is c), -1) \
                if config is not None else -1
            PlotBuilder._draw_curve(ax, c, xs, ys, xls, es, idx)

        for _, (_, y, _, _) in bars:
            y_for_range.append(np.asarray(y, dtype=float))
        PlotBuilder._draw_bars(ax, bars)

        if view is None and axis_cfg.auto_scale and y_for_range:
            chunks = [v[np.isfinite(v)] for v in y_for_range if v.size]
            flat = np.concatenate(chunks) if chunks else np.array([])
            if flat.size:
                ymin, ymax = float(flat.min()), float(flat.max())
                if ymin == ymax:
                    ymin, ymax = ymin - 0.5, ymax + 0.5
                pad = 0.05 * (ymax - ymin)
                try:
                    if axis_cfg.scale == "log":
                        ax.set_ylim(max(ymin - pad, 1e-12), ymax + pad)
                    else:
                        ax.set_ylim(ymin - pad, ymax + pad)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    @staticmethod
    def _auto_x_range(resolved_line, resolved_bar):
        xs = [r[0] for _, r in resolved_line]
        for _, r in resolved_bar:
            x, y, x_labels, _ = r
            xs.append(np.arange(len(y)) if x_labels is not None else x)
        vals = [v[np.isfinite(v)] for v in xs if len(v)]
        if not vals:
            return 0.0, 1.0
        allx = np.concatenate(vals)
        if not allx.size:
            return 0.0, 1.0
        lo, hi = float(allx.min()), float(allx.max())
        if lo == hi:
            lo, hi = lo - 0.5, hi + 0.5
        pad = 0.03 * (hi - lo)
        return lo - pad, hi + pad

    @staticmethod
    def _slice_window(x, y, x_labels, x0, x1, yerr=None):
        lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
        m = 0.02 * (hi - lo) if hi > lo else 0.0
        mask = (x >= lo - m) & (x <= hi + m)
        if not mask.any():
            mask = np.ones_like(x, dtype=bool)
        if mask.all():
            return x, y, x_labels, yerr
        idx = np.where(mask)[0]
        return (x[idx], y[idx],
                [x_labels[i] for i in idx] if x_labels is not None else None,
                yerr[idx] if yerr is not None else None)

    @staticmethod
    def _resolve_data(curve, datasets: list):
        """返回 (x, y, x文本标签或None, y误差或None)；失败返回 None。"""
        ds = next((d for d in datasets if d.name == curve.dataset_name), None)
        if ds is None:
            return None
        x = ds.columns.get(curve.x_column)
        y = ds.columns.get(curve.y_column)
        if x is None or y is None:
            return None
        n = min(len(x), len(y))
        x, y = list(x)[:n], list(y)[:n]

        x_labels = None
        try:
            x_num = np.asarray(x, dtype=float)
        except (TypeError, ValueError):
            x_num = np.arange(len(x))
            x_labels = [str(v) for v in x]
        try:
            y_num = np.asarray(y, dtype=float)
        except (TypeError, ValueError):
            return None

        mask = np.isfinite(x_num) & np.isfinite(y_num)
        if x_labels is not None:
            x_labels = [x_labels[i] for i in np.where(mask)[0]]

        yerr = None
        col = getattr(curve, "error_y_column", "") or ""
        if col and col in ds.columns:
            try:
                raw = np.asarray(list(ds.columns[col])[:n], dtype=float)
                errs = np.zeros(n, dtype=float)
                errs[:len(raw)] = raw
                yerr = np.abs(errs[mask])
                yerr[~np.isfinite(yerr)] = 0.0
            except (TypeError, ValueError):
                yerr = None
        return x_num[mask], y_num[mask], x_labels, yerr

    @staticmethod
    def _draw_curve(ax, c, xs, ys, x_labels, yerr=None, curve_index: int = -1) -> None:
        label = c.label if c.label else None
        marker = c.marker if c.marker != "None" else "None"
        if c.plot_type == "scatter":
            linestyle, marker = "None", ("o" if marker == "None" else marker)
        elif c.plot_type == "line_point":
            linestyle = c.linestyle if c.linestyle != "None" else "-"
            marker = "o" if marker == "None" else marker
        else:
            linestyle = c.linestyle

        kwargs = dict(linestyle=linestyle, linewidth=c.linewidth,
                      marker=marker, markersize=c.markersize,
                      color=c.color, alpha=c.alpha, label=label)
        if yerr is not None and len(yerr) == len(xs):
            kwargs.update(yerr=yerr, capsize=getattr(c, "error_cap_size", 3.0),
                          ecolor=c.color, elinewidth=max(c.linewidth * 0.7, 0.6))
            container = ax.errorbar(xs, ys, **kwargs)
            artist = getattr(container, "lines", [None])[0] if hasattr(
                container, "lines") else None
        else:
            artist = ax.plot(xs, ys, **kwargs)[0]
        # 供图上鼠标编辑反查曲线配置（选中、数据点拖拽）
        if artist is not None:
            artist._curviva_curve_index = curve_index
            artist._curviva_dataset = c.dataset_name
            artist._curviva_y_column = c.y_column
            artist._curviva_x_column = c.x_column

        if x_labels is not None and len(x_labels) <= 50:
            ax.set_xticks(np.arange(len(x_labels)))
            ax.set_xticklabels(x_labels)

    @staticmethod
    def _draw_bars(ax, resolved_bar) -> None:
        if not resolved_bar:
            return
        n = len(resolved_bar)
        for j, (c, (x, y, x_labels, yerr)) in enumerate(resolved_bar):
            base = np.arange(len(y)) if x_labels is not None else x
            w = c.bar_width / n
            offset = (j - (n - 1) / 2) * w
            kwargs = dict(width=w * 0.92, color=c.color, alpha=c.alpha,
                          label=c.label if c.label else None)
            if yerr is not None and len(yerr) == len(y):
                kwargs.update(yerr=yerr, capsize=getattr(c, "error_cap_size", 3.0),
                              error_kw={"ecolor": c.color, "elinewidth": 0.8})
            ax.bar(base + offset, y, **kwargs)

        first = resolved_bar[0][1]
        if first[2] is not None:
            ax.set_xticks(np.arange(len(first[2])))
            ax.set_xticklabels(first[2])

    @staticmethod
    def _apply_ticks(ax, axis_cfg, is_x: bool) -> None:
        axis = ax.xaxis if is_x else ax.yaxis
        if axis_cfg.tick_mode == "num":
            axis.set_major_locator(MaxNLocator(nbins=max(axis_cfg.num_ticks, 2)))
        elif axis_cfg.tick_mode == "step":
            if axis_cfg.tick_step > 0:
                axis.set_major_locator(MultipleLocator(axis_cfg.tick_step))
        if axis_cfg.decimal_places >= 0:
            axis.set_major_formatter(
                FormatStrFormatter(f"%.{axis_cfg.decimal_places}f"))
