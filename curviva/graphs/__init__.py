"""图形 / 图片文档域。

    controller.py   ★ GraphController：唯一对外调用入口
    model.py        Document / DocumentLibrary：文档数据与序列化

图形文档保存尺寸、DPI、单位、图上文本标注、图例位置与选中曲线；
图片文档保存图片路径与显示缩放。文档节点挂在项目树上，随 .cvproj
一起保存、撤销与重做。
"""
