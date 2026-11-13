"""扩展域「控制调用文件」。

TemplateController 统一对外提供 P3 能力：图形模板、批处理导出、
Python 脚本与插件。界面、菜单、脚本 API 都只通过这里调用。
"""

from curviva.templates import batch, scripting, style_template


SCRIPT_EXAMPLES = [
    ("批量生成曲线", '''# 用第一个数据集的所有数值列批量生成曲线
ds = api.datasets()[0]
cols = api.numeric_columns(ds)
for col in cols[1:]:
    api.add_curve(ds, cols[0], col, label=col)
api.set_title("Python 脚本批量绘图")
api.log("已生成", len(cols) - 1, "条曲线")'''),
    ("分析 + 拟合一条龙", '''ds = api.datasets()[0]
cols = api.numeric_columns(ds)
res = api.analyze("savgol", dataset=ds, x_col=cols[0], y_col=cols[1], window=9)
api.log(res.summary, "->", res.created_dataset)
fit = api.fit(dataset=ds, x_col=cols[0], y_col=cols[1], model_key="linear")
api.log(fit.message)
api.log("参数:", fit.params)'''),
    ("描述统计", '''for ds in api.datasets():
    cols = api.numeric_columns(ds)
    if cols:
        r = api.analyze("describe", dataset=ds, y_col=cols[0], all_columns=True)
        api.log(ds, "->", r.summary)'''),
]


class TemplateController:
    def __init__(self, app=None):
        self.app = app

    # ------------------------------------------------------------------
    # 图形模板
    # ------------------------------------------------------------------

    def templates(self) -> list:
        return style_template.list_templates()

    def template_names(self) -> list:
        return [t["name"] for t in self.templates()]

    def save_template(self, name: str) -> str:
        path = style_template.save_template(name, self.app.config_ctrl.to_dict())
        self.app.project.log(f"保存图形模板：{name}")
        self.app.status(f"已保存模板「{name}」")
        return path

    def apply_template(self, name: str) -> None:
        self.app.checkpoint(f"应用模板：{name}")
        info = style_template.load_template(name)
        if info["builtin"]:
            self.app.config_ctrl.apply_style(name)
        else:
            self.app.config_ctrl.from_dict(info["config"])
        self.app.refresh("template")

    def delete_template(self, name: str) -> bool:
        return style_template.delete_template(name)

    # ------------------------------------------------------------------
    # 批处理
    # ------------------------------------------------------------------

    def batch_export(self, files: list, out_dir: str, fmt: str = "png",
                     dpi: int = 300, x_column: str = "", y_columns: list = None,
                     plot_type: str = "line", title_from_file: bool = True,
                     template_name: str = "", progress=None) -> dict:
        template = self.app.config_ctrl.to_dict()
        if template_name:
            info = style_template.load_template(template_name)
            if not info["builtin"]:
                template = info["config"]
        return batch.batch_export(
            files, template, out_dir, fmt=fmt, dpi=dpi,
            x_column=x_column, y_columns=y_columns, plot_type=plot_type,
            title_from_file=title_from_file, progress=progress)

    # ------------------------------------------------------------------
    # Python 脚本与插件（仅 .py）
    # ------------------------------------------------------------------

    def script_examples(self) -> list:
        return SCRIPT_EXAMPLES

    def run_script(self, code: str) -> tuple:
        self.app.checkpoint("运行 Python 脚本")
        api = scripting.AppScriptAPI(self.app)
        ok, output = scripting.run_script(code, api)
        self.app.project.log(f"Python 脚本：{'成功' if ok else '失败'}｜{output[:120]}")
        self.app.project.set_workspace("script", code)
        self.app.refresh("script")
        return ok, output

    def plugins(self) -> list:
        return scripting.discover_plugins()

    def run_plugin(self, name_or_path: str) -> tuple:
        path = name_or_path
        if not path.endswith(".py"):
            for p in self.plugins():
                if p["name"] == name_or_path:
                    path = p["path"]
                    break
        self.app.checkpoint(f"运行插件：{name_or_path}")
        api = scripting.AppScriptAPI(self.app)
        ok, output = scripting.run_plugin(path, api)
        self.app.project.log(f"插件 {name_or_path}：{'成功' if ok else '失败'}")
        self.app.refresh("plugin")
        return ok, output
