"""Origin 式「在图上直接用鼠标修改」交互编辑器。

挂载到某个 PlotCanvas 上，不改动绘图配置本身，而是把编辑结果写到
GraphDocument（文本标注、图例位置、选中曲线），或通过 CoreController
把数据点拖拽结果写回工作表。渲染后由 post_render_callbacks 自动叠加，
因此缩放、刷新、撤销重做后都不会丢失。

支持的鼠标操作：
- 选择：单击曲线选中并定位右侧「曲线」属性页；拖动文本 / 图例；
- 平移：在坐标轴内拖动平移 X/Y 范围（与滚轮缩放、智能抽稀联动）；
- 框选放大：拖出矩形放大到该区域；
- 文本：单击空白处新增标注，拖动已有标注移动，双击编辑，右键删除；
- 图例：单击任意位置把图例放到该处并继续拖动；
- 数据点：拖动曲线上的点，写回原工作表对应单元格；
- 双击：曲线→曲线属性，文本→编辑文本，图例→图例字体，轴附近→坐标轴设置；
- 右键：完整上下文菜单；滚轮：以光标为锚点缩放；双击空白：还原视图。
"""

import numpy as np
from matplotlib.patches import Rectangle
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QInputDialog, QMenu

MODES = [
    ("select", "选择", "点选曲线、拖动文本与图例"),
    ("pan", "平移", "在坐标轴内拖动平移视窗"),
    ("zoom", "框选放大", "拖出矩形放大到选区"),
    ("text", "文本", "单击新增标注，双击编辑，拖动移动"),
    ("legend", "图例", "单击或拖动改变图例位置"),
    ("data", "数据点", "拖动点写回工作表数据"),
]
MODE_NAMES = dict((m[0], m[1]) for m in MODES)


