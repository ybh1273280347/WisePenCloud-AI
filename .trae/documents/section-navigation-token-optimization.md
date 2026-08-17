# Section 导航 Token 优化：完整性标识 + 正文解耦 + 方向排除

## 摘要

在工具契约层为 LOCATE / READ 增加三项轻量增强，降低 Agent 导航决策成本，不触碰索引与排序核心：

1. `is_complete`：locate 响应中 Section 元数据的完整性标识，消除盲目 `getSectionContent` 补读
2. `include_body`：`getSectionContent` 的正文开关，"翻目录"式漫游不再携带正文
3. `exclude_directions`：`getSectionContent` 的导航方向黑名单，从契约层阻断回头跳转

## 现状分析

### 痛点对应的代码事实

**痛点 1（重载）**：[candidate\_locator.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/application/rag/navigate/candidate_locator.py) 的 `_build_retrieved_section_views` 只把**命中的** ReadingBlock 提升为 `RetrievalReadingBlockView`。Section 的直属正文可能由多个 block 组成（ReadingBlock 按 4000 字符切分），模型无法判断已返回文本是否覆盖全节，只能"求稳"再调 `getSectionContent`。

**痛点 2（漫游贵）**：[endpoints/read.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/api/endpoints/read.py) 的 `getSectionContent` 无条件返回 `text` 全文；模型只想看 `navigation`（父/子/兄弟锚点）时也被迫承担正文 token。

**痛点 3（回头跳）**：[content.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/application/rag/read/content.py) 的 `SectionNavigationView` 总是同时返回 `parent/previous/next/children`；A→next→B 后 B 的 `previous` 指回 A，无契约层手段屏蔽。

### 关键数据结构（已探明）

* `Section.content_spans`：直属正文原文半开区间（[structure.py:47](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/domain/models/structure.py#L47)，不含标题/子节）

* `ReadingBlock.source_spans`：block 在原文中的区间（与 content\_spans 同坐标系）

* `SourceEvidence` 同时携带 `record.section`（含 content\_spans）与 `record.reading_block`（含 source\_spans）——**is\_complete 所需数据已在证据中，零额外 IO**

* locate 响应 schema（[schemas/locate.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/api/schemas/locate.py)）直接复用应用层 dataclass，加字段自动进契约

## 对原方案的评估与修正

| 原方案                             | 评估                                                                              | 修正                                                                           | <br />                              |
| ------------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | :---------------------------------- |
| is\_complete 加在"locate 及导航工具"   | `getSectionContent` 的 `text` 定义即 Section 直属正文**全集**，该处 is\_complete 恒 true，无信息量 | **仅加在 locate 响应**（`RetrievedSectionView`）                                    | <br />                              |
| is\_complete 由后端判断（未定算法）        | 需确定性、零额外读取                                                                      | **区间覆盖法**：提升 blocks 的 source\_spans 合并后完整覆盖 section 全部 content\_spans → true | <br />                              |
| include\_body=false"裁剪 text 字段" | 端点已有 `response_model_exclude_none=True`；返回空串仍占 token 且语义含糊                      | `text: str` → \`str                                                          | None\`，排除时置 **None**，字段从 JSON 中彻底消失 |
| exclude\_directions 黑名单         | 校验需拒绝非法方向名                                                                      | pydantic `Literal["parent","previous","next","children"]` 自动校验（非法值 422）      | <br />                              |

边界语义（区间覆盖法）：

* 纯标题节（content\_spans 为空）：无正文可读，恒 `is_complete=True`

* FLAT\_TEXT 合成节：单 block 即全集，命中即 `is_complete=True`

* SECTIONED 部分命中：命中 block 区间联合 ⊉ content\_spans → `false`

## 改动清单

### 1. is\_complete（locate 响应）

**[candidate\_locator.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/application/rag/navigate/candidate_locator.py)**

* `RetrievedSectionView` 增加 `is_complete: bool = True` 字段

* `_build_retrieved_section_views` 中按 section 聚合已提升 block 的 `source_spans`（注意：`record.reading_block.source_spans` 在 record 层可用，block 去重后收集），与 `record.section.content_spans` 做覆盖判定

* 新增模块级辅助函数：

```python
def _spans_cover(covered: list[SourceSpan], target: list[SourceSpan]) -> bool:
    """target 的每个区间都被 covered 的合并区间完整包含。"""
    if not target:
        return True
    merged: list[list[int]] = []  # [start, end] 排序合并
    for span in sorted(covered, key=lambda s: s.start_offset):
        if merged and span.start_offset <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], span.end_offset)
        else:
            merged.append([span.start_offset, span.end_offset])
    # 对每个 target 区间二分/线性找包含它的合并区间
    ...
