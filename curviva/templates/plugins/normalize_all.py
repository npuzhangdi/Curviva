"""内置示例插件：把每个数值列归一化到 [0,1]，生成新的数据集。

这是 Curviva 插件的标准写法（仅 Python）：
    NAME / DESCRIPTION 为插件元信息，run(api) 为入口。
"""

NAME = "归一化全部数值列"
DESCRIPTION = "把每个数据集的数值列按最小-最大归一化，并生成可绘图的新数据集"


def run(api):
    count = 0
    for name in api.datasets():
        cols = api.numeric_columns(name)
        if not cols:
            continue
        result = {}
        for col in cols:
            v = api.values(name, col)
            span = float(v.max() - v.min())
            result[col] = (v - float(v.min())) / (span or 1.0)
        api.add_dataset(name + "-归一化", result)
        api.log(f"已归一化 {name}：{len(cols)} 列")
        count += 1
    if count == 0:
        api.log("没有可处理的数据集，请先导入数据。")
    else:
        api.log(f"完成，共生成 {count} 个新数据集。")
    api.refresh()
