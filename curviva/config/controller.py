"""配置域「控制调用文件」。

整个软件中，任何模块想读取/替换/克隆/序列化绘图配置，都只通过
ConfigController 这一个入口，不直接操作 dataclass 内部字段。

职责：
- 持有唯一的 PlotConfig 实例（与 AppController 共享同一对象引用）；
- 配置 <-> 纯 Python 字典互转（供项目文件、撤销重做、模板使用）；
- 配置克隆、结构签名、样式主题应用。
"""

from dataclasses import asdict, fields, is_dataclass

from curviva.config.plot_config import (
    AxisConfig,
    CurveConfig,
    GlobalConfig,
    PlotConfig,
    SubplotConfig,
)


def _from_dict(cls, data: dict):
    """把字典还原为 dataclass，自动忽略多余键、补齐缺失键（向前兼容）。"""
    if not isinstance(data, dict):
        return cls()
    known = {f.name for f in fields(cls)}
    kwargs = {}
    for key, value in data.items():
        if key not in known:
            continue
        target = next((f for f in fields(cls) if f.name == key), None)
        if target is None:
            continue
        if is_dataclass(target.type) and isinstance(value, dict):
            kwargs[key] = _from_dict(target.type, value)
        else:
            kwargs[key] = value
    try:
        return cls(**kwargs)
    except TypeError:
        return cls()


def _list_from_dict(cls, items) -> list:
    return [_from_dict(cls, it) for it in items] if isinstance(items, list) else []


class ConfigController:
    """配置域统一对外 API。"""

    def __init__(self, app=None):
        self.app = app
        self.config = PlotConfig()
        self.config.ensure_subplots()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def new(self) -> PlotConfig:
        self.config = PlotConfig()
        self.config.ensure_subplots()
        return self.config

    def replace(self, config: PlotConfig) -> PlotConfig:
        """整体替换配置对象（撤销重做 / 打开项目后调用）。"""
        self.config = config
        self.config.ensure_subplots()
        self.config.clamp_curve_indices()
        return self.config

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self.config)

    def from_dict(self, data: dict) -> PlotConfig:
        cfg = PlotConfig(
            global_cfg=_from_dict(GlobalConfig, data.get("global_cfg", {})),
            subplots=_list_from_dict(SubplotConfig, data.get("subplots", [])),
            curves=_list_from_dict(CurveConfig, data.get("curves", [])),
        )
        # 嵌套的 AxisConfig 需要单独还原
        for sub_raw, sub in zip(data.get("subplots", []) or [], cfg.subplots):
            if not isinstance(sub_raw, dict):
                continue
            sub.x_axis = _from_dict(AxisConfig, sub_raw.get("x_axis", {}))
            sub.y_axis = _from_dict(AxisConfig, sub_raw.get("y_axis", {}))
            sub.y2_axis = _from_dict(AxisConfig, sub_raw.get("y2_axis", {}))
        return self.replace(cfg)

    def clone(self) -> PlotConfig:
        return self.from_dict(self.to_dict())

    # ------------------------------------------------------------------
    # 派生信息
    # ------------------------------------------------------------------

    def signature(self, datasets=None) -> str:
        """结构签名：用于判断是否需要刷新面板里的动态下拉选项。"""
        g = self.config.global_cfg
        ds_names = ",".join(d.name for d in (datasets or []))
        return (f"{g.rows}x{g.cols}|{len(self.config.curves)}|{ds_names}|"
                f"{sum(1 for c in self.config.curves if c.y_axis == 'right')}")

    # ------------------------------------------------------------------
    # 样式主题（实现放在 project 域，此处仅做转发）
    # ------------------------------------------------------------------

    def style_names(self) -> list:
        from curviva.project.style_presets import style_names
        return style_names()

    def apply_style(self, name: str) -> None:
        from curviva.project.style_presets import apply_style
        apply_style(self.config, name)
