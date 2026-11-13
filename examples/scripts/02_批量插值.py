# Curviva Python 脚本示例 02：批量插值重采样
# 先导入 examples/data 里的几张表，再运行本脚本；结果会自动成为新数据集。

count = 0
for name in api.datasets():
    cols = api.numeric_columns(name)
    if len(cols) < 2:
        continue
    api.analyze("resample", dataset=name, x_column=cols[0],
                y_column=cols[1], n_points=60, method="linear")
    api.log("已等间距插值：", name, cols[0], "→", cols[1])
    count = count + 1

api.log("共处理", count, "张表格")
api.refresh()
