"""核心域「控制调用文件」。

CoreController 是「数据 + 绘图引擎」对外的唯一入口。UI、分析、拟合、
脚本等任何模块都不直接 import DataManager / PlotBuilder，统一经由此处调用。
"""

import numpy as np

from curviva.core.data_manager import DataManager, DataSet
from curviva.core.file_readers import DATA_FILE_FILTER, is_excel
from curviva.core.plot_builder import PlotBuilder


class CoreController:
    """数据管理与渲染的统一 API。"""

    def __init__(self, app=None):
        self.app = app
        self.data = DataManager()

    # ------------------------------------------------------------------
    # 导入
    # ------------------------------------------------------------------

    def import_csv(self, path: str) -> DataSet:
        return self.data.import_csv(path)

    def excel_sheets(self, path: str) -> list:
        return self.data.read_excel_sheets(path)

    def import_excel(self, path: str, sheets=None) -> list:
        return self.data.import_excel(path, sheets)

    def import_clipboard(self, text: str) -> DataSet:
        return self.data.import_clipboard(text)

    def load_demo(self) -> None:
        self.data.load_demo_data()

    # --- 统一打开数据文件（Excel / CSV / TXT / DAT / TSV / ASC ...） ---

    @staticmethod
    def data_file_filter() -> str:
        return DATA_FILE_FILTER

    @staticmethod
    def is_excel_file(path: str) -> bool:
        return is_excel(path)

    @staticmethod
    def text_import_spec(path: str, options: dict = None) -> dict:
        """供「文本导入向导」预览：只解析，不入库。"""
        from curviva.core.file_readers import read_text_file
        return read_text_file(path, options or {})

    def open_data_file(self, path: str, options: dict = None,
                       sheets=None, folder: str = None) -> list:
        """打开现有数据文件并自动挂到项目树；返回新建 DataSet 列表。"""
        imported = self.data.import_file(path, options, sheets)
        ws = getattr(self.app, "workspace", None) if self.app else None
        if ws is not None:
            for ds in imported:
                ws.attach_dataset(ds.name, folder)
        return imported

    # ------------------------------------------------------------------
    # 数据集查询与增删
    # ------------------------------------------------------------------

    def datasets(self) -> list:
        return self.data.datasets

    def dataset_names(self) -> list:
        return [d.name for d in self.data.datasets]

    def get_dataset(self, name: str):
        return self.data.get_dataset(name)

    def columns(self, name: str) -> list:
        ds = self.get_dataset(name)
        return list(ds.column_order) if ds else []

    def numeric_columns(self, name: str) -> list:
        ds = self.get_dataset(name)
        return ds.numeric_columns() if ds else []

    def column_values(self, dataset_name: str, column: str) -> np.ndarray:
        ds = self.get_dataset(dataset_name)
        if ds is None or column not in ds.columns:
            raise ValueError(f"未找到数据列「{dataset_name}.{column}」。")
        return np.asarray(ds.columns[column], dtype=float)

    def remove_dataset(self, name: str) -> None:
        self.data.remove_dataset(name)

    def add_dataset(self, ds: DataSet) -> None:
        self.data.add_dataset(ds)

    def add_result_dataset(self, name: str, columns: dict,
                           formulas: dict = None) -> DataSet:
        """由 {列名: 数组} 创建结果数据集（分析/拟合结果统一走此处）。"""
        ds = DataSet(name)
        for col, values in columns.items():
            arr = np.asarray(values)
            if arr.ndim == 0:
                arr = arr.reshape(1)
            if arr.dtype.kind in "fiub":
                ds.add_column(col, arr.astype(float))
            else:
                ds.add_column(col, [str(v) for v in arr.tolist()])
        if formulas:
            ds.formulas = dict(formulas)
        self.data.add_dataset(ds)
        return ds

    # ------------------------------------------------------------------
    # P0 公式列 / 工作簿编辑
    # ------------------------------------------------------------------

    def add_formula_column(self, dataset_name: str, col_name: str, expr: str):
        return self.data.add_formula_column(dataset_name, col_name, expr)

    def remove_formula_column(self, dataset_name: str, col_name: str):
        return self.data.remove_formula_column(dataset_name, col_name)

    def recompute_all(self) -> list:
        return self.data.recompute_all()

    def set_cell(self, dataset_name: str, col_name: str, row: int, text: str) -> bool:
        return self.data.set_cell(dataset_name, col_name, row, text)

    # ------------------------------------------------------------------
    # 工作簿结构编辑（项目资源管理器 / 工作簿编辑器）
    # ------------------------------------------------------------------

    def create_sheet(self, name: str, rows: int = 30, ncols: int = 2) -> DataSet:
        return self.data.create_sheet(name, rows, ncols)

    def rename_dataset(self, old_name: str, new_name: str) -> str:
        return self.data.rename_dataset(old_name, new_name)

    def add_column(self, dataset_name: str, col_name: str, values=None) -> str:
        return self.data.add_column(dataset_name, col_name, values)

    def remove_column(self, dataset_name: str, col_name: str) -> None:
        self.data.remove_column(dataset_name, col_name)

    def rename_column(self, dataset_name: str, old: str, new: str) -> str:
        return self.data.rename_column(dataset_name, old, new)

    def insert_column(self, dataset_name: str, index: int,
                      col_name: str = None) -> str:
        return self.data.insert_column(dataset_name, index, col_name)

    def insert_rows(self, dataset_name: str, start: int, count: int = 1) -> None:
        self.data.insert_rows(dataset_name, start, count)

    def add_rows(self, dataset_name: str, count: int = 1) -> None:
        self.data.add_rows(dataset_name, count)

    def remove_rows(self, dataset_name: str, start: int, count: int = 1) -> None:
        self.data.remove_rows(dataset_name, start, count)

    # ------------------------------------------------------------------
    # Origin 式工作表（列元数据 / 公式 / 选区粘贴）
    # ------------------------------------------------------------------

    def column_meta(self, name: str) -> dict:
        return self.data.column_meta(name)

    def set_column_meta(self, name: str, col: str, **fields) -> None:
        self.data.set_column_meta(name, col, **fields)

    def set_column_designation(self, name: str, col: str, d: str) -> None:
        self.data.set_column_designation(name, col, d)

    def set_column_formula(self, name: str, col: str, expr: str) -> list:
        return self.data.set_column_formula(name, col, expr)

    def paste_block(self, name: str, row: int, col: int, block: list,
                    header_row: bool = False) -> dict:
        return self.data.paste_block(name, row, col, block, header_row)

    def clear_cells(self, name: str, cells: list) -> int:
        return self.data.clear_cells(name, cells)

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    def export_csv(self, dataset_name: str, path: str,
                   include_meta: bool = False) -> None:
        self.data.export_csv(dataset_name, path, include_meta)

    def export_excel(self, path: str) -> None:
        self.data.export_excel(path)

    # ------------------------------------------------------------------
    # 渲染与序列化
    # ------------------------------------------------------------------

    def render(self, figure, config, view_state=None) -> None:
        PlotBuilder.build(figure, config, self.data.datasets, view_state=view_state)

    def to_dict(self) -> list:
        return self.data.to_dict()

    def load_dict(self, items: list) -> None:
        self.data.load_dict(items)

    def clear(self) -> None:
        self.data.clear()
