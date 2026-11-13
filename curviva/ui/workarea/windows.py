"""工作区三种文档子窗口：表格 / 图形 / 图片（外加多表工作簿）。"""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QMdiSubWindow,
    QPushButton,
    QScrollArea,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from curviva.graphs.model import KIND_GRAPH
from curviva.ui import theme
from curviva.ui.canvas_widget import PlotCanvas
from curviva.ui.worksheet.worksheet_grid import WorksheetGrid
from curviva.ui.workarea.graph_editor import GraphEditor


def _btn(text: str, tone: str, slot) -> QPushButton:
    b = QPushButton(text)
    if tone == "accent":
        b.setProperty("accent", True)
    elif tone:
        b.setProperty("tone", tone)
    b.clicked.connect(slot)
    return b


class DocumentSubWindow(QMdiSubWindow):
    """所有工作区子窗口的基类：携带文档类型与 id，供窗口管理菜单识别。"""

    def __init__(self, ctl, doc, kind: str):
        super().__init__()
        self.ctl = ctl
        self.app = ctl.app
        self.doc = doc
        self.document = doc               # mdi_area 最小化/显示时使用
        self.doc_kind = kind
        self.doc_id = doc.id
        self.setWindowTitle(doc.name)
        self.setObjectName("docSubWindow")
        # Origin 风格：子窗口标题栏带类型图标 + 右上角三个按钮
        # （最小化 / 最大化·还原 / 关闭）
        self.setWindowFlags(Qt.SubWindow | Qt.WindowTitleHint |
                            Qt.WindowMinMaxButtonsHint |
                            Qt.WindowCloseButtonHint)
        self.setWindowIcon(theme.origin_icon(
            {"sheet": "book", "graph": "graph", "image": "image"}.get(kind, "book")))
        self.setMinimumSize(340, 240)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

    def on_activated(self) -> None:
        pass

    def refresh_document(self) -> None:
        pass

    def closeEvent(self, event):                    # noqa: N802 (Qt 命名)
        try:
            self.ctl.on_window_closed(self)
        except Exception:                          # noqa: BLE001
            pass
        super().closeEvent(event)


