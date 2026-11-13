"""图形 / 图片文档设置对话框。"""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QDoubleSpinBox,
)

from curviva.graphs.model import SIZE_PRESETS


class GraphSizeDialog(QDialog):
    """图形出版尺寸：预设 + 自定义宽高 + 单位 + DPI。"""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle(f"图形尺寸 · {doc.name}")
        self.resize(360, 240)
        root = QVBoxLayout(self)

        tip = QLabel("设置该图形窗口的导出尺寸；单位会自动换算为英寸，"
                     "导出 PNG/SVG/PDF 时按此尺寸与 DPI 输出。")
        tip.setObjectName("hintCard")
        tip.setWordWrap(True)
        root.addWidget(tip)

        form = QFormLayout()
        self.preset = QComboBox()
        self.preset.addItem("自定义 / 当前", None)
        for label, w, h in SIZE_PRESETS:
            self.preset.addItem(label, (w, h))
        form.addRow("常用出版尺寸", self.preset)

        self.width = QDoubleSpinBox()
        self.width.setRange(0.5, 60.0)
        self.width.setDecimals(2)
        self.width.setSingleStep(0.5)
        self.width.setValue(float(doc.width))
        form.addRow("宽度", self.width)

        self.height = QDoubleSpinBox()
        self.height.setRange(0.5, 60.0)
        self.height.setDecimals(2)
        self.height.setSingleStep(0.5)
        self.height.setValue(float(doc.height))
        form.addRow("高度", self.height)

        self.unit = QComboBox()
        for text, key in (("英寸 inch", "inch"), ("厘米 cm", "cm"),
                          ("毫米 mm", "mm"), ("像素 px", "px")):
            self.unit.addItem(text, key)
        i = self.unit.findData(doc.unit)
        self.unit.setCurrentIndex(i if i >= 0 else 0)
        form.addRow("单位", self.unit)

        self.dpi = QSpinBox()
        self.dpi.setRange(50, 2400)
        self.dpi.setSingleStep(50)
        self.dpi.setValue(int(doc.dpi))
        form.addRow("导出 DPI", self.dpi)

        self.preview = QLabel()
        self.preview.setObjectName("hintCard")
        form.addRow("实际像素", self.preview)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.preset.currentIndexChanged.connect(self._on_preset)
        for w in (self.width, self.height, self.dpi):
            w.valueChanged.connect(self._refresh_preview)
        self.unit.currentIndexChanged.connect(self._refresh_preview)
        self._refresh_preview()

    def _on_preset(self) -> None:
        value = self.preset.currentData()
        if not value:
            return
        self.unit.setCurrentIndex(self.unit.findData("inch"))
        self.width.setValue(value[0])
        self.height.setValue(value[1])
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        w, h = self.width.value(), self.height.value()
        unit = self.unit.currentData()
        factor = {"inch": 1.0, "cm": 1 / 2.54, "mm": 1 / 25.4}.get(unit, 0.0)
        if factor:
            px_w, px_h = w * factor * self.dpi.value(), h * factor * self.dpi.value()
        else:
            px_w, px_h = w, h
        self.preview.setText(f"{int(round(px_w))} × {int(round(px_h))} px "
                             f"@ {self.dpi.value()} dpi")

    def values(self) -> dict:
        return {"width": self.width.value(), "height": self.height.value(),
                "unit": self.unit.currentData(), "dpi": self.dpi.value()}
