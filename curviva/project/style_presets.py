"""P0 样式主题预设（对标 Origin 的 Theme / 样式库）。

每个预设是一份纯 Python 字典，描述全局字体/配色、曲线调色板与子图外观；
apply_style 把它应用到 PlotConfig 上，用户保存 .cvproj 或 .cvstyle 时会带上主题名。
"""

STYLES = {
    "默认（Curviva 湖蓝）": {
        "font_family": "Arial", "base_fontsize": 10.0, "title_fontsize": 14.0,
        "face_color": "white", "linewidth": 1.5, "grid": False,
        "grid_alpha": 0.5, "legend_frame": True, "spines": True,
        "palette": ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
                    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"],
    },
    "期刊黑白（灰度印刷）": {
        "font_family": "Times New Roman", "base_fontsize": 9.0, "title_fontsize": 12.0,
        "face_color": "white", "linewidth": 1.2, "grid": False,
        "grid_alpha": 0.3, "legend_frame": False, "spines": True,
        "palette": ["#000000", "#555555", "#888888", "#AAAAAA", "#333333",
                    "#666666", "#999999", "#BBBBBB", "#444444", "#777777"],
        "markers": ["o", "s", "^", "D", "v", "*", "+", "x", ".", "o"],
    },
    "经典 Origin": {
        "font_family": "Arial", "base_fontsize": 10.0, "title_fontsize": 12.0,
        "face_color": "white", "linewidth": 1.4, "grid": False,
        "grid_alpha": 0.4, "legend_frame": True, "spines": True,
        "palette": ["#000000", "#FF0000", "#0000FF", "#008000", "#FF8000",
                    "#800080", "#00AAAA", "#A0A0A0", "#8B4513", "#FF00FF"],
    },
    "高对比演示": {
        "font_family": "Microsoft YaHei", "base_fontsize": 13.0, "title_fontsize": 18.0,
        "face_color": "white", "linewidth": 2.6, "grid": True,
        "grid_alpha": 0.35, "legend_frame": True, "spines": True,
        "palette": ["#165DFF", "#F53F3F", "#00B42A", "#FF7D00", "#722ED1",
                    "#0FC6C2", "#F77234", "#86909C", "#EB0AA4", "#0E42D2"],
    },
    "柔和浅色": {
        "font_family": "Microsoft YaHei", "base_fontsize": 10.0, "title_fontsize": 13.0,
        "face_color": "#FBFCFF", "linewidth": 1.8, "grid": True,
        "grid_alpha": 0.25, "legend_frame": False, "spines": False,
        "palette": ["#5B8FF9", "#F6BD16", "#5AD8A6", "#E8684A", "#6DC8EC",
                    "#9270CA", "#FF9D4D", "#269A99", "#FF99C3", "#AAB7C4"],
    },
}

DEFAULT_STYLE = "默认（Curviva 湖蓝）"


def style_names() -> list:
    return list(STYLES)


def resolve(name: str) -> dict:
    return STYLES.get(name, STYLES[DEFAULT_STYLE])


def apply_style(config, name: str) -> None:
    """把预设应用到配置对象（不重绘，由调用方统一刷新）。"""
    s = resolve(name)
    g = config.global_cfg
    g.font_family = s["font_family"]
    g.base_fontsize = s["base_fontsize"]
    g.title_fontsize = s["title_fontsize"]
    g.face_color = s["face_color"]
    g.style_name = name

    palette = s["palette"]
    for i, curve in enumerate(config.curves):
        curve.color = palette[i % len(palette)]
        curve.linewidth = s["linewidth"]
        markers = s.get("markers")
        if markers and curve.plot_type in ("scatter", "line_point"):
            curve.marker = markers[i % len(markers)]

    for sub in config.subplots:
        sub.grid_show = s["grid"]
        sub.grid_alpha = s["grid_alpha"]
        sub.legend_frame = s["legend_frame"]
        sub.show_top = sub.show_bottom = sub.show_left = sub.show_right = s["spines"]