# ----------------------------------------------------------------------
class SheetSubWindow(DocumentSubWindow):
    """Origin 式工作簿（Book）窗口：网格 + 底部工作表标签 + 新增按钮。

    一个 Book 对应一组数据集：主表（如 Book1）与其续表（Book1-2、
    Book1-3 …）。底部标签显示 Sheet1 / Sheet2 …，可切换、可新增。
    """

    def __init__(self, ctl, name: str):
        doc = _PseudoDoc(name)
        super().__init__(ctl, doc, "sheet")
        sheet_ctl = ctl.sheet_controller
        self.sheet_ctl = sheet_ctl
        self._base = name            # Book 基准名（窗口身份，不随切换变化）
        self._current = name         # 当前显示的工作表（数据集名）

        widget = QWidget()
        widget.setObjectName("sheetWindow")
        root = QVBoxLayout(widget)
        root.setContentsMargins(4, 4, 4, 2)
        root.setSpacing(2)
        self.grid = WorksheetGrid(sheet_ctl, name)
        self.grid.selection_info_changed.connect(self._on_selection_info)

        self.info = QLabel(name)
        self.info.setObjectName("sheetStatus")
        root.addWidget(self.grid, 1)

        # ---- Origin 式底部工作表标签：Sheet1 / Sheet2 … + 新增 ----
        bar_row = QHBoxLayout()
        bar_row.setSpacing(3)
        self.sheet_tabs = QTabBar()
        self.sheet_tabs.setObjectName("sheetTabs")
        self.sheet_tabs.setExpanding(False)
        self.sheet_tabs.setDrawBase(False)
        self.sheet_tabs.currentChanged.connect(self._on_tab_changed)
        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setToolTip("在此工作簿中新增一张工作表")
        add_btn.setAutoRaise(True)
        add_btn.setFixedWidth(20)
        add_btn.clicked.connect(self._add_sheet)
        bar_row.addWidget(add_btn)
        bar_row.addWidget(self.sheet_tabs, 1)
        bar_row.addWidget(self.info)
        root.addLayout(bar_row)

        self.setWidget(widget)
        self.resize(880, 560)
        self.info.setText(getattr(self.grid, "_status", name))
        self._rebuild_sheet_bar(select=self._current)

    def _on_selection_info(self, text: str) -> None:
        self.info.setText(text)

    # ------------------------------------------------------------------
    # 工作表（Book 的 Sheet）管理
    # ------------------------------------------------------------------

    @property
    def dataset_name(self) -> str:
        return self._current

    def _book_sheets(self) -> list:
        """本工作簿包含的全部数据表：主表 + BookN-2 / BookN-3 …"""
        base = self._base
        core = self.sheet_ctl.core
        names = set(core.dataset_names())
        sheets = []
        if base in names:
            sheets.append(base)
        i = 2
        while f"{base}-{i}" in names:
            sheets.append(f"{base}-{i}")
            i += 1
        return sheets

    def _rebuild_sheet_bar(self, select: str = "") -> None:
        self.sheet_tabs.blockSignals(True)
        while self.sheet_tabs.count():
            self.sheet_tabs.removeTab(self.sheet_tabs.count() - 1)
        sheets = self._book_sheets()
        select = select or self._current
        current = 0
        for i, name in enumerate(sheets):
            label = f"Sheet{i + 1}"
            self.sheet_tabs.addTab(label)
            self.sheet_tabs.setTabToolTip(i, name)
            if name == select:
                current = i
        self.sheet_tabs.blockSignals(False)
        self.sheet_tabs.setCurrentIndex(current)

    def _on_tab_changed(self, index: int) -> None:
        sheets = self._book_sheets()
        if not (0 <= index < len(sheets)):
            return
        name = sheets[index]
        if name == self._current:
            return
        self._switch_sheet(name)

    def _switch_sheet(self, name: str) -> None:
        """切换到工作簿中的另一张表：替换网格控件并刷新（标题保持 Book 名）。"""
        if self.sheet_ctl.core.get_dataset(name) is None:
            return
        if name == self._current:
            return
        self._current = name
        old = self.grid
        new_grid = WorksheetGrid(self.sheet_ctl, name)
        new_grid.selection_info_changed.connect(self._on_selection_info)
        root = old.parentWidget().layout()
        idx = root.indexOf(old)
        root.insertWidget(idx, new_grid, 1)
        root.removeWidget(old)
        old.deleteLater()
        self.grid = new_grid
        self.info.setText(getattr(new_grid, "_status", name))

    def _add_sheet(self) -> None:
        """在此工作簿中新增一张表（BookN-i），并自动挂到同一文件夹。"""
        base = self._base
        core = self.sheet_ctl.core
        i = 2
        while f"{base}-{i}" in set(core.dataset_names()):
            i += 1
        name = f"{base}-{i}"
        try:
            core.create_sheet(name, 32, 2)
        except Exception:                          # noqa: BLE001
            return
        ws = getattr(self.ctl.app, "workspace", None)
        if ws is not None:
            folder = ws.folder_of_dataset(base)
            ws.attach_dataset(name, folder.id if folder else None)
        self.app.checkpoint("工作簿：新增工作表")
        self._rebuild_sheet_bar(select=name)
        self._switch_sheet(name)

    # ------------------------------------------------------------------

    def refresh_document(self) -> None:
        self._rebuild_sheet_bar(select=self._current)
        self.grid.refresh()

    def _copy(self):
        self.grid.copy_selection(False)

    def _paste(self):
        self.grid.paste_from_clipboard()

    def _add_curve(self):
        self.sheet_ctl.add_curve(self.dataset_name)
        self.ctl.open_graph()

    def _operation(self, key: str = ""):
        self.sheet_ctl.open_operation(self.dataset_name, key)

    def _fit(self):
        self.ctl.quick_fit(self.dataset_name)

    def _export(self):
        self.sheet_ctl.export_csv(self.dataset_name)

    def add_row_toolbar(self):
        return None


