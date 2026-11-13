"""Origin 风格「项目资源管理器」面板（最左侧独立可停靠窗口）。

项目视图：项目根 → 文件夹（可嵌套） → 表格 / 工作簿 → 数据列；
工作台视图：按「数据表 / 图形 / 最近操作」分组的扁平总览。

树上可新建文件夹与空白表格、导入 CSV/Excel/剪贴板、重命名、复制、
删除、拖拽归类、导出，以及直接对表格执行插值、平滑、微积分、寻峰等
数据处理；所有结构随 .cvproj 保存并支持撤销重做。
"""

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from curviva.config.plot_config import DEFAULT_COLORS, CurveConfig
from curviva.ui import theme
from curviva.ui.panels.data_dialogs import DataPreviewDialog, ExcelSheetDialog
from curviva.ui.panels.sheet_dialog import SheetEditorDialog
from curviva.ui.panels.workspace_dialogs import NewSheetDialog, OperationDialog
from curviva.workspace.model import (
    DOCUMENT_KINDS,
    KIND_FOLDER,
    KIND_GRAPH,
    KIND_IMAGE,
    KIND_ROOT,
    KIND_SHEET,
    ROOT_ID,
)

ROLE_ID = Qt.UserRole
ROLE_KIND = Qt.UserRole + 1
ROLE_REF = Qt.UserRole + 2

# 右键「数据处理」常用快捷入口（完整列表在对话框内仍可切换）
QUICK_OPS = [
    ("插值 / 等间距重采样", "resample"),
    ("Savitzky–Golay 平滑", "savgol"),
    ("移动平均", "moving"),
    ("归一化", "normalize"),
    ("基线扣除", "baseline"),
    ("数值微分", "derivative"),
    ("累积积分", "integral"),
    ("FFT 幅度谱", "fft"),
    ("寻峰 / 峰面积", "find_peaks"),
    ("描述统计", "describe"),
]


