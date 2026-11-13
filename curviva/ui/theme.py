"""主题模块：Curviva 现代化外观（多色渐变设计系统）。

包含四层视觉处理：
1. 现代化 QSS 样式表 —— 品牌渐变、语义化按钮配色、圆角卡片、柔和玻璃面板；
2. 程序化图标 —— 数字框箭头、勾选标记、品牌 Logo、彩色圆点（不依赖外部资源）；
3. Windows DWM 亚克力模糊（毛玻璃）—— Win10/11 上尽力启用，失败静默降级；
4. Windows 11 系统级窗口圆角。

设计原则：视觉失败不阻塞功能 —— 任何一项系统效果不可用都自动降级为
纯 QSS 的半透明玻璃质感，不影响程序运行。

配色体系（浅色主题，保持科研绘图区的纯白背景不受影响）：
- 品牌主色：靛紫 → 湖蓝的水平渐变；
- 语义色：蓝(主要)、青(数据)、绿(成功)、紫(批量)、橙(提示)、红(危险)；
- 五个属性选项卡各有一个识别色，便于快速定位。
"""

import ctypes
import math
import os
import sys
import tempfile

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QApplication, QGroupBox, QTabWidget

# ------------------------------------------------------------------
# 配色常量（Origin 布局 + 现代扁平视觉）
# ------------------------------------------------------------------

# 顶部区域：现代中性炭灰
ORIGIN_BAR_BG = "#23272E"           # 菜单栏背景
ORIGIN_BAR_BG2 = "#2C3138"          # 工具栏行背景
ORIGIN_BORDER = "#14181D"           # 顶部区域分隔线
ORIGIN_TEXT = "#E7E9EC"             # 顶部区域文字
ORIGIN_TEXT_DIM = "#A7ADB6"
ORIGIN_WORKSPACE = "#8A9099"        # MDI 工作区背景
ORIGIN_SUB_ACTIVE = "#2F6FEB"       # 激活子窗口标题栏（现代蓝）
ORIGIN_SUB_ACTIVE2 = "#4A86F2"
ORIGIN_SUB_TITLE = "#FFFFFF"
ORIGIN_STATUS = "#F3F4F6"           # 状态栏浅灰

BRAND_A = "#4A86F2"
BRAND_B = "#2F6FEB"
BRAND_C = "#1E57C8"

ACCENT = "#2F6FEB"           # 主题强调色（现代蓝）
ACCENT_HOVER = "#4A86F2"
ACCENT_DARK = "#1E57C8"

C_BLUE = "#3E8BFF"
C_VIOLET = "#9B6BF2"
C_CYAN = "#12B5B0"
C_GREEN = "#22B07D"
C_ORANGE = "#F2954A"
C_RED = "#EE6A73"

GLASS_BG = "rgba(255, 255, 255, 0.85)"
GLASS_BG_HOVER = "rgba(255, 255, 255, 0.96)"
GLASS_BORDER = "rgba(96, 106, 128, 0.28)"
TEXT_MAIN = "#25292E"
TEXT_DIM = "#6A7280"
RADIUS = "6px"

# 五个属性选项卡的识别色（顺序与 MainWindow 中的 addTab 一致）
TAB_COLORS = [C_BLUE, C_VIOLET, C_CYAN, C_ORANGE, C_GREEN]

# 品牌渐变（QSS 片段，供多处复用）
_BRAND_GRAD = (f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
               f"stop:0 {BRAND_A}, stop:0.52 {BRAND_B}, stop:1 {BRAND_C})")


# ------------------------------------------------------------------
# 程序化图标（避免引入图片资源文件）
# ------------------------------------------------------------------

def _icon_dir() -> str:
    d = os.path.join(tempfile.gettempdir(), "curviva_style")
    os.makedirs(d, exist_ok=True)
    return d


def _ensure_icons():
    """生成 QSS 所需的箭头/勾选图标，返回 (up, down, check) 的正斜杠路径。"""
    d = _icon_dir()
    up = os.path.join(d, "arrow_up.png").replace("\\", "/")
    down = os.path.join(d, "arrow_down.png").replace("\\", "/")
    check = os.path.join(d, "check.png").replace("\\", "/")

    def _arrow(path, points):
        if os.path.exists(path):
            return
        pix = QPixmap(10, 6)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#4B5675"))
        painter.drawPolygon(QPolygonF([QPointF(*pt) for pt in points]))
        painter.end()
        pix.save(path)

    _arrow(up, [(0, 6), (10, 6), (5, 0)])
    _arrow(down, [(0, 0), (10, 0), (5, 6)])

    if not os.path.exists(check):
        pix = QPixmap(12, 12)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("white"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPolyline(QPolygonF([QPointF(2.2, 6.2), QPointF(5.0, 9.0),
                                        QPointF(10.0, 3.2)]))
        painter.end()
        pix.save(check)

    return up, down, check


def brand_logo(size: int = 40) -> QPixmap:
    """生成品牌 Logo：白色圆角底板 + 渐变曲线与数据点。"""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#FFFFFF"))
    grad.setColorAt(1.0, QColor("#E4EAFF"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(0, 0, size, size, size * 0.26, size * 0.26)

    pts = []
    for i in range(25):
        x = size * 0.14 + (size * 0.72) * i / 24
        y = size * 0.52 + math.sin(i / 24 * math.pi * 2.1 - 0.5) * size * 0.24
        pts.append(QPointF(x, y))
    path = QPainterPath()
    path.moveTo(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(ACCENT), max(2.0, size * 0.065),
                  Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)

    p.setPen(Qt.NoPen)
    for i, color in ((4, C_CYAN), (12, C_ORANGE), (20, BRAND_A)):
        p.setBrush(QColor(color))
        p.drawEllipse(pts[i], size * 0.055, size * 0.055)
    p.end()
    return pix


def dot_icon(color: str, size: int = 12) -> QIcon:
    """生成带描边的彩色圆点图标，用于选项卡与数据树。"""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color).darker(118), 1))
    p.setBrush(QColor(color))
    r = (size - 2) / 2
    p.drawRoundedRect(1, 1, size - 2, size - 2, r, r)
    p.end()
    return QIcon(pix)


