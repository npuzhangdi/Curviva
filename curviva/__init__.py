"""Curviva —— 科研绘图与数据分析工作台（v0.0.0）。

模块化架构：每个功能域一个文件夹，域内有且只有一个「控制调用文件」
controller.py 对外暴露 API；顶层 controller.py 的 AppController 负责组合调度。

    curviva/controller.py          总控 AppController
    config/controller.py          配置域（配置模型 / 序列化 / 样式名）
    core/controller.py            数据 + 绘图引擎域
    project/controller.py         P0 项目 / 撤销重做 / 样式主题
    workspace/controller.py       项目管理树（文件夹 / 表格 / 图形 / 图片）
    graphs/controller.py          图形 / 图片文档域（尺寸、标注、图片）
    analysis/controller.py        P2 数据处理与分析
    fitting/controller.py         P1 公式拟合
    templates/controller.py       P3 模板 / 批处理 / Python 扩展
    examples/controller.py        （项目根 examples/）示例资源域
    ui/controller.py              界面域装配
    ui/panels/controller.py       面板集合
    ui/worksheet/controller.py    Origin 风格工作表域
    ui/workarea/controller.py     中间 MDI 工作区 + 图上鼠标编辑
    ui/toolbar/controller.py      随选中对象切换的上下文工具栏

扩展（公式列、自定义拟合模型、脚本、插件）**仅支持 Python**。
"""

__version__ = "0.0.0"
__app_name__ = "Curviva"
