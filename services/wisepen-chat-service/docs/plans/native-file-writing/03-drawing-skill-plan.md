# 绘图 skill 计划

## 1. 文档定位

本文档规划一套“绘图 skill / 绘图能力”。

目标不是简单生成一张图，而是：

- 在沙箱里直接写代码生成图像文件
- 支持单独交付图片
- 支持嵌入 DOCX 等文档
- 对主流绘图格式做稳定校验
- 评估 `matplotlib`、`seaborn` 及其他主流绘图库的适用边界

## 2. 核心目标

### 2.1 产物目标

至少支持这些输出：

- PNG
- SVG
- PDF
- 可选 JPG

### 2.2 使用目标

绘图产物既可以：

- 作为独立 image 文件交付
- 也可以被 DOCX / HTML 等文档 builder 嵌入

### 2.3 实现目标

绘图能力运行在沙箱中，直接写代码生成图片，不依赖本地模型部署。

## 3. 社区绘图库评估

### 3.1 `matplotlib`

定位：

- 主绘图库
- v1 默认基础引擎

优点：

- 社区最成熟
- 图形类型全面
- 文件导出稳定
- 对 PNG/SVG/PDF 支持成熟
- 与学术、报告、论文图表场景最匹配
- 后端稳定，沙箱环境友好

缺点：

- 默认美观度一般
- 样式需要精心封装
- API 偏底层

结论：

- 必须作为核心依赖

### 3.2 `seaborn`

定位：

- 基于 matplotlib 的高级统计绘图封装

优点：

- 默认风格更好
- 统计图、分布图、分类图上手快
- 适合常见分析与报告图表

缺点：

- 本质仍依赖 matplotlib
- 某些细粒度排版仍需回到底层

结论：

- v1 应作为首选高级封装层之一

### 3.3 `plotly`

定位：

- 交互图优先，也支持静态图导出

优点：

- 交互性强
- 现代感好
- 图表类型丰富

缺点：

- 静态导出依赖 `kaleido`
- 对“论文/正式报告静态图”不一定优于 matplotlib
- 在沙箱中依赖链更重

结论：

- 可作为可选依赖
- 适合交互图或业务仪表盘图，不作为 v1 主静态绘图栈

### 3.4 `altair`

定位：

- 声明式统计可视化

优点：

- 语义清晰
- 与数据表驱动逻辑契合

缺点：

- 静态导出链路依赖较多
- 图形能力与工程控制相比 matplotlib 不够直接

结论：

- 可评估为后续补充，不作为 v1 主路径

### 3.5 `bokeh`

定位：

- 交互图表与浏览器展示

优点：

- Web 端交互性好

缺点：

- 静态图片导出不如 matplotlib 稳定直接
- 更适合交互场景，不适合当前“文件产物优先”目标

结论：

- 不作为 v1 主路径

### 3.6 其他补充库

可视情况补充：

- `scienceplots`
  - 强烈推荐评估
  - 原因：给 matplotlib 提供成熟学术风格 preset
- `networkx`
  - 若后续需要关系图
- `graphviz`
  - 若后续需要流程图/有向图
- `pillow`
  - 用于基础图片后处理

## 4. 主栈结论

v1 主绘图栈建议固定为：

- `matplotlib`
- `seaborn`
- `scienceplots`
- `pillow`

可选扩展：

- `plotly + kaleido`

原因：

- 最符合“直接写代码、稳定导出图片、适合正式文档嵌入”的业务目标
- 社区最成熟
- 沙箱里运行稳定
- 对论文/报告类图表最合适

## 5. 能力分层

### 5.1 Chart Intent Layer

负责表达：

- 图表类型
- 输入数据结构
- 风格要求
- 输出格式
- 是否用于文档嵌入

### 5.2 Drawing Spec Layer

统一中间表示：

- figure size
- dpi
- font family
- palette
- axis labels
- legend
- title
- export formats

### 5.3 Renderer Layer

分别对应：

- `MatplotlibRenderer`
- `SeabornRenderer`
- `PlotlyRenderer`（可选）

### 5.4 Validation Layer

