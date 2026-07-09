# WisePen Python 附件消费侧文档解析技术报告

## 1. 背景

WisePen 当前存在两类文档处理链路：

```text
Java 知识库入库链路：
  重视长期质量、结构完整性、索引可靠性

Python 附件消费链路：
  重视速度、稳定性、即时问答、多模态上下文组装
```

本报告只覆盖 **Python 附件消费侧**。该链路的目标不是替代 Java 知识库入库，而是在用户上传附件后，快速解析出可供模型消费的文本、表格、图片等上下文。

---

## 2. 最终技术选型

### 2.1 路由策略

| 文件类型                          | 解析策略                         | 说明                                 |
| ----------------------------- | ---------------------------- | ---------------------------------- |
| PDF                           | **MinerU**                   | PDF 解析质量要求高，其他方案在表格、公式、图文结构上不足     |
| DOCX                          | **Docling**                  | 实测稳定，Markdown 输出质量好，表格结构可用         |
| PPTX                          | **Docling**                  | 实测稳定，可解析 slide、文本、表格、图片            |
| XLSX                          | **pandas / openpyxl**        | XLSX 本质是结构化表格数据，Python 侧不走 Docling |
| TXT / MD / JSON / YAML / Code | Direct loader                | 直接读取即可                             |
| 其他冷门格式                        | **Docling -> MarkItDown 兜底** | Docling 优先，MarkItDown 只做最后兜底       |

核心结论：

```text
PDF 用 MinerU。
Office 全家桶用 Docling。
XLSX 单独走 pandas/openpyxl。
其他边角格式 Docling 优先，MarkItDown 兜底。
```

---

## 3. Docling Office 实测结果

### 3.1 PPTX 测试结果

测试文件：

```text
C:\Users\12732\Downloads\Chapter4 频域.pptx
```

结果：

```text
status = ConversionStatus.SUCCESS
pages = 73
tables = 2
pictures = 268

run1 = 16.6137s
run2 = 2.2207s
run3 = 2.1969s
```

判断：

```text
PPTX 解析成功。
图片链路可用。
冷启动较慢，但热运行速度很理想。
Docling 可作为 PPTX 主解析器。
```

### 3.2 DOCX 测试结果

测试文件：

```text
C:\Users\12732\Downloads\复旦_中国近现代史纲要_期末开卷资料_教材页码定位_选择题论述题完整版.docx
```

结果：

```text
status = ConversionStatus.SUCCESS
markdown_chars = 99114
text_chars = 96450
tables = 134
pictures = 0

run1 = 5.6781s
run2 = 6.4757s
run3 = 7.5664s
```

判断：

```text
DOCX 解析成功。
大体量文本和表格均可稳定输出。
Docling 可作为 DOCX 主解析器。
```

---

## 4. 图片消费方案

### 4.1 问题

Docling 可以将 PPTX 中的图片导出为引用形式，例如：

```markdown
![Image](D:\...\image_000001.png)
```

但生产环境不能依赖本地文件路径，原因包括：

```text
1. 本地路径无法跨服务访问
2. 会泄露服务器目录结构
3. 无法做权限控制
4. 图片生命周期难以管理
5. 不适合多机部署
```

同时，Python 附件消费侧不希望长期保存图片资产。

---

### 4.2 最终方案：Base64 内嵌 + 多模态拆分

采用 Docling 的 embedded image 模式：

```python
from docling_core.types.doc import ImageRefMode

markdown = doc.export_to_markdown(
    image_mode=ImageRefMode.EMBEDDED,
    image_placeholder="<!-- image -->",
    traverse_pictures=False,
)
```

Docling 生成的 Markdown 中图片形态类似：

```markdown
![Image](data:image/png;base64,iVBORw0KGgoAAA...)
```

随后将 Markdown 拆分为：

```text
stripped_markdown:
  去除 base64 图片后的纯文本 Markdown

images:
  从 Markdown 中提取出的 data:image/...;base64,... 图片输入
```

---

## 5. 模型消费协议

多模态模型可以消费 base64 图片，但必须作为 **image input part** 传入，而不是作为普通文本。

### 5.1 错误方式

```python
content = "![Image](data:image/png;base64,...)"
```

这种情况下，模型大概率会把 base64 当成普通文本。

### 5.2 正确方式

```python
content = [
    {
        "type": "input_text",
        "text": stripped_markdown,
    },
    {
        "type": "input_image",
        "image_url": images[0].data_url,
    },
]
```

这也是最终定稿的多模态上下文格式。

---

## 6. 图片选择策略

PPTX 实测中存在：

```text
73 slides
268 pictures
```

因此不能将所有图片一次性发送给模型。

默认策略：

```text
普通总结 / 普通问答：
  只发送 stripped_markdown

用户明确问图片、图表、流程图、公式、某一页：
  选择相关页面/slide 的少量图片作为 input_image

限制：
  max_images_per_request = 3~6
  max_images_per_slide = 1~2
```

图片只作为本次模型调用的临时内存产物，不长期保存。

---

## 7. 推荐数据结构

```python
class EmbeddedImagePart(BaseModel):
    image_id: str
    mime_type: str
    data_url: str
    page_no: int | None = None
    slide_no: int | None = None
    alt: str | None = None


class AttachmentParseResult(BaseModel):
    parser: str
    file_type: str
    content: str                 # stripped_markdown
    embedded_images: list[EmbeddedImagePart]
    warnings: list[str] = []
```

注意：

```text
data_url 不写日志。
data_url 不落库。
data_url 不返回前端。
data_url 只在本次模型调用链路中短暂存在。
```

---

## 8. 生命周期策略

本方案不引入长期图片存储。

```text
原始上传附件：
  按现有附件生命周期处理

Docling 解析出的 base64 图片：
  仅在本次请求内存中存在

模型调用完成：
  释放 embedded_images

最终回答：
  默认只返回文本结果
```

如果未来需要前端展示源文档图片或支持长时间追问图片，再升级为会话级 Artifact Sandbox。当前定稿版本不引入该复杂度。

---

## 9. 最终链路

```text
用户上传附件
  ↓
Attachment Parse Router
  ↓
按类型分流：
  PDF  -> MinerU
  DOCX -> Docling
  PPTX -> Docling
  XLSX -> pandas/openpyxl
  其他 -> Docling -> MarkItDown
  ↓
Docling Office:
  export_to_markdown(ImageRefMode.EMBEDDED)
  ↓
split_embedded_images()
  ↓
AttachmentParseResult:
  content = stripped_markdown
  embedded_images = base64 data URLs
  ↓
Context Assembler:
  默认只使用 content
  必要时选择少量 embedded_images
  ↓
Model Runtime:
  input_text + input_image
```

---

## 10. 定稿结论

WisePen Python 附件消费侧文档解析方案定稿为：

```text
PDF：
  MinerU

DOCX / PPTX：
  Docling

XLSX：
  pandas / openpyxl

其他冷门格式：
  Docling -> MarkItDown 兜底

图片消费：
  Docling ImageRefMode.EMBEDDED
  base64 内嵌
  拆分为 input_text + input_image
  不长期保存图片
```

该方案兼顾：

```text
速度
稳定性
多模态能力
无图片持久化压力
模型可直接消费
工程边界清晰
```

最终核心实现格式：

```python
content = [
    {
        "type": "input_text",
        "text": stripped_markdown,
    },
    {
        "type": "input_image",
        "image_url": images[0].data_url,
    },
]
```
