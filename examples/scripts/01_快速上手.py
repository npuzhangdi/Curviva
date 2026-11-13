# Curviva Python 脚本示例 01：快速上手
# 菜单「文件 → 打开示例 → Python 示例 → 01_快速上手.py」会自动载入脚本编辑器。
# 扩展语言仅支持 Python；脚本通过 api 门面操作软件。

names = api.datasets()
api.log("当前数据集：", names)
api.log("项目树：", api.workspace_outline())

for name in names:
    cols = api.numeric_columns(name)
    api.log(name, "的数值列：", cols)
    if len(cols) >= 2:
        api.add_curve(name, cols[0], cols[1], label=name + " 曲线")

api.set_title("Curviva 脚本示例")
api.set_labels(x="x", y="y")
api.refresh()
