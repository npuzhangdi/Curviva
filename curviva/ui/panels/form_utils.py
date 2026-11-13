"""动态表单工具：按分析操作的参数 schema 自动生成 Qt 控件。

新增分析操作只要在 operations.py 里声明参数 schema，界面会自动生成
对应的数字框/下拉框/复选框，无需改 UI 代码。
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)


class SchemaForm(QWidget):
    """schema: [{key,label,type,default,min,max,step,decimals,options,optional}]。"""

    def __init__(self, schema: list, parent=None):
        super().__init__(parent)
        self.schema = schema
        self.widgets = {}
        form = QFormLayout(self)
        form.setContentsMargins(2, 2, 2, 2)
        form.setSpacing(6)
        for item in schema:
            w = self._make_widget(item)
            self.widgets[item["key"]] = w
            form.addRow(item.get("label", item["key"]), w)
        self._form = form

    def _make_widget(self, item: dict) -> QWidget:
        kind = item.get("type", "text")
        default = item.get("default")
        if kind == "int":
            w = QSpinBox()
            w.setRange(int(item.get("min", -1000000)), int(item.get("max", 1000000)))
            w.setSingleStep(int(item.get("step", 1)))
            w.setKeyboardTracking(False)
            if default is not None:
                w.setValue(int(default))
            return w
        if kind == "float":
            if item.get("optional"):
                w = QLineEdit()
                w.setPlaceholderText("留空 = 不过滤")
                if default is not None:
                    w.setText(str(default))
                return w
            w = QDoubleSpinBox()
            w.setRange(float(item.get("min", -1e12)), float(item.get("max", 1e12)))
            w.setDecimals(int(item.get("decimals", 3)))
            w.setSingleStep(10 ** (-int(item.get("decimals", 3))))
            w.setKeyboardTracking(False)
            if default is not None:
                w.setValue(float(default))
            return w
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(default))
            return w
        if kind == "combo":
            w = QComboBox()
            for text, value in item.get("options", []):
                w.addItem(text, value)
            if default is not None:
                i = w.findData(default)
                if i >= 0:
                    w.setCurrentIndex(i)
            return w
        w = QLineEdit()
        w.setPlaceholderText(item.get("placeholder", ""))
        if default is not None:
            w.setText(str(default))
        return w

    def values(self) -> dict:
        out = {}
        for item in self.schema:
            w = self.widgets[item["key"]]
            kind = item.get("type")
            if isinstance(w, QSpinBox):
                out[item["key"]] = w.value()
            elif isinstance(w, QDoubleSpinBox):
                out[item["key"]] = w.value()
            elif isinstance(w, QCheckBox):
                out[item["key"]] = w.isChecked()
            elif isinstance(w, QComboBox):
                out[item["key"]] = w.currentData()
            else:
                text = w.text().strip()
                if kind == "float" and item.get("optional"):
                    out[item["key"]] = float(text) if text else None
                else:
                    out[item["key"]] = text
        return out

    def set_values(self, values: dict) -> None:
        for key, value in (values or {}).items():
            w = self.widgets.get(key)
            if w is None or value is None:
                continue
            if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                w.setValue(value)
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(value))
            elif isinstance(w, QComboBox):
                i = w.findData(value)
                if i >= 0:
                    w.setCurrentIndex(i)
            elif isinstance(w, QLineEdit):
                w.setText(str(value))


def fill_combo_with_names(combo: QComboBox, names: list, keep: str = "") -> None:
    """保留当前选中项地刷新名称下拉框。"""
    current = keep or combo.currentText()
    combo.blockSignals(True)
    combo.clear()
    for name in names:
        combo.addItem(name, name)
    i = combo.findData(current)
    combo.setCurrentIndex(i if i >= 0 else (0 if names else -1))
    combo.blockSignals(False)
