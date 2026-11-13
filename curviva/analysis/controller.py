"""分析域「控制调用文件」。

AnalysisController 是 P2 数据处理能力的唯一入口：列出操作、返回参数
schema、执行分析、把结果落成新数据集、输出日志并请求界面刷新。
"""

import csv

from curviva.analysis import operations


class AnalysisController:
    def __init__(self, app=None):
        self.app = app
        self.last = None

    def operations(self) -> list:
        return operations.operation_menu()

    def schema(self, key: str) -> list:
        return list(operations.get_operation(key).params)

    def description(self, key: str) -> str:
        return operations.get_operation(key).description

    def run(self, key: str, params: dict):
        """执行一个分析操作；结果统一生成数据集，供后续绘图/拟合复用。"""
        self.app.checkpoint(f"数据分析：{key}")
        result = operations.run(self.app.core, key, params)
        if result.dataset and result.columns:
            ds = self.app.core.add_result_dataset(result.name, result.columns)
            result.created_dataset = ds.name
        self.last = result
        self.app.project.log(f"{result.name}｜{result.summary}")
        self.app.refresh("analysis")
        return result

    def export_result(self, result, path: str) -> str:
        """把结果表导出为 UTF-8 CSV。"""
        if result is None:
            raise ValueError("没有可导出的分析结果。")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(result.headers)
            for row in result.rows:
                w.writerow(row)
        return path
