"""examples 域「控制调用文件」。

ExamplesController 是示例资源对外的唯一入口：列出示例、按类型打开示例。
菜单、脚本、插件都只调用它，不直接读 examples 目录。

打开动作通过 AppController / UI 注入的 hook 完成：
    hook("open_sheet", name)   打开工作表窗口并显示该数据集
    hook("load_script", code)  把示例脚本载入工作台脚本编辑器
"""

import os

GROUPS = [
    ("data", "示例数据"),
    ("projects", "示例项目"),
    ("scripts", "Python 示例"),
]

DATA_EXTS = {".csv", ".txt", ".dat", ".tsv", ".asc", ".xy", ".xye",
             ".prn", ".out", ".xlsx", ".xlsm"}
PROJECT_EXTS = {".cvproj"}
SCRIPT_EXTS = {".py"}

DESCRIPTIONS = {
    "01_线性拟合.csv": "30 组带噪声的线性数据，适合演示散点图 + 线性拟合",
    "02_高斯峰.txt": "Tab 分隔双高斯峰，含注释行与 Origin 式 Long Name / Units / Comments 列头",
    "03_多曲线.dat": "空格分隔多列数据，一次导入 3 条曲线并批量生成",
    "04_分组柱状.csv": "文本类别列 + 两组数值，适合分组柱状图",
    "05_GBK中文表头.txt": "GBK 编码、分号分隔的中文表头，验证编码自动识别",
    "06_多表格工作簿.xlsx": "三个工作表的 Excel 工作簿，可点选要导入的表",
    "07_注释与缺失值.txt": "以 ! 开头的注释、空白分隔、缺失值 -- 自动转 NaN",
    "示例项目.cvproj": "含 2 张表、1 个文件夹、2 条曲线与完整样式的项目",
    "01_快速上手.py": "列出数据集与数值列，添加一条曲线并改标题",
    "02_批量插值.py": "遍历全部数据集，对 X/Y 批量执行插值重采样",
    "03_示例插件.py": "可复制到 ~/.curviva/plugins 的 Python 插件模板",
}


class ExamplesController:
    def __init__(self, app=None):
        self.app = app
        self.root = os.path.dirname(os.path.abspath(__file__))

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def dir(self, group: str) -> str:
        return os.path.join(self.root, group)

    def list_examples(self) -> list:
        """返回 [{group, group_label, name, path, kind, description}]。"""
        items = []
        for group, label in GROUPS:
            folder = self.dir(group)
            if not os.path.isdir(folder):
                continue
            for fn in sorted(os.listdir(folder)):
                path = os.path.join(folder, fn)
                if not os.path.isfile(path):
                    continue
                ext = os.path.splitext(fn)[1].lower()
                if ext in DATA_EXTS:
                    kind = "data"
                elif ext in PROJECT_EXTS:
                    kind = "project"
                elif ext in SCRIPT_EXTS:
                    kind = "script"
                else:
                    continue
                items.append({
                    "group": group, "group_label": label, "name": fn,
                    "path": path, "kind": kind,
                    "description": DESCRIPTIONS.get(fn, "示例文件"),
                })
        return items

    def grouped(self) -> dict:
        out = {label: [] for _, label in GROUPS}
        for item in self.list_examples():
            out.setdefault(item["group_label"], []).append(item)
        return out

    def first_data_path(self) -> str:
        for item in self.list_examples():
            if item["kind"] == "data":
                return item["path"]
        return ""

    # ------------------------------------------------------------------
    # 打开
    # ------------------------------------------------------------------

    def open(self, path: str):
        """打开一个示例，返回 (类型, 载荷)。只允许打开本域内的文件。"""
        path = os.path.abspath(str(path))
        if not path.startswith(self.root):
            raise ValueError("只能打开 examples 文件夹内的示例。")
        if not os.path.isfile(path):
            raise ValueError(f"示例文件不存在：{path}")
        ext = os.path.splitext(path)[1].lower()
        app = self.app
        if app is None:
            raise ValueError("示例控制器未绑定应用总控。")

        if ext in PROJECT_EXTS:
            app.project.open(path)
            return "project", path

        if ext in SCRIPT_EXTS:
            with open(path, "r", encoding="utf-8") as f:
                code = f.read()
            app.hook("load_script", code)
            app.refresh("example_script")
            return "script", code

        imported = app.core.open_data_file(path)
        app.refresh("example_data")
        if imported:
            app.hook("open_sheet", imported[0].name)
        return "data", imported
