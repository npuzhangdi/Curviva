"""右侧「属性窗口」顶部的选中对象属性摘要。

随工作区当前激活窗口自动更新：
表格 → 名称 / 行列数 / 所在文件夹；
图形 → 名称 / 页面尺寸与 DPI / 所在文件夹；
图片 → 名称 / 缩放与文件 / 所在文件夹。
"""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SelectionSummaryPanel(QWidget):
    """显示工作区中选中文件（表格 / 图形 / 图片）的属性摘要。"""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setObjectName("summaryPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(3)

        self.title = QLabel("未选中文档")
        self.title.setObjectName("summaryTitle")
        self.line1 = QLabel("")
        self.line1.setObjectName("summaryLine")
        self.line2 = QLabel("")
        self.line2.setObjectName("summaryLine")
        self.line3 = QLabel("")
        self.line3.setObjectName("summaryLine")
        for label in (self.title, self.line1, self.line2, self.line3):
            label.setWordWrap(True)
            root.addWidget(label)
        root.addStretch(1)

    # ------------------------------------------------------------------
    def set_context(self, kind: str, doc_id: str, title: str) -> None:
        labels = {"sheet": "工作表", "graph": "图形窗口", "image": "图片窗口"}
        if kind not in labels:
            self.title.setText("未选中文档")
            self.line1.setText("在工作区点击任意窗口，")
            self.line2.setText("此处将显示它的属性摘要。")
            self.line3.setText("")
            return
        ws = self.app.workspace
        folder = ""
        node = (self.app.workspace.tree.node_for_document(doc_id)
                if kind in ("graph", "image") else
                self.app.workspace.tree.node_for_ref(doc_id))
        if node is not None:
            folder = ws.path_of_dataset(node.ref) if kind == "sheet" else \
                ws.path(node.id)

        self.title.setText(f"{title or '未命名'}")
        if kind == "sheet":
            ds = self.app.core.get_dataset(doc_id)
            if ds is None:
                return
            self.line1.setText("类型：工作簿 (Book)")
            self.line2.setText(
                f"{ds.row_count()} 行 × {len(ds.column_order)} 列　·　"
                f"公式列 {len(ds.formulas)} 个")
            self.line3.setText(f"所在文件夹：{folder or '项目根'}")
        elif kind == "graph":
            doc = self.app.graphs.get(doc_id)
            if doc is None:
                return
            self.line1.setText("类型：图形窗口")
            self.line2.setText(
                f"{doc.display_size()}　·　{int(doc.dpi)} DPI")
            self.line3.setText(f"所在文件夹：{folder or '项目根'}")
        else:
            doc = self.app.graphs.get(doc_id)
            if doc is None:
                return
            import os
            self.line1.setText("类型：图片窗口")
            self.line2.setText(
                f"缩放 {int(doc.zoom)}%　·　"
                f"{os.path.basename(doc.image_path) or '未导入图片'}")
            self.line3.setText(f"所在文件夹：{folder or '项目根'}")
