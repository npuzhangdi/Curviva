"""窗口管理域：每个停靠窗口的显示、位置、浮动、宽度与内部选项卡设置。

- WindowManager        由 UIController 持有，负责实际操作与布局持久化；
- WindowManagerDialog  逐窗口设置对话框（每个窗口一页）；
- build_menu           生成菜单栏「窗口管理」的全部动作。

布局通过 QSettings 持久化，启动时自动恢复上次布局。
"""

import json

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

AREAS = [
    ("左侧", Qt.LeftDockWidgetArea),
    ("右侧", Qt.RightDockWidgetArea),
    ("顶部", Qt.TopDockWidgetArea),
    ("底部", Qt.BottomDockWidgetArea),
    ("浮动为独立窗口", None),
]


class WindowManager:
    """统一管理主窗口中的全部 QDockWidget。"""

    def __init__(self, window, ui=None):
        self.window = window
        self.ui = ui
        self.entries = {}                 # key -> 窗口配置字典
        # 布局结构变化时递增版本号，旧布局（含已删除窗口的尺寸）自动失效
        self.settings = QSettings("Curviva", "Curviva_v0.0.0.layout3")
        self._tab_actions = {}

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    def register(self, key: str, dock, title: str, tabs=None,
                 tab_labels: list = None, area=Qt.LeftDockWidgetArea,
                 width: int = 320) -> None:
        self.entries[key] = {
            "dock": dock, "title": title, "tabs": tabs,
            "tab_labels": list(tab_labels or []),
            "default_area": area, "default_width": width,
        }

    def titles(self) -> dict:
        return {k: e["title"] for k, e in self.entries.items()}

    # ------------------------------------------------------------------
    # 单窗口设置
    # ------------------------------------------------------------------

    def dock(self, key: str):
        e = self.entries.get(key)
        return e["dock"] if e else None

    def set_visible(self, key: str, visible: bool) -> None:
        dock = self.dock(key)
        if dock is None:
            return
        dock.setVisible(bool(visible))

    def set_area(self, key: str, area) -> None:
        dock = self.dock(key)
        if dock is None:
            return
        if area is None:
            dock.setFloating(True)
            dock.show()
            return
        if dock.isFloating():
            dock.setFloating(False)
        self.window.removeDockWidget(dock)
        self.window.addDockWidget(area, dock)
        dock.show()

    def set_width(self, key: str, width: int) -> None:
        """左右停靠时调宽度；上下停靠（如工作表）时调高度。

        注意：不使用 setMinimumWidth 固化尺寸，否则用户之后无法把
        停靠窗口拖得更窄（width 只作为一次性的目标尺寸）。
        """
        dock = self.dock(key)
        if dock is None:
            return
        width = max(150, min(int(width), 1200))
        area = self.window.dockWidgetArea(dock)
        vertical = area in (Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea)
        # 解除历史固化：先放开最小尺寸约束，再按目标宽度调整
        if vertical:
            dock.setMinimumHeight(120)
        else:
            dock.setMinimumWidth(140)
        try:
            self.window.resizeDocks([dock], [width],
                                    Qt.Vertical if vertical else Qt.Horizontal)
        except Exception:                      # noqa: BLE001 - 布局引擎不支持时降级
            if vertical:
                dock.resize(dock.width(), width)
            else:
                dock.resize(width, dock.height())

    def current_area(self, key: str):
        dock = self.dock(key)
        if dock is None:
            return None
        if dock.isFloating():
            return None
        return self.window.dockWidgetArea(dock)

    def tab_labels(self, key: str) -> list:
        e = self.entries.get(key)
        if not e or e["tabs"] is None:
            return []
        return e["tab_labels"]

    def is_tab_visible(self, key: str, index: int) -> bool:
        e = self.entries.get(key)
        if not e or e["tabs"] is None:
            return True
        tabs = e["tabs"]
        if not hasattr(tabs, "isTabVisible"):
            return tabs.isTabEnabled(index)
        return tabs.isTabVisible(index)

    def set_tab_visible(self, key: str, index: int, visible: bool) -> bool:
        e = self.entries.get(key)
        if not e or e["tabs"] is None:
            return False
        tabs = e["tabs"]
        if not visible and sum(self.is_tab_visible(key, i)
                               for i in range(tabs.count())) <= 1:
            QMessageBox.information(
                self.window, "无法隐藏", "每个窗口至少要保留一个可见的选项卡。")
            return False
        if hasattr(tabs, "setTabVisible"):
            tabs.setTabVisible(index, bool(visible))
        else:                                  # 老版本 Qt 降级为禁用
            tabs.setTabEnabled(index, bool(visible))
        for (k, i), action in self._tab_actions.items():
            if k == key and i == index:
                action.blockSignals(True)
                action.setChecked(bool(visible))
                action.blockSignals(False)
        return True

    # ------------------------------------------------------------------
    # 批量操作
    # ------------------------------------------------------------------

    def show_all(self) -> None:
        for key in self.entries:
            self.set_visible(key, True)

    def hide_all(self) -> None:
        for key in self.entries:
            self.set_visible(key, False)

    def reset_layout(self) -> None:
        for key, e in self.entries.items():
            self.set_area(key, e["default_area"])
            for i in range(e["tabs"].count() if e["tabs"] is not None else 0):
                if hasattr(e["tabs"], "setTabVisible"):
                    e["tabs"].setTabVisible(i, True)
                else:
                    e["tabs"].setTabEnabled(i, True)
            self.set_width(key, e["default_width"])
            self.set_visible(key, True)
        self._sync_tab_actions()

    def _sync_tab_actions(self) -> None:
        for (key, index), action in self._tab_actions.items():
            action.blockSignals(True)
            action.setChecked(self.is_tab_visible(key, index))
            action.blockSignals(False)

    # ------------------------------------------------------------------
    # 布局持久化
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        out = {}
        for key, e in self.entries.items():
            dock, tabs = e["dock"], e["tabs"]
            area = self.current_area(key)
            area_text = "左侧"
            for text, candidate in AREAS:
                if candidate is not None and area == candidate:
                    area_text = text
                    break
            vertical = area in (Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea)
            out[key] = {
                "visible": bool(dock.isVisible()),
                "floating": bool(dock.isFloating()),
                "area": area_text if area is not None else None,
                "width": int(dock.height() if vertical else dock.width()),
                "tabs": [self.is_tab_visible(key, i)
                         for i in range(tabs.count())] if tabs is not None else [],
            }
        return out

    def save_layout(self) -> None:
        self.settings.setValue("window_layout", json.dumps(self.snapshot(),
                                                           ensure_ascii=False))

    def has_saved_layout(self) -> bool:
        return bool(self.settings.value("window_layout", ""))

    def restore_layout(self, data: dict = None) -> bool:
        if data is None:
            raw = self.settings.value("window_layout", "")
            if not raw:
                return False
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                return False
        if not isinstance(data, dict):
            return False
        for key, cfg in data.items():
            if key not in self.entries or not isinstance(cfg, dict):
                continue
            area_text = cfg.get("area")
            if cfg.get("floating") or area_text is None:
                self.set_area(key, None)
            else:
                target = next((a for text, a in AREAS if text == area_text),
                              Qt.LeftDockWidgetArea)
                self.set_area(key, target)
            tabs = self.entries[key]["tabs"]
            if tabs is not None:
                states = cfg.get("tabs", [])
                for i in range(tabs.count()):
                    want = bool(states[i]) if i < len(states) else True
                    if hasattr(tabs, "setTabVisible"):
                        tabs.setTabVisible(i, want)
                    else:
                        tabs.setTabEnabled(i, want)
            self.set_visible(key, bool(cfg.get("visible", True)))
            if cfg.get("width"):
                self.set_width(key, cfg["width"])
        self._sync_tab_actions()
        return True

    # ------------------------------------------------------------------
    # 菜单
    # ------------------------------------------------------------------

    def toggle_visible(self, key: str) -> None:
        """切换某个停靠窗口的显示 / 隐藏（「查看」菜单用）。"""
        e = self.entries.get(key)
        if e is not None:
            e["dock"].setVisible(not e["dock"].isVisible())

    def build_tab_menu(self, menu) -> None:
        """单独构建「面板选项卡显示」子菜单（「查看」菜单用）。"""
        for key, e in self.entries.items():
            tabs, labels = e["tabs"], e["tab_labels"]
            if tabs is None:
                continue
            for i in range(tabs.count()):
                label = labels[i] if i < len(labels) else f"选项卡 {i + 1}"
                action = QAction(f"{e['title']} · {label}", menu)
                action.setCheckable(True)
                action.setChecked(self.is_tab_visible(key, i))
                action.toggled.connect(
                    lambda checked, k=key, idx=i, a=action:
                    self._on_tab_toggled(checked, k, idx, a))
                menu.addAction(action)
                self._tab_actions[(key, i)] = action

    def build_menu(self, menu) -> None:
        menu.addAction("窗口布局设置…", lambda: self.open_dialog())
        menu.addSeparator()

        for key, e in self.entries.items():
            action = e["dock"].toggleViewAction()
            action.setText(e["title"])
            action.setToolTip(f"显示 / 隐藏「{e['title']}」")
            menu.addAction(action)

        menu.addSeparator()
        single = menu.addMenu("单独设置某个窗口")
        for key, e in self.entries.items():
            single.addAction(f"{e['title']}…",
                             lambda k=key: self.open_dialog(k))

        tab_menu = menu.addMenu("面板选项卡显示")
        for key, e in self.entries.items():
            tabs, labels = e["tabs"], e["tab_labels"]
            if tabs is None:
                continue
            for i in range(tabs.count()):
                label = labels[i] if i < len(labels) else f"选项卡 {i + 1}"
                action = QAction(f"{e['title']} · {label}", menu)
                action.setCheckable(True)
                action.setChecked(self.is_tab_visible(key, i))
                action.toggled.connect(
                    lambda checked, k=key, idx=i, a=action:
                    self._on_tab_toggled(checked, k, idx, a))
                tab_menu.addAction(action)
                self._tab_actions[(key, i)] = action

        menu.addSeparator()
        menu.addAction("显示全部窗口", self.show_all)
        menu.addAction("隐藏全部侧栏", self.hide_all)
        menu.addSeparator()
        menu.addAction("保存当前布局", self._save_and_notify)
        menu.addAction("恢复默认布局", self._reset_and_notify)

    def _on_tab_toggled(self, checked: bool, key: str, index: int,
                        action: QAction) -> None:
        if not self.set_tab_visible(key, index, checked):
            action.blockSignals(True)
            action.setChecked(True)
            action.blockSignals(False)

    def _save_and_notify(self) -> None:
        self.save_layout()
        self.window.statusBar().showMessage("当前窗口布局已保存", 5000)

    def _reset_and_notify(self) -> None:
        self.reset_layout()
        self.window.statusBar().showMessage("已恢复默认窗口布局", 5000)

    def open_dialog(self, focus_key: str = None) -> None:
        dlg = WindowManagerDialog(self, focus_key, self.window)
        dlg.exec()


