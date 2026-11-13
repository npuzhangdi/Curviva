"""examples 示例域：独立的示例资源文件夹，同时是一个功能域。

    examples/
    ├── controller.py       ★ ExamplesController（唯一对外调用入口）
    ├── README.md           示例清单与使用说明
    ├── data/               CSV / TXT / DAT / XLSX 示例数据
    ├── projects/           .cvproj 示例项目
    └── scripts/            仅 Python 的脚本 / 插件示例

软件菜单「文件 → 打开示例」由 controller.list_examples() 动态生成，
新增示例文件只需放进对应子目录，无需改动界面代码。
"""
