"""Origin 风格工作表网格：列标 + 列头信息行 + 单元格 + Excel 式复制粘贴。

结构（从上到下）：
    A(X) x        B(Y) y        C(yEr) err      ← 水平表头：列字母(列类型) + 列名
    长名称        时间           强度            ← 元数据行（可编辑）
    单位          s             a.u.
    注释          扫描位置       荧光强度
    公式 F(x)=                                ← 仅 Python 表达式，自动重算
    1  0.0        1.2           0.05           ← 数据行（行号 1..N）
    2  0.1        1.4           0.05
"""

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QInputDialog,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTableWidgetSelectionRange,
)

from curviva.core.file_readers import detect_delimiter, split_line

MAX_ROWS = 2000                    # 单表最多显示行数（数据本身不受限）
META_KEYS = ("long_name", "unit", "comment", "formula")
META_VERTICAL = ("长名称", "单位", "注释", "F(x)=")
META_HINTS = ("Long Name", "Units", "Comments", "Python 公式列表达式")
DESIGNATIONS = [
    ("X（自变量）", "X"), ("Y（因变量）", "Y"), ("Z（第三维）", "Z"),
    ("yEr（Y 误差）", "yEr"), ("xEr（X 误差）", "xEr"),
    ("L（标签 / 文本）", "L"), ("D（忽略）", "D"),
]

META_BG = QColor("#EAF2FF")
META_BG_ALT = QColor("#F4F8FF")
FORMULA_BG = QColor("#FFF3E4")
META_FG = QColor("#3B4C72")


