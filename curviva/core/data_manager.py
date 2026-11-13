"""数据管理模块。

负责：CSV / Excel 导入、剪贴板粘贴导入、内置示例数据、数据集统一存储。
列数据约定：数值列存为 numpy.ndarray(float)，文本列存为 list[str]。
"""

import csv
import os

import numpy as np


def _can_float(text) -> bool:
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False


class DataSet:
    """一个数据集：若干命名列，列内元素等长。"""

    def __init__(self, name: str, file_path: str = ""):
        self.name = name
        self.file_path = file_path
        self.columns: dict = {}        # 列名 -> ndarray 或 list[str]
        self.column_order: list = []   # 保持列的显示顺序
        self.formulas: dict = {}       # 列名 -> Python 表达式（P0 公式列，自动重算）
        # Origin 式列元数据：长名称 / 单位 / 注释 / 公式提示 / 列类型(X/Y/yEr/L/D)
        self.column_meta: dict = {}

    def _default_meta(self, name: str, values, is_first: bool = False) -> dict:
        numeric = isinstance(values, np.ndarray)
        if is_first:
            designation = "X"
        elif any(k in name.lower() for k in ("err", "error", "误差", "sd", "std")):
            designation = "yEr"
        elif numeric:
            designation = "Y"
        else:
            designation = "L"
        return {"long_name": name, "unit": "", "comment": "",
                "formula": "", "designation": designation}

    def add_column(self, name: str, values, replace: bool = False) -> str:
        """新增一列；replace=True 时覆盖同名列（公式列重算使用）。"""
        if name in self.columns:
            if replace:
                self.columns[name] = values
                return name
            i = 2
            while f"{name}_{i}" in self.columns:
                i += 1
            name = f"{name}_{i}"
        is_first = not self.column_order
        self.columns[name] = values
        self.column_order.append(name)
        self.column_meta.setdefault(name, self._default_meta(name, values, is_first))
        return name

    def meta(self, col: str) -> dict:
        base = {"long_name": "", "unit": "", "comment": "",
                "formula": "", "designation": ""}
        base.update(self.column_meta.get(col, {}))
        if not base["long_name"]:
            base["long_name"] = col
        if not base["designation"]:
            base["designation"] = "Y" if isinstance(self.columns.get(col), np.ndarray) else "L"
        return base

    def set_meta(self, col: str, **fields) -> None:
        m = self.meta(col)
        for key in ("long_name", "unit", "comment", "formula", "designation"):
            if key in fields:
                m[key] = str(fields[key])
        self.column_meta[col] = m

    def numeric_columns(self) -> list:
        return [c for c in self.column_order if isinstance(self.columns[c], np.ndarray)]

    def row_count(self) -> int:
        if not self.column_order:
            return 0
        return len(self.columns[self.column_order[0]])

    # ------------------------------------------------------------------
    # P0 公式列（仅 Python 表达式）
    # ------------------------------------------------------------------

    def recompute_formulas(self) -> list:
        """按列顺序重算全部公式列；返回失败信息列表。"""
        from curviva.core.formula_engine import evaluate_dataset_expression
        errors = []
        for name in self.column_order:
            expr = self.formulas.get(name)
            if not expr:
                continue
            try:
                self.columns[name] = evaluate_dataset_expression(expr, self)
            except Exception as e:                     # noqa: BLE001 - 用户表达式需友好报错
                errors.append(f"「{name}」：{e}")
        return errors

    # ------------------------------------------------------------------
    # 序列化（项目文件 / 撤销重做）
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        cols = {}
        for name in self.column_order:
            v = self.columns[name]
            if isinstance(v, np.ndarray):
                cols[name] = {"kind": "num", "values": [float(t) for t in v.tolist()]}
            else:
                cols[name] = {"kind": "text", "values": [str(t) for t in list(v)]}
        return {
            "name": self.name,
            "file_path": self.file_path,
            "column_order": list(self.column_order),
            "columns": cols,
            "formulas": dict(self.formulas),
            "column_meta": {c: dict(self.meta(c)) for c in self.column_order},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DataSet":
        ds = cls(data.get("name", "数据集"), data.get("file_path", ""))
        for name in data.get("column_order", []):
            item = data.get("columns", {}).get(name)
            if not item:
                continue
            values = (np.asarray(item.get("values", []), dtype=float)
                      if item.get("kind") == "num"
                      else list(item.get("values", [])))
            ds.add_column(name, values)
        ds.formulas = dict(data.get("formulas", {}))
        for col, m in (data.get("column_meta") or {}).items():
            if col in ds.columns:
                ds.column_meta[col] = dict(ds.meta(col), **m)
        return ds


class DataManager:
    """管理全部数据集，供曲线引用。"""

    def __init__(self):
        self.datasets: list = []       # DataSet 列表

    # ------------------------------------------------------------------
    # 数据集增删
    # ------------------------------------------------------------------

    def add_dataset(self, ds: DataSet) -> None:
        # 重名时自动编号
        names = {d.name for d in self.datasets}
        if ds.name in names:
            i = 2
            while f"{ds.name} ({i})" in names:
                i += 1
            ds.name = f"{ds.name} ({i})"
        self.datasets.append(ds)

    def remove_dataset(self, name: str) -> None:
        self.datasets = [d for d in self.datasets if d.name != name]

    def get_dataset(self, name: str):
        for d in self.datasets:
            if d.name == name:
                return d
        return None

    # ------------------------------------------------------------------
    # 公共解析：表头判断 + 列构建（CSV / Excel / 剪贴板共用）
    # ------------------------------------------------------------------

    @staticmethod
    def _split_header(rows: list, ncols: int):
        """判断首行是否为表头（任一单元格可转数字则视为无表头）。

        返回 (header列表, data_rows, has_header)。
        """
        first = rows[0]
        has_header = not any(_can_float(c) for c in first)
        if has_header:
            header = [(str(first[i]) if i < len(first) and str(first[i]).strip() != ""
                       else f"列{i + 1}") for i in range(ncols)]
            data_rows = rows[1:]
        else:
            header = [f"列{i + 1}" for i in range(ncols)]
            data_rows = rows
        return header, data_rows, has_header

    def _build_dataset(self, name: str, header: list, data_rows: list,
                       file_path: str = "") -> DataSet:
        """由表头与数据行构建 DataSet（自动数值化）。"""
        ds = DataSet(name=name, file_path=file_path)
        ncols = len(header)
        for i, col_name in enumerate(header):
            raw = [(r[i] if i < len(r) else "") for r in data_rows]
            try:
                values = np.array([float(v) for v in raw], dtype=float)
            except (TypeError, ValueError):
                values = [str(v) for v in raw]
            ds.add_column(col_name, values)
        if not ds.column_order:
            raise ValueError("未解析到有效数据列。")
        return ds

    def _import_table_rows(self, rows: list, name: str, file_path: str = "") -> DataSet:
        """从二维文本表构建数据集（表头自动识别）并入库。"""
        ncols = max(len(r) for r in rows)
        header, data_rows, _ = self._split_header(rows, ncols)
        ds = self._build_dataset(name, header, data_rows, file_path)
        self.add_dataset(ds)
        return ds

    # ------------------------------------------------------------------
    # 统一数据文件打开（CSV / TXT / DAT / TSV / ASC / Excel）
    # ------------------------------------------------------------------

    MISSING = {"", "--", "-", "na", "n/a", "nan", "none", "null"}

    @classmethod
    def _coerce_column(cls, raw: list):
        """把一列文本尽量转成数值；缺失值用 NaN，含文本则整列保持文本。"""
        texts = [("" if v is None else str(v).strip()) for v in raw]
        missing = cls.MISSING
        filled = [t for t in texts if t.lower() not in missing]
        if filled and all(_can_float(t) for t in filled):
            return np.array([np.nan if t.lower() in missing else float(t)
                             for t in texts], dtype=float)
        return texts

    def _dataset_from_spec(self, spec: dict, path: str = "") -> DataSet:
        ds = DataSet(name=spec["name"], file_path=path or spec.get("path", ""))
        for i, col in enumerate(spec["header"]):
            raw = [(r[i] if i < len(r) else "") for r in spec["rows"]]
            final = ds.add_column(col, self._coerce_column(raw))
            fields = {k: v for k, v in (spec.get("meta", {}).get(col) or {}).items()
                      if k in ("long_name", "unit", "comment", "formula",
                               "designation") and str(v).strip()}
            if fields:
                ds.set_meta(final, **fields)
        if not ds.column_order:
            raise ValueError("未解析到有效数据列。")
        return ds

    def import_file(self, path: str, options: dict = None,
                    sheet_names=None) -> list:
        """打开任意支持格式的数据文件；Excel 每个工作表生成一个 DataSet。"""
        from curviva.core.file_readers import read_any
        specs = read_any(path, options or {}, sheet_names)
        imported = []
        for spec in specs:
            try:
                ds = self._dataset_from_spec(spec, path)
            except ValueError:
                continue
            self.add_dataset(ds)
            imported.append(ds)
        if not imported:
            raise ValueError("文件中未找到可导入的数据。")
        return imported

    # ------------------------------------------------------------------
    # CSV 导入（走统一管线，兼容中文 GBK 编码与多分隔符）
    # ------------------------------------------------------------------

    def import_csv(self, path: str) -> DataSet:
        """导入 CSV / 文本数据；表头、分隔符、编码、元数据行自动识别。"""
        return self.import_file(path)[0]

    # ------------------------------------------------------------------
    # Excel 导入（多工作表）
    # ------------------------------------------------------------------

    def read_excel_sheets(self, path: str) -> list:
        """读取工作簿的全部工作表名（不导入数据，供选择对话框展示）。"""
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        names = list(wb.sheetnames)
        wb.close()
        return names

    def import_excel(self, path: str, sheet_names=None) -> list:
        """导入 Excel 工作簿的一个或多个工作表，每个工作表生成一个数据集。

        sheet_names 为空时导入全部工作表。返回导入的 DataSet 列表。
        说明：v0.0.0 基于 openpyxl，支持 .xlsx / .xlsm，暂不支持旧版 .xls。
        """
        return self.import_file(path, sheet_names=sheet_names)

    # ------------------------------------------------------------------
    # 剪贴板粘贴导入
    # ------------------------------------------------------------------

    def import_clipboard(self, text: str) -> DataSet:
        """从剪贴板文本（TSV / CSV）直接创建数据集，无需文件。"""
        lines = [l for l in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                 if l.strip() != ""]
        if not lines:
            raise ValueError("剪贴板中没有可用数据。")
        first = lines[0]
        if "\t" in first:
            delim = "\t"
        elif ";" in first and "," not in first:
            delim = ";"
        else:
            delim = ","
        rows = [r for r in csv.reader(lines, delimiter=delim) if r]
        names = {d.name for d in self.datasets}
        base = "粘贴数据"
        name = base
        i = 2
        while name in names:
            name = f"{base} {i}"
            i += 1
        return self._import_table_rows(rows, name=name)

    # ------------------------------------------------------------------
    # 内置示例数据
    # ------------------------------------------------------------------

    def load_demo_data(self) -> None:
        """载入三组内置示例数据，便于开箱即用。"""
        # 1) 函数曲线
        ds1 = DataSet(name="示例-函数曲线")
        x = np.linspace(0, 4 * np.pi, 200)
        ds1.add_column("x", x)
        ds1.add_column("sin(x)", np.sin(x))
        ds1.add_column("cos(x)", np.cos(x))
        ds1.add_column("衰减振荡", np.sin(x) * np.exp(-x / 8))
        self.add_dataset(ds1)

        # 2) 散点数据
        rng = np.random.default_rng(42)
        ds2 = DataSet(name="示例-散点数据")
        xs = np.sort(rng.uniform(0, 10, 40))
        ds2.add_column("x", xs)
        ds2.add_column("y", 2.0 * xs + 1.0 + rng.normal(0, 1.2, xs.size))
        self.add_dataset(ds2)

        # 3) 柱状数据（文本类别列）
        ds3 = DataSet(name="示例-柱状数据")
        ds3.add_column("类别", ["A", "B", "C", "D", "E"])
        ds3.add_column("数值", np.array([23.0, 45.0, 12.0, 36.0, 29.0]))
        self.add_dataset(ds3)

    # ------------------------------------------------------------------
    # P0 公式列 / 工作簿
    # ------------------------------------------------------------------

    def add_formula_column(self, dataset_name: str, col_name: str,
                           expr: str) -> tuple:
        """新增（或更新）公式列并立即重算。返回 (DataSet, 错误列表)。"""
        from curviva.core.formula_engine import evaluate_dataset_expression
        ds = self.get_dataset(dataset_name)
        if ds is None:
            raise ValueError(f"未找到数据集「{dataset_name}」。")
        col_name = (col_name or "").strip()
        if not col_name:
            raise ValueError("请填写新列名称。")
        values = evaluate_dataset_expression(expr, ds)   # 先验证表达式
        ds.add_column(col_name, values, replace=True)
        ds.formulas[col_name] = expr
        errors = ds.recompute_formulas()
        return ds, errors

    def remove_formula_column(self, dataset_name: str, col_name: str) -> None:
        ds = self.get_dataset(dataset_name)
        if ds is None or col_name not in ds.columns:
            return
        del ds.columns[col_name]
        ds.column_order.remove(col_name)
        ds.formulas.pop(col_name, None)

    def recompute_all(self) -> list:
        errors = []
        for ds in self.datasets:
            errors.extend(f"[{ds.name}] {m}" for m in ds.recompute_formulas())
        return errors

    def set_cell(self, dataset_name: str, col_name: str, row: int, text: str) -> bool:
        """编辑工作簿单元格；数值列写入失败时保持文本化。返回是否成功。"""
        ds = self.get_dataset(dataset_name)
        if ds is None or col_name not in ds.columns or not (0 <= row < ds.row_count()):
            return False
        col = ds.columns[col_name]
        if isinstance(col, np.ndarray):
            try:
                col[row] = float(text)
                ds.recompute_formulas()
                return True
            except (TypeError, ValueError):
                converted = [str(v) for v in col.tolist()]
                converted[row] = text
                ds.columns[col_name] = converted
                return True
        col[row] = text
        return True

    # ------------------------------------------------------------------
    # 工作簿结构编辑（项目树「新建表格」与工作簿编辑器共用）
    # ------------------------------------------------------------------

    def create_sheet(self, name: str, rows: int = 30, ncols: int = 2) -> DataSet:
        """新建一张空白表格：X + Y/Y2/… 列，自动避让重名。"""
        rows = max(1, min(int(rows), 100000))
        ncols = max(1, min(int(ncols), 50))
        ds = DataSet(name=name or "新建表格")
        ds.add_column("X", np.arange(rows, dtype=float))
        for i in range(1, ncols):
            col = "Y" if i == 1 else f"Y{i}"
            ds.add_column(col, np.zeros(rows, dtype=float))
        self.add_dataset(ds)
        return ds

    def rename_dataset(self, old_name: str, new_name: str) -> str:
        """重命名数据集并返回最终名称（自动避让重名）。"""
        ds = self.get_dataset(old_name)
        if ds is None:
            raise ValueError(f"未找到数据集「{old_name}」。")
        new_name = (new_name or "").strip() or old_name
        used = {d.name for d in self.datasets if d is not ds}
        final = new_name
        i = 2
        while final in used:
            final = f"{new_name} ({i})"
            i += 1
        ds.name = final
        return final

    def add_column(self, dataset_name: str, col_name: str, values=None) -> str:
        ds = self.get_dataset(dataset_name)
        if ds is None:
            raise ValueError(f"未找到数据集「{dataset_name}」。")
        col_name = (col_name or "").strip()
        if not col_name:
            raise ValueError("请填写列名。")
        n = ds.row_count()
        if values is None:
            values = np.zeros(max(n, 1), dtype=float)
        elif np.isscalar(values):
            values = np.full(max(n, 1), float(values), dtype=float)
        else:
            values = np.asarray(values)
            if values.ndim == 0:
                values = np.full(max(n, 1), float(values), dtype=float)
            elif values.size != n:
                raise ValueError(f"新列长度 {values.size} 与表格行数 {n} 不一致。")
        return ds.add_column(col_name, values)

    def remove_column(self, dataset_name: str, col_name: str) -> None:
        ds = self.get_dataset(dataset_name)
        if ds is None or col_name not in ds.columns:
            return
        if len(ds.column_order) <= 1:
            raise ValueError("表格至少需要保留一列。")
        del ds.columns[col_name]
        ds.column_order.remove(col_name)
        ds.column_meta.pop(col_name, None)
        ds.formulas.pop(col_name, None)

    def rename_column(self, dataset_name: str, old: str, new: str) -> str:
        ds = self.get_dataset(dataset_name)
        if ds is None or old not in ds.columns:
            raise ValueError("未找到该数据列。")
        new = (new or "").strip()
        if not new:
            raise ValueError("列名不能为空。")
        if new == old:
            return old
        used = set(ds.column_order) - {old}
        final = new
        i = 2
        while final in used:
            final = f"{new}_{i}"
            i += 1
        ds.columns[final] = ds.columns.pop(old)
        ds.column_order[ds.column_order.index(old)] = final
        if old in ds.column_meta:
            ds.column_meta[final] = ds.column_meta.pop(old)
        if old in ds.formulas:
            ds.formulas[final] = ds.formulas.pop(old)
        return final

    def insert_column(self, dataset_name: str, index: int,
                      col_name: str = None) -> str:
        """在指定位置插入一列（工作表「左侧插入列」）。"""
        ds = self.get_dataset(dataset_name)
        if ds is None:
            raise ValueError(f"未找到数据集「{dataset_name}」。")
        name = (col_name or "").strip() or f"列{len(ds.column_order) + 1}"
        final = self.add_column(dataset_name, name)
        ds.column_order.remove(final)
        ds.column_order.insert(max(0, min(int(index), len(ds.column_order))), final)
        ds.set_meta(final, designation="Y" if ds.column_order[0] != final else "X")
        return final

    def insert_rows(self, dataset_name: str, start: int, count: int = 1) -> None:
        """在指定位置插入若干空行（工作表「在上方插入行」）。"""
        ds = self.get_dataset(dataset_name)
        if ds is None:
            return
        n = ds.row_count()
        start = max(0, min(int(start), n))
        count = max(1, min(int(count), 100000))
        for col in ds.column_order:
            v = ds.columns[col]
            if isinstance(v, np.ndarray):
                ds.columns[col] = np.insert(v, start, np.zeros(count, dtype=float))
            else:
                rest = list(v)
                rest[start:start] = [""] * count
                ds.columns[col] = rest
        ds.recompute_formulas()

    def add_rows(self, dataset_name: str, count: int = 1) -> None:
        ds = self.get_dataset(dataset_name)
        if ds is None:
            return
        count = max(1, min(int(count), 100000))
        for col in ds.column_order:
            v = ds.columns[col]
            if isinstance(v, np.ndarray):
                ds.columns[col] = np.concatenate([v, np.zeros(count, dtype=float)])
            else:
                ds.columns[col] = list(v) + [""] * count

    def remove_rows(self, dataset_name: str, start: int, count: int = 1) -> None:
        ds = self.get_dataset(dataset_name)
        if ds is None:
            return
        n = ds.row_count()
        start = max(0, min(int(start), n))
        count = max(1, min(int(count), n - start))
        if count <= 0:
            return
        for col in ds.column_order:
            v = ds.columns[col]
            if isinstance(v, np.ndarray):
                ds.columns[col] = np.delete(v, np.s_[start:start + count])
            else:
                rest = list(v)
                del rest[start:start + count]
                ds.columns[col] = rest
        ds.recompute_formulas()

    # ------------------------------------------------------------------
    # Origin 式工作表层：列元数据 / 公式 / 选区粘贴
    # ------------------------------------------------------------------

    def column_meta(self, name: str) -> dict:
        ds = self.get_dataset(name)
        return {c: ds.meta(c) for c in ds.column_order} if ds else {}

    def set_column_meta(self, name: str, col: str, **fields) -> None:
        ds = self.get_dataset(name)
        if ds is None or col not in ds.columns:
            raise ValueError("未找到该数据列。")
        ds.set_meta(col, **fields)

    def set_column_designation(self, name: str, col: str,
                               designation: str) -> None:
        self.set_column_meta(name, col, designation=designation)

    def set_column_formula(self, name: str, col: str, expr: str) -> list:
        """设置 / 清除列公式（仅 Python 表达式）。返回重算错误列表。"""
        ds = self.get_dataset(name)
        if ds is None or col not in ds.columns:
            raise ValueError("未找到该数据列。")
        expr = (expr or "").strip()
        if not expr:
            ds.formulas.pop(col, None)
            return []
        return self.add_formula_column(name, col, expr)[1]

    @staticmethod
    def _write_cell(ds: DataSet, col: str, row: int, text: str) -> None:
        arr = ds.columns[col]
        value = "" if text is None else str(text).strip()
        if isinstance(arr, np.ndarray):
            if value == "" or value.lower() in ("nan", "na", "--", "none"):
                arr[row] = np.nan
                return
            try:
                arr[row] = float(value)
                return
            except (TypeError, ValueError):
                arr = ["" if np.isnan(v) else f"{v:.10g}" for v in arr.tolist()]
                ds.columns[col] = arr
        arr[row] = str(text)

    def paste_block(self, name: str, start_row: int, start_col: int,
                    block: list, header_row: bool = False) -> dict:
        """把二维选区写入工作表（Ctrl+V）；自动扩展行 / 列，公式列只读跳过。"""
        ds = self.get_dataset(name)
        if ds is None:
            raise ValueError(f"未找到数据集「{name}」。")
        block = [[("" if v is None else str(v)) for v in row]
                 for row in (block or []) if row is not None]
        if not block:
            return {"changed": 0, "rows_added": 0, "cols_added": 0}
        data = block[1:] if header_row else block
        headers = block[0] if header_row else []
        ncols = max((len(r) for r in block), default=0)
        start_row = max(0, int(start_row))
        start_col = max(0, int(start_col))

        before_cols, before_rows = len(ds.column_order), ds.row_count()
        cols_needed = start_col + ncols
        while len(ds.column_order) < cols_needed:
            self.add_column(name, f"列{len(ds.column_order) + 1}")
        if headers:
            for j, text in enumerate(headers):
                idx = start_col + j
                if idx >= len(ds.column_order) or not text.strip():
                    continue
                old = ds.column_order[idx]
                if text.strip() != old:
                    self.rename_column(name, old, text.strip())
        rows_needed = start_row + len(data)
        if rows_needed > ds.row_count():
            self.add_rows(name, rows_needed - ds.row_count())

        changed = 0
        for i, row in enumerate(data):
            for j, text in enumerate(row):
                idx = start_col + j
                if idx >= len(ds.column_order):
                    break
                col = ds.column_order[idx]
                if col in ds.formulas:
                    continue
                self._write_cell(ds, col, start_row + i, text)
                changed += 1
        ds.recompute_formulas()
        return {"changed": changed,
                "rows_added": ds.row_count() - before_rows,
                "cols_added": len(ds.column_order) - before_cols}

    def clear_cells(self, name: str, cells: list) -> int:
        """清空 [(行, 列序号)]；公式列跳过。返回写入数。"""
        ds = self.get_dataset(name)
        if ds is None:
            return 0
        n = 0
        for row, j in cells:
            if not (0 <= j < len(ds.column_order) and 0 <= row < ds.row_count()):
                continue
            col = ds.column_order[j]
            if col in ds.formulas:
                continue
            self._write_cell(ds, col, row, "")
            n += 1
        ds.recompute_formulas()
        return n

    # ------------------------------------------------------------------
    # 导出 / 序列化
    # ------------------------------------------------------------------

    def export_csv(self, dataset_name: str, path: str,
                   include_meta: bool = False) -> None:
        ds = self.get_dataset(dataset_name)
        if ds is None:
            raise ValueError(f"未找到数据集「{dataset_name}」。")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(ds.column_order)
            if include_meta:
                for key in ("long_name", "unit", "comment"):
                    label = {"long_name": "Long Name", "unit": "Units",
                             "comment": "Comments"}[key]
                    writer.writerow([label] + [ds.meta(c)[key]
                                               for c in ds.column_order[1:]])
            for r in range(ds.row_count()):
                writer.writerow([ds.columns[c][r] for c in ds.column_order])

    def export_excel(self, path: str) -> None:
        from openpyxl import Workbook
        wb = Workbook()
        wb.remove(wb.active)
        for ds in self.datasets:
            ws = wb.create_sheet(title=ds.name[:31] or "Sheet")
            ws.append(ds.column_order)
            for r in range(ds.row_count()):
                ws.append([ds.columns[c][r] for c in ds.column_order])
        wb.save(path)

    def to_dict(self) -> list:
        return [ds.to_dict() for ds in self.datasets]

    def load_dict(self, items: list) -> None:
        self.datasets = [DataSet.from_dict(d) for d in (items or [])]

    def clear(self) -> None:
        self.datasets = []