负责：

- 文件存在
- 格式完整性
- 可打开性
- 尺寸与分辨率
- 透明背景/字体回退等问题

## 6. 风格系统

### 6.1 学术风格

v1 至少应预置一套学术绘图风格：

- serif 字体
- 适合论文插图的字号
- 线宽与网格控制
- legend 间距
- 黑白打印友好

推荐直接基于：

- `scienceplots`
- 再叠加项目自己的 token

### 6.2 文档嵌入风格

图像如果用于嵌入 DOCX，应支持：

- 与文档主字体匹配
- 与文档页宽匹配
- 标题/图题位置一致
- 背景透明或白底可配置

## 7. 输出与嵌入

### 7.1 独立交付

绘图能力必须能单独交付：

- `chart.png`
- `chart.svg`
- `chart.pdf`

### 7.2 文档嵌入

嵌入链路固定为：

1. 先生成图片文件
2. 再由 DOCX builder 引入该图片文件
3. 图片与图题在 DOCX 中统一布局
4. 最终通过 `DOCX -> PDF` 链导出整份文档

说明：

- 图像本身是独立 artifact
- DOCX 只引用该 artifact

## 8. 校验策略

### 8.1 结构校验

对绘图 spec 做：

- 图表类型校验
- 数据字段校验
- 样式 token 校验
- 输出格式校验

### 8.2 文件校验

对输出图片做：

- 文件存在
- MIME/扩展名一致
- 可被 Pillow 或相应 parser 打开
- 宽高与 DPI 读取

### 8.3 视觉校验

对主交付图片至少做：

- 标题未被裁切
- 坐标轴标签完整
- legend 未溢出
- 字体未异常回退
- 透明背景与预期一致

若后续接视觉审查模型，可扩展自动视觉 QA；v1 先以工程校验为主。

## 9. 接口建议

### 9.1 统一请求模型

- `DrawingRequest`
- `DrawingSpec`
- `DrawingStylePreset`
- `DrawingResult`
- `DrawingValidationReport`

### 9.2 `DrawingRequest`

最少包含：

- `chart_type`
- `data`
- `preset_id`
- `output_formats`
- `intended_use`
  - `standalone`
  - `docx_embed`
  - `html_embed`

### 9.3 `DrawingResult`

最少包含：

- `artifacts`
- `primary_artifact`
- `validation_report`
- `embed_metadata`

## 10. 依赖策略

建议主依赖：

- `matplotlib`
- `seaborn`
- `scienceplots`
- `pillow`

建议可选依赖：

- `plotly`
- `kaleido`
- `networkx`
- `graphviz`

说明：

- 这些依赖不涉及本地模型部署
- 在沙箱中直接安装和运行即可

## 11. 与 DOCX/PDF/HTML/MD 的关系

### 11.1 DOCX

- 图像可直接嵌入 DOCX
- 图题由 DOCX builder 统一写入

### 11.2 PDF

- 图像可单独输出 PDF
- 也可先嵌入 DOCX，再整体导出 PDF

### 11.3 HTML

- 图像可由 HTML 直接引用
- SVG 特别适合 HTML 嵌入

### 11.4 Markdown

- Markdown 可直接引用图片路径
- 但 Markdown 自身不负责图像版式，只负责链接

## 12. 测试与验收

### 12.1 单测

- chart type -> renderer mapping
- style preset 覆盖率
- 多格式导出结果
- validation report 分类

### 12.2 集成测试

- 折线图
- 柱状图
- 散点图
- 热力图
- 箱线图
- 学术风格图
- 图像嵌入 DOCX

### 12.3 验收

- 图片文件可独立交付
- 图片可嵌入 DOCX
- 字体、标签、legend、标题不裁切
- 学术风格 preset 生效

## 13. 最终结论

绘图 skill 的 v1 主线应固定为：

- `matplotlib` 作为主引擎
- `seaborn` 作为高级统计封装
- `scienceplots` 作为学术风格加速器
- 输出图片既可单独交付，也可嵌入 DOCX / HTML
- 通过统一文件编写能力纳入 artifact 和 validation 链