# ------------------------------------------------------------------
# Origin 风格程序化图标（工具栏 / 子窗口 / 菜单共用）
# ------------------------------------------------------------------

def origin_icon(kind: str, size: int = 20) -> QIcon:
    """生成 Origin 风格的小图标（纯 QPainter 绘制，不依赖外部资源）。"""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    s = size
    m = s * 0.08                       # 边距

    def pen(color, w=1.4):
        return QPen(QColor(color), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    if kind == "project":
        p.setPen(pen("#3E6EA8", 1.2))
        p.setBrush(QColor("#CDE1F5"))
        p.drawRect(m, m + s * 0.12, s - 2 * m, s * 0.62)
        p.setBrush(QColor("#3E6EA8"))
        p.drawRect(m, m + s * 0.12, s - 2 * m, s * 0.16)
    elif kind == "new":
        p.setPen(pen("#5B6B7E"))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(m, m, s * 0.62, s - 2 * m)
        p.setPen(pen("#22B07D", 1.6))
        p.drawLine(QPointF(s * 0.72, s * 0.5), QPointF(s - m, s * 0.5))
        p.drawLine(QPointF(s * 0.82, s * 0.4), QPointF(s * 0.82, s * 0.6))
    elif kind == "open":
        p.setPen(pen("#B8860B", 1.2))
        p.setBrush(QColor("#F5D98A"))
        p.drawRect(m, s * 0.3, s * 0.62, s * 0.45)
        p.drawRect(m + s * 0.06, s * 0.22, s * 0.4, s * 0.1)
    elif kind == "save":
        p.setPen(pen("#3E6EA8", 1.2))
        p.setBrush(QColor("#4A7EBB"))
        p.drawRect(m, m, s - 2 * m, s - 2 * m)
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(s * 0.26, m + s * 0.08, s * 0.48, s * 0.3)
        p.drawRect(s * 0.26, s * 0.55, s * 0.48, s * 0.32)
    elif kind in ("undo", "redo"):
        color = "#22B07D" if kind == "undo" else "#D85A30"
        p.setPen(pen(color, 1.8))
        path = QPainterPath()
        if kind == "undo":
            path.moveTo(s * 0.8, s * 0.68)
            path.quadTo(s * 0.78, s * 0.24, s * 0.28, s * 0.3)
            arrow = [QPointF(s * 0.42, s * 0.14), QPointF(s * 0.24, s * 0.3),
                     QPointF(s * 0.44, s * 0.44)]
        else:
            path.moveTo(s * 0.2, s * 0.68)
            path.quadTo(s * 0.22, s * 0.24, s * 0.72, s * 0.3)
            arrow = [QPointF(s * 0.58, s * 0.14), QPointF(s * 0.76, s * 0.3),
                     QPointF(s * 0.56, s * 0.44)]
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF(arrow))
    elif kind == "sheet":
        p.setPen(pen("#3E6EA8", 1.1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(m, m, s - 2 * m, s - 2 * m)
        p.setBrush(QColor("#4A7EBB"))
        p.drawRect(m, m, s - 2 * m, s * 0.2)
        for i in (1, 2):
            y = m + s * 0.2 + i * (s - 2 * m - s * 0.2) / 3
            p.setPen(pen("#9FB8D4", 1.0))
            p.drawLine(QPointF(m, y), QPointF(s - m, y))
        p.setPen(pen("#9FB8D4", 1.0))
        p.drawLine(QPointF(s * 0.42, m + s * 0.2), QPointF(s * 0.42, s - m))
    elif kind == "graph":
        p.setPen(pen("#5B6B7E", 1.2))
        p.drawLine(QPointF(m, m + 1), QPointF(m, s - m))
        p.drawLine(QPointF(m, s - m), QPointF(s - m, s - m))
        p.setPen(pen("#D84545", 1.6))
        path = QPainterPath()
        path.moveTo(s * 0.18, s * 0.66)
        path.cubicTo(s * 0.4, s * 0.2, s * 0.62, s * 0.86, s * 0.88, s * 0.3)
        p.drawPath(path)
    elif kind == "image":
        p.setPen(pen("#1B9366", 1.2))
        p.setBrush(QColor("#EAF3DE"))
        p.drawRect(m, s * 0.2, s - 2 * m, s * 0.6)
        p.setBrush(QColor("#22B07D"))
        p.drawEllipse(QPointF(s * 0.32, s * 0.42), s * 0.07, s * 0.07)
        p.setPen(pen("#3B6D11", 1.3))
        p.drawPolyline(QPolygonF([QPointF(s * 0.2, s * 0.68),
                                  QPointF(s * 0.42, s * 0.5),
                                  QPointF(s * 0.6, s * 0.62),
                                  QPointF(s * 0.8, s * 0.4)]))
    elif kind == "folder":
        p.setPen(pen("#B8860B", 1.2))
        p.setBrush(QColor("#F5D98A"))
        p.drawRect(m, s * 0.28, s * 0.58, s * 0.44)
        p.drawRect(m + s * 0.05, s * 0.2, s * 0.34, s * 0.09)
    elif kind == "import":
        p.setPen(pen("#22B07D", 1.8))
        p.drawLine(QPointF(s * 0.5, s * 0.1), QPointF(s * 0.5, s * 0.6))
        p.setBrush(QColor("#22B07D"))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(s * 0.34, s * 0.48),
                                 QPointF(s * 0.66, s * 0.48),
                                 QPointF(s * 0.5, s * 0.72)]))
        p.setPen(pen("#5B6B7E", 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(m, s * 0.8), QPointF(s - m, s * 0.8))
    elif kind == "plot_line":
        p.setPen(pen("#3E6EA8", 1.4))
        p.drawLine(QPointF(m, s - m), QPointF(s - m, m))
    elif kind == "plot_symbol":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#D84545"))
        for pt in ((0.25, 0.7), (0.5, 0.45), (0.75, 0.25)):
            p.drawEllipse(QPointF(s * pt[0], s * pt[1]), s * 0.09, s * 0.09)
    elif kind == "plot_linesymbol":
        p.setPen(pen("#3E6EA8", 1.4))
        p.drawPolyline(QPolygonF([QPointF(s * 0.25, s * 0.7),
                                  QPointF(s * 0.5, s * 0.45),
                                  QPointF(s * 0.75, s * 0.25)]))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#D84545"))
        for pt in ((0.25, 0.7), (0.5, 0.45), (0.75, 0.25)):
            p.drawEllipse(QPointF(s * pt[0], s * pt[1]), s * 0.08, s * 0.08)
    elif kind == "plot_bar":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#4A7EBB"))
        p.drawRect(s * 0.16, s * 0.4, s * 0.2, s * 0.44)
        p.drawRect(s * 0.42, s * 0.22, s * 0.2, s * 0.62)
        p.setBrush(QColor("#22B07D"))
        p.drawRect(s * 0.68, s * 0.52, s * 0.2, s * 0.32)
    elif kind == "plot_fit":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#8899AA"))
        for pt in ((0.2, 0.75), (0.34, 0.62), (0.48, 0.58),
                   (0.62, 0.4), (0.8, 0.26)):
            p.drawEllipse(QPointF(s * pt[0], s * pt[1]), s * 0.06, s * 0.06)
        p.setPen(pen("#D85A30", 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(s * 0.14, s * 0.82), QPointF(s * 0.88, s * 0.2))
    elif kind == "analysis":
        p.setPen(pen("#8551D9", 1.5))
        p.drawLine(QPointF(s * 0.2, s * 0.2), QPointF(s * 0.8, s * 0.2))
        p.drawLine(QPointF(s * 0.2, s * 0.2), QPointF(s * 0.42, s * 0.62))
        p.drawLine(QPointF(s * 0.42, s * 0.62), QPointF(s * 0.8, s * 0.2))
        p.drawLine(QPointF(s * 0.28, s * 0.46), QPointF(s * 0.66, s * 0.46))
    elif kind == "book":
        p.setPen(pen("#3E6EA8", 1.1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(m, s * 0.34, s * 0.66, s * 0.46)
        p.drawRect(s * 0.28, s * 0.2, s * 0.66, s * 0.46)
        p.setBrush(QColor("#4A7EBB"))
        p.drawRect(s * 0.28, s * 0.2, s * 0.66, s * 0.12)
    elif kind == "batch":
        p.setPen(pen("#3E6EA8", 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(s * 0.15, s * 0.75),
                                  QPointF(s * 0.4, s * 0.45),
                                  QPointF(s * 0.62, s * 0.6),
                                  QPointF(s * 0.85, s * 0.28)]))
        p.drawPolyline(QPolygonF([QPointF(s * 0.15, s * 0.85),
                                  QPointF(s * 0.45, s * 0.62),
                                  QPointF(s * 0.68, s * 0.78),
                                  QPointF(s * 0.85, s * 0.55)]))
    elif kind == "insert_col":
        p.setPen(pen("#3E6EA8", 1.1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(m, s * 0.16, s * 0.56, s * 0.68)
        p.setPen(pen("#22B07D", 1.8))
        p.drawLine(QPointF(s * 0.76, s * 0.28), QPointF(s * 0.76, s * 0.66))
        p.drawLine(QPointF(s * 0.6, s * 0.47), QPointF(s * 0.92, s * 0.47))
    elif kind == "insert_row":
        p.setPen(pen("#3E6EA8", 1.1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(m, s * 0.16, s * 0.68, s * 0.56)
        p.setPen(pen("#22B07D", 1.8))
        p.drawLine(QPointF(s * 0.28, s * 0.84), QPointF(s * 0.66, s * 0.84))
        p.drawLine(QPointF(s * 0.47, s * 0.68), QPointF(s * 0.47, s * 1.0 - m))
    elif kind == "copy":
        p.setPen(pen("#5B6B7E", 1.1))
        p.setBrush(QColor("#E8ECF2"))
        p.drawRect(m, m, s * 0.5, s * 0.5)
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(s * 0.36, s * 0.36, s * 0.56, s * 0.56)
    elif kind == "paste":
        p.setPen(pen("#BA7517", 1.1))
        p.setBrush(QColor("#F5D98A"))
        p.drawRect(m, s * 0.2, s * 0.6, s * 0.7)
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(s * 0.42, s * 0.32, s * 0.5, s * 0.5)
    elif kind == "export":
        p.setPen(pen("#1B9366", 1.8))
        p.drawLine(QPointF(s * 0.5, s * 0.12), QPointF(s * 0.5, s * 0.62))
        p.setBrush(QColor("#1B9366"))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(s * 0.34, s * 0.5),
                                 QPointF(s * 0.66, s * 0.5),
                                 QPointF(s * 0.5, s * 0.74)]))
        p.setPen(pen("#5B6B7E", 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(m, s * 0.86), QPointF(s - m, s * 0.86))
    elif kind == "mode_select":
        p.setPen(pen("#2B2B2B", 1.3))
        p.setBrush(QColor("#FFFFFF"))
        p.drawPolygon(QPolygonF([QPointF(s * 0.3, s * 0.15),
                                 QPointF(s * 0.3, s * 0.8),
                                 QPointF(s * 0.5, s * 0.62),
                                 QPointF(s * 0.62, s * 0.86),
                                 QPointF(s * 0.7, s * 0.82),
                                 QPointF(s * 0.58, s * 0.58),
                                 QPointF(s * 0.78, s * 0.56)]))
    elif kind == "mode_text":
        p.setPen(pen("#8551D9", 2.2))
        p.drawLine(QPointF(s * 0.22, s * 0.2), QPointF(s * 0.78, s * 0.2))
        p.drawLine(QPointF(s * 0.5, s * 0.2), QPointF(s * 0.5, s * 0.82))
        p.drawLine(QPointF(s * 0.36, s * 0.82), QPointF(s * 0.64, s * 0.82))
    elif kind == "mode_legend":
        p.setPen(pen("#1D9E75", 1.2))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(s * 0.16, s * 0.22, s * 0.68, s * 0.52)
        p.setBrush(QColor("#D84545"))
        p.drawEllipse(QPointF(s * 0.3, s * 0.38), s * 0.06, s * 0.06)
        p.setBrush(QColor("#3E6EA8"))
        p.drawEllipse(QPointF(s * 0.3, s * 0.58), s * 0.06, s * 0.06)
        p.setPen(pen("#5B6B7E", 1.1))
        p.drawLine(QPointF(s * 0.42, s * 0.38), QPointF(s * 0.72, s * 0.38))
        p.drawLine(QPointF(s * 0.42, s * 0.58), QPointF(s * 0.72, s * 0.58))
    elif kind == "mode_data":
        p.setPen(pen("#D84545", 1.3))
        p.drawLine(QPointF(s * 0.2, s * 0.8), QPointF(s * 0.8, s * 0.2))
        p.setBrush(QColor("#FFFFFF"))
        p.setPen(pen("#2B2B2B", 1.2))
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.12, s * 0.12)
        p.setPen(pen("#2F567F", 1.6))
        p.drawLine(QPointF(s * 0.62, s * 0.62), QPointF(s * 0.82, s * 0.82))
        p.drawPolygon(QPolygonF([QPointF(s * 0.76, s * 0.84),
                                 QPointF(s * 0.88, s * 0.8),
                                 QPointF(s * 0.84, s * 0.9)]))
    elif kind == "mode_pan":
        p.setPen(pen("#5B6B7E", 1.6))
        p.drawLine(QPointF(s * 0.14, s * 0.5), QPointF(s * 0.86, s * 0.5))
        p.drawLine(QPointF(s * 0.5, s * 0.14), QPointF(s * 0.5, s * 0.86))
        p.setBrush(QColor("#5B6B7E"))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(s * 0.2, s * 0.42),
                                 QPointF(s * 0.2, s * 0.58),
                                 QPointF(s * 0.06, s * 0.5)]))
        p.drawPolygon(QPolygonF([QPointF(s * 0.8, s * 0.42),
                                 QPointF(s * 0.8, s * 0.58),
                                 QPointF(s * 0.94, s * 0.5)]))
    elif kind == "mode_zoom":
        p.setPen(pen("#3E6EA8", 1.6))
        p.setBrush(QColor("#EAF3FB"))
        p.drawEllipse(QPointF(s * 0.42, s * 0.42), s * 0.26, s * 0.26)
        p.drawLine(QPointF(s * 0.62, s * 0.62), QPointF(s * 0.86, s * 0.86))
    elif kind == "image_zoom":
        p.setPen(pen("#3E6EA8", 1.6))
        p.setBrush(QColor("#EAF3FB"))
        p.drawEllipse(QPointF(s * 0.42, s * 0.42), s * 0.24, s * 0.24)
        p.drawLine(QPointF(s * 0.6, s * 0.6), QPointF(s * 0.84, s * 0.84))
        p.setPen(pen("#2F567F", 1.4))
        p.drawLine(QPointF(s * 0.3, s * 0.42), QPointF(s * 0.54, s * 0.42))
        p.drawLine(QPointF(s * 0.42, s * 0.3), QPointF(s * 0.42, s * 0.54))
    elif kind == "image_fit":
        p.setPen(pen("#1B9366", 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawRect(m, s * 0.2, s - 2 * m, s * 0.6)
        p.setPen(pen("#1B9366", 1.5))
        p.drawPolyline(QPolygonF([QPointF(s * 0.62, s * 0.34),
                                  QPointF(s * 0.74, s * 0.34),
                                  QPointF(s * 0.74, s * 0.46)]))
        p.drawPolyline(QPolygonF([QPointF(s * 0.38, s * 0.66),
                                  QPointF(s * 0.26, s * 0.66),
                                  QPointF(s * 0.26, s * 0.54)]))
    elif kind == "image_orig":
        p.setPen(pen("#5B6B7E", 1.3))
        p.setBrush(QColor("#EAF3FB"))
        p.drawRect(m, s * 0.2, s - 2 * m, s * 0.6)
        p.setPen(pen("#D84545", 1.4))
        p.drawLine(QPointF(m, s * 0.2), QPointF(s - m, s * 0.8))
        p.drawLine(QPointF(m, s * 0.8), QPointF(s - m, s * 0.2))
    else:  # 兜底：中性方块
        p.setPen(pen("#5B6B7E", 1.2))
        p.setBrush(QColor("#E8ECF2"))
        p.drawRect(m, m, s - 2 * m, s - 2 * m)
    p.end()
    return QIcon(pix)


# ------------------------------------------------------------------
# 结构化着色工具（供主窗口在构建界面后调用）
# ------------------------------------------------------------------

def colorize_tabs(tabs: QTabWidget, colors=TAB_COLORS) -> None:
    """为每个选项卡设置识别色圆点图标。"""
    for i in range(min(tabs.count(), len(colors))):
        tabs.setTabIcon(i, dot_icon(colors[i], 10))


def colorize_groups(panel, tone: str) -> None:
    """把某个属性面板内的全部分组框统一着上同一色系（左侧彩条 + 彩色标题）。"""
    for gb in panel.findChildren(QGroupBox):
        gb.setProperty("tone", tone)
        gb.style().unpolish(gb)
        gb.style().polish(gb)


# ------------------------------------------------------------------
# 全局样式表
# ------------------------------------------------------------------

MODERN_QSS = f"""
* {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 12px;
    color: {TEXT_MAIN};
    selection-background-color: {ACCENT};
    selection-color: white;
}}

QMainWindow, QDialog {{
    background-color: #F7F8FA;
}}

/* ---------- 顶部区域（Origin 式深灰：品牌行 + 菜单栏） ---------- */
#brandBar {{
    background-color: {ORIGIN_BAR_BG};
    border: none;
    border-bottom: 1px solid {ORIGIN_BORDER};
}}
#brandBar QLabel {{ color: {ORIGIN_TEXT}; }}
#brandTitle {{
    font-size: 15px;
    font-weight: 700;
    color: white;
}}
#brandSub {{
    font-size: 10px;
    color: {ORIGIN_TEXT_DIM};
}}
#brandHint {{
    font-size: 11px;
    color: {ORIGIN_TEXT_DIM};
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 10px;
    padding: 3px 10px;
}}
#versionChip {{
    background-color: rgba(255, 255, 255, 0.12);
    color: {ORIGIN_TEXT};
    border: 1px solid rgba(255, 255, 255, 0.30);
    border-radius: 10px;
    padding: 2px 9px;
    font-weight: 600;
}}
#brandBar QMenuBar {{
    background: transparent;
    border: none;
}}
#brandBar QMenuBar::item {{
    color: {ORIGIN_TEXT};
    background: transparent;
    border-radius: 4px;
    padding: 4px 11px;
}}
#brandBar QMenuBar::item:selected {{
    background-color: {ORIGIN_SUB_ACTIVE};
    color: white;
}}

/* ---------- 分组框（现代扁平卡片 + 色条识别） ---------- */
QGroupBox {{
    background-color: #FBFCFD;
    border: 1px solid #E4E7EC;
    border-left: 3px solid {ACCENT};
    border-radius: 8px;
    margin-top: 12px;
    padding: 10px 8px 8px 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #333A45;
    font-weight: 600;
}}
QGroupBox[tone="blue"]   {{ border-left-color: {C_BLUE}; }}
QGroupBox[tone="violet"] {{ border-left-color: {C_VIOLET}; }}
QGroupBox[tone="cyan"]   {{ border-left-color: {C_CYAN}; }}
QGroupBox[tone="green"]  {{ border-left-color: {C_GREEN}; }}
QGroupBox[tone="orange"] {{ border-left-color: {C_ORANGE}; }}
QGroupBox[tone="blue"]::title   {{ color: #2C73D8; }}
QGroupBox[tone="violet"]::title {{ color: #8551D9; }}
QGroupBox[tone="cyan"]::title   {{ color: #0C948F; }}
QGroupBox[tone="green"]::title  {{ color: #1B9366; }}
QGroupBox[tone="orange"]::title {{ color: #D47A2F; }}

/* ---------- 停靠面板标题栏（现代深色细分隔条） ---------- */
QDockWidget {{ color: {ORIGIN_TEXT}; titlebar-close-icon: none; }}
QDockWidget::title {{
    background: {ORIGIN_BAR_BG2};
    color: {ORIGIN_TEXT};
    border: none;
    border-bottom: 1px solid {ORIGIN_BORDER};
    padding: 5px 10px;
    margin: 0;
    font-weight: 600;
    text-align: left;
}}

/* ---------- 输入控件 ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: rgba(255, 255, 255, 0.92);
    border: 1px solid {GLASS_BORDER};
    border-radius: 7px;
    padding: 4px 7px;
    min-height: 21px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
    background-color: white;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
    border-left: 1px solid {GLASS_BORDER};
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
    background: rgba(232, 236, 255, 0.95);
}}
QComboBox QAbstractItemView {{
    background-color: #FFFFFF;
    border: 1px solid {GLASS_BORDER};
    border-radius: 8px;
    selection-background-color: {ACCENT};
    selection-color: white;
    outline: none;
    padding: 2px;
}}

/* ---------- 数字框加减按钮 ---------- */
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border: none;
    border-left: 1px solid {GLASS_BORDER};
    border-bottom: 1px solid {GLASS_BORDER};
    border-top-right-radius: 7px;
    background: rgba(232, 236, 255, 0.95);
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border: none;
    border-left: 1px solid {GLASS_BORDER};
    border-bottom-right-radius: 7px;
    background: rgba(232, 236, 255, 0.95);
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: rgba(90, 108, 246, 0.28);
}}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
    background: rgba(90, 108, 246, 0.52);
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QComboBox::up-arrow {{
    image: url({{up_img}}); width: 10px; height: 6px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QComboBox::down-arrow {{
    image: url({{down_img}}); width: 10px; height: 6px;
}}

/* ---------- 复选框 / 单选框 ---------- */
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px;
    border: 1px solid #C3CBE2;
    border-radius: 4px;
    background: white;
}}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {_BRAND_GRAD};
    border-color: {ACCENT};
    image: url({{check_img}});
}}

/* ---------- 按钮：Origin 式扁平浅灰 + 语义强调 ---------- */
QPushButton {{
    background-color: #FFFFFF;
    border: 1px solid #D7DCE3;
    border-radius: 6px;
    padding: 5px 12px;
    min-height: 22px;
    color: #2B3038;
}}
QPushButton:hover {{
    background-color: #F2F7FF;
    border-color: {ACCENT};
}}
QPushButton:pressed {{ background-color: #E3EDFD; }}
QPushButton:disabled {{
    color: rgba(80, 90, 110, 0.45);
    background-color: rgba(255, 255, 255, 0.40);
}}

/* 主要操作：Origin 钢蓝实心 */
QPushButton[accent="true"], QPushButton[tone="primary"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {ORIGIN_SUB_ACTIVE2}, stop:1 {ORIGIN_SUB_ACTIVE});
    color: white;
    border: 1px solid {ACCENT_DARK};
    font-weight: 600;
}}
QPushButton[accent="true"]:hover, QPushButton[tone="primary"]:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_DARK};
}}
QPushButton[accent="true"]:pressed, QPushButton[tone="primary"]:pressed {{
    background: {ACCENT_DARK};
}}

/* 青色：数据导入类（扁平） */
QPushButton[tone="cyan"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E1F5EE, stop:1 #C8EDE0);
    color: #0F6E56; border: 1px solid #1D9E75; font-weight: 600;
}}
QPushButton[tone="cyan"]:hover {{ background: #B5E8D8; border-color: #0F6E56; }}
QPushButton[tone="cyan"]:pressed {{ background: #AFDFCF; }}

/* 紫色：批量 / 示例类（扁平） */
QPushButton[tone="violet"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F0EBFB, stop:1 #E2D8F5);
    color: #534AB7; border: 1px solid #7F77DD; font-weight: 600;
}}
QPushButton[tone="violet"]:hover {{ background: #D8CCF2; border-color: #534AB7; }}
QPushButton[tone="violet"]:pressed {{ background: #CBBBEE; }}

/* 绿色：成功 / 确认类（扁平） */
QPushButton[tone="green"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #EAF3DE, stop:1 #D8EBC2);
    color: #3B6D11; border: 1px solid #639922; font-weight: 600;
}}
QPushButton[tone="green"]:hover {{ background: #CBE6A8; border-color: #3B6D11; }}
QPushButton[tone="green"]:pressed {{ background: #BCDC97; }}

/* 橙色：预览 / 提示类（扁平） */
QPushButton[tone="orange"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FAEEDA, stop:1 #F5DFC0);
    color: #854F0B; border: 1px solid #BA7517; font-weight: 600;
}}
QPushButton[tone="orange"]:hover {{ background: #F2D6AE; border-color: #854F0B; }}
QPushButton[tone="orange"]:pressed {{ background: #ECCB9C; }}

/* 红色：删除等破坏性操作（扁平） */
QPushButton[tone="danger"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FCEBEB, stop:1 #F7D6D6);
    color: #A32D2D; border: 1px solid #E24B4A; font-weight: 600;
}}
QPushButton[tone="danger"]:hover {{ background: #F5C4C4; border-color: #A32D2D; }}
QPushButton[tone="danger"]:pressed {{ background: #EFB0B0; }}

/* ---------- 工具栏 ---------- */
QToolBar {{ background: transparent; border: none; spacing: 2px; padding: 2px; }}
QToolBar QToolButton {{
    background: rgba(255, 255, 255, 0.75);
    border: 1px solid {GLASS_BORDER};
    border-radius: 6px;
    padding: 2px;
}}
QToolBar QToolButton:hover {{
    background-color: rgba(90, 108, 246, 0.14);
    border-color: {ACCENT};
}}
QToolBar QToolButton:checked {{
    background-color: rgba(90, 108, 246, 0.24);
    border-color: {ACCENT};
}}
QToolBar::separator {{ background: {GLASS_BORDER}; width: 1px; margin: 4px 3px; }}

/* ---------- 画布卡片 ---------- */
#canvasCard {{
    background-color: rgba(255, 255, 255, 0.94);
    border: 1px solid rgba(122, 134, 190, 0.34);
    border-radius: 12px;
}}
#canvasHeader {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 rgba(109, 93, 246, 0.16), stop:1 rgba(56, 162, 240, 0.14));
    border: 1px solid rgba(122, 134, 190, 0.28);
    border-left: 3px solid {BRAND_B};
    border-radius: 7px;
    color: #3F4B75;
    font-weight: 600;
    padding: 4px 10px;
}}

/* ---------- 选项卡（现代下划线式） ---------- */
QTabWidget::pane {{
    border: none;
    border-top: 1px solid #E4E7EC;
    background-color: #FFFFFF;
    top: 0px;
}}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background-color: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 6px 9px;
    margin-right: 0px;
    color: #5F6673;
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT_MAIN};
    background-color: rgba(47, 111, 235, 0.06);
}}

/* ---------- 树 / 列表 ---------- */
QTreeWidget, QListWidget, QTreeView, QListView, QTableWidget {{
    background-color: #FFFFFF;
    border: 1px solid #E4E7EC;
    border-radius: 6px;
    padding: 0px;
    outline: none;
    alternate-background-color: #FAFBFC;
}}
QHeaderView::section {{
    background-color: #F5F6F8;
    color: #4A515C;
    border: none;
    border-bottom: 1px solid #E4E7EC;
    border-right: 1px solid #ECEEF1;
    padding: 4px 6px;
    font-weight: 600;
}}
QTreeWidget::item, QListView::item, QListWidget::item {{
    border-radius: 4px;
    padding: 2px 3px;
    min-height: 18px;
}}
QTreeWidget::item:selected, QListView::item:selected, QListWidget::item:selected {{
    background-color: rgba(47, 111, 235, 0.14);
    color: #12305F;
}}
QTreeWidget::item:hover:!selected, QListView::item:hover:!selected,
QListWidget::item:hover:!selected {{
    background-color: rgba(47, 111, 235, 0.06);
}}

/* ---------- 项目资源管理器（Origin 风格树） ---------- */
#explorerCaption {{
    font-weight: 600;
    color: {TEXT_DIM};
    padding-left: 2px;
}}
#explorerTree, #explorerContents {{
    border: none;
    background-color: #FFFFFF;
}}
#explorerTree::item, #explorerContents::item {{
    padding: 2px 2px;
    min-height: 19px;
}}
#explorerTree::item:selected, #explorerContents::item:selected {{
    background-color: rgba(47, 111, 235, 0.14);
    color: #12305F;
}}

/* ---------- 工作簿底部 Sheet 标签与状态条 ---------- */
#sheetTabs {{
    background: transparent;
    border: none;
}}
#sheetTabs::tab {{
    background-color: #F0F2F5;
    border: 1px solid #E4E7EC;
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    padding: 3px 12px;
    margin-right: 2px;
    color: #5F6673;
}}
#sheetTabs::tab:selected {{
    background-color: #FFFFFF;
    color: {ACCENT};
    border-color: #D7DCE3;
    font-weight: 600;
}}
#sheetStatus {{
    color: #7A828E;
    font-size: 10.5px;
    padding-right: 6px;
}}

/* ---------- Origin 风格工作表（第 4 个可管理窗口） ---------- */
#worksheetBook {{
    background: transparent;
}}
#worksheetBook QPushButton {{
    padding: 5px 11px;
    min-height: 22px;
    font-size: 11px;
}}
#worksheetBook QCheckBox {{
    spacing: 5px;
    color: {TEXT_DIM};
    font-size: 11px;
}}
#worksheetBook QTabBar::tab {{
    padding: 5px 16px;
    font-weight: 600;
}}
#worksheetGrid {{
    background-color: #FFFFFF;
    gridline-color: #E6E8EC;
    border: 1px solid #E4E7EC;
    font-family: "Consolas", "Microsoft YaHei UI", monospace;
    font-size: 11px;
    selection-background-color: #D8E6FD;
    selection-color: #12305F;
}}
#worksheetGrid::item {{
    padding: 1px 4px;
}}
#worksheetGrid QHeaderView::section {{
    background-color: #F5F6F8;
    color: #3A414C;
    border-right: 1px solid #E4E7EC;
    border-bottom: 1px solid #E4E7EC;
    padding: 3px 5px;
    font-family: "Microsoft YaHei UI", sans-serif;
    font-size: 11px;
    font-weight: 600;
}}
QTableCornerButton::section {{
    background: #F5F6F8;
    border: none;
    border-right: 1px solid #E4E7EC;
    border-bottom: 1px solid #E4E7EC;
}}

/* ---------- 结果表格 / 脚本编辑器（P0~P3 新增面板） ---------- */
QTableWidget::item {{
    padding: 3px 6px;
    border-bottom: 1px solid rgba(122, 134, 190, 0.10);
}}
QTableWidget::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 rgba(90, 108, 246, 0.22), stop:1 rgba(56, 162, 240, 0.22));
    color: {TEXT_MAIN};
}}
QPlainTextEdit, QTextEdit {{
    background-color: rgba(255, 255, 255, 0.88);
    border: 1px solid {GLASS_BORDER};
    border-radius: {RADIUS};
    padding: 7px 9px;
    selection-background-color: rgba(90, 108, 246, 0.24);
    color: {TEXT_MAIN};
}}
QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {ACCENT};
}}
QScrollBar:horizontal {{
    height: 9px;
    background: transparent;
}}
QScrollBar::handle:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 rgba(90, 108, 246, 0.45), stop:1 rgba(56, 162, 240, 0.45));
    border-radius: 4px;
    min-width: 36px;
}}

/* ---------- 提示卡片 ---------- */
#hintCard {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 rgba(155, 107, 242, 0.10), stop:1 rgba(56, 162, 240, 0.10));
    border: 1px solid rgba(155, 107, 242, 0.20);
    border-left: 3px solid {C_VIOLET};
    border-radius: 8px;
    color: #5B6285;
    padding: 6px 9px;
    font-size: 11px;
}}

/* ---------- 菜单 / 滚动条 / 状态栏 ---------- */
QMenuBar {{ background-color: {ORIGIN_BAR_BG}; }}
QMenuBar::item {{ color: {ORIGIN_TEXT}; border-radius: 4px; padding: 4px 11px; background: transparent; }}
QMenuBar::item:selected {{ background-color: {ORIGIN_SUB_ACTIVE}; color: white; }}
QMenu {{
    background-color: #FAFAFA;
    border: 1px solid {ORIGIN_BORDER};
    border-radius: 4px;
    padding: 3px;
}}
QMenu::item {{ border-radius: 4px; padding: 5px 24px 5px 14px; color: #2B2B2B; }}
QMenu::item:selected {{ background: {ORIGIN_SUB_ACTIVE}; color: white; }}
QMenu::separator {{ height: 1px; background: #C9C9C9; margin: 3px 8px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: #C5CBD4;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: #9AA3AF;
}}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; border: none; height: 0; width: 0;
}}
/* ---------- 中间 MDI 工作区 + 上下文工具栏（Origin 式深灰工具条） ---------- */
#workareaMdi {{
    background-color: {ORIGIN_WORKSPACE};
    border: none;
}}
QMdiSubWindow {{
    background-color: #FFFFFF;
    border: 1px solid {ORIGIN_BORDER};
    border-radius: 8px;
}}
QMdiSubWindow::title {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {ORIGIN_SUB_ACTIVE2}, stop:1 {ORIGIN_SUB_ACTIVE});
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border-bottom: 1px solid {ORIGIN_BORDER};
    padding: 4px 10px;
    color: {ORIGIN_SUB_TITLE};
    font-weight: 600;
}}
QToolBar#standardToolBar {{
    background-color: {ORIGIN_BAR_BG2};
    border: none;
    border-bottom: 1px solid {ORIGIN_BORDER};
    padding: 3px 8px;
    spacing: 2px;
}}
QToolBar#standardToolBar QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 2px 5px;
}}
QToolBar#standardToolBar QToolButton:hover {{
    background-color: {ORIGIN_SUB_ACTIVE};
    border-color: {ORIGIN_SUB_ACTIVE};
}}
QToolBar#standardToolBar::separator {{
    background: rgba(255, 255, 255, 0.22); width: 1px; margin: 4px 4px;
}}
QToolBar#contextToolBar {{
    background-color: {ORIGIN_BAR_BG2};
    border: none;
    border-bottom: 1px solid {ORIGIN_BORDER};
    padding: 3px 8px;
    spacing: 2px;
}}
QToolBar#contextToolBar QToolButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 2px;
}}
QToolBar#contextToolBar QToolButton:hover {{
    background-color: {ORIGIN_SUB_ACTIVE};
    border-color: {ORIGIN_SUB_ACTIVE};
}}
QToolBar#contextToolBar QToolButton:checked {{
    background: {ORIGIN_SUB_ACTIVE};
    border-color: {ORIGIN_SUB_ACTIVE};
}}
QToolBar#contextToolBar QSpinBox, QToolBar#contextToolBar QDoubleSpinBox,
QToolBar#contextToolBar QComboBox {{
    background-color: #3F3F3F;
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 4px;
    padding: 3px 5px;
    color: {ORIGIN_TEXT};
    selection-background-color: {ORIGIN_SUB_ACTIVE};
}}
QToolBar#contextToolBar QLabel#contextLabel {{
    color: {ORIGIN_TEXT_DIM};
    font-weight: 600;
    padding: 0 8px;
}}
/* ---------- 选中对象属性摘要（右侧属性窗口顶部） ---------- */
#summaryPanel {{
    background-color: #FFFFFF;
    border: 1px solid #E4E7EC;
    border-radius: 8px;
    padding: 8px;
}}
#summaryPanel QLabel {{ color: #2B3038; font-size: 11px; }}
#summaryPanel QLabel#summaryTitle {{
    font-size: 12px;
    font-weight: 600;
    color: {ACCENT_DARK};
}}
#summaryPanel QLabel#summaryLine {{ color: #626A76; }}

/* ---------- 选中图片 / 图形窗口内容 ---------- */
#sheetWindow, #graphWindow, #imageWindow {{
    background-color: #FFFFFF;
}}
#imageView {{
    background-color: #F4F4F4;
    color: {TEXT_DIM};
    border: 1px dashed {GLASS_BORDER};
    border-radius: 4px;
}}
QStatusBar {{
    background-color: {ORIGIN_STATUS};
    border-top: 1px solid #C9C9C9;
    color: {TEXT_MAIN};
}}
QStatusBar::item {{ border: none; }}
QToolTip {{
    background-color: #FFFFFF;
    color: {TEXT_MAIN};
    border: 1px solid {ACCENT};
    border-radius: 6px;
    padding: 4px 7px;
}}
"""


def apply_theme(app: QApplication) -> None:
    """应用全局现代化主题（在创建任何窗口之前调用）。"""
    app.setStyle("Fusion")
    app.setFont(app.font())
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#F2F2F2"))
    palette.setColor(QPalette.WindowText, QColor(TEXT_MAIN))
    palette.setColor(QPalette.Base, QColor("white"))
    palette.setColor(QPalette.Text, QColor(TEXT_MAIN))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor("white"))
    app.setPalette(palette)

    up_img, down_img, check_img = _ensure_icons()
    # MODERN_QSS 是 f-string：定义时双花括号已变为字面单花括号，
    # 因此不能用 .format()（会把 CSS 规则的花括号当字段解析），
    # 只需对三个图标占位符做简单替换。
    qss = (MODERN_QSS
           .replace("{up_img}", up_img)
           .replace("{down_img}", down_img)
           .replace("{check_img}", check_img))
    app.setStyleSheet(qss)


# ------------------------------------------------------------------
# Windows 系统级效果（尽力而为，失败静默降级）
# ------------------------------------------------------------------

def _enable_acrylic_blur(hwnd: int) -> bool:
    """通过 SetWindowCompositionAttribute 启用亚克力模糊（毛玻璃）。"""
    if sys.platform != "win32":
        return False
    try:
        class AccentPolicy(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_uint),
                ("AccentFlags", ctypes.c_uint),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_uint),
            ]

        accent = AccentPolicy(4, 2, 0xC8FFFFFF, 0)
        proto = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p)
        set_attr = proto(("SetWindowCompositionAttribute", ctypes.windll.user32))
        size = ctypes.sizeof(accent)
        data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        return bool(set_attr(ctypes.c_void_p(hwnd), 19, data) and size)
    except Exception:
        return False


def _enable_rounded_corners(hwnd: int) -> bool:
    """Windows 11：启用系统级窗口圆角。"""
    if sys.platform != "win32":
        return False
    try:
        value = ctypes.c_int(2)
        hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), 33, ctypes.byref(value), ctypes.sizeof(value))
        return hr == 0
    except Exception:
        return False


def polish_window(window) -> None:
    """窗口显示后调用：启用毛玻璃与系统圆角（尽力而为）。"""
    try:
        hwnd = int(window.winId())
        _enable_acrylic_blur(hwnd)
        _enable_rounded_corners(hwnd)
    except Exception:
        pass  # 任何失败都不影响功能