class WindowManagerDialog(QDialog):
    """每个窗口一页：显示与否、停靠位置、浮动、宽度、内部选项卡。"""

    def __init__(self, manager: WindowManager, focus_key: str = None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.pages = {}
        self.setWindowTitle("窗口管理 / 布局设置")
        self.resize(480, 430)

        root = QVBoxLayout(self)
        tip = QLabel("每个窗口都可以单独设置显示与否、停靠位置、浮动状态与宽度；"
                     "窗口内的每个选项卡也可以单独显示或隐藏。")
        tip.setObjectName("hintCard")
        tip.setWordWrap(True)
        root.addWidget(tip)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        for key, e in manager.entries.items():
            page = self._build_page(key, e)
            self.tabs.addTab(page, e["title"])
            self.pages[key] = page
        if focus_key in self.pages:
            self.tabs.setCurrentWidget(self.pages[focus_key])

        row = QHBoxLayout()
        reset_btn = QPushButton("恢复默认布局")
        reset_btn.setProperty("tone", "orange")
        reset_btn.clicked.connect(self._on_reset)
        row.addWidget(reset_btn)
        row.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Apply | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.button(QDialogButtonBox.Apply).setText("应用")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        row.addWidget(buttons)
        root.addLayout(row)
        self._sync_from_manager()

    # ------------------------------------------------------------------
    def _build_page(self, key: str, e: dict) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)

        gb = QGroupBox("窗口属性")
        form = QFormLayout(gb)
        visible = QCheckBox("显示此窗口")
        area_combo = QComboBox()
        for text, area in AREAS:
            area_combo.addItem(text, area)
        width_spin = QSpinBox()
        width_spin.setRange(200, 1200)
        width_spin.setSingleStep(10)
        width_spin.setKeyboardTracking(False)
        form.addRow("", visible)
        form.addRow("停靠位置", area_combo)
        form.addRow("宽度 / 高度（px）", width_spin)
        v.addWidget(gb)

        gb2 = QGroupBox("该窗口内的选项卡（单独显示 / 隐藏）")
        v2 = QVBoxLayout(gb2)
        tab_checks = []
        tabs = e["tabs"]
        if tabs is not None and tabs.count():
            for i in range(tabs.count()):
                label = (e["tab_labels"][i] if i < len(e["tab_labels"])
                         else f"选项卡 {i + 1}")
                cb = QCheckBox(label)
                v2.addWidget(cb)
                tab_checks.append(cb)
        else:
            v2.addWidget(QLabel("此窗口没有可单独设置的选项卡。"))
            gb2.setEnabled(False)
        v.addWidget(gb2, 1)

        hint = QLabel("提示：隐藏最后一个选项卡会被阻止；"
                      "也可以把窗口拖成浮动，或用标题栏按钮临时关闭。")
        hint.setObjectName("hintCard")
        hint.setWordWrap(True)
        v.addWidget(hint)

        page._widgets = {"visible": visible, "area": area_combo,
                         "width": width_spin, "tab_checks": tab_checks}
        return page

    def _sync_from_manager(self) -> None:
        m = self.manager
        for key, page in self.pages.items():
            w, dock = page._widgets, m.dock(key)
            if dock is None:
                continue
            w["visible"].setChecked(dock.isVisible())
            area = m.current_area(key)
            i = w["area"].findData(area)
            w["area"].setCurrentIndex(i if i >= 0 else 0)
            vertical = m.current_area(key) in (Qt.TopDockWidgetArea,
                                              Qt.BottomDockWidgetArea)
            size = dock.height() if vertical else dock.width()
            w["width"].setValue(max(200, min(size, 1200)))
            for idx, cb in enumerate(w["tab_checks"]):
                cb.setChecked(m.is_tab_visible(key, idx))

    # ------------------------------------------------------------------
    def apply(self) -> None:
        m = self.manager
        for key, page in self.pages.items():
            w = page._widgets
            want = w["area"].currentData()
            dock = m.dock(key)
            changed = ((want is None) != (dock is not None and dock.isFloating())
                       or (want is not None and m.current_area(key) != want))
            if changed:
                m.set_area(key, want)
            for idx, cb in enumerate(w["tab_checks"]):
                if m.is_tab_visible(key, idx) != cb.isChecked():
                    if not m.set_tab_visible(key, idx, cb.isChecked()):
                        cb.setChecked(True)
            m.set_visible(key, w["visible"].isChecked())
            m.set_width(key, w["width"].value())
        self._sync_from_manager()
        if self.window() is not None and hasattr(self.window(), "statusBar"):
            self.window().statusBar().showMessage("窗口设置已应用", 4000)

    def _on_accept(self) -> None:
        self.apply()
        self.manager.save_layout()
        self.accept()

    def _on_reset(self) -> None:
        self.manager.reset_layout()
        self._sync_from_manager()
