"""主窗口：菜单、居中画布、停靠面板与信号调度中心。

改造要点（模块化）：
- 所有功能通过 AppController（curviva/controller.py）调度；
- 界面装配通过 UIController（curviva/ui/controller.py）；
- 主窗口本身只负责菜单、快捷键、状态栏与刷新去重。
"""

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMenuBar,
    QMessageBox,
)

from curviva import __version__
from curviva.config.plot_config import DEFAULT_COLORS, CurveConfig
from curviva.project.project_io import PROJECT_FILTER
from curviva.ui.canvas_widget import PlotCanvas, PlotToolbar
from curviva.ui.controller import UIController


class MainWindow(QMainWindow):
    def __init__(self, app, ui: UIController = None):
        super().__init__()
        self.app = app
        self.ui = ui or UIController(app)
        self.panels = self.ui.panels

        self.setWindowTitle(f"Curviva v{__version__}")
        self.resize(1600, 950)
        self.setAcceptDrops(True)          # 直接把数据文件拖进主窗口即可打开

        self._last_structure_sig = ""
        self._polished = False
        self._refreshing = False
        self._checkpoint_pending = False

        self._checkpoint_timer = QTimer(self)
        self._checkpoint_timer.setSingleShot(True)
        self._checkpoint_timer.setInterval(1000)
        self._checkpoint_timer.timeout.connect(
            lambda: setattr(self, "_checkpoint_pending", False))

        # 先装配停靠区与窗口管理器，再建菜单（「窗口管理」菜单需要它）
        self._build_center()
        self.ui.attach(self)
        self._build_menus()

        # 总控回调：状态栏、导出、整体刷新
        self.app.hooks["status"] = lambda text: self.statusBar().showMessage(text, 8000)
        self.app.hooks["export"] = self._export_hook
        self.app.add_listener(self._on_app_changed)

        self._update_structure_signature(force=True)
        self.refresh_all()
        self.statusBar().showMessage(
            "就绪　·　左侧：项目管理（项目 / 文件夹 / 表格 / 图形 / 图片）　·　"
            "中间：可最小化的工作区　·　工具栏随选中对象切换　·　"
            "图形上可用鼠标直接修改")

    # ------------------------------------------------------------------
    @property
    def config(self):
        return self.app.config

    @property
    def data_manager(self):
        return self.app.data_manager

    # ------------------------------------------------------------------
    # 示例数据
    # ------------------------------------------------------------------

    def _load_demo(self) -> None:
        """载入示例数据；若当前没有曲线，则同步创建示例曲线。"""
        self._checkpoint("载入示例数据")
        self.app.core.load_demo()
        if not self.app.config.curves:
            self._create_demo_curves()
        self.app.refresh("demo")

    def _create_demo_curves(self) -> None:
        if not self.app.datasets:
            return
        cfg = self.app.config
        sub = cfg.subplots[0]
        sub.title = "函数曲线示例"
        sub.x_axis.label = "x"
        sub.y_axis.label = "y"
        sub.grid_show = True
        ds = self.app.datasets[0]
        cfg.curves.append(_make_curve(
            "sin(x)", ds, "x", "sin(x)", "line", DEFAULT_COLORS[0], "-", "None"))
        cfg.curves.append(_make_curve(
            "cos(x)", ds, "x", "cos(x)", "line_point", DEFAULT_COLORS[1], "--", "o"))
        cfg.curves.append(_make_curve(
            "衰减振荡", ds, "x", "衰减振荡", "line", DEFAULT_COLORS[2], "-.", "None"))

    # ------------------------------------------------------------------
    # 菜单
    # ------------------------------------------------------------------

    def _build_menus(self) -> None:
        """Origin 标准菜单结构：文件 / 编辑 / 查看 / 插入 / 绘图 / 分析 /
        统计 / 拟合 / 工具 / 窗口 / 帮助。"""
        mb = QMenuBar()
        wa = self.ui.workarea

        # --- 文件 File ---
        m_file = mb.addMenu("文件")
        self._act(m_file, "新建项目", self._on_new_project, "Ctrl+N")
        self._act(m_file, "打开项目 (.cvproj)", self._on_open_project, "Ctrl+O")
        self._act(m_file, "保存项目", lambda: self._on_save_project(False), "Ctrl+S")
        self._act(m_file, "项目另存为…", lambda: self._on_save_project(True))
        m_file.addSeparator()
        imp = m_file.addMenu("导入数据")
        self._act(imp, "打开数据文件（CSV / TXT / Excel）…",
                  lambda: self.open_data_file(False), "Ctrl+Shift+O")
        self._act(imp, "文本导入向导（编码 / 分隔符 / 列头）…",
                  lambda: self.open_data_file(True))
        self._act(imp, "从剪贴板新建工作表", self._paste_new_sheet, "Ctrl+Shift+V")
        self._build_examples_menu(m_file)
        m_file.addSeparator()
        exp = m_file.addMenu("导出图形")
        for label, fmt in (("PNG 图片", "png"), ("SVG 矢量", "svg"),
                           ("PDF 矢量", "pdf"), ("EPS 矢量", "eps")):
            self._act(exp, label, lambda f=fmt: self._export_image(f))
        m_file.addSeparator()
        self._act(m_file, "退出", self.close)

        # --- 编辑 Edit ---
        m_edit = mb.addMenu("编辑")
        self._act(m_edit, "撤销", self._on_undo, "Ctrl+Z")
        self._act(m_edit, "重做", self._on_redo, "Ctrl+Y")
        m_edit.addSeparator()
        style_menu = m_edit.addMenu("应用样式主题")
        for name in self.app.project.styles():
            self._act(style_menu, name, lambda n=name: self.app.project.apply_style(n))

        # --- 查看 View ---
        m_view = mb.addMenu("查看")
        wm = self.ui.window_manager
        for key, title in (("explorer", "项目管理器"), ("properties", "属性窗口")):
            self._act(m_view, f"显示 / 隐藏「{title}」",
                      lambda k=key: wm.toggle_visible(k))
        m_view.addAction(self.ui.toolbar.toggle_action())
        m_view.addSeparator()
        tabs_menu = m_view.addMenu("面板选项卡显示")
        wm.build_tab_menu(tabs_menu)
        self._act(m_view, "刷新全部图形", wa.render_graphs)

        # --- 插入 Insert ---
        m_ins = mb.addMenu("插入")
        self._act(m_ins, "新建文件夹", self.panels.explorer.create_folder_here)
        self._act(m_ins, "新建表格", self.panels.explorer.create_sheet_here)
        self._act(m_ins, "新建图形窗口", lambda: wa.new_graph())
        self._act(m_ins, "新建图片窗口", lambda: wa.new_image())
        self._act(m_ins, "导入图片文件…", lambda: wa.import_image(self))
        self._act(m_ins, "打开多表工作簿", wa.open_book)

        # --- 绘图 Plot（Origin 核心工作流：作用于当前选中表格）---
        m_plot = mb.addMenu("绘图")
        self._act(m_plot, "折线图", lambda: self._plot_active("line"),
                  "把当前工作表的 X/Y 列绘制为折线图")
        self._act(m_plot, "散点图", lambda: self._plot_active("scatter"))
        self._act(m_plot, "点线图", lambda: self._plot_active("line_point"))
        self._act(m_plot, "柱形图", lambda: self._plot_active("bar"))
        m_plot.addSeparator()
        self._act(m_plot, "批量生成曲线（共享 X）", self._batch_active_sheet)
        self._act(m_plot, "曲线属性（双 Y 轴 / 误差棒）",
                  lambda: self.ui.focus_property("curve_panel"))
        m_plot.addSeparator()
        self._act(m_plot, "坐标轴设置", lambda: self.ui.focus_property("axis_panel"))
        self._act(m_plot, "图例字体", lambda: self.ui.focus_property("legend_panel"))
        self._act(m_plot, "边框网格", lambda: self.ui.focus_property("frame_panel"))

        # --- 分析 Analysis ---
        m_ana = mb.addMenu("分析")
        for label, key in (
                ("插值 / 等间距重采样", "resample"),
                ("Savitzky–Golay 平滑", "savgol"), ("移动平均", "moving"),
                ("归一化", "normalize"), ("基线扣除", "baseline"),
                ("数值微分", "derivative"), ("累积积分", "integral"),
                ("FFT 幅度谱", "fft"), ("寻峰 / 峰面积", "find_peaks")):
            self._act(m_ana, label, lambda k=key: wa.active_operation(k))
        m_ana.addSeparator()
        self._act(m_ana, "全部处理操作（数据分析面板）",
                  lambda: self.ui.focus_tool("analysis_panel"))

        # --- 统计 Statistics ---
        m_stat = mb.addMenu("统计")
        self._act(m_stat, "描述统计（当前表格）",
                  lambda: wa.active_operation("describe"))
        self._act(m_stat, "描述统计面板", lambda: self.ui.focus_tool("analysis_panel"))

        # --- 拟合 Fitting ---
        m_fit = mb.addMenu("拟合")
        quick = m_fit.addMenu("快速拟合当前表格")
        for label, key in (("线性", "linear"), ("二次多项式", "poly2"),
                           ("三次多项式", "poly3"), ("指数", "exp"),
                           ("高斯", "gauss"), ("洛伦兹", "lorentz"),
                           ("Sigmoid", "sigmoid")):
            self._act(quick, label, lambda k=key: wa.quick_fit("", k))
        m_fit.addSeparator()
        self._act(m_fit, "公式拟合面板", lambda: self.ui.focus_tool("fitting_panel"))
        self._act(m_fit, "拟合报告 / 结果", lambda: self.ui.focus_tool("fitting_panel"))
        self._act(m_fit, "拟合曲线上图说明", self._show_fit_hint)

        # --- 工具 Tools ---
        m_tools = mb.addMenu("工具")
        self._act(m_tools, "图形模板 / 批处理", self._focus_template)
        self._act(m_tools, "Python 脚本", self._focus_script)
        self._act(m_tools, "Python 插件与日志", self._focus_plugin)

        # --- 窗口 Window ---
        m_window = mb.addMenu("窗口")
        m_window.addAction("层叠排列", wa.area.cascade_all)
        m_window.addAction("平铺排列", wa.area.tile_all)
        m_window.addAction("最小化全部文档", wa.area.minimize_all)
        m_window.addAction("还原全部文档", wa.area.restore_all)
        m_window.addSeparator()
        wa.build_windows_menu(m_window)
        m_window.addSeparator()
        self._act(m_window, "关闭当前文档窗口", lambda: self._close_active_doc())
        self._act(m_window, "关闭全部文档窗口", wa.area.close_all)
        m_window.addSeparator()
        m_window_manage = m_window.addMenu("停靠窗口管理")
        wm.build_menu(m_window_manage)

        # --- 帮助 Help ---
        m_help = mb.addMenu("帮助")
        self._act(m_help, "关于 Curviva", self._show_about)

        # 菜单栏直接置顶，其下只有一行工具栏（在 UIController.attach 中装配）
        self.setMenuBar(mb)

    # ------------------------------------------------------------------
    # 示例文件夹 / 数据文件打开
    # ------------------------------------------------------------------

    def _build_examples_menu(self, menu) -> None:
        ex_menu = menu.addMenu("打开示例")
        try:
            groups = self.app.examples.grouped()
        except Exception:                          # noqa: BLE001
            groups = {}
        for label, items in groups.items():
            if not items:
                continue
            sub = ex_menu.addMenu(label)
            for item in items:
                self._act(sub, item["name"],
                          lambda p=item["path"]: self._open_example(p))
        ex_menu.addSeparator()
        self._act(ex_menu, "浏览 examples 文件夹…", self._browse_examples)

    def _browse_examples(self) -> None:
        path = self.app.examples.root
        try:
            if hasattr(os, "startfile"):
                os.startfile(path)                 # noqa: S606 (Windows 资源管理器)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception as e:                     # noqa: BLE001
            QMessageBox.information(self, "示例文件夹", f"示例目录：{path}\n{e}")

    def _open_example(self, path: str) -> None:
        try:
            kind, payload = self.app.examples.open(path)
        except Exception as e:                     # noqa: BLE001
            QMessageBox.warning(self, "打开示例失败", str(e))
            return
        if kind == "data":
            names = "、".join(d.name for d in payload)
            self.statusBar().showMessage(f"已打开示例数据：{names}", 8000)
        elif kind == "script":
            self.statusBar().showMessage(
                "示例 Python 脚本已载入「工作台 → Python 脚本」，可点运行", 8000)
        else:
            self.statusBar().showMessage(f"已打开示例项目：{payload}", 8000)

    def open_data_file(self, wizard: bool = False) -> list:
        """菜单 / hook 入口：统一的打开数据文件对话框。"""
        from curviva.ui.panels.import_dialog import open_data_file
        return open_data_file(self, self.app, wizard=wizard)

    def _paste_new_sheet(self) -> None:
        if self.ui.worksheet is not None:
            self.ui.worksheet.new_from_clipboard(self)

    # ------------------------------------------------------------------
    # 文件拖放（CSV / TXT / DAT / Excel / .cvproj）
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:            # noqa: N802 (Qt 命名)
        if event.mimeData() is not None and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:                 # noqa: N802 (Qt 命名)
        from curviva.ui.panels.import_dialog import open_data_files
        paths = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.isLocalFile()]
        if not paths:
            return
        projects = [p for p in paths if p.lower().endswith(".cvproj")]
        for path in projects:
            try:
                self.app.project.open(path)
            except Exception as e:                     # noqa: BLE001
                QMessageBox.warning(self, "打开项目失败", str(e))
        others = [p for p in paths if p not in projects]
        from curviva.graphs.controller import GraphController
        images = [p for p in others if GraphController.is_image_file(p)]
        for path in images:
            try:
                self.app.checkpoint("拖放：导入图片")
                self.app.graphs.import_image(path)
            except Exception as e:                 # noqa: BLE001
                QMessageBox.warning(self, "导入图片失败", str(e))
        others = [p for p in others if p not in images]
        if others:
            open_data_files(self, self.app, others)
        event.acceptProposedAction()

    @staticmethod
    def _act(menu, text, slot, shortcut: str = "") -> QAction:
        action = QAction(text, menu)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        menu.addAction(action)
        return action

    def _plot_active(self, plot_type: str) -> None:
        """Origin 核心工作流：把当前选中的表格按指定图型一键绘图。"""
        name = self._active_sheet_name()
        if not name:
            QMessageBox.information(
                self, "绘图", "请先在工作区或项目树中选中一个表格窗口。")
            return
        self.ui.worksheet.add_curve(name, plot_type=plot_type)
        self.ui.workarea.open_graph()

    # ------------------------------------------------------------------
    # 中心画布
    # ------------------------------------------------------------------

    def _build_center(self) -> None:
        """中央是 MDI 工作区：表格 / 图形 / 图片都是可最小化的子窗口。"""
        self.ui.build_center(self)

    @property
    def canvas(self):
        """兼容旧调用：始终返回当前主图形窗口的画布。"""
        return self.ui.primary_canvas()

    # ------------------------------------------------------------------
    # 调度与刷新
    # ------------------------------------------------------------------

    def _checkpoint(self, label: str) -> None:
        """连续操作合并为一个撤销点（1 秒窗口），避免历史栈被控件信号刷爆。"""
        if self._checkpoint_pending:
            return
        self.app.checkpoint(label)
        self._checkpoint_pending = True
        self._checkpoint_timer.start()

    def _make_structure_signature(self) -> str:
        return self.app.config_ctrl.signature(self.app.datasets)

    def _update_structure_signature(self, force: bool = False) -> bool:
        sig = self._make_structure_signature()
        changed = force or sig != self._last_structure_sig
        self._last_structure_sig = sig
        return changed

    def _on_config_changed(self) -> None:
        if self._refreshing:
            return
        self._checkpoint("修改绘图配置")
        if self._update_structure_signature():
            self.panels.refresh_dynamic()
        self.ui.render_graphs()

    def _on_data_changed(self) -> None:
        if self._refreshing:
            return
        self._checkpoint("数据变更")
        self._update_structure_signature(force=True)
        self.panels.rebind()
        self.ui.sync_from_app()

    def _on_app_changed(self, reason: str = "changed") -> None:
        """总控状态被替换（打开项目/撤销/脚本/拟合结果等）后的完整刷新。"""
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self.panels.rebind()
            self._update_structure_signature(force=True)
            self.ui.sync_from_app()
            self.statusBar().showMessage(f"状态已更新（{reason}）", 5000)
        finally:
            self._refreshing = False

    def refresh_all(self) -> None:
        self.panels.refresh_dynamic()
        self.ui.sync_from_app()

    # ------------------------------------------------------------------
    # 菜单动作
    # ------------------------------------------------------------------

    def _on_new_project(self) -> None:
        self.app.project.new()
        self.statusBar().showMessage("已新建空白项目", 6000)

    def _on_open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开 Curviva 项目", "", PROJECT_FILTER)
        if not path:
            return
        try:
            self.app.project.open(path)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))
            return
        self.statusBar().showMessage(f"已打开项目：{path}", 8000)

    def _on_save_project(self, save_as: bool) -> None:
        path = ""
        if save_as or not self.app.project.current_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "保存项目", "untitled.cvproj", PROJECT_FILTER)
            if not path:
                return
        try:
            saved = self.app.project.save(path or None)
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return
        self.statusBar().showMessage(f"已保存项目：{saved}", 8000)

    def _on_undo(self) -> None:
        if not self.app.undo():
            self.statusBar().showMessage("没有可撤销的操作", 4000)

    def _on_redo(self) -> None:
        if not self.app.redo():
            self.statusBar().showMessage("没有可重做的操作", 4000)

    def _quick_analysis(self, key: str) -> None:
        self.ui.focus_tool("analysis_panel")
        combo = self.panels.analysis_panel.op_combo
        i = combo.findData(key)
        if i >= 0:
            combo.setCurrentIndex(i)

    # ------------------------------------------------------------------
    # 工作区文档菜单辅助
    # ------------------------------------------------------------------

    def _close_active_doc(self) -> None:
        sw = self.ui.workarea.area.active()
        if sw is not None:
            sw.close()

    def _active_sheet_name(self) -> str:
        return self.ui.workarea.active_sheet_name()

    def _export_active_csv(self) -> None:
        name = self._active_sheet_name()
        if name:
            self.ui.worksheet.export_csv(name)
        else:
            QMessageBox.information(self, "提示", "请先选中一个表格窗口。")

    def _plot_active_sheet(self) -> None:
        name = self._active_sheet_name()
        if not name:
            QMessageBox.information(self, "提示", "请先选中一个表格窗口。")
            return
        self.ui.worksheet.add_curve(name)
        self.ui.workarea.open_graph()

    def _batch_active_sheet(self) -> None:
        name = self._active_sheet_name()
        if not name:
            QMessageBox.information(self, "提示", "请先选中一个表格窗口。")
            return
        cols = self.app.core.numeric_columns(name)
        if len(cols) < 2:
            QMessageBox.information(self, "提示", "该表格至少需要两列数值数据。")
            return
        self._checkpoint("菜单：批量生成曲线")
        for y in cols[1:]:
            self.ui.worksheet.add_curve(name, y)
        self.ui.workarea.open_graph()

    def _active_graph_do(self, path: str) -> None:
        """'canvas.reset_view' / 'editor.copy_to_clipboard' 这类两级调用。"""
        win = self.ui.workarea.active_graph_window()
        if win is None:
            return
        obj = win
        for part in path.split(".")[:-1]:
            obj = getattr(obj, part, None)
            if obj is None:
                return
        fn = getattr(obj, path.split(".")[-1], None)
        if callable(fn):
            fn()

    def _reset_graph_size(self) -> None:
        win = self.ui.workarea.active_graph_window()
        if win is None:
            return
        self._checkpoint("图形：恢复默认尺寸")
        self.app.graphs.set_size(win.doc_id, 8.0, 6.0, "inch", 300)

    def _clear_graph_overlays(self) -> None:
        win = self.ui.workarea.active_graph_window()
        if win is not None:
            win.editor._clear_overlays()

    def _show_fit_hint(self) -> None:
        QMessageBox.information(
            self, "拟合结果上图",
            "在「曲线拟合」面板选择模型并执行拟合后，可点击：\n"
            "· 拟合曲线上图 —— 生成平滑拟合曲线（可带 95% 置信带）\n"
            "· 残差上图 —— 生成残差散点数据集\n"
            "拟合曲线与残差都是普通数据集 + 曲线，会随 .cvproj 一起保存。")

    def _focus_template(self) -> None:
        self.ui.focus_tool("workflow_panel")
        self.panels.workflow_panel.tabs.setCurrentIndex(0)

    def _focus_script(self) -> None:
        self.ui.focus_tool("workflow_panel")
        self.panels.workflow_panel.tabs.setCurrentIndex(1)

    def _focus_plugin(self) -> None:
        self.ui.focus_tool("workflow_panel")
        self.panels.workflow_panel.tabs.setCurrentIndex(2)

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    def _export_image(self, fmt: str) -> None:
        filters = {
            "png": "PNG 图片 (*.png)", "svg": "SVG 矢量图 (*.svg)",
            "eps": "EPS 矢量图 (*.eps)", "pdf": "PDF 矢量文档 (*.pdf)",
        }
        path, _ = QFileDialog.getSaveFileName(
            self, "导出图片", f"curviva.{fmt}", filters[fmt])
        if not path:
            return
        if self._export_hook(path, fmt):
            win = self.ui.workarea.active_graph_window()
            doc = self.app.graphs.get(win.doc_id) if win is not None else None
            size = doc.display_size() if doc else ""
            self.statusBar().showMessage(f"已导出：{path}　{size}", 8000)
        else:
            QMessageBox.warning(self, "导出失败", "导出图片时出错，请检查路径与格式。")

    def _export_hook(self, path: str, fmt: str = "png") -> bool:
        """供脚本 api.export() / 批处理 / 菜单调用的无对话框导出。

        优先使用当前图形窗口自己的出版尺寸与 DPI；没有图形窗口时回退到
        主画布 + 全局 DPI。
        """
        import os
        if not os.path.splitext(path)[1]:
            path = f"{path}.{fmt}"
        try:
            win = (self.ui.workarea.active_graph_window()
                   if self.ui.workarea is not None else None)
            if win is not None:
                win.export(path, fmt)
                return True
            canvas = self.ui.primary_canvas()
            if canvas is None:
                # 工作区为空：按需打开主图形窗口再导出
                if self.app.graphs.documents():
                    win = self.ui.workarea.ensure_primary()
                    win.export(path, fmt)
                else:
                    return False
            else:
                dpi = max(self.app.config.global_cfg.dpi, 300.0)
                canvas.export_image(path, dpi)
            return True
        except Exception:                        # noqa: BLE001
            return False

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "关于 Curviva",
            f"<b>Curviva v{__version__}</b><br>科研绘图与数据分析工作台"
            "<p>模块化架构：每个功能域一个文件夹，域内有 controller.py 统一调用入口；"
            "顶层 AppController 负责调度。</p>"
            "<p><b>P0</b> 项目 .cvproj / 撤销重做 / 样式主题 / Python 公式列<br>"
            "<b>P1</b> 拟合函数库 / 自定义 Python 表达式 / 权重 / 残差 / 报告<br>"
            "<b>P2</b> 描述统计 / 平滑 / 微积分 / 插值 / 寻峰<br>"
            "<b>P3</b> 图形模板 / 批处理 / 双 Y 轴图层 / Python 脚本与插件</p>"
            "<p><b>左侧项目管理</b>：新建项目、文件夹、表格、图形与图片，"
            "树状归类、导入与粘贴、右键数据处理；"
            "<b>中间工作区</b>：表格 / 图形 / 图片都是可最小化、显示隐藏、"
            "层叠平铺的独立窗口。</p>"
            "<p><b>上下文工具栏</b>随选中对象切换：表格→数据画图 / 拟合 / 数据处理，"
            "图形→鼠标编辑工具 / 尺寸 DPI / 导出，图片→缩放与显示尺寸。</p>"
            "<p><b>Origin 式图上编辑</b>：点选曲线、拖动图例与文本、框选放大、"
            "平移、拖拽数据点写回工作表、双击曲线/轴进入属性设置。"
            "<b>窗口管理</b>菜单可逐个设置停靠窗口与全部工作区文档。</p>"
            "<p><b>Origin 风格工作表</b>：A(X)/B(Y) 列标、长名称/单位/注释/公式行、"
            "Ctrl+C / Ctrl+V 自动扩展行列；可直接打开 CSV / TXT / DAT / XLSX，"
            "或把文件拖进窗口。独立的 <b>examples</b> 文件夹提供示例。</p>"
            "<p>扩展语言<b>仅支持 Python</b>，不提供 LabTalk、Origin C 等其它语言。</p>")

    def showEvent(self, event) -> None:          # noqa: N802 (Qt 命名)
        super().showEvent(event)
        if not self._polished:
            self._polished = True
            QTimer.singleShot(50, lambda: self.ui.polish(self))


def _make_curve(label, ds, x_col, y_col, plot_type, color, linestyle, marker):
    return CurveConfig(
        label=label, dataset_name=ds.name, x_column=x_col, y_column=y_col,
        plot_type=plot_type, color=color, linestyle=linestyle, marker=marker)
