"""P0 撤销 / 重做（对标 Origin 的 Undo/Redo 历史）。

保存的是「完整状态快照」的纯字典（配置 + 数据集 + 附加信息），因此
撤销不仅是样式回退，也包括导入数据、公式列、拟合结果、曲线增删等。
"""

from copy import deepcopy


class History:
    def __init__(self, limit: int = 60):
        self.limit = limit
        self._undo: list = []      # [(label, state)]
        self._redo: list = []

    # ------------------------------------------------------------------
    def push(self, state: dict, label: str = "修改") -> None:
        self._undo.append((label, deepcopy(state)))
        if len(self._undo) > self.limit:
            del self._undo[0]
        self._redo.clear()

    def undo(self, current: dict):
        if not self._undo:
            return None
        label, state = self._undo.pop()
        self._redo.append((label, deepcopy(current)))
        return deepcopy(state)

    def redo(self, current: dict):
        if not self._redo:
            return None
        label, state = self._redo.pop()
        self._undo.append((label, deepcopy(current)))
        return deepcopy(state)

    # ------------------------------------------------------------------
    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo_label(self) -> str:
        return self._undo[-1][0] if self._undo else ""

    def redo_label(self) -> str:
        return self._redo[-1][0] if self._redo else ""

    def last_state(self):
        return self._undo[-1][1] if self._undo else None

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