class ExplorerPanel(QWidget):
    """项目 / 工作台树状视图。"""

    structure_changed = Signal(str)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._updating = False
        self._build_ui()
        self._connect()
        self.refresh_from_app()

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # 视图切换（项目 / 工作台）不再用下拉框占位，改为右键菜单切换；
        # 控件保留在内部以便复用原有刷新逻辑。
        self.view_combo = QComboBox()
        self.view_combo.addItem("项目", "project")
        self.view_combo.addItem("工作台", "workspace")
        self.view_combo.hide()

        # ---- Origin 项目管理器布局：上方文件夹树 + 下方文件夹内容 ----
        from PySide6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)

        self.tree = QTreeWidget()
        self.tree.setObjectName("explorerTree")
        self.tree.setHeaderLabels(["文件夹", "信息"])
        self.tree.setColumnWidth(0, 96)
        self.tree.header().setStretchLastSection(True)
        self.tree.setIconSize(QSize(13, 13))
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setDefaultDropAction(Qt.MoveAction)
        self.tree.setMinimumWidth(120)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        splitter.addWidget(self.tree)

        self.contents = QTreeWidget()
        self.contents.setObjectName("explorerContents")
        self.contents.setHeaderLabels(["名称", "大小", "注解"])
        self.contents.setColumnWidth(0, 74)
        self.contents.setColumnWidth(1, 40)
        self.contents.setIconSize(QSize(12, 12))
        self.contents.setSelectionMode(QAbstractItemView.SingleSelection)
        self.contents.setContextMenuPolicy(Qt.CustomContextMenu)
        self.contents.setAlternatingRowColors(True)
        self.contents.setMinimumWidth(120)
        self.contents.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        splitter.addWidget(self.contents)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([320, 260])

        self.setMinimumWidth(150)
        root.addWidget(splitter, 1)

    def _connect(self) -> None:
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemDoubleClicked.connect(self._on_tree_double_click)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.contents.customContextMenuRequested.connect(self._on_contents_menu)
        self.contents.itemDoubleClicked.connect(self._on_contents_double_click)
        self.tree.itemClicked.connect(lambda *_: setattr(self, "_last_focus", "tree"))
        self.contents.itemClicked.connect(
            lambda *_: setattr(self, "_last_focus", "contents"))
        self._last_focus = "tree"

    # ------------------------------------------------------------------
    # 图标与树构建
    # ------------------------------------------------------------------

    def _icon(self, kind: str, numeric: bool = True):
        style = self.style()
        if kind == KIND_ROOT:
            return style.standardIcon(QStyle.SP_DesktopIcon)
        if kind == KIND_FOLDER:
            return style.standardIcon(QStyle.SP_DirIcon)
        if kind == KIND_SHEET:
            return theme.origin_icon("book")
        if kind == KIND_GRAPH:
            return theme.origin_icon("graph")
        if kind == KIND_IMAGE:
            return theme.origin_icon("image")
        if kind == "column":
            return theme.dot_icon(theme.C_BLUE if numeric else theme.C_ORANGE, 10)
        if kind == "group":
            return style.standardIcon(QStyle.SP_DirOpenIcon)
        if kind == "curve":
            return theme.dot_icon(theme.C_VIOLET, 10)
        return theme.dot_icon(theme.C_GREEN, 10)

    def _item(self, text: str, info: str, kind: str,
              node_id: str = "", ref: str = "", icon_kind: str = None,
              numeric: bool = True, draggable: bool = False) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text, info])
        item.setData(0, ROLE_ID, node_id)
        item.setData(0, ROLE_KIND, kind)
        item.setData(0, ROLE_REF, ref)
        item.setIcon(0, self._icon(icon_kind or kind, numeric))
        if draggable:
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
        else:
            item.setFlags(item.flags() & ~Qt.ItemIsDragEnabled)
        return item

    def _save_expanded(self) -> None:
        if self.view_combo.currentData() != "project":
            return
        for i in range(self.tree.topLevelItemCount()):
            self._save_expanded_rec(self.tree.topLevelItem(i))

    def _save_expanded_rec(self, item: QTreeWidgetItem) -> None:
        node_id = item.data(0, ROLE_ID)
        node = self.app.workspace.node(node_id) if node_id else None
        if node is not None:
            node.expanded = item.isExpanded()
        for i in range(item.childCount()):
            self._save_expanded_rec(item.child(i))

    def refresh_from_app(self) -> None:
        """由面板控制器在每次全局刷新时调用：同步数据集 + 重建树。"""
        self.app.workspace.sync()
        self._refresh_tree()

    def _refresh_tree(self) -> None:
        self._save_expanded()
        _, keep_id, _, _ = self._current()
        self.tree.blockSignals(True)
        self.tree.clear()
        if self.view_combo.currentData() == "workspace":
            self._populate_workspace()
            self.tree.setDragEnabled(False)
            self.tree.setAcceptDrops(False)
        else:
            self._populate_project()
            self.tree.setDragEnabled(True)
            self.tree.setAcceptDrops(True)
        self.tree.blockSignals(False)
        if keep_id:
            self._select_node(keep_id)
        self._refresh_contents()


    def _populate_project(self) -> None:
        """Origin 项目管理器：树上只放项目根与文件夹；内容在下方列表。"""
        ws = self.app.workspace
        root_node = ws.root()
        root_item = self._item(root_node.name, "项目", KIND_ROOT,
                               ROOT_ID, icon_kind=KIND_ROOT, draggable=False)
        self.tree.addTopLevelItem(root_item)
        self._add_folders(root_item, root_node)
        root_item.setExpanded(True)

    def _add_folders(self, parent_item: QTreeWidgetItem, parent_node) -> None:
        for node in parent_node.children:
            if node.kind == KIND_FOLDER:
                info = f"{len(node.children)} 项"
                item = self._item(node.name, info, KIND_FOLDER, node.id,
                                  draggable=True)
                parent_item.addChild(item)
                self._add_folders(item, node)
                item.setExpanded(node.expanded)

    # ------------------------------------------------------------------
    # 文件夹内容列表（Origin：名称 / 大小 / 注解）
    # ------------------------------------------------------------------

    def _selected_folder_id(self) -> str:
        """当前应展示内容的文件夹：优先树选中项，工作台视图用项目根。"""
        if self.view_combo.currentData() == "workspace":
            return ROOT_ID
        _, node_id, kind, ref = self._current()
        if kind in (KIND_FOLDER, KIND_ROOT) and node_id:
            return node_id
        return self.app.workspace.active_folder().id

    def _refresh_contents(self) -> None:
        """内容列表：只显示选中文件夹下的表格 / 图形 / 图片（不显示子文件夹）。"""
        folder_id = self._selected_folder_id()
        folder = self.app.workspace.node(folder_id) or self.app.workspace.root()
        self.contents.blockSignals(True)
        self.contents.clear()
        for node in folder.children:
            if node.kind == KIND_SHEET:
                ds = self.app.core.get_dataset(node.ref)
                if ds is None:
                    continue
                kb = max(1, ds.row_count() * len(ds.column_order) * 8 // 1024)
                self._add_content(node.name, f"{kb}KB",
                                  f"工作簿 · {ds.row_count()} 行 × "
                                  f"{len(ds.column_order)} 列",
                                  KIND_SHEET, node.id, node.ref)
            elif node.kind in DOCUMENT_KINDS:
                doc = self.app.graphs.get(node.ref)
                if doc is None:
                    continue
                if doc.kind == KIND_GRAPH:
                    size, note = doc.display_size(), "图形窗口"
                else:
                    size = "—"
                    if doc.image_path and os.path.isfile(doc.image_path):
                        size = f"{os.path.getsize(doc.image_path) // 1024}KB"
                    note = os.path.basename(doc.image_path) or "未导入图片"
                self._add_content(node.name, size, note, doc.kind,
                                  node.id, node.ref)
        self.contents.blockSignals(False)

    def _add_content(self, name: str, size: str, note: str,
                     kind: str, node_id: str, ref: str) -> None:
        item = QTreeWidgetItem([name, size, note])
        item.setData(0, ROLE_ID, node_id)
        item.setData(0, ROLE_KIND, kind)
        item.setData(0, ROLE_REF, ref)
        item.setIcon(0, self._icon(kind))
        self.contents.addTopLevelItem(item)

    def _contents_current(self):
        item = self.contents.currentItem()
        if item is None:
            return None, "", "", ""
        return (item, item.data(0, ROLE_ID) or "",
                item.data(0, ROLE_KIND) or "", item.data(0, ROLE_REF) or "")

    def _populate_workspace(self) -> None:
        ws = self.app.workspace
        top = self._item(ws.project_name, "工作台", KIND_ROOT, ROOT_ID,
                         icon_kind=KIND_ROOT)
        self.tree.addTopLevelItem(top)

        sheets = self.app.core.datasets()
        g1 = self._item(f"数据表（{len(sheets)}）", "全部工作簿", "group",
                        icon_kind="group")
        top.addChild(g1)
        for ds in sheets:
            path = ws.path_of_dataset(ds.name)
            g1.addChild(self._item(ds.name, path, KIND_SHEET,
                                   ref=ds.name, icon_kind=KIND_SHEET))

        curves = self.app.config.curves
        g2 = self._item(f"图形（{len(curves)} 条曲线）", "绘图区内容", "group",
                        icon_kind="group")
        top.addChild(g2)
        for i, c in enumerate(curves):
            g2.addChild(self._item(c.label or f"曲线 {i + 1}",
                                   f"{c.dataset_name}.{c.y_column} · {c.plot_type}",
                                   "curve", ref=str(i), icon_kind="curve"))

        docs = self.app.graphs.documents()
        g4 = self._item(f"图形 / 图片（{len(docs)}）", "工作区文档", "group",
                        icon_kind="group")
        top.addChild(g4)
        for doc in docs:
            info = (doc.display_size() if doc.kind == KIND_GRAPH
                    else (os.path.basename(doc.image_path) or "未导入图片"))
            node = self.app.workspace.tree.node_for_document(doc.id)
            g4.addChild(self._item(doc.name, info, doc.kind,
                                   node.id if node else "",
                                   ref=doc.id, icon_kind=doc.kind))

        logs = self.app.project.workspace.get("analysis_log", [])[-12:]
        g3 = self._item(f"最近操作（{len(logs)}）", "随项目保存", "group",
                        icon_kind="group")
        top.addChild(g3)
        for text in reversed(logs):
            g3.addChild(self._item(str(text)[:60], "", "log", icon_kind="log"))
        top.setExpanded(True)
        for i in range(top.childCount()):
            top.child(i).setExpanded(True)

    # ------------------------------------------------------------------
    # 选中信息与辅助
    # ------------------------------------------------------------------

    def _current(self):
        item = self.tree.currentItem()
        if item is None:
            return None, "", "", ""
        return (item, item.data(0, ROLE_ID) or "",
                item.data(0, ROLE_KIND) or "", item.data(0, ROLE_REF) or "")

    def _target_folder(self) -> str:
        # 内容列表选中项所在的文件夹优先（Origin 行为：内容属于当前文件夹）
        if self._last_focus == "contents" and \
                self.view_combo.currentData() == "project":
            _, node_id, kind, ref = self._contents_current()
            if kind in DOCUMENT_KINDS and ref:
                parent = self.app.workspace.folder_of_document(ref)
                if parent is not None:
                    return parent.id
            if kind == KIND_SHEET and ref:
                parent = self.app.workspace.folder_of_dataset(ref)
                if parent is not None:
                    return parent.id
            if kind in (KIND_FOLDER, KIND_ROOT) and node_id:
                return node_id
        _, node_id, kind, ref = self._current()
        if kind in (KIND_FOLDER, KIND_ROOT) and node_id:
            return node_id
        if kind in DOCUMENT_KINDS and ref:
            parent = self.app.workspace.folder_of_document(ref)
            if parent is not None:
                return parent.id
        if kind in (KIND_SHEET, "column") and ref:
            parent = self.app.workspace.folder_of_dataset(ref)
            if parent is not None:
                return parent.id
        return self.app.workspace.active_folder().id

    def _focus_tool(self, key: str) -> None:
        ui = getattr(self.window(), "ui", None)
        if ui is not None and hasattr(ui, "focus_tool"):
            ui.focus_tool(key)

    def _focus_property(self, key: str) -> None:
        ui = getattr(self.window(), "ui", None)
        if ui is not None and hasattr(ui, "focus_property"):
            ui.focus_property(key)

    def _on_view_changed(self) -> None:
        self._refresh_tree()

    def _selection(self):
        """按最后点击的列表返回当前选中：(node_id, kind, ref)。"""
        if self._last_focus == "contents":
            _, node_id, kind, ref = self._contents_current()
            if node_id or kind:
                return node_id, kind, ref
        _, node_id, kind, ref = self._current()
        return node_id, kind, ref

    def _on_rename(self) -> None:
        node_id, kind, _ = self._selection()
        if not node_id:
            return
        if kind == KIND_ROOT:
            self._rename_project()
        elif kind in (KIND_FOLDER, KIND_SHEET) + DOCUMENT_KINDS:
            self._rename_node(node_id)
        else:
            QMessageBox.information(self, "提示", "请选中一个文件夹、表格或图形。")

    def _on_delete(self) -> None:
        node_id, kind, ref = self._selection()
        if kind in DOCUMENT_KINDS and ref:
            self._delete_document(ref)
        elif kind in (KIND_FOLDER, KIND_SHEET) and node_id:
            self._delete_node(node_id)
        else:
            QMessageBox.information(self, "提示", "请选中一个文件夹、表格或图形。")

    def _on_current_changed(self, *_args) -> None:
        _, node_id, kind, _ = self._current()
        if kind in (KIND_FOLDER, KIND_ROOT) and node_id:
            self.app.workspace.set_active_folder(node_id)
            self._refresh_contents()

    # ------------------------------------------------------------------
    # 双击（树：项目视图只有文件夹；内容列表：打开文档）
    # ------------------------------------------------------------------

    def _on_tree_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        kind = item.data(0, ROLE_KIND)
        ref = item.data(0, ROLE_REF)
        if kind in (KIND_SHEET, "column"):
            if ref:
                self._open_sheet(ref)
        elif kind in DOCUMENT_KINDS:
            if ref:
                self.app.hook("open_document", ref)
        elif kind == KIND_FOLDER:
            item.setExpanded(not item.isExpanded())
        elif kind == "curve":
            self._focus_property("curve_panel")
        elif kind == "log":
            self._focus_tool("workflow_panel")

    def _on_contents_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        kind = item.data(0, ROLE_KIND)
        ref = item.data(0, ROLE_REF)
        node_id = item.data(0, ROLE_ID)
        if kind == KIND_SHEET:
            if ref:
                self._open_sheet(ref)
        elif kind in DOCUMENT_KINDS:
            if ref:
                self.app.hook("open_document", ref)
        elif kind == KIND_FOLDER and node_id:
            self._select_node(node_id)

    def _on_contents_menu(self, pos) -> None:
        item = self.contents.itemAt(pos)
        if item is not None:
            self.contents.setCurrentItem(item)
        node_id = (item.data(0, ROLE_ID) or "") if item else ""
        kind = (item.data(0, ROLE_KIND) or "") if item else ""
        ref = (item.data(0, ROLE_REF) or "") if item else ""
        menu = QMenu(self)
        if kind == KIND_SHEET:
            self._sheet_menu(menu, node_id, ref)
        elif kind in DOCUMENT_KINDS:
            self._document_menu(menu, kind, ref)
        elif kind == KIND_FOLDER:
            menu.addAction("打开此文件夹（树中定位）",
                           lambda: self._select_node(node_id))
            menu.addAction("在此新建表格", lambda: self._new_sheet(node_id))
            menu.addAction("重命名", lambda: self._rename_node(node_id))
            menu.addAction("删除", lambda: self._delete_node(node_id))
        else:
            menu.addAction("在此新建表格", lambda: self._new_sheet(self._selected_folder_id()))
            menu.addAction("在此新建文件夹", lambda: self._new_folder(self._selected_folder_id()))
        menu.addSeparator()
        menu.addAction("刷新", self.refresh_from_app)
        menu.exec(self.contents.viewport().mapToGlobal(pos))

    def _open_sheet(self, name: str) -> None:
        """优先打开底部 Origin 风格工作表窗口；未装配时回退到旧对话框。"""
        if self.app.core.get_dataset(name) is None:
            return
        ui = getattr(self.window(), "ui", None)
        if ui is not None and hasattr(ui, "open_sheet"):
            ui.open_sheet(name)
            return
        SheetEditorDialog(self.app.core, name, self).exec()
        self.app.refresh("worksheet")

    # ------------------------------------------------------------------
    # 右键菜单
    # ------------------------------------------------------------------

    def _on_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            item = self.tree.topLevelItem(0)
            if item is None:
                return
        self.tree.setCurrentItem(item)
        node_id = item.data(0, ROLE_ID) or ""
        kind = item.data(0, ROLE_KIND) or ""
        ref = item.data(0, ROLE_REF) or ""

        menu = QMenu(self)
        if kind in (KIND_ROOT, KIND_FOLDER):
            self._folder_menu(menu, node_id, kind)
        elif kind == KIND_SHEET:
            self._sheet_menu(menu, node_id, ref)
        elif kind in DOCUMENT_KINDS:
            self._document_menu(menu, kind, ref)
        elif kind == "column":
            menu.addAction("在工作表中打开", lambda: self._open_sheet(ref))
            menu.addAction("公式列设置", lambda: self._focus_tool("project_panel"))
        elif kind == "curve":
            menu.addAction("曲线属性", lambda: self._focus_property("curve_panel"))
        elif kind in ("group", "log"):
            menu.addAction("打开工作台", lambda: self._focus_tool("workflow_panel"))
        menu.addSeparator()
        menu.addAction("切换到工作台视图" if self.view_combo.currentData() == "project"
                       else "切换到项目视图", self.toggle_view)
        menu.addAction("刷新", self.refresh_from_app)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _folder_menu(self, menu: QMenu, node_id: str, kind: str) -> None:
        menu.addAction("在此新建文件夹", lambda: self._new_folder(node_id))
        menu.addAction("在此新建表格", lambda: self._new_sheet(node_id))
        menu.addAction("在此新建图形窗口",
                       lambda: self._new_document(KIND_GRAPH, node_id))
        menu.addAction("在此新建图片窗口",
                       lambda: self._new_document(KIND_IMAGE, node_id))
        imp = menu.addMenu("导入数据到此文件夹")
        imp.addAction("图片文件…", lambda: self._import_image_to(node_id))
        imp.addAction("CSV 文件…", lambda: self._import_csv(node_id))
        imp.addAction("Excel 工作簿…", lambda: self._import_excel(node_id))
        imp.addAction("TXT / DAT 文本（导入向导）…",
                      lambda: self._import_any(node_id, True))
        imp.addAction("任意数据文件…", lambda: self._import_any(node_id, False))
        imp.addAction("从剪贴板粘贴…", lambda: self._paste(node_id))
        menu.addSeparator()
        menu.addAction("设为当前文件夹", lambda: self._set_active(node_id))
        if kind == KIND_ROOT:
            menu.addAction("重命名项目", self._rename_project)
        else:
            menu.addAction("重命名文件夹", lambda: self._rename_node(node_id))
            menu.addAction("删除文件夹（含内容）", lambda: self._delete_node(node_id))
        menu.addSeparator()
        menu.addAction("展开全部", self.tree.expandAll)
        menu.addAction("折叠全部", self._collapse_all)

    def _document_menu(self, menu: QMenu, kind: str, ref: str) -> None:
        menu.addAction("在工作区打开", lambda: self.app.hook("open_document", ref))
        doc = self.app.graphs.get(ref)
        if doc is None:
            return
        if kind == KIND_GRAPH:
            menu.addAction("图形尺寸 / DPI 设置…",
                           lambda: self._open_size_dialog(ref))
            menu.addAction("导出此图形 (PNG)…",
                           lambda: self._export_graph(ref, "png"))
        else:
            menu.addAction("导入 / 更换图片…", lambda: self._import_image(ref))
        menu.addSeparator()
        node = self.app.workspace.tree.node_for_document(ref)
        menu.addAction("重命名", lambda: self._rename_node(node.id if node else ""))
        menu.addAction("删除", lambda: self._delete_document(ref))

    def _open_size_dialog(self, ref: str) -> None:
        wa = self.app.hook("workarea")
        if wa is not None:
            wa.open_size_dialog(ref)

    def _export_graph(self, ref: str, fmt: str = "png") -> None:
        wa = self.app.hook("workarea")
        if wa is not None:
            wa.export_graph(ref, fmt)

    def _sheet_menu(self, menu: QMenu, node_id: str, ref: str) -> None:
        menu.addAction("在工作表中打开", lambda: self._open_sheet(ref))
        menu.addAction("预览数据", lambda: self._preview(ref))
        menu.addSeparator()
        ops = menu.addMenu("数据处理")
        for label, key in QUICK_OPS:
            ops.addAction(label, lambda k=key, r=ref, n=node_id:
                          self._open_operation(r, n, k))
        ops.addAction("全部处理操作…", lambda: self._open_operation(ref, node_id, ""))
        menu.addAction("生成曲线", lambda: self._add_curve(ref))
        menu.addAction("公式列设置", lambda: self._focus_tool("project_panel"))
        menu.addSeparator()
        menu.addAction("重命名表格", lambda: self._rename_node(node_id))
        menu.addAction("复制表格", lambda: self._duplicate(ref, node_id))
        menu.addAction("导出 CSV…", lambda: self._export_csv(ref))
        menu.addAction("删除表格", lambda: self._delete_node(node_id))

    def _collapse_all(self) -> None:
        self.tree.collapseAll()
        root = self.tree.topLevelItem(0)
        if root is not None:
            root.setExpanded(True)

    # ------------------------------------------------------------------
    # 供菜单栏调用的公开入口
    # ------------------------------------------------------------------

    def create_sheet_here(self) -> None:
        self._new_sheet(self._target_folder())

    def create_folder_here(self) -> None:
        self._new_folder(self._target_folder())

    def create_graph_here(self) -> None:
        self._new_document(KIND_GRAPH, self._target_folder())

    def create_image_here(self) -> None:
        self._new_document(KIND_IMAGE, self._target_folder())

    def create_project(self) -> None:
        """新建项目：清空全部内容，并允许给项目命名。"""
        ret = QMessageBox.question(
            self, "新建项目",
            "新建项目会清空当前全部数据、图形与窗口（可用 Ctrl+Z 撤销）。\n确定继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        name, ok = QInputDialog.getText(self, "新建项目", "项目名称：",
                                        text="未命名项目")
        if not ok:
            return
        self.app.checkpoint("项目管理：新建项目")
        self.app.project.new()
        if name.strip():
            self.app.workspace.set_project_name(name.strip())
        self.app.refresh("new_project")
        wa = self.app.hook("workarea")
        if wa is not None:
            wa.area.close_all()          # Origin 行为：新建项目后工作区为空
        self.app.status(f"已新建项目：{name.strip() or '未命名项目'}")

    # --- 图形 / 图片文档 --------------------------------------------

    def _new_document(self, kind: str, parent_id: str) -> None:
        label = "图形" if kind == KIND_GRAPH else "图片"
        base = self.app.workspace.tree.unique_child_name(
            parent_id or ROOT_ID, f"新建{label}")
        name, ok = QInputDialog.getText(self, f"新建{label}窗口",
                                        f"{label}名称：", text=base)
        if not ok or not name.strip():
            return
        self.app.checkpoint(f"项目管理：新建{label}")
        doc = self.app.graphs.new_document(kind, name.strip(), parent_id)
        self.app.hook("open_document", doc.id)
        self.app.refresh("new_document")
        node = self.app.workspace.tree.node_for_document(doc.id)
        if node is not None:
            self._select_node(node.id)

    def _import_image_to(self, folder_id: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入图片到文件夹", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp *.svg);;"
            "所有文件 (*.*)")
        if not path:
            return
        self.app.checkpoint("项目管理：导入图片")
        doc = self.app.graphs.new_image("", folder_id, path=path)
        self.app.hook("open_document", doc.id)
        self.app.refresh("import_image")
        self.app.status(f"已导入图片：{doc.name}")

    def _import_image(self, doc_id: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "更换图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp *.svg);;"
            "所有文件 (*.*)")
        if not path:
            return
        self.app.checkpoint("图片：更换文件")
        self.app.graphs.set_image_path(doc_id, path)
        self.app.hook("open_document", doc_id)

    def _delete_document(self, doc_id: str) -> None:
        doc = self.app.graphs.get(doc_id)
        if doc is None:
            return
        ret = QMessageBox.question(
            self, "确认删除", f"确定删除「{doc.name}」及其窗口吗？\n可用 Ctrl+Z 撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self.app.checkpoint("项目管理：删除文档")
        self.app.graphs.remove(doc_id)
        self.app.refresh("delete_document")

    def show_and_focus(self) -> None:
        self.tree.setFocus()
        self.app.status(f"当前文件夹：{self.app.workspace.active_folder().name}")

    # ------------------------------------------------------------------
    # 节点操作
    # ------------------------------------------------------------------

    def _set_active(self, node_id: str) -> None:
        self.app.workspace.set_active_folder(node_id)

        self.app.status(f"当前文件夹：{self.app.workspace.path(node_id)}")

    def _new_folder(self, parent_id: str) -> None:
        name, ok = QInputDialog.getText(
            self, "新建文件夹", "文件夹名称：", text=self.app.workspace.tree.unique_child_name(
                parent_id or ROOT_ID, "新建文件夹"))
        if not ok or not name.strip():
            return
        self.app.checkpoint("项目树：新建文件夹")
        node = self.app.workspace.new_folder(parent_id or ROOT_ID, name.strip())
        self.app.refresh("explorer_folder")
        self._select_node(node.id)

    def _new_sheet(self, parent_id: str) -> None:
        folder = parent_id or ROOT_ID
        dlg = NewSheetDialog(self.app.workspace.path(folder), self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        self.app.checkpoint("项目树：新建表格")
        node = self.app.workspace.new_sheet(folder, v["name"], v["rows"], v["columns"])
        self.app.refresh("explorer_sheet")
        self._select_node(node.id)
        self._open_sheet(node.ref)

    def _select_node(self, node_id: str) -> None:
        for i in range(self.tree.topLevelItemCount()):
            found = self._find_item(self.tree.topLevelItem(i), node_id)
            if found is not None:
                self.tree.setCurrentItem(found)
                found.setExpanded(True)
                return
        # 文档 / 表格节点在内容列表中定位
        for i in range(self.contents.topLevelItemCount()):
            item = self.contents.topLevelItem(i)
            if item.data(0, ROLE_ID) == node_id:
                self.contents.setCurrentItem(item)
                return

    def _find_item(self, item: QTreeWidgetItem, node_id: str):
        if item.data(0, ROLE_ID) == node_id:
            return item
        for i in range(item.childCount()):
            found = self._find_item(item.child(i), node_id)
            if found is not None:
                return found
        return None

    def _rename_project(self) -> None:
        name, ok = QInputDialog.getText(
            self, "重命名项目", "项目名称：", text=self.app.workspace.project_name)
        if not ok or not name.strip():
            return
        self.app.checkpoint("项目树：重命名项目")
        self.app.workspace.set_project_name(name.strip())
        self.app.refresh("explorer_rename")
        self.app.status(f"项目已重命名为：{name.strip()}")

    def _rename_node(self, node_id: str) -> None:
        node = self.app.workspace.node(node_id)
        if node is None:
            return
        name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=node.name)
        if not ok or not name.strip() or name.strip() == node.name:
            return
        self.app.checkpoint("项目树：重命名节点")
        self.app.workspace.rename(node_id, name.strip())
        self.app.refresh("explorer_rename")

    def _delete_node(self, node_id: str) -> None:
        node = self.app.workspace.node(node_id)
        if node is None or node.kind == KIND_ROOT:
            return
        extra = ("及其全部子文件夹与表格" if node.kind == KIND_FOLDER else "及其数据")
        ret = QMessageBox.question(
            self, "确认删除", f"确定删除「{node.name}」{extra}吗？\n"
            "引用被删表格的曲线也会一并移除，可用 Ctrl+Z 撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self.app.checkpoint("项目树：删除节点")
        self.app.workspace.remove(node_id, delete_data=True)
        self.app.refresh("explorer_delete")

    def _duplicate(self, ref: str, node_id: str) -> None:
        ds = self.app.core.get_dataset(ref)
        if ds is None:
            return
        self.app.checkpoint("项目树：复制表格")
        cols = {c: ds.columns[c] for c in ds.column_order}
        clone = self.app.core.add_result_dataset(f"{ref} 副本", cols, ds.formulas)
        folder = self.app.workspace.folder_of_dataset(ref)
        self.app.workspace.attach_dataset(clone.name, folder.id if folder else None)
        self.app.refresh("explorer_duplicate")
        self.app.status(f"已复制为「{clone.name}」")

    def _preview(self, ref: str) -> None:
        ds = self.app.core.get_dataset(ref)
        if ds is not None:
            DataPreviewDialog(ds, self).exec()

    def _export_csv(self, ref: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出表格", f"{ref}.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            self.app.core.export_csv(ref, path)
            self.app.status(f"已导出：{path}")
        except Exception as e:                        # noqa: BLE001
            QMessageBox.warning(self, "导出失败", str(e))

    def _add_curve(self, ref: str) -> None:
        """生成曲线：统一走工作表域（智能选列），并打开图形窗口。"""
        ui = getattr(self.window(), "ui", None)
        if ui is not None and getattr(ui, "worksheet", None) is not None:
            ui.worksheet.add_curve(ref)
            if getattr(ui, "workarea", None) is not None:
                ui.workarea.open_graph()
            return
        cols = self.app.core.columns(ref)
        numeric = self.app.core.numeric_columns(ref)
        if not cols:
            return
        x = "X" if "X" in cols else (numeric[0] if numeric else cols[0])
        ys = [c for c in numeric if c != x]
        y = ys[0] if ys else (cols[-1] if len(cols) > 1 else cols[0])
        self.app.checkpoint("项目树：生成曲线")
        n = len(self.app.config.curves)
        self.app.config.curves.append(CurveConfig(
            label=f"{ref}·{y}", dataset_name=ref, x_column=x, y_column=y,
            plot_type="line", color=DEFAULT_COLORS[n % len(DEFAULT_COLORS)]))
        self.app.refresh("explorer_curve")
        self.app.status(f"已把「{ref}.{y}」加入绘图区")

    # ------------------------------------------------------------------
    # 数据导入 / 处理
    # ------------------------------------------------------------------

    def toggle_view(self) -> None:
        """在项目视图 / 工作台视图之间切换（右键菜单入口）。"""
        self.view_combo.setCurrentIndex(
            0 if self.view_combo.currentData() == "workspace" else 1)

    def _on_import_menu(self) -> None:
        menu = QMenu(self)
        folder = self._target_folder()
        menu.addAction("导入 CSV…", lambda: self._import_csv(folder))
        menu.addAction("导入 Excel 工作簿…", lambda: self._import_excel(folder))
        menu.addAction("文本导入向导…", lambda: self._import_any(folder, True))
        menu.addAction("打开任意数据文件…", lambda: self._import_any(folder, False))
        menu.addAction("从剪贴板粘贴…", lambda: self._paste(folder))
        menu.addAction("导入图片文件…", lambda: self._import_image_to(folder))
        menu.addSeparator()
        menu.addAction("新建图形窗口", lambda: self._new_document(KIND_GRAPH, folder))
        menu.addAction("新建图片窗口", lambda: self._new_document(KIND_IMAGE, folder))
        menu.exec(self.mapToGlobal(self.rect().center()))

    def _import_csv(self, folder_id: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 CSV 到文件夹", "", "CSV 文件 (*.csv);;所有文件 (*.*)")
        if not path:
            return
        try:
            self.app.checkpoint("项目树：导入 CSV")
            ds = self.app.core.import_csv(path)
        except Exception as e:                        # noqa: BLE001
            QMessageBox.warning(self, "导入失败", str(e))
            return
        self._attach_new(ds.name, folder_id, f"已导入「{ds.name}」")

    def _import_excel(self, folder_id: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 Excel 工作簿", "",
            "Excel 工作簿 (*.xlsx *.xlsm);;所有文件 (*.*)")
        if not path:
            return
        try:
            sheets = self.app.core.excel_sheets(path)
            dlg = ExcelSheetDialog(sheets, self)
            if dlg.exec() != ExcelSheetDialog.Accepted or not dlg.selected_sheets():
                return
            self.app.checkpoint("项目树：导入 Excel")
            imported = self.app.core.import_excel(path, dlg.selected_sheets())
        except Exception as e:                        # noqa: BLE001
            QMessageBox.warning(self, "导入失败", str(e))
            return
        for ds in imported:
            self.app.workspace.attach_dataset(ds.name, folder_id)
        self.app.refresh("explorer_import")
        self.app.status(f"已导入 {len(imported)} 张表格到当前文件夹")

    def _import_any(self, folder_id: str, wizard: bool = False) -> None:
        """统一打开 CSV/TXT/DAT/TSV/ASC/Excel，并归入当前文件夹。"""
        from curviva.ui.panels.import_dialog import open_data_file
        imported = open_data_file(self, self.app, wizard=wizard,
                                  folder=folder_id)
        if imported:
            self.app.refresh("explorer_import")
            self.app.status(f"已导入 {len(imported)} 张表格到当前文件夹")

    def _paste(self, folder_id: str) -> None:
        text = QGuiApplication.clipboard().text()
        try:
            self.app.checkpoint("项目树：粘贴数据")
            ds = self.app.core.import_clipboard(text)
        except Exception as e:                        # noqa: BLE001
            QMessageBox.warning(self, "粘贴失败", str(e))
            return
        self._attach_new(ds.name, folder_id, f"已粘贴生成「{ds.name}」")

    def _attach_new(self, name: str, folder_id: str, message: str) -> None:
        self.app.workspace.attach_dataset(name, folder_id)
        self.app.refresh("explorer_import")
        self.app.status(message)

    def _open_operation(self, ref: str, node_id: str, key: str) -> None:
        folder = self.app.workspace.folder_of_dataset(ref)
        dlg = OperationDialog(
            self.app, ref, folder.id if folder else None, key, self)
        dlg.exec()
        self.app.refresh("explorer_operation")

    # ------------------------------------------------------------------
    # 拖拽归类（项目视图）
    # ------------------------------------------------------------------

    def dropEvent(self, event) -> None:                # noqa: N802 (Qt 命名)
        if self.view_combo.currentData() != "project":
            event.ignore()
            return
        try:
            point = event.position().toPoint()
        except AttributeError:                        # Qt5 兼容
            point = event.pos()
        target = self.tree.itemAt(point)
        source = self.tree.currentItem()
        if source is None or target is None:
            event.ignore()
            return
        src_id = source.data(0, ROLE_ID)
        src_kind = source.data(0, ROLE_KIND)
        dst_id = target.data(0, ROLE_ID)
        dst_kind = target.data(0, ROLE_KIND)
        if not src_id or src_kind == KIND_ROOT:
            event.ignore()
            return
        if dst_kind in (KIND_SHEET, "column") + DOCUMENT_KINDS:
            parent = self.app.workspace.tree.parent_of(dst_id)[0]
            dst_id = parent.id if parent else ROOT_ID
        elif dst_kind not in (KIND_ROOT, KIND_FOLDER):
            event.ignore()
            return
        event.accept()                                # 不让 Qt 直接搬动 item
        if self.app.workspace.move(src_id, dst_id):
            self.app.checkpoint("项目树：拖拽归类")
            self.app.refresh("explorer_move")
            self._select_node(src_id)