def col_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA（与 Origin / Excel 一致）。"""
    out, n = "", index + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def fmt(value) -> str:
    if isinstance(value, (float, np.floating)):
        return "" if np.isnan(float(value)) else f"{float(value):.10g}"
    return "" if value is None else str(value)


class WorksheetGrid(QTableWidget):
    """一个数据集对应一张工作表。所有写操作经 WorksheetController -> CoreController。"""

    selection_info_changed = Signal(str)

    def __init__(self, controller, dataset_name: str, parent=None):
        super().__init__(parent)
        self.ctl = controller
        self.dataset_name = dataset_name
        self.show_meta = True
        self.paste_header = False       # 粘贴时把首行作为列名
        self._updating = False

        self.setObjectName("worksheetGrid")
        self.setAlternatingRowColors(True)
        self.setGridStyle(Qt.SolidLine)
        self.setSelectionMode(QAbstractItemView.ContiguousSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setEditTriggers(QAbstractItemView.DoubleClicked |
                             QAbstractItemView.EditKeyPressed |
                             QAbstractItemView.AnyKeyPressed)
        self.setTabKeyNavigation(True)
        self.setCornerButtonEnabled(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setDefaultSectionSize(96)
        self.horizontalHeader().setMinimumSectionSize(56)
        # Origin 式：末列自动拉伸铺满窗口，避免右侧大片空白
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setDefaultSectionSize(21)
        self.verticalHeader().setMinimumWidth(46)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)

        self.itemChanged.connect(self._on_item_changed)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.itemSelectionChanged.connect(self._emit_selection_info)
        self._load()

    # ------------------------------------------------------------------
    # 构建 / 刷新
    # ------------------------------------------------------------------

    @property
    def core(self):
        return self.ctl.core

    @property
    def meta_count(self) -> int:
        return len(META_KEYS) if self.show_meta else 0

    def _load(self) -> None:
        ds = self.core.get_dataset(self.dataset_name)
        self._updating = True
        self.blockSignals(True)
        try:
            if ds is None:
                self.clear()
                self.setRowCount(0)
                self.setColumnCount(0)
                return
            cols = list(ds.column_order)
            total = ds.row_count()
            shown = min(total, MAX_ROWS)
            meta_n = self.meta_count
            self.clear()
            self.setColumnCount(len(cols))
            self.setRowCount(meta_n + shown)
            headers = [f"{col_letter(j)}({ds.meta(c)['designation']})  {c}"
                       for j, c in enumerate(cols)]
            self.setHorizontalHeaderLabels(headers)
            self.setVerticalHeaderLabels(
                list(META_VERTICAL if self.show_meta else ()) +
                [str(i + 1) for i in range(shown)])

            for j, col in enumerate(cols):
                if self.show_meta:
                    for k, key in enumerate(META_KEYS):
                        text = (ds.formulas.get(col, "") if key == "formula"
                                else ds.meta(col).get(key, ""))
                        item = QTableWidgetItem(str(text))
                        item.setBackground(QBrush(META_BG if k % 2 == 0 else META_BG_ALT))
                        item.setForeground(QBrush(META_FG))
                        item.setToolTip(f"{col} · {META_HINTS[k]}")
                        self.setItem(k, j, item)
                numeric = isinstance(ds.columns[col], np.ndarray)
                is_formula = col in ds.formulas
                for i in range(shown):
                    item = QTableWidgetItem(fmt(ds.columns[col][i]))
                    if is_formula:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        item.setBackground(QBrush(FORMULA_BG))
                        item.setToolTip("公式列（只读）：" + ds.formulas[col])
                    elif numeric:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.setItem(meta_n + i, j, item)
            self._status = (f"{self.dataset_name}　·　{total} 行 × {len(cols)} 列"
                            + (f"（显示前 {shown} 行）" if total > shown else ""))
        finally:
            self.blockSignals(False)
            self._updating = False
        self._emit_selection_info()

    def refresh(self) -> None:
        self._load()

    def set_show_meta(self, show: bool) -> None:
        self.show_meta = bool(show)
        self._load()

    # ------------------------------------------------------------------
    # 单元格编辑
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating:
            return
        ds = self.core.get_dataset(self.dataset_name)
        if ds is None:
            return
        row, col_index = item.row(), item.column()
        cols = list(ds.column_order)
        if not (0 <= col_index < len(cols)):
            return
        col = cols[col_index]
        text = item.text()
        meta_n = self.meta_count
        if row < meta_n:
            key = META_KEYS[row]
            if key == "formula":
                try:
                    errors = self.core.set_column_formula(
                        self.dataset_name, col, text)
                except Exception as e:                    # noqa: BLE001
                    self.ctl.status(f"公式错误：{e}")
                    self._load()
                    return
                if errors:
                    self.ctl.status("公式错误：" + errors[0])
                    self._load()
                    return
            else:
                self.core.set_column_meta(self.dataset_name, col, **{key: text})
            self.ctl.quiet_changed(self.dataset_name, f"已更新「{col}」列头信息")
        else:
            data_row = row - meta_n
            self.core.set_cell(self.dataset_name, col, data_row, text)
            self.core.recompute_all()
            self.ctl.quiet_changed(self.dataset_name,
                                   f"已写入 {col}[{data_row + 1}] = {text}")

    # ------------------------------------------------------------------
    # 键盘：Ctrl+C / Ctrl+V / Delete
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:               # noqa: N802 (Qt 命名)
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
            event.accept()
            return
        if event.matches(QKeySequence.Paste):
            self.paste_from_clipboard()
            event.accept()
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.clear_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def _ranges(self) -> list:
        ranges = self.selectedRanges()
        if ranges:
            return list(ranges)
        row, col = self.currentRow(), self.currentColumn()
        if row < 0 or col < 0:
            return []
        return [QTableWidgetSelectionRange(row, col, row, col)]

    def _range(self):
        ranges = self._ranges()
        return ranges[0] if ranges else None

    def copy_selection(self, with_header: bool = False) -> None:
        rng = self._range()
        if rng is None:
            return
        ds = self.core.get_dataset(self.dataset_name)
        cols = list(ds.column_order) if ds else []
        lines = []
        if with_header:
            lines.append("\t".join(cols[rng.leftColumn():rng.rightColumn() + 1]))
        for r in range(rng.topRow(), rng.bottomRow() + 1):
            cells = []
            for c in range(rng.leftColumn(), rng.rightColumn() + 1):
                item = self.item(r, c)
                cells.append(item.text() if item is not None else "")
            lines.append("\t".join(cells))
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.ctl.status(f"已复制 {rng.rowCount()} 行 × {rng.columnCount()} 列"
                        + ("（含列名）" if with_header else ""))

    def paste_from_clipboard(self) -> None:
        text = QGuiApplication.clipboard().text()
        if not text or not text.strip():
            return
        lines = [l for l in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                 if l.strip()]
        if not lines:
            return
        delim = detect_delimiter(lines)
        block = [split_line(l, delim) for l in lines]
        rng = self._range()
        start_col = max(0, rng.leftColumn()) if rng is not None else 0
        if rng is not None and rng.topRow() >= self.meta_count:
            start_row = rng.topRow() - self.meta_count
        else:
            start_row = 0
        try:
            self.ctl.checkpoint("工作表：粘贴选区")
            result = self.core.paste_block(self.dataset_name, start_row,
                                           start_col, block,
                                           header_row=self.paste_header)
        except Exception as e:                             # noqa: BLE001
            QMessageBox.warning(self, "粘贴失败", str(e))
            return
        self.ctl.structural_changed(
            self.dataset_name,
            f"已粘贴 {result['changed']} 个单元格"
            + (f"，新增 {result['rows_added']} 行 / {result['cols_added']} 列"
               if result["rows_added"] or result["cols_added"] else ""))

    def clear_selection(self) -> None:
        cells = []
        for rng in self._ranges():
            for r in range(max(rng.topRow(), self.meta_count), rng.bottomRow() + 1):
                for c in range(rng.leftColumn(), rng.rightColumn() + 1):
                    cells.append((r - self.meta_count, c))
        if not cells:
            return
        try:
            self.ctl.checkpoint("工作表：清空选区")
            n = self.core.clear_cells(self.dataset_name, cells)
        except Exception as e:                             # noqa: BLE001
            QMessageBox.warning(self, "清空失败", str(e))
            return
        self._load()
        self.ctl.quiet_changed(self.dataset_name, f"已清空 {n} 个单元格")

    # ------------------------------------------------------------------
    # 右键菜单
    # ------------------------------------------------------------------

    def _col_at(self, index: int) -> str:
        ds = self.core.get_dataset(self.dataset_name)
        cols = list(ds.column_order) if ds else []
        return cols[index] if 0 <= index < len(cols) else ""

    def _on_context_menu(self, pos) -> None:
        index = self.indexAt(pos)
        if not index.isValid():
            return
        self.setCurrentCell(index.row(), index.column())
        col = self._col_at(index.column())
        rng = self._range()
        menu = QMenu(self)
        menu.addAction("复制（Ctrl+C）", lambda: self.copy_selection(False))
        menu.addAction("复制含列名", lambda: self.copy_selection(True))
        menu.addAction("粘贴（Ctrl+V）", self.paste_from_clipboard)
        menu.addAction("清空选中（Delete）", self.clear_selection)
        menu.addSeparator()

        cm = menu.addMenu(f"列操作　{col_letter(index.column())} · {col}")
        cm.addAction("在左侧插入列", lambda: self._insert_col(index.column()))
        cm.addAction("在右侧插入列", lambda: self._insert_col(index.column() + 1))
        cm.addAction("重命名列…", lambda: self._rename_col(col))
        cm.addAction("设置列公式（Python）…", lambda: self._set_formula(col))
        dm = cm.addMenu("设置列类型")
        for label, d in DESIGNATIONS:
            dm.addAction(label, lambda v=d, c=col: self._set_designation(c, v))
        cm.addSeparator()
        cm.addAction("删除列", lambda: self._delete_col(col))

        rm = menu.addMenu("行操作")
        rm.addAction("在上方插入行…", self._insert_rows)
        rm.addAction("删除选中行", self._delete_rows)
        rm.addAction("在末尾追加行…", self._append_rows)
        menu.addSeparator()
        menu.addAction("生成曲线", lambda: self.ctl.add_curve(self.dataset_name, col))
        om = menu.addMenu("数据处理")
        for label, key in (("插值 / 等间距重采样", "resample"),
                           ("Savitzky–Golay 平滑", "savgol"),
                           ("归一化", "normalize"), ("数值微分", "derivative"),
                           ("累积积分", "integral"), ("寻峰 / 峰面积", "find_peaks"),
                           ("描述统计", "describe")):
            om.addAction(label, lambda k=key: self.ctl.open_operation(
                self.dataset_name, k))
        menu.addSeparator()
        menu.addAction("导出 CSV…", lambda: self.ctl.export_csv(self.dataset_name))
        menu.addAction("导出全部工作簿 Excel…", self.ctl.export_excel)
        menu.exec(self.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # 结构操作
    # ------------------------------------------------------------------

    def _insert_col(self, index: int) -> None:
        try:
            self.ctl.checkpoint("工作表：插入列")
            name = self.core.insert_column(self.dataset_name, index)
        except Exception as e:                             # noqa: BLE001
            QMessageBox.warning(self, "插入列失败", str(e))
            return
        self.ctl.structural_changed(self.dataset_name, f"已插入列「{name}」")

    def _rename_col(self, col: str) -> None:
        name, ok = QInputDialog.getText(self, "重命名列", "新列名：", text=col)
        if not ok or not name.strip() or name.strip() == col:
            return
        try:
            self.ctl.checkpoint("工作表：重命名列")
            final = self.ctl.rename_column(self.dataset_name, col, name.strip())
        except Exception as e:                             # noqa: BLE001
            QMessageBox.warning(self, "重命名失败", str(e))
            return
        self.ctl.structural_changed(self.dataset_name, f"列已重命名为「{final}」")

    def _delete_col(self, col: str) -> None:
        if QMessageBox.question(self, "删除列", f"确定删除列「{col}」吗？",
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.ctl.checkpoint("工作表：删除列")
            self.ctl.delete_column(self.dataset_name, col)
        except Exception as e:                             # noqa: BLE001
            QMessageBox.warning(self, "删除列失败", str(e))
            return
        self.ctl.structural_changed(self.dataset_name, f"已删除列「{col}」")

    def _set_designation(self, col: str, designation: str) -> None:
        self.core.set_column_designation(self.dataset_name, col, designation)
        self._load()
        self.ctl.quiet_changed(self.dataset_name,
                               f"「{col}」列类型 → {designation}")

    def _set_formula(self, col: str) -> None:
        ds = self.core.get_dataset(self.dataset_name)
        expr, ok = QInputDialog.getText(
            self, "Python 公式列",
            "表达式（列引用 A/B/C、col(\"列名\")，可用 np / math / x / i）：",
            text=ds.formulas.get(col, "") if ds else "")
        if not ok:
            return
        try:
            self.ctl.checkpoint("工作表：设置列公式")
            errors = self.core.set_column_formula(self.dataset_name, col, expr)
        except Exception as e:                             # noqa: BLE001
            QMessageBox.warning(self, "公式错误", str(e))
            return
        if errors:
            QMessageBox.warning(self, "公式错误", "\n".join(errors[:6]))
            return
        self.ctl.structural_changed(self.dataset_name,
                                    f"「{col}」公式已更新" if expr.strip()
                                    else f"「{col}」已转为普通列")

    def _insert_rows(self) -> None:
        rng = self._range()
        start = (rng.topRow() - self.meta_count) if rng is not None else 0
        start = max(0, start)
        count, ok = QInputDialog.getInt(self, "插入行", "插入行数：", 1, 1, 10000, 1)
        if not ok:
            return
        self.ctl.checkpoint("工作表：插入行")
        self.core.insert_rows(self.dataset_name, start, count)
        self.ctl.structural_changed(self.dataset_name,
                                    f"已在第 {start + 1} 行前插入 {count} 行")

    def _append_rows(self) -> None:
        count, ok = QInputDialog.getInt(self, "追加行", "追加行数：", 10, 1, 100000, 10)
        if not ok:
            return
        self.ctl.checkpoint("工作表：追加行")
        self.core.add_rows(self.dataset_name, count)
        self.ctl.structural_changed(self.dataset_name, f"已追加 {count} 行")

    def _delete_rows(self) -> None:
        rng = self._range()
        if rng is None:
            return
        start = max(0, rng.topRow() - self.meta_count)
        count = rng.bottomRow() - max(rng.topRow(), self.meta_count) + 1
        if count <= 0:
            QMessageBox.information(self, "提示", "请先选中数据行。")
            return
        self.ctl.checkpoint("工作表：删除行")
        self.core.remove_rows(self.dataset_name, start, count)
        self.ctl.structural_changed(self.dataset_name, f"已删除 {count} 行")

    # ------------------------------------------------------------------
    # 供工具栏调用的公开入口
    # ------------------------------------------------------------------

    def insert_column(self) -> None:
        self._insert_col(max(0, self.currentColumn()) + 1)

    def insert_row(self) -> None:
        self._insert_rows()

    def append_row(self) -> None:
        self._append_rows()

    def delete_column(self) -> None:
        col = self._col_at(self.currentColumn())
        if col:
            self._delete_col(col)

    def delete_row(self) -> None:
        self._delete_rows()

    def set_paste_header(self, enabled: bool) -> None:
        self.paste_header = bool(enabled)

    # ------------------------------------------------------------------
    def _emit_selection_info(self) -> None:
        base = getattr(self, "_status", self.dataset_name)
        values = []
        for rng in self._ranges():
            for r in range(max(rng.topRow(), self.meta_count), rng.bottomRow() + 1):
                for c in range(rng.leftColumn(), rng.rightColumn() + 1):
                    item = self.item(r, c)
                    if item is None or not item.text().strip():
                        continue
                    try:
                        values.append(float(item.text()))
                    except ValueError:
                        pass
        if len(values) > 1:
            import numpy as np
            base += (f"　|　选中 {len(values)} 个数值：均值 "
                     f"{np.mean(values):.6g} · 求和 {np.sum(values):.6g} · "
                     f"范围 [{min(values):.6g}, {max(values):.6g}]")
        self.selection_info_changed.emit(base)
