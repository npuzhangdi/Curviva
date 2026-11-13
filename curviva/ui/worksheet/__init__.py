"""Origin 风格工作表域（界面子域）。

    ui/worksheet/
    ├── controller.py           ★ WorksheetController（唯一对外调用入口）
    ├── worksheet_book.py       多工作表标签窗口 + 工具栏
    └── worksheet_grid.py       列标 / 列头信息 / 单元格 / 复制粘贴网格

其它模块只与 controller.py 交互，不直接创建网格或标签窗口。
"""
