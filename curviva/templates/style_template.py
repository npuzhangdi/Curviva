"""P3 图形模板（对标 Origin 的 Graph Template / Theme Gallery）。

模板分两类：
- 内置模板：即 P0 的样式主题预设（只改样式，保留当前曲线与数据映射）；
- 用户模板：.cvstyle JSON 文件，保存完整的绘图配置（布局、轴、曲线样式）。
"""

import json
import os
import re

from curviva.project.style_presets import style_names

TEMPLATE_EXT = ".cvstyle"


def user_template_dir() -> str:
    path = os.path.join(os.path.expanduser("~"), ".curviva", "templates")
    os.makedirs(path, exist_ok=True)
    return path


def _safe_name(name: str) -> str:
    clean = re.sub(r'[\\/:*?"<>|]', "_", (name or "").strip())
    if not clean:
        raise ValueError("请填写模板名称。")
    return clean


def list_templates() -> list:
    items = [{"name": n, "builtin": True, "path": ""} for n in style_names()]
    folder = user_template_dir()
    for fn in sorted(os.listdir(folder)):
        if fn.lower().endswith(TEMPLATE_EXT):
            items.append({"name": os.path.splitext(fn)[0], "builtin": False,
                          "path": os.path.join(folder, fn)})
    return items


def save_template(name: str, config_dict: dict) -> str:
    clean = _safe_name(name)
    path = os.path.join(user_template_dir(), clean + TEMPLATE_EXT)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"format": "CurvivaStyle", "name": clean,
                   "config": config_dict}, f, ensure_ascii=False, indent=2)
    return path


def load_template(name: str) -> dict:
    """返回 {'builtin': bool, 'config': dict 或 None}。"""
    if name in style_names():
        return {"builtin": True, "config": None}
    path = os.path.join(user_template_dir(), _safe_name(name) + TEMPLATE_EXT)
    if not os.path.exists(path):
        raise ValueError(f"未找到模板「{name}」。")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("format") != "CurvivaStyle":
        raise ValueError("模板文件格式不正确。")
    return {"builtin": False, "config": data.get("config", {})}


def delete_template(name: str) -> bool:
    if name in style_names():
        return False
    path = os.path.join(user_template_dir(), _safe_name(name) + TEMPLATE_EXT)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