```

**[schemas/locate.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/api/schemas/locate.py)**：无需改动（`sections: list[RetrievedSectionView]` 直接引用 dataclass，新字段自动进契约）。

### 2. include\_body（getSectionContent）

**[content.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/application/rag/read/content.py)**

* `SectionContentView.text: str` → `str | None = None`

* `get_sections` 增加 `include_body: bool = True` 关键字参数，透传 `_to_section_content_view(content, include_body=...)`

* `_to_section_content_view`：`text=content.text if include_body else None`

**[schemas/read.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/api/schemas/read.py)**

* `SectionContentRequest` 增加 `include_body: bool = True`

**[endpoints/read.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/api/endpoints/read.py)**

* `get_section_content` 传递 `include_body=request.include_body`

### 3. exclude\_directions（getSectionContent）

**[schemas/read.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/api/schemas/locate.py)** **之上的 read schema**

* 定义 `NavigationDirection = Literal["parent", "previous", "next", "children"]`

* `SectionContentRequest` 增加 `exclude_directions: list[NavigationDirection] = Field(default_factory=list, max_length=4)`

**[content.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/application/rag/read/content.py)**

* `get_sections` 增加 `exclude_directions: Sequence[str] = ()` 参数（应用层接收已校验集合，转 `frozenset`）

* `_to_section_content_view` 按 `frozenset` 过滤：`"parent" in excluded → parent=None`，`"children" in excluded → children=[]`，previous/next 同理

**[endpoints/read.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/src/rag/api/endpoints/read.py)**

* 传递 `exclude_directions=request.exclude_directions`

### 不改动的部分

* `PublishedResourceReader.get_sections`（reader 协议）：正文/导航事实照旧全量返回，裁剪发生在视图组装层——存储边界职责不变

* `get_pages`、`getDocumentOutline`：方案范围外

* 检索、排序、图谱链路：零影响

## 测试计划

**[test\_reading\_entry\_locator.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/tests/rag/test_reading_entry_locator.py)**

* 新增：多 block section 部分命中 → `is_complete=False`；全覆盖 → `True`；FLAT\_TEXT → `True`

* 现有 `_record` 构造的 section `content_spans=[SourceSpan(0,10)]`、block `source_spans=[SourceSpan(0,10)]` → 现有断言处 `is_complete` 天然为 True，不破坏存量

**[test\_read\_endpoints.py](d:/WisePenCloud-AI/WisePenCloud-AI-rag-v2/services/wisepen-rag-service-v2/tests/rag/test_read_endpoints.py)**

* `include_body=False`：响应无 `text` 键（或为 None），`navigation` 完整

* `exclude_directions=["previous"]`：`navigation.previous` 为 None/缺失，其余方向保留

* `exclude_directions=["children"]`：`navigation.children` 为空

* 非法方向名 → 422 校验拒绝

* 默认参数（不传新字段）→ 响应与现状完全一致（向后兼容）

## 假设与决策

1. 参数命名沿用原方案（`is_complete` / `include_body` / `exclude_directions`），与团队文档对齐
2. `include_body` 默认 True、`exclude_directions` 默认空——纯增量，老调用方零感知
3. is\_complete 用区间覆盖而非 block 计数：无需知道 section 的 block 总数（locator 侧无此数据），且对"命中 block 覆盖全部正文区间"的判定更直接
4. 过滤/裁剪全部在应用层视图组装完成，不改 Mongo reader 协议与存储 schema

## 验证步骤

1. `pytest tests/rag/test_read_endpoints.py tests/rag/test_reading_entry_locator.py -q`（新增+存量）
2. `pytest tests -q` 全量回归（基线 177 passed）
3. 手工冒烟（可选）：`getSectionContent` 带 `include_body=false, exclude_directions=["previous"]` 观察响应 JSON 裁剪效果

