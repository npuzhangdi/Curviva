"""图形 / 图片「文档」数据模型（纯 Python，可 JSON 序列化）。

对标 Origin 的 Graph 窗口 / Image 窗口：每个图形、每张图片都是项目里的
一个独立文档，拥有自己的尺寸、DPI、图层标注与选中状态；工作区中间用
MDI 子窗口逐个承载，可最小化、显示、隐藏。

模型不依赖 Qt、matplotlib 或 DataSet，界面只通过 graphs/controller.py 操作。
"""

import uuid
from dataclasses import asdict, dataclass, field

KIND_GRAPH = "graph"
KIND_IMAGE = "image"

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".svg")

# 常用出版尺寸（英寸）
SIZE_PRESETS = [
    ("默认 8 × 6 in", 8.0, 6.0),
    ("单栏 3.5 × 2.6 in", 3.5, 2.6),
    ("双栏 7.0 × 4.5 in", 7.0, 4.5),
    ("A4 纵向 8.27 × 11.69 in", 8.27, 11.69),
    ("A4 横向 11.69 × 8.27 in", 11.69, 8.27),
    ("正方形 6 × 6 in", 6.0, 6.0),
    ("幻灯片 10 × 5.63 in", 10.0, 5.63),
]


def _new_id() -> str:
    return "doc_" + uuid.uuid4().hex[:10]


@dataclass
class Document:
    """一个可放进工作区的文档。kind = graph / image。"""

    id: str = field(default_factory=_new_id)
    name: str = "图形 1"
    kind: str = KIND_GRAPH
    # --- 图形尺寸 ---
    width: float = 8.0                 # 英寸（unit=inch）或毫米（unit=mm）
    height: float = 6.0
    unit: str = "inch"
    dpi: int = 300
    face_color: str = "white"
    # --- 图上直接编辑（Origin 式）产生的叠加内容 ---
    texts: list = field(default_factory=list)       # [{x,y,text,size,color,axes}]
    legend_anchor: list = None                      # [x, y] 轴域坐标；None = 用配置位置
    selected_curve: int = -1
    mode: str = "select"                            # select/pan/zoom/text/legend/data
    notes: str = ""
    # --- 图片文档 ---
    image_path: str = ""
    zoom: int = 100                                 # 显示缩放百分比
    fit_window: bool = True
    # --- 视图 ---
    minimized: bool = False
    visible: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        d = dict(data or {})
        valid = {f for f in cls.__dataclass_fields__}
        d = {k: v for k, v in d.items() if k in valid}
        obj = cls(**d)
        if not obj.id:
            obj.id = _new_id()
        obj.texts = [dict(t) for t in (obj.texts or []) if isinstance(t, dict)]
        return obj

    # ------------------------------------------------------------------
    def size_inches(self) -> tuple:
        if self.unit == "mm":
            return self.width / 25.4, self.height / 25.4
        if self.unit == "cm":
            return self.width / 2.54, self.height / 2.54
        if self.unit == "px":
            dpi = max(int(self.dpi or 100), 1)
            return self.width / dpi, self.height / dpi
        return float(self.width), float(self.height)

    def size_pixels(self) -> tuple:
        w, h = self.size_inches()
        return int(round(w * self.dpi)), int(round(h * self.dpi))

    def display_size(self) -> str:
        return f"{self.width:g} × {self.height:g} {self.unit}"

    def set_size(self, w: float, h: float, unit: str = None, dpi: int = None) -> None:
        self.width = max(0.5, float(w))
        self.height = max(0.5, float(h))
        if unit:
            self.unit = unit
        if dpi:
            self.dpi = max(50, min(int(dpi), 2400))

    def add_text(self, x: float, y: float, text: str, size: float = 11,
                 color: str = "#25304A", axes: int = 0) -> dict:
        item = {"x": float(x), "y": float(y), "text": str(text),
                "size": float(size), "color": color, "axes": int(axes)}
        self.texts.append(item)
        return item

    def remove_text(self, index: int) -> bool:
        if 0 <= index < len(self.texts):
            self.texts.pop(index)
            return True
        return False


class DocumentLibrary:
    """文档集合：只负责存取与序列化，不牵涉界面与项目树。"""

    def __init__(self):
        self.docs: dict = {}
        self.order: list = []

    # ------------------------------------------------------------------
    def create(self, kind: str = KIND_GRAPH, name: str = "", **kwargs) -> Document:
        kind = kind if kind in (KIND_GRAPH, KIND_IMAGE) else KIND_GRAPH
        base = name or ("图形" if kind == KIND_GRAPH else "图片")
        final = self.unique_name(base)
        doc = Document(name=final, kind=kind)
        for k, v in kwargs.items():
            if hasattr(doc, k):
                setattr(doc, k, v)
        self.docs[doc.id] = doc
        self.order.append(doc.id)
        return doc

    def unique_name(self, base: str) -> str:
        used = {d.name for d in self.docs.values()}
        if base not in used:
            return base
        i = 2
        while f"{base} {i}" in used:
            i += 1
        return f"{base} {i}"

    def get(self, doc_id: str):
        return self.docs.get(doc_id)

    def first(self, kind: str = None):
        for i in self.order:
            d = self.docs.get(i)
            if d is not None and (kind is None or d.kind == kind):
                return d
        return None

    def all(self, kind: str = None) -> list:
        out = [self.docs[i] for i in self.order if i in self.docs]
        return [d for d in out if kind is None or d.kind == kind]

    def remove(self, doc_id: str) -> Document:
        doc = self.docs.pop(doc_id, None)
        if doc_id in self.order:
            self.order.remove(doc_id)
        return doc

    def rename(self, doc_id: str, name: str) -> str:
        doc = self.docs.get(doc_id)
        if doc is None or not (name or "").strip():
            return ""
        used = {d.name for i, d in self.docs.items() if i != doc_id}
        final = name.strip()
        i = 2
        while final in used:
            final = f"{name.strip()} {i}"
            i += 1
        doc.name = final
        return final

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"docs": [d.to_dict() for d in self.all()],
                "order": list(self.order)}

    def load_dict(self, data: dict) -> None:
        self.docs, self.order = {}, []
        for item in (data or {}).get("docs", []) or []:
            d = Document.from_dict(item)
            self.docs[d.id] = d
            self.order.append(d.id)

    def reset(self) -> None:
        self.docs, self.order = {}, []
