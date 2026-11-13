"""P0 项目文件读写（.cvproj，UTF-8 JSON，对标 Origin 的 .opju）。

项目文件包含：完整绘图配置、全部数据集（含公式列定义）、工作区文本
（脚本内容、拟合摘要、分析日志）。拟合/分析产生的曲线与数据已经作为
普通数据集与曲线保存在项目里，因此重新打开后图形可完整还原。
"""

import datetime
import json
import os

from curviva import __version__

PROJECT_FORMAT = "CurvivaProject"
PROJECT_EXT = ".cvproj"
PROJECT_FILTER = "Curviva 项目 (*.cvproj);;所有文件 (*.*)"


def blank_workspace() -> dict:
    """工作区文本 + Origin 风格项目资源树（tree 由 workspace 域写入）。"""
    return {"script": "", "fit_summary": [], "analysis_log": [], "notes": "",
            "tree": None, "documents": None}


def make_state(config: dict, datasets: list, workspace: dict = None) -> dict:
    return {
        "format": PROJECT_FORMAT,
        "version": __version__,
        "app": "Curviva",
        "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "config": config,
        "datasets": datasets,
        "workspace": {**blank_workspace(), **(workspace or {})},
    }


def save_state(path: str, state: dict) -> None:
    if not path.lower().endswith(PROJECT_EXT):
        path += PROJECT_EXT
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return path


def load_state(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        state = json.load(f)
    if not isinstance(state, dict) or state.get("format") != PROJECT_FORMAT:
        raise ValueError("这不是有效的 Curviva 项目文件（.cvproj）。")
    state.setdefault("workspace", blank_workspace())
    state.setdefault("config", {})
    state.setdefault("datasets", [])
    return state