class _PseudoDoc:
    """表格窗口复用数据集名作为 doc_id，用一个轻量对象承载公共属性。"""

    def __init__(self, name: str):
        self.id = name
        self.name = name
        self.minimized = False
        self.visible = True


# ----------------------------------------------------------------------
class GraphSubWindow(DocumentSubWindow):
    """图形窗口：独立 Figure + 画布 + Origin 式鼠标编辑器。"""

    def __init__(self, ctl, doc):
        super().__init__(ctl, doc, KIND_GRAPH)
        self.canvas = PlotCanvas(renderer=self.app.render)
        self.editor = GraphEditor(self.canvas, self.app, doc, callbacks={
            "status": self.app.status,
            "curve_selected": self._on_curve_selected,
            "focus_property": ctl.ui.focus_property if ctl.ui else (lambda *_: None),
            "size_dialog": lambda: ctl.open_size_dialog(doc.id),
            "export": lambda fmt: ctl.export_graph(doc.id, fmt),
        })
        self.canvas.post_render_callbacks.append(self.editor.apply_overlays)
        self.canvas.double_click_hook = self.editor.on_qt_double_click

        widget = QWidget()
        widget.setObjectName("graphWindow")
        root = QVBoxLayout(widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.canvas, 1)
        self.setWidget(widget)
        self.apply_size()
        self.render()

    # ------------------------------------------------------------------
    def _on_curve_selected(self, index: int) -> None:
        ctl = self.ctl
        if ctl.ui is None:
            return
        ctl.ui.focus_property("curve_panel")
        panel = ctl.ui.panels.curve_panel
        if hasattr(panel, "curve_list") and 0 <= index < panel.curve_list.count():
            panel.curve_list.setCurrentRow(index)

    def apply_size(self) -> None:
        w, h = self.doc.size_inches()
        self.canvas.figure.set_size_inches(w, h, forward=False)
        self.resize(max(480, int(w * 80)), max(380, int(h * 80)))

    def render(self) -> None:
        self.canvas.render(self.app.config, self.app.datasets)

    def set_mode(self, mode: str) -> None:
        self.editor.set_mode(mode)
        self.app.graphs.set_mode(self.doc.id, mode)

    def refresh_document(self) -> None:
        self.setWindowTitle(self.doc.name)
        self.apply_size()
        self.render()

    def export(self, path: str, fmt: str = "png") -> None:
        self.canvas.export_image(path, max(int(self.doc.dpi), 300),
                                 size=self.doc.size_inches())


