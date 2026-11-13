# Curviva Python 插件示例 03（仅支持 Python）
# 用法：复制本文件到 ~/.curviva/plugins/ ，软件「工作台 → Python 插件」会自动发现。
# 插件必须声明 NAME / DESCRIPTION 与 run(api)。

NAME = "示例：数据表概览"
DESCRIPTION = "列出全部数据集的行列数与数值列，并生成归一化结果表"


def run(api):
    api.log("=== 数据表概览 ===")
    for name in api.datasets():
        cols = api.columns(name)
        numeric = api.numeric_columns(name)
        api.log(name, "：", len(cols), "列，数值列", numeric)
        if numeric:
            api.analyze("normalize", dataset=name,
                        x_column=numeric[0], y_column=numeric[0],
                        mode="minmax")
    api.log("=== 完成 ===")
    api.refresh()
