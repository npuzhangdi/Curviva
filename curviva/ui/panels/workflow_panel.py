"""P3「工作台」面板：图形模板、批处理、仅 Python 的脚本与插件、日志。"""

import os

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from curviva.ui.panels.form_utils import fill_combo_with_names


class WorkflowPanel(QWidget):
    """左侧「工作台」选项卡（内部再分三个子页）。"""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.files: list = []
        self.out_dir = ""
        self.tabs = QTabWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.tabs)
        self.tabs.addTab(self._build_template_page(), "模板 / 批处理")
        self.tabs.addTab(self._build_script_page(), "Python 脚本")
        self.tabs.addTab(self._build_plugin_page(), "插件 / 日志")
        self._connect_all()
        self.refresh_from_app()

    # ------------------------------------------------------------------
    def _build_template_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)

        gb = QGroupBox("图形模板（.cvstyle）")
        f = QFormLayout(gb)
        self.template_combo = QComboBox()
        f.addRow("模板", self.template_combo)
        row = QHBoxLayout()
        self.tpl_save_btn = QPushButton("保存当前为模板")
        self.tpl_save_btn.setProperty("accent", True)
        self.tpl_apply_btn = QPushButton("应用")
        self.tpl_apply_btn.setProperty("tone", "green")
        self.tpl_del_btn = QPushButton("删除")
        self.tpl_del_btn.setProperty("tone", "danger")
        for b in (self.tpl_save_btn, self.tpl_apply_btn, self.tpl_del_btn):
            row.addWidget(b)
        f.addRow(row)
        v.addWidget(gb)

        gb2 = QGroupBox("批处理：多文件套用同一配置批量出图")
        f2 = QFormLayout(gb2)
        self.fmt_combo = QComboBox()
        for text, key in (("PNG 位图", "png"), ("SVG 矢量", "svg"),
                          ("PDF 矢量", "pdf"), ("EPS 矢量", "eps")):
            self.fmt_combo.addItem(text, key)
        self.dpi_spin = QLineEdit("300")
        self.x_col_edit = QLineEdit()
        self.x_col_edit.setPlaceholderText("留空 = 自动取第一个数值列")
        self.files_btn = QPushButton("选择数据文件…")
        self.files_btn.setProperty("tone", "cyan")
        self.dir_btn = QPushButton("选择输出目录…")
        self.dir_btn.setProperty("tone", "cyan")
        self.files_label = QLabel("未选择文件")
        self.files_label.setObjectName("hintCard")
        self.files_label.setWordWrap(True)
        self.dir_label = QLabel("未选择输出目录")
        self.dir_label.setObjectName("hintCard")
        self.dir_label.setWordWrap(True)
        self.batch_btn = QPushButton("开始批量导出")
        self.batch_btn.setProperty("accent", True)
        f2.addRow("输出格式", self.fmt_combo)
        f2.addRow("导出 DPI", self.dpi_spin)
        f2.addRow("共享 X 列", self.x_col_edit)
        f2.addRow(self.files_btn)
        f2.addRow(self.files_label)
        f2.addRow(self.dir_btn)
        f2.addRow(self.dir_label)
        f2.addRow(self.batch_btn)
        v.addWidget(gb2)
        self.batch_status = QLabel("支持 CSV / XLSX；每个工作表生成一张图。")
        self.batch_status.setObjectName("hintCard")
        self.batch_status.setWordWrap(True)
        v.addWidget(self.batch_status)
        v.addStretch(1)
        return page

    def _build_script_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        tip = QLabel("扩展语言仅支持 Python。通过 api 操作数据、曲线、分析、拟合与导出；"
                     "禁止导入 os/sys/subprocess 等模块。")
        tip.setObjectName("hintCard")
        tip.setWordWrap(True)
        v.addWidget(tip)

        row = QHBoxLayout()
        self.example_combo = QComboBox()
        for name, _ in self.app.templates.script_examples():
            self.example_combo.addItem(name, name)
        self.insert_example_btn = QPushButton("插入示例")
        self.insert_example_btn.setProperty("tone", "violet")
        self.run_script_btn = QPushButton("▶ 运行脚本")
        self.run_script_btn.setProperty("accent", True)
        self.clear_script_btn = QPushButton("清空输出")
        row.addWidget(self.example_combo, 1)
        row.addWidget(self.insert_example_btn)
        row.addWidget(self.run_script_btn)
        row.addWidget(self.clear_script_btn)
        v.addLayout(row)

        self.script_edit = QPlainTextEdit()
        self.script_edit.setPlaceholderText("# 在这里写 Python 脚本，例如：\n"
                                            "api.log('数据集', api.datasets())")
        self.script_edit.setMinimumHeight(180)
        v.addWidget(self.script_edit, 3)
        out_label = QLabel("输出")
        v.addWidget(out_label)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText("脚本输出 / 错误信息显示在这里")
        self.output_edit.setMinimumHeight(140)
        v.addWidget(self.output_edit, 2)
        return page

    def _build_plugin_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        gb = QGroupBox("Python 插件（仅 .py）")
        f = QFormLayout(gb)
        self.plugin_combo = QComboBox()
        self.plugin_desc = QLabel("插件目录：curviva/templates/plugins 与 ~/.curviva/plugins")
        self.plugin_desc.setObjectName("hintCard")
        self.plugin_desc.setWordWrap(True)
        self.plugin_run_btn = QPushButton("运行插件")
        self.plugin_run_btn.setProperty("accent", True)
        f.addRow("插件", self.plugin_combo)
        f.addRow(self.plugin_desc)
        f.addRow(self.plugin_run_btn)
        v.addWidget(gb)

        gb2 = QGroupBox("操作日志（随项目保存）")
        v2 = QVBoxLayout(gb2)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(200)
        v2.addWidget(self.log_edit)
        row = QHBoxLayout()
        self.log_refresh_btn = QPushButton("刷新日志")
        self.log_clear_btn = QPushButton("清空日志")
        self.log_clear_btn.setProperty("tone", "danger")
        row.addWidget(self.log_refresh_btn)
        row.addWidget(self.log_clear_btn)
        v2.addLayout(row)
        v.addWidget(gb2, 1)
        return page

    # ------------------------------------------------------------------
    def _connect_all(self) -> None:
        self.tpl_save_btn.clicked.connect(self._on_tpl_save)
        self.tpl_apply_btn.clicked.connect(self._on_tpl_apply)
        self.tpl_del_btn.clicked.connect(self._on_tpl_delete)
        self.files_btn.clicked.connect(self._on_pick_files)
        self.dir_btn.clicked.connect(self._on_pick_dir)
        self.batch_btn.clicked.connect(self._on_batch)
        self.insert_example_btn.clicked.connect(self._on_insert_example)
        self.run_script_btn.clicked.connect(self._on_run_script)
        self.clear_script_btn.clicked.connect(self.output_edit.clear)
        self.plugin_combo.currentIndexChanged.connect(self._on_plugin_changed)
        self.plugin_run_btn.clicked.connect(self._on_run_plugin)
        self.log_refresh_btn.clicked.connect(self._refresh_log)
        self.log_clear_btn.clicked.connect(self._on_clear_log)

    # ------------------------------------------------------------------
    def refresh_from_app(self) -> None:
        fill_combo_with_names(self.template_combo,
                              self.app.templates.template_names())
        self.plugins = self.app.templates.plugins()
        self.plugin_combo.blockSignals(True)
        self.plugin_combo.clear()
        for p in self.plugins:
            self.plugin_combo.addItem(p["name"], p["path"])
        self.plugin_combo.blockSignals(False)
        self._on_plugin_changed()
        self._refresh_log()
        script = self.app.project.workspace.get("script", "")
        if script and not self.script_edit.toPlainText().strip():
            self.script_edit.setPlainText(script)

    def _output(self, text: str) -> None:
        self.output_edit.setPlainText(text or "（无输出）")
        self._refresh_log()

    def _refresh_log(self) -> None:
        logs = self.app.project.workspace.get("analysis_log", [])
        self.log_edit.setPlainText("\n".join(logs[-200:]))

    def _on_clear_log(self) -> None:
        self.app.project.set_workspace("analysis_log", [])
        self._refresh_log()

    # ------------------------------------------------------------------
    def _on_tpl_save(self) -> None:
        name, ok = QInputDialog.getText(self, "保存图形模板", "模板名称：")
        if not ok or not name.strip():
            return
        try:
            self.app.templates.save_template(name.strip())
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return
        self.refresh_from_app()

    def _on_tpl_apply(self) -> None:
        name = self.template_combo.currentData()
        if not name:
            return
        try:
            self.app.templates.apply_template(name)
        except Exception as e:
            QMessageBox.warning(self, "应用失败", str(e))
            return
        self.app.status(f"已应用模板：{name}")

    def _on_tpl_delete(self) -> None:
        name = self.template_combo.currentData()
        if not name:
            return
        if not self.app.templates.delete_template(name):
            QMessageBox.information(self, "提示", "内置样式主题不可删除。")
            return
        self.refresh_from_app()

    # ------------------------------------------------------------------
    def _on_pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择待批处理的数据文件", "",
            "数据文件 (*.csv *.xlsx *.xlsm);;所有文件 (*.*)")
        if not paths:
            return
        self.files = paths
        self.files_label.setText(f"已选择 {len(paths)} 个文件：" +
                                 "、".join(os.path.basename(p) for p in paths[:3]) +
                                 ("…" if len(paths) > 3 else ""))

    def _on_pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not path:
            return
        self.out_dir = path
        self.dir_label.setText(path)

    def _on_batch(self) -> None:
        if not self.files or not self.out_dir:
            QMessageBox.information(self, "提示", "请先选择数据文件与输出目录。")
            return
        try:
            dpi = int(float(self.dpi_spin.text() or 300))
        except ValueError:
            dpi = 300

        def progress(i, total, msg):
            self.batch_status.setText(f"[{i}/{total}] {msg}")
            QApplication.processEvents()

        try:
            result = self.app.templates.batch_export(
                self.files, self.out_dir, fmt=self.fmt_combo.currentData(),
                dpi=dpi, x_column=self.x_col_edit.text().strip(),
                progress=progress)
        except Exception as e:
            QMessageBox.warning(self, "批处理失败", str(e))
            return
        self.batch_status.setText(
            f"完成：成功 {result['ok']} 张，失败 {result['failed']} 项，输出目录 {self.out_dir}")
        self._refresh_log()
        QMessageBox.information(self, "批处理完成",
                                f"成功导出 {result['ok']} 张图，失败 {result['failed']} 项。")

    # ------------------------------------------------------------------
    def _on_insert_example(self) -> None:
        name = self.example_combo.currentData()
        for n, code in self.app.templates.script_examples():
            if n == name:
                self.script_edit.setPlainText(code)
                break

    def _on_run_script(self) -> None:
        code = self.script_edit.toPlainText()
        ok, output = self.app.templates.run_script(code)
        self._output(("✅ " if ok else "❌ ") + (output or "脚本执行完毕"))

    # ------------------------------------------------------------------
    def _on_plugin_changed(self) -> None:
        path = self.plugin_combo.currentData()
        desc = ""
        for p in self.plugins:
            if p["path"] == path:
                desc = p["description"] + (f"（加载错误：{p['error']}）" if p["error"] else "")
                break
        self.plugin_desc.setText(desc or "插件目录：curviva/templates/plugins 与 ~/.curviva/plugins")

    def _on_run_plugin(self) -> None:
        path = self.plugin_combo.currentData()
        if not path:
            QMessageBox.information(self, "提示", "没有可用插件。")
            return
        ok, output = self.app.templates.run_plugin(path)
        self._output(("✅ " if ok else "❌ ") + output)
