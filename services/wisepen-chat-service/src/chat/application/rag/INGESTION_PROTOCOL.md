# RAG 入库协议

本文说明当前 WisePen RAG 入库阶段已经确定的内部协议。它只描述当前可落地的非权限入库边界，不预留 ACL、权限过滤或授权证据缓存字段。

## 当前上游输入

上游 Kafka 协议尚未最终定稿，但当前确定会提供：

- 已注入页码标记的 Markdown 正文。
- 预计算好的 ACL。

当前 RAG 入库代码只消费 Markdown 与文档归属信息。ACL 暂不进入当前协议；等权限模型确定后，应作为独立边界接入。

## 入库负载

`RagMarkdownIngestionPayload` 表达一篇 Markdown 文档的入库输入：

| 字段                 | 类型    | 语义                       |
|--------------------|-------|--------------------------|
| `resource_id`      | `str` | 业务资源根。当前只作为索引归属标识，不表达权限。 |
| `document_id`      | `str` | 文档稳定 ID。                 |
| `document_version` | `str` | 上游文档版本或修订号。              |
| `markdown`         | `str` | 已注入页码标记的 Markdown 正文。    |
| `title`            | `str` | 文档标题。                    |

页码标记统一格式：

```markdown
<!-- page 3 -->
```

## 分块结果

`RagChunkingResult` 是当前入库分块结果：

| 字段                 | 类型                           | 语义                                              |
|--------------------|------------------------------|-------------------------------------------------|
| `parent_chunks`    | `tuple[RagParentChunk, ...]` | 父块集合，用于后续上下文回填。                                 |
| `child_chunks`     | `tuple[RagChildChunk, ...]`  | 子块集合，用于精准检索与 Context Indexing。                  |
| `pipeline`         | `str`                        | 实际使用的 chunking pipeline。当前默认 `nested_markdown`。 |
| `resource_id`      | `str`                        | 透传入库负载的资源归属标识。                                  |
| `document_id`      | `str`                        | 透传入库负载的文档 ID。                                   |
| `document_version` | `str`                        | 透传入库负载的文档版本。                                    |
| `title`            | `str`                        | 透传入库负载的文档标题。                                    |

## Chunk 写入模型

`RagParentChunk` 与 `RagChildChunk` 的共同字段：

| 字段              | 类型                               | 语义                            |
|-----------------|----------------------------------|-------------------------------|
| `chunk_id`      | `str`                            | chunking engine 产出的 chunk ID。 |
| `text`          | `str`                            | chunk 原文。最终证据引用使用这个字段。        |
| `chunk_index`   | `int`                            | 当前层级内的顺序索引。                   |
| `start_offset`  | `int                             | None`                         | chunk 在整篇 Markdown 原文中的起始字符偏移。 |
| `end_offset`    | `int                             | None`                         | chunk 在整篇 Markdown 原文中的结束字符偏移。 |
| `extra_indexes` | `tuple[RagChunkExtraIndex, ...]` | 该 chunk 命中的额外索引投影。            |
| `content_hash`  | `str`                            | chunk 原文 hash。                |

`RagChildChunk` 额外字段：

| 字段                 | 类型    | 语义                                       |
|--------------------|-------|------------------------------------------|
| `parent_chunk_id`  | `str` | 子块所属父块 ID。                               |
| `indexing_context` | `str` | Context Indexing 小模型生成的上下文补充。            |
| `indexing_text`    | `str` | 用于 embedding / lexical indexing 的完整索引文本。 |

`indexing_text` 只服务检索，不作为最终引用证据。最终引用仍使用 `text`。

## 额外索引

`RagChunkExtraIndex` 是当前证据定位的核心结构。它是 chunk 的组成部分，不单独作为一张影子索引表建模。

| 字段             | 类型                | 语义                                                       |
|----------------|-------------------|----------------------------------------------------------|
| `index_name`   | `str`             | 完整索引名，例如 `page:3`、`section:鉴权 > Token`、`anchor:Table 1`。 |
| `index_kind`   | `IndexKind`       | 索引类型：`PAGE`、`SECTION`、`ANCHOR`。                          |
| `start_offset` | `int              | None`                                                    | 该索引覆盖的 Markdown 起始字符偏移。 |
| `end_offset`   | `int              | None`                                                    | 该索引覆盖的 Markdown 结束字符偏移。 |
| `section_path` | `tuple[str, ...]` | `SECTION` 索引对应的章节路径。                                     |
| `page_label`   | `str              | None`                                                    | `PAGE` 索引对应的页码标签。 |
| `anchor_label` | `str              | None`                                                    | `ANCHOR` 索引对应的表格、图片或公式锚点标签。 |

固定语义：

- 页码叫 `page_label`，表示页码标签，不表示页对象或页索引实体。
- 章节路径叫 `section_path`，表示从上级标题到当前标题的路径。
- 锚点叫 `anchor_label`，表示表格、图片、公式等可引用标签。
- 索引实体字段统一使用 `index_name` 和 `index_kind`。

## 证据回溯粒度

当前证据回溯粒度是 chunk。

`chunking_engine` 已保证 Markdown chunk 不跨页，因此不保存 `page_range` 或 `page_numbers` 这类冗余字段。需要页码时，从
`extra_indexes` 中读取 `index_kind == PAGE` 的 `page_label`。

证据定位路径：

```text
RagChildChunk.chunk_id
  -> RagChildChunk.text
  -> start_offset / end_offset
  -> extra_indexes(page_label / section_path / anchor_label)
```

命中子块后，如需要更完整上下文，通过 `parent_chunk_id` 回到父块。

## 当前禁止项

当前协议不要包含：

- ACL 投影字段。
- 权限 filter 字段。
- VIEW hard auth 结果。
- 已授权 evidence 物化缓存字段。
- 只为未来权限模型预留的占位 DTO。
- `extra_index_names` 这类只保存索引名、再靠别处反查的影子字段。
- `page_range` / `page_numbers` 这类已经由不跨页 chunk 保证掉的冗余字段。
- `page` / `anchor` 这类无法判断是标签、索引还是对象的模糊字段。

## 后续权限接入边界

等权限模型确定后，权限能力应作为独立边界接入：

- 入库协议仍保留当前非权限 chunk 与 extra index 结构。
- 权限投影、检索前 filter、prompt 前 hard auth 不混入当前 chunk 写入模型。
- 如果需要权限相关持久化模型，应另起明确命名的模型和处理链路。