class GraphEditor:
    """一个图形窗口一个实例；doc 是 graphs/model.py 的 Document。"""

    def __init__(self, canvas, app, doc, callbacks: dict = None):
        self.canvas = canvas
        self.app = app
        self.doc = doc
        self.callbacks = callbacks or {}
        self.mode = doc.mode or "select"
        self._texts = []            # [(文档索引, Text artist, ax)]
        self._drag = None
        self._rect = None
        self._lines_cache = []
        canvas.mpl_connect("button_press_event", self.on_press)
        canvas.mpl_connect("motion_notify_event", self.on_motion)
        canvas.mpl_connect("button_release_event", self.on_release)
        self.set_mode(self.mode)

    # ------------------------------------------------------------------
    def _cb(self, name, *args):
        fn = self.callbacks.get(name)
        if callable(fn):
            try:
                fn(*args)
            except Exception:              # noqa: BLE001
                pass

    def set_mode(self, mode: str) -> None:
        if mode not in MODE_NAMES:
            mode = "select"
        self.mode = mode
        self.doc.mode = mode
        cursor = {
            "select": Qt.ArrowCursor, "pan": Qt.OpenHandCursor,
            "zoom": Qt.CrossCursor, "text": Qt.IBeamCursor,
            "legend": Qt.SizeAllCursor, "data": Qt.PointingHandCursor,
        }.get(mode, Qt.ArrowCursor)
        self.canvas.setCursor(QCursor(cursor))
        self._cb("status", f"图形编辑模式：{MODE_NAMES[mode]}　·　{MODES[[m[0] for m in MODES].index(mode)][2]}")

    # ------------------------------------------------------------------
    # 渲染后叠加：文本 / 图例 / 选中高亮
    # ------------------------------------------------------------------

    def apply_overlays(self, figure) -> None:
        # 绘图引擎按全局配置设过 figure 尺寸；图形文档可以有自己的出版尺寸，
        # 渲染后再覆盖一次（forward=False 不改变 Qt 画布显示大小）。
        try:
            w, h = self.doc.size_inches()
            figure.set_size_inches(w, h, forward=False)
        except Exception:                 # noqa: BLE001
            pass
        self._texts = []
        main_axes = [ax for ax in figure.axes
                     if getattr(ax, "_curviva_index", None) is not None]
        if not main_axes:
            return
        cfg = self.app.config
        for ax in figure.axes:
            # 清除上一次叠加产生的文本，避免重复累积
            for t in list(ax.texts):
                if str(t.get_gid() or "").startswith("curviva-text-"):
                    t.remove()

        # --- 图例位置 ---
        anchor = self.doc.legend_anchor
        for ax in main_axes:
            leg = ax.get_legend()
            if leg is None:
                continue
            if not anchor:
                continue
            handles, labels = ax.get_legend_handles_labels()
            idx = ax._curviva_index
            sub = cfg.subplots[idx] if idx < len(cfg.subplots) else None
            leg.remove()
            ax.legend(handles, labels, loc="upper left",
                      bbox_to_anchor=(float(anchor[0]), float(anchor[1])),
                      bbox_transform=ax.transAxes, borderaxespad=0.0,
                      fontsize=sub.legend_fontsize if sub else 10,
                      frameon=sub.legend_frame if sub else True)

        # --- 文本标注 ---
        for i, item in enumerate(self.doc.texts or []):
            idx = int(item.get("axes", 0) or 0)
            ax = next((a for a in main_axes if a._curviva_index == idx),
                      main_axes[0])
            artist = ax.text(float(item.get("x", 0.5)), float(item.get("y", 0.5)),
                             str(item.get("text", "")),
                             transform=ax.transAxes,
                             fontsize=float(item.get("size", 11)),
                             color=item.get("color", "#25304A"),
                             gid=f"curviva-text-{i}", zorder=20,
                             bbox=dict(boxstyle="round,pad=0.25", fc="white",
                                       ec="none", alpha=0.55))
            self._texts.append((i, artist, ax))

        # --- 选中曲线高亮 ---
        self._lines_cache = []
        for ax in figure.axes:
            for line in ax.lines:
                ci = getattr(line, "_curviva_curve_index", -1)
                if ci < 0:
                    continue
                if not hasattr(line, "_curviva_base_lw"):
                    line._curviva_base_lw = line.get_linewidth()
                    line._curviva_base_ms = line.get_markersize()
                sel = (ci == self.doc.selected_curve)
                line.set_linewidth(line._curviva_base_lw + (1.8 if sel else 0.0))
                line.set_markersize(line._curviva_base_ms + (2.0 if sel else 0.0))
                if sel:
                    line.set_zorder(8)
                self._lines_cache.append((line, ax, ci))

    def reapply(self) -> None:
        self.apply_overlays(self.canvas.figure)
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    # 命中测试（全部基于显示坐标，避免依赖 matplotlib 事件类型）
    # ------------------------------------------------------------------

    def _axes_at(self, x, y):
        for ax in self.canvas.figure.axes:
            try:
                if ax.get_window_extent().contains(x, y):
                    return ax
            except Exception:                 # noqa: BLE001
                continue
        return None

    def _frac(self, ax, x, y):
        try:
            fx, fy = ax.transAxes.inverted().transform((x, y))
            return float(fx), float(fy)
        except Exception:                     # noqa: BLE001
            return 0.5, 0.5

    def _data(self, ax, x, y):
        try:
            dx, dy = ax.transData.inverted().transform((x, y))
            return float(dx), float(dy)
        except Exception:                     # noqa: BLE001
            return 0.0, 0.0

    def _hit(self, x, y):
        """返回 (类型, ...)。优先级：文本 > 图例 > 曲线。"""
        for i, artist, ax in self._texts:
            try:
                if artist.get_window_extent().contains(x, y):
                    return ("text", i, ax)
            except Exception:                 # noqa: BLE001
                continue
        for ax in self.canvas.figure.axes:
            leg = ax.get_legend()
            if leg is None:
                continue
            try:
                if leg.get_window_extent().contains(x, y):
                    return ("legend", ax)
            except Exception:                 # noqa: BLE001
                continue
        tol = 9.0 * max(float(self.canvas.devicePixelRatioF()), 1.0)
        best = None
        for line, ax, ci in self._lines_cache:
            try:
                xd = np.asarray(line.get_xdata(), dtype=float)
                yd = np.asarray(line.get_ydata(), dtype=float)
                n = min(len(xd), len(yd))
                if n == 0:
                    continue
                pts = ax.transData.transform(np.column_stack((xd[:n], yd[:n])))
                d = np.hypot(pts[:, 0] - x, pts[:, 1] - y)
                j = int(np.argmin(d))
                if np.isfinite(d[j]) and d[j] < tol and (best is None or d[j] < best[0]):
                    best = (d[j], line, ax, j, ci)
            except Exception:                 # noqa: BLE001
                continue
        if best is not None:
            return ("line", best[1], best[2], best[3], best[4])
        return ("none",)

    def _qt_pos(self, qevent):
        dpr = float(self.canvas.devicePixelRatioF())
        pos = qevent.position() * dpr
        return float(pos.x()), float(self.canvas.height()) * dpr - float(pos.y())

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def on_press(self, event) -> None:
        if event.button == 3 or getattr(event, "button", None) == "right":
            self._context_menu(event)
            return
        if getattr(event, "dblclick", False):
            return
        x, y = float(event.x), float(event.y)
        ax = event.inaxes or self._axes_at(x, y)
        hit = self._hit(x, y)
        fx, fy = self._frac(ax, x, y) if ax is not None else (0.5, 0.5)
        idx = getattr(ax, "_curviva_index", 0) if ax is not None else 0
        if idx is None:
            idx = 0

        if self.mode == "text":
            if hit[0] == "text":
                self._begin_drag("text", x, y, index=hit[1], ax=ax)
            elif ax is not None:
                self._add_text_dialog(fx, fy, idx)
            return

        if self.mode == "legend":
            self.app.checkpoint("图上编辑：移动图例")
            self.app.graphs.set_legend_anchor(self.doc.id, (fx, fy))
            self._begin_drag("legend", x, y, ax=ax)
            self.reapply()
            return

        if self.mode == "pan":
            if ax is None:
                return
            self._begin_drag("pan", x, y, ax=ax,
                             xlim=ax.get_xlim(), ylim=ax.get_ylim())
            return

        if self.mode == "zoom":
            if ax is None:
                return
            dx, dy = self._data(ax, x, y)
            self._rect = Rectangle((dx, dy), 0, 0, fill=False,
                                   edgecolor="#5A6CF6", linewidth=1.4,
                                   linestyle="--", zorder=30)
            ax.add_patch(self._rect)
            self._begin_drag("zoom", x, y, ax=ax, start_data=(dx, dy))
            self.canvas.draw_idle()
            return

        if self.mode == "data":
            target = hit if hit[0] == "line" else self._selected_line_hit()
            if target and target[0] == "line":
                self.app.checkpoint("图上编辑：拖动数据点")
                self._begin_drag("data", x, y, line=target[1], ax=target[2],
                                 point=target[3], curve_index=target[4])
            else:
                self._cb("status", "数据点模式：请先选中一条曲线，再点住曲线上的点拖动")
            return

        # ---- 选择模式 ----
        if hit[0] == "text":
            self.app.checkpoint("图上编辑：移动文本")
            self._begin_drag("text", x, y, index=hit[1], ax=ax)
            return
        if hit[0] == "legend":
            self.app.checkpoint("图上编辑：移动图例")
            self._begin_drag("legend", x, y, ax=ax)
            return
        if hit[0] == "line":
            ci = hit[4]
            self.doc.selected_curve = ci
            self._cb("curve_selected", ci)
            self.reapply()
            label = (self.app.config.curves[ci].label
                     if 0 <= ci < len(self.app.config.curves) else str(ci))
            self._cb("status", f"已选中曲线：{label}（右侧「曲线」页可修改样式）")
            return
        if self.doc.selected_curve >= 0:
            self.doc.selected_curve = -1
            self.reapply()

    def _selected_line_hit(self):
        for line, ax, ci in self._lines_cache:
            if ci == self.doc.selected_curve:
                try:
                    xd = line.get_xdata()
                    yd = line.get_ydata()
                    pts = ax.transData.transform(
                        np.column_stack((np.asarray(xd, float), np.asarray(yd, float))))
                    return ("line", line, ax, 0, ci, pts)
                except Exception:             # noqa: BLE001
                    continue
        return None

    def _begin_drag(self, kind, x, y, **kwargs) -> None:
        self._drag = {"type": kind, "start": (x, y), **kwargs}

    # ------------------------------------------------------------------
    def on_motion(self, event) -> None:
        x, y = float(event.x), float(event.y)
        if event.inaxes is not None and event.xdata is not None:
            self._cb("status", f"x = {event.xdata:.5g}　y = {event.ydata:.5g}"
                              f"　·　模式：{MODE_NAMES[self.mode]}")
        d = self._drag
        if not d:
            return
        kind = d["type"]

        if kind in ("text", "legend"):
            ax = d.get("ax") or event.inaxes
            if ax is None:
                return
            fx, fy = self._frac(ax, x, y)
            if kind == "text":
                self.app.graphs.set_text(self.doc.id, d["index"], x=fx, y=fy)
            else:
                self.app.graphs.set_legend_anchor(self.doc.id, (fx, fy))
            self.reapply()
            return

        if kind == "pan":
            ax = d["ax"]
            try:
                inv = ax.transData.inverted()
                x0, y0 = inv.transform(d["start"])
                x1, y1 = inv.transform((x, y))
                dx, dy = x0 - x1, y0 - y1
                lx, ly = d["xlim"], d["ylim"]
                ax.set_xlim(lx[0] + dx, lx[1] + dx)
                ax.set_ylim(ly[0] + dy, ly[1] + dy)
                self.canvas.draw_idle()
            except Exception:                 # noqa: BLE001
                pass
            return

        if kind == "zoom":
            ax = d["ax"]
            if self._rect is None or event.xdata is None:
                return
            sx, sy = d["start_data"]
            self._rect.set_width(float(event.xdata) - sx)
            self._rect.set_height(float(event.ydata) - sy)
            self.canvas.draw_idle()
            return

        if kind == "data":
            if event.ydata is None:
                return
            line = d["line"]
            try:
                yd = np.asarray(line.get_ydata(), dtype=float).copy()
                yd[d["point"]] = float(event.ydata)
                line.set_ydata(yd)
                self.canvas.draw_idle()
            except Exception:                 # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    def on_release(self, event) -> None:
        d = self._drag
        self._drag = None
        if not d:
            return
        kind = d["type"]

        if kind == "zoom":
            ax = d["ax"]
            if self._rect is not None:
                try:
                    self._rect.remove()
                except Exception:             # noqa: BLE001
                    pass
                self._rect = None
            if event.xdata is not None:
                sx, sy = d["start_data"]
                ex, ey = float(event.xdata), float(event.ydata)
                if abs(ex - sx) > 1e-12 and abs(ey - sy) > 1e-12:
                    ax.set_xlim(sorted((sx, ex)))
                    ax.set_ylim(sorted((sy, ey)))
                self.canvas.draw_idle()
            return

        if kind == "data":
            self._commit_data_point(d)
            return

        if kind in ("text", "legend"):
            self.reapply()
            self._cb("status", "图上编辑已更新（可用 Ctrl+Z 撤销）")

    def _commit_data_point(self, d: dict) -> None:
        line, ci = d["line"], d.get("curve_index", -1)
        if ci < 0 or ci >= len(self.app.config.curves):
            return
        c = self.app.config.curves[ci]
        ds = self.app.core.get_dataset(c.dataset_name)
        if ds is None:
            return
        try:
            xd = np.asarray(line.get_xdata(), dtype=float)
            yd = np.asarray(line.get_ydata(), dtype=float)
            j = int(d["point"])
            xv, yv = float(xd[j]), float(yd[j])
            xcol = np.asarray(list(ds.columns.get(c.x_column, [])), dtype=float)
            if xcol.size == 0:
                return
            row = int(np.nanargmin(np.abs(xcol - xv)))
            self.app.core.set_cell(c.dataset_name, c.y_column, row, f"{yv:.10g}")
            self.app.refresh("graph_data_edit")
            self._cb("status", f"已写回 {c.dataset_name}.{c.y_column}[{row + 1}] = {yv:.6g}")
        except Exception as e:                 # noqa: BLE001
            self._cb("status", f"数据点写回失败：{e}")

    # ------------------------------------------------------------------
    # 双击（Qt 钩子，返回 True 表示已处理，不再还原视图）
    # ------------------------------------------------------------------

    def on_qt_double_click(self, qevent) -> bool:
        x, y = self._qt_pos(qevent)
        ax = self._axes_at(x, y)
        if ax is None:
            return False
        hit = self._hit(x, y)
        fx, fy = self._frac(ax, x, y)
        idx = getattr(ax, "_curviva_index", 0) or 0

        if hit[0] == "text":
            i = hit[1]
            old = self.doc.texts[i].get("text", "")
            text, ok = QInputDialog.getText(self.canvas, "编辑文本标注",
                                            "文本内容（留空删除）：", text=old)
            if ok:
                self.app.checkpoint("图上编辑：修改文本")
                if text.strip():
                    self.app.graphs.set_text(self.doc.id, i, text=text)
                else:
                    self.app.graphs.remove_text(self.doc.id, i)
                self.reapply()
            return True

        if hit[0] == "legend":
            self._cb("focus_property", "legend_panel")
            self._cb("status", "已切换到「图例字体」设置页")
            return True

        if hit[0] == "line":
            ci = hit[4]
            self.doc.selected_curve = ci
            self._cb("curve_selected", ci)
            self._cb("focus_property", "curve_panel")
            self.reapply()
            return True

        # 轴附近双击 -> 坐标轴设置
        bbox = ax.get_window_extent()
        if (x - bbox.x0 < 42 or bbox.x1 - x < 42 or
                y - bbox.y0 < 34 or bbox.y1 - y < 34):
            self._cb("focus_property", "axis_panel")
            self._cb("status", "已切换到「坐标轴」设置页")
            return True

        if self.mode == "text":
            self._add_text_dialog(fx, fy, idx)
            return True
        return False                          # 空白双击 -> 还原视图

    # ------------------------------------------------------------------
    # 文本与右键菜单
    # ------------------------------------------------------------------

    def _add_text_dialog(self, fx: float, fy: float, axes: int = 0) -> None:
        text, ok = QInputDialog.getText(self.canvas, "添加文本标注",
                                        "文本内容：", text="文本标注")
        if not ok or not text.strip():
            return
        self.app.checkpoint("图上编辑：添加文本")
        self.app.graphs.add_text(self.doc.id, fx, fy, text.strip(), axes=axes)
        self.reapply()
        self._cb("status", f"已添加文本标注：{text.strip()}")

    def _context_menu(self, event) -> None:
        x, y = float(event.x), float(event.y)
        ax = event.inaxes or self._axes_at(x, y)
        fx, fy = self._frac(ax, x, y) if ax is not None else (0.5, 0.5)
        idx = getattr(ax, "_curviva_index", 0) if ax is not None else 0
        idx = idx or 0
        hit = self._hit(x, y)

        gui = getattr(event, "guiEvent", None)
        pos = (gui.globalPos() if gui is not None and hasattr(gui, "globalPos")
               else self.canvas.mapToGlobal(self.canvas.rect().center()))
        menu = QMenu(self.canvas)
        menu.addAction("在此添加文本标注…",
                       lambda: self._add_text_dialog(fx, fy, idx))
        if hit[0] == "text":
            i = hit[1]
            menu.addAction("编辑该文本…", lambda: self._edit_text(i))
            menu.addAction("删除该文本", lambda: self._delete_text(i))
        menu.addAction("清除全部标注 / 复位图例", self._clear_overlays)
        menu.addSeparator()
        mode_menu = menu.addMenu("编辑工具")
        for key, label, _ in MODES:
            mode_menu.addAction(label, lambda k=key: self.set_mode(k))
        menu.addAction("还原视图", self.canvas.reset_view)
        menu.addSeparator()
        menu.addAction("复制图形到剪贴板", self.copy_to_clipboard)
        menu.addAction("导出此图形…", lambda: self._cb("export", "png"))
        menu.addAction("图形尺寸设置…", lambda: self._cb("size_dialog"))
        menu.addSeparator()
        menu.addAction("曲线属性", lambda: self._cb("focus_property", "curve_panel"))
        menu.addAction("坐标轴设置", lambda: self._cb("focus_property", "axis_panel"))
        menu.addAction("图例字体", lambda: self._cb("focus_property", "legend_panel"))
        menu.exec(pos)

    def _edit_text(self, i: int) -> None:
        if not (0 <= i < len(self.doc.texts)):
            return
        old = self.doc.texts[i].get("text", "")
        text, ok = QInputDialog.getText(self.canvas, "编辑文本标注",
                                        "文本内容：", text=old)
        if ok:
            self.app.checkpoint("图上编辑：修改文本")
            self.app.graphs.set_text(self.doc.id, i, text=text)
            self.reapply()

    def _delete_text(self, i: int) -> None:
        self.app.checkpoint("图上编辑：删除文本")
        self.app.graphs.remove_text(self.doc.id, i)
        self.reapply()

    def _clear_overlays(self) -> None:
        self.app.checkpoint("图上编辑：清除标注")
        self.app.graphs.clear_overlays(self.doc.id)
        self.canvas.reset_view()

    def copy_to_clipboard(self) -> None:
        QGuiApplication.clipboard().setPixmap(self.canvas.grab())
        self._cb("status", "图形已复制到剪贴板（位图）")