# ----------------------------------------------------------------------
class ImageSubWindow(DocumentSubWindow):
    """图片窗口：显示外部图片，可缩放、适应窗口、另存。"""

    def __init__(self, ctl, doc):
        super().__init__(ctl, doc, "image")
        self.pixmap = QPixmap()
        widget = QWidget()
        widget.setObjectName("imageWindow")
        root = QVBoxLayout(widget)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        row = QHBoxLayout()
        row.setSpacing(5)
        row.addWidget(_btn("导入图片…", "accent", self._choose_image))
        row.addWidget(_btn("适应窗口", "cyan", self.fit_window))
        row.addWidget(_btn("原始大小", "", self.original_size))
        row.addSpacing(6)
        row.addWidget(QLabel("缩放"))
        self.zoom_combo = QComboBox()
        for z in (25, 50, 75, 100, 150, 200, 300, 400):
            self.zoom_combo.addItem(f"{z}%", z)
        self.zoom_combo.currentIndexChanged.connect(self._on_zoom)
        row.addWidget(self.zoom_combo)
        row.addStretch(1)
        row.addWidget(_btn("另存为…", "", self._save_as))
        root.addLayout(row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.view = QLabel("尚未导入图片。点「导入图片…」选择 PNG / JPG / BMP / SVG 等文件。")
        self.view.setObjectName("imageView")
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setWordWrap(True)
        self.scroll.setWidget(self.view)
        root.addWidget(self.scroll, 1)

        self.info = QLabel()
        self.info.setObjectName("hintCard")
        root.addWidget(self.info)
        self.setWidget(widget)
        self.resize(720, 480)
        self.refresh_document()

    # ------------------------------------------------------------------
    def refresh_document(self) -> None:
        self.setWindowTitle(self.doc.name)
        path = self.doc.image_path or ""
        if path and os.path.isfile(path) and self.pixmap.load(path):
            self.show_pixmap()
        else:
            self.pixmap = QPixmap()
            self.view.setText("尚未导入图片，或图片文件已移动。\n"
                              "点「导入图片…」选择 PNG / JPG / BMP / GIF / SVG 等文件。")
            self.view.resize(self.scroll.viewport().size())
            self.info.setText(f"{self.doc.name}　·　未载入图片")
        i = self.zoom_combo.findData(int(self.doc.zoom))
        if i >= 0:
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.setCurrentIndex(i)
            self.zoom_combo.blockSignals(False)

    def show_pixmap(self) -> None:
        if self.pixmap.isNull():
            return
        pm = self.pixmap
        if self.doc.fit_window:
            avail = self.scroll.viewport().size()
            pm = self.pixmap.scaled(max(avail.width() - 16, 100),
                                    max(avail.height() - 16, 100),
                                    Qt.KeepAspectRatio, Qt.SmoothTransformation)
        elif self.doc.zoom != 100:
            f = self.doc.zoom / 100.0
            pm = self.pixmap.scaled(int(self.pixmap.width() * f),
                                    int(self.pixmap.height() * f),
                                    Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.view.setPixmap(pm)
        self.view.resize(pm.size())
        self.info.setText(
            f"{self.doc.name}　·　原图 {self.pixmap.width()} × {self.pixmap.height()} px"
            f"　·　显示 {pm.width()} × {pm.height()} px"
            f"　·　缩放 {self.doc.zoom}%")

    def fit_window(self) -> None:
        self.app.graphs.set_zoom(self.doc.id, self.doc.zoom, fit=True)
        self.show_pixmap()

    def original_size(self) -> None:
        self.app.graphs.set_zoom(self.doc.id, 100, fit=False)
        self.show_pixmap()

    def _on_zoom(self) -> None:
        z = self.zoom_combo.currentData()
        if z:
            self.app.graphs.set_zoom(self.doc.id, z, fit=False)
            self.show_pixmap()

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp *.svg);;"
            "所有文件 (*.*)")
        if not path:
            return
        self.app.checkpoint("图片：导入")
        self.app.graphs.set_image_path(self.doc.id, path)
        self.doc.fit_window = True
        self.refresh_document()

    def _save_as(self) -> None:
        if self.pixmap.isNull():
            QMessageBox.information(self, "提示", "当前没有可保存的图片。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "另存图片",
                                              f"{self.doc.name}.png",
                                              "PNG 图片 (*.png)")
        if path:
            self.pixmap.save(path)

    def resizeEvent(self, event):                   # noqa: N802 (Qt 命名)
        super().resizeEvent(event)
        if self.doc.fit_window and not self.pixmap.isNull():
            self.show_pixmap()


# ----------------------------------------------------------------------
class BookSubWindow(DocumentSubWindow):
    """多表工作簿：把 WorksheetBook（多标签）作为独立子窗口。"""

    def __init__(self, ctl, book):
        doc = _PseudoDoc("book")
        super().__init__(ctl, doc, "book")
        self.setWindowTitle("多表工作簿")
        self.book = book
        self.setWidget(book)
        self.resize(820, 440)

    def refresh_document(self) -> None:
        self.book.sync_from_app()
