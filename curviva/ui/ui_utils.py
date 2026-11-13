"""界面公共工具：下拉框填充等。"""

from PySide6.QtWidgets import QComboBox


def fill_combo(combo: QComboBox, pairs, value=None, labels=None):
    """用 (显示名, 值) 列表填充下拉框并选中 value。

    labels: 可选，替代 pairs 的显示名列表（与 combo 当前项数相同时按索引映射）。
    返回被选中的索引。
    """
    combo.blockSignals(True)
    combo.clear()
    for label, val in pairs:
        combo.addItem(label, val)
    index = -1
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            index = i
            break
    if index < 0 and combo.count() > 0:
        index = 0
    if index >= 0:
        combo.setCurrentIndex(index)
    combo.blockSignals(False)
    return index


def fill_options(combo: QComboBox, labels, current_index=0):
    """用纯文本列表填充下拉框并选中指定索引（blockSignals 保护）。

    每个选项的 userData 同步设为其文本，保证 currentData() 可用。
    """
    combo.blockSignals(True)
    combo.clear()
    for lb in labels:
        combo.addItem(lb, lb)   # userData = 文本本身
    if combo.count() > 0:
        combo.setCurrentIndex(max(0, min(current_index, combo.count() - 1)))
    combo.blockSignals(False)
