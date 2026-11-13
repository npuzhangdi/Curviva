"""数据文件打开：文本导入向导（选项 + 实时预览）+ 统一打开入口。

菜单、工作表工具栏、项目树、拖放都调用 open_data_file()，保证
CSV / TXT / DAT / TSV / ASC / Excel 的导入行为一致：
Excel 先点选工作表（未选中不导入），文本文件可选导入向导。
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from curviva.core.file_readers import (
    DATA_FILE_FILTER,
    DELIMITER_CHOICES,
    ENCODING_CHOICES,
    EXCEL_EXTS,
    LEGACY_XLS_EXTS,
    default_options,
    extension,
    read_text_file,
)
from curviva.ui.panels.data_dialogs import ExcelSheetDialog

PREVIEW_ROWS = 16
META_KEYS = ("long_name", "unit", "comment", "formula")
META_LABELS = ("长名称", "单位", "注释", "F(x)=")


class TextImportDialog(QDialog):
    """Origin 式文本导入选项：编码、分隔符、注释、跳过行、表头、列头信息行。"""

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(f"文本导入选项 — {os.path.basename(path)}")
        self.resize(760, 520)
        root = QVBoxLayout(self)

        form = QFormLayout()
        self.encoding = QComboBox()
        for text, value in ENCODING_CHOICES:
            self.encoding.addItem(text, value)
        self.delimiter = QComboBox()
        for text, value in DELIMITER_CHOICES:
            self.delimiter.addItem(text, value)
        self.comment = QLineEdit(default_options()["comment"])
        self.comment.setToolTip("多个前缀用逗号分隔，例如：#,!,//,%")
        self.skip = QSpinBox()
        self.skip.setRange(0, 1000)
        self.skip.setKeyboardTracking(False)
        self.header = QComboBox()
        self.header.addItem("自动判断（首行含数字则视为数据）", "auto")
        self.header.addItem("首行是列名", True)
        self.header.addItem("无列名（全部是数据）", False)
        self.meta_rows = QComboBox()
        self.meta_rows.addItem("自动识别带标签的 Long Name / Units 行", "auto")
        for n in range(0, 5):
            self.meta_rows.addItem(f"表头后 {n} 行是列头信息" if n else "没有列头信息行", n)
        form.addRow("文件编码", self.encoding)
        form.addRow("分隔符", self.delimiter)
        form.addRow("注释前缀", self.comment)
        form.addRow("跳过前 N 行", self.skip)
        form.addRow("表头", self.header)
        form.addRow("列头信息行", self.meta_rows)
        root.addLayout(form)

        hint = QLabel("解析预览（列头信息行会写入工作表的长名称 / 单位 / 注释 / 公式）：")
        hint.setObjectName("hintCard")
        root.addWidget(hint)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, 1)

        self.info = QLabel("")
        self.info.setObjectName("hintCard")
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("导入")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        for widget in (self.encoding, self.delimiter, self.header, self.meta_rows):
            widget.currentIndexChanged.connect(lambda *_: self._refresh())
        self.comment.textChanged.connect(lambda *_: self._refresh())
        self.skip.valueChanged.connect(lambda *_: self._refresh())
        self._refresh()

    # ------------------------------------------------------------------
    def options(self) -> dict:
        return {
            "encoding": self.encoding.currentData(),
            "delimiter": self.delimiter.currentData(),
            "comment": self.comment.text(),
            "skip_rows": self.skip.value(),
            "header": self.header.currentData(),
            "meta_rows": self.meta_rows.currentData(),
        }

    def _refresh(self) -> None:
        try:
            spec = read_text_file(self.path, self.options())
        except Exception as e:                       # noqa: BLE001
            self.info.setText(f"解析失败：{e}")
            return
        cols = spec["header"]
        rows = spec["rows"][:PREVIEW_ROWS]
        self.table.clear()
        self.table.setColumnCount(len(cols))
        self.table.setRowCount(len(META_KEYS) + len(rows))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setVerticalHeaderLabels(
            list(META_LABELS) + [str(i + 1) for i in range(len(rows))])
        for j, col in enumerate(cols):
            m = spec["meta"].get(col, {})
            for k, key in enumerate(META_KEYS):
                item = QTableWidgetItem(str(m.get(key, "")))
                item.setBackground(self.palette().alternateBase())
                self.table.setItem(k, j, item)
            for i, row in enumerate(rows):
                text = str(row[j]) if j < len(row) else ""
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(len(META_KEYS) + i, j, item)
        delim = spec["delimiter"]
        delim_text = ("空白" if delim == "whitespace" else
                      "Tab" if delim == "\t" else repr(delim))
        self.info.setText(
            f"编码：{spec['encoding']}　·　分隔符：{delim_text}　·　"
            f"识别列头信息 {spec['meta_lines']} 行　·　"
            f"共 {len(spec['rows'])} 行 × {len(cols)} 列（预览前 {len(rows)} 行）")


# ------------------------------------------------------------------
# 统一打开入口
# ------------------------------------------------------------------

def open_data_file(parent, app, path: str = None, wizard: bool = False,
                   folder: str = None) -> list:
    """打开一个数据文件；返回新建 DataSet 列表（取消/失败返回 []）。

    folder 为项目树节点 id，指定导入表格挂到哪个文件夹。
    """
    if not path:
        path, _ = QFileDialog.getOpenFileName(
            parent, "打开数据文件", "", DATA_FILE_FILTER)
    if not path:
        return []
    ext = extension(path)
    if ext in LEGACY_XLS_EXTS:
        QMessageBox.information(
            parent, "暂不支持 .xls",
            "请把旧版 Excel 文件另存为 .xlsx 后再打开。\n"
            "CSV / TXT / DAT / TSV / ASC / XLSX / XLSM 均可直接打开。")
        return []

    sheets, options = None, None
    try:
        if ext in EXCEL_EXTS:
            names = app.core.excel_sheets(path)
            dlg = ExcelSheetDialog(names, parent)
            if dlg.exec() != QDialog.Accepted or not dlg.selected_sheets():
                return []
            sheets = dlg.selected_sheets()
        elif wizard:
            dlg = TextImportDialog(path, parent)
            if dlg.exec() != QDialog.Accepted:
                return []
            options = dlg.options()
    except Exception as e:                           # noqa: BLE001
        QMessageBox.warning(parent, "读取失败", str(e))
        return []

    try:
        app.checkpoint("打开数据文件")
        imported = app.execute("open_data", path=path, options=options,
                               sheets=sheets, folder=folder)
    except Exception as e:                           # noqa: BLE001
        QMessageBox.warning(parent, "导入失败", str(e))
        return []
    if imported:
        app.hook("open_sheet", imported[0].name)
        app.status(f"已打开：{os.path.basename(path)}　·　"
                   + "、".join(d.name for d in imported))
    return imported


def open_data_files(parent, app, paths: list, folder: str = None) -> list:
    """拖放多个文件时逐个打开（文本文件用自动选项，不弹向导）。"""
    out = []
    for path in paths or []:
        if os.path.isfile(path):
            out.extend(open_data_file(parent, app, path=path,
                                      wizard=False, folder=folder))
    return out
