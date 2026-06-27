# 原生 DOCX 编辑与 DOCX->PDF 链路计划

## 1. 文档定位

本文档在原有 DOCX 原生编辑方案基础上，补充并固定 PDF 策略：

- PDF 不再被定义为独立富文档编辑能力
- PDF 明确定义为 `DOCX -> PDF` 导出链路
- 复用 DOCX 编辑、样式和校验主能力

## 2. 总体策略

### 2.1 DOCX 仍是主编辑格式

所有正式文档排版、字体、样式、页眉页脚、段落、表格等，都在 DOCX 层完成。

### 2.2 PDF 是导出结果

PDF 的职责：

- 最终交付
- 只读版本
- 打印/归档版本
- 嵌入或引用图像后的最终版面输出

### 2.3 不采用直接 PDF 编排作为主线

不主推：

- `reportlab` 作为富文档主编写方式
- HTML -> PDF 作为主文档链

原因：

- 用户目标是“符合格式的 Word 文档 + 可导出 PDF”
- DOCX 作为主编辑格式更符合真实办公与学术业务形态
- Word 样式系统、Google Docs 导入链、后续编辑链都以 DOCX 为核心

## 3. 社区方案评估

### 3.1 主导出方案：LibreOffice / soffice

主推方案固定为：

- `soffice --headless --convert-to pdf`

原因：

- 社区成熟
- 对 DOCX 转 PDF 兼容性最好
- 与现有 Documents skill 的 render/QA 工作流天然兼容
- 不需要本地 Office COM
- 更适合沙箱中批处理

### 3.2 备选方案

#### Microsoft Office / Word Automation

不作为主路径。

原因：

- 平台依赖强
- 自动化环境复杂
- 不适合通用沙箱

#### HTML -> PDF（如 WeasyPrint / wkhtmltopdf）

不作为主路径。

原因：

- 这相当于引入另一套版式系统
- 会绕开 DOCX 原生样式
- 与“复用 DOCX 编辑主能力”目标冲突

#### 纯 Python PDF 生成（如 reportlab）

不作为 DOCX 文档导出主路径。

原因：

- 更适合独立 PDF 票据、报告、图表附件
- 不适合承接 Word 学术/办公文档的编辑主线

## 4. 能力分层

### 4.1 Docx Build Layer

负责：

- 文档结构
- 样式系统
- 字体与排版
- OOXML patch

### 4.2 Pdf Export Layer

负责：

- 从已经通过 DOCX 校验的 `.docx` 生成 `.pdf`
- 管理导出命令、临时目录、失败诊断

### 4.3 Pdf Validation Layer

负责：

- 页数
- 文件完整性
- 可渲染性
- 基本视觉检查

## 5. 实现接口建议

### 5.1 新接口

- `DocxBuildRequest`
- `DocxBuildResult`
- `PdfExportRequest`
- `PdfExportResult`
- `PdfValidationReport`

### 5.2 `PdfExportRequest`

最少包含：

- `source_docx_path`
- `target_pdf_path`
- `render_pngs`
- `emit_pdf_validation`

### 5.3 `PdfExportResult`

最少包含：

- `pdf_path`
- `page_count`
- `render_artifacts`
- `validation_report`
- `warnings`

## 6. 导出流程

固定导出顺序：

1. 先完成 DOCX 原生生成或编辑
2. 先跑 DOCX 自身结构与渲染校验
3. 只有 DOCX 通过最低验收门槛后，才允许进入 PDF 导出
4. 使用 `soffice --headless --convert-to pdf`
5. 对输出 PDF 执行校验
6. 必要时渲染 PDF 页图检查视觉结果

说明：

- 不允许直接从“未验证的 DOCX”导出 PDF 再拿 PDF 当最终依据
- PDF 只是 DOCX 能力的下游产物

## 7. 校验策略

### 7.1 DOCX 校验先行

PDF 质量默认依赖上游 DOCX 质量。

因此 PDF 导出前必须有：

- DOCX AST/结构校验
- OOXML 校验
- render_docx 视觉 QA

### 7.2 PDF 校验

PDF 校验必须至少包含：

- 文件存在
- 文件可打开
- 页数可读取
- 页图可渲染

若环境允许，建议进一步做：

- 页尺寸读取
- 文本/字体基础检查
- 页脚页码位置巡检

### 7.3 渲染工具

复用现有 PDF skill 建议：

- Poppler `pdftoppm`
- `pdfinfo`
- `pypdf`
- `pdfplumber`

## 8. 与 DOCX 编辑能力的关系

### 8.1 完全复用样式系统

PDF 链路不得引入第二套视觉样式系统。

所有版式、字体、标题层级、表格几何都以 DOCX 为单一真源。

### 8.2 图像嵌入关系

图表等图片先作为独立产物生成，再嵌入 DOCX，最终随 DOCX 一起导出 PDF。

这样可以保证：

- 单独图片可交付
- DOCX 可引用
- PDF 可继承最终版式

## 9. 依赖策略

### 9.1 推荐主依赖

- `python-docx`
- `lxml`
- `LibreOffice/soffice`
- `pypdf`
- `pdfplumber`
- `pdftoppm`

### 9.2 可接受但非主线

- `reportlab`
  - 仅适合未来独立 PDF 直写场景
- `weasyprint`
  - 仅适合未来 HTML 文档链，不纳入本主线

## 10. 测试与验收

### 10.1 单测

- `PdfExportRequest -> command mapping`
- 导出失败时的错误分类
- 输出路径、临时目录、文件存在性检查

### 10.2 集成测试

- 学术风格 DOCX -> PDF
- 多页表格 DOCX -> PDF
- 图片嵌入 DOCX -> PDF
- 中英混排 DOCX -> PDF

### 10.3 视觉验收

- PDF 页数与 DOCX 页数一致性
- 页图是否可正常渲染
- 是否存在截断、错页、图表漂移

## 11. 最终结论

PDF 在本规划中被固定为：

- `DOCX -> PDF` 成熟导出链
- 复用 DOCX 主编辑能力
- 使用 LibreOffice/soffice 作为主转换栈
- 经过 PDF 自身校验后再交付
