"""内置示例插件：输出数据集概览报告（行数、列数、数值列、均值范围）。"""

NAME = "数据集概览报告"
DESCRIPTION = "在工作台输出窗口列出所有数据集的结构与基础统计"


def run(api):
    names = api.datasets()
    if not names:
        api.log("当前没有数据集。")
        return
    api.log(f"共 {len(names)} 个数据集：")
    for name in names:
        cols = api.columns(name)
        numeric = api.numeric_columns(name)
        rows = len(api.values(name, numeric[0])) if numeric else 0
        means = []
        for col in numeric:
            v = api.values(name, col)
            means.append(f"{col}={float(v.mean()):.4g}")
        api.log(f"  · {name}：{rows} 行 × {len(cols)} 列，数值列 {len(numeric)} 个")
        if means:
            api.log("    均值 " + ", ".join(means[:6]))
