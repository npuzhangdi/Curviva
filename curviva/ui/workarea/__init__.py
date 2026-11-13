"""中间工作区域（MDI 多文档）。

    controller.py     ★ WorkareaController：唯一对外调用入口
    mdi_area.py       WorkareaMdiArea：子窗口容器与排列
    windows.py        Sheet / Graph / Image / Book 四类子窗口
    graph_editor.py   Origin 式鼠标在图上直接修改（选择/平移/缩放/文本/图例/数据点）
    graph_dialogs.py  图形出版尺寸设置

表格、图形、图片都是可最小化、可显示隐藏的独立窗口；当前激活窗口的
类型会驱动顶部上下文工具栏切换对应操作。
"""
