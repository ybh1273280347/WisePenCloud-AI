# RAG 检索策略与词法门控

本文约束 WisePen 私有知识库 RAG 的默认检索形态，以及 Elasticsearch 在方案中的真实角色。

## 默认策略

第一版 RAG 默认采用 Qdrant-first hybrid：

- Qdrant 承担 dense retrieval。
- Qdrant 同时承担 sparse / BM25 / 基础全文过滤。
- 应用侧负责 rerank、diversify 和 Context Builder。

默认不把 Elasticsearch 作为常驻的第二条 lexical 召回 lane。

## Elasticsearch 的角色

Elasticsearch 只在需要严格词法门控时启用，典型场景包括：

- 必须精确命中的术语、错误码、版本号、函数名、文件名。
- quoted phrase、term / terms、复杂布尔条件、field analyzer 约束。
- 需要更强的高亮、词法分析或运维隔离能力。

如果 Qdrant 的 sparse/BM25、phrase filter 和字段约束已经足够，就不要再引入 Elasticsearch 作为重复的 BM25 通道。

## 检索模式

| profile | 默认执行 |
| --- | --- |
| `balanced` | Qdrant hybrid，通常不启用 Elasticsearch。 |
| `semantic` | Qdrant dense 权重更高，通常不启用 Elasticsearch。 |
| `lexical` | Qdrant sparse/BM25 权重更高；只有在确实需要严格词法门控时才启用 Elasticsearch。 |
| `anchored_exact` | 以 `must_terms`、quoted phrases、keyword 字段和 hard filter 为主；Elastic 只作为可选的严格词法门控实现。 |

## Review 规则

- 不要把 Elasticsearch 仅仅当成“另一套 BM25”。
- 不要把 Elastic 的分数和 Qdrant 的分数默认并列竞争。
- 不要让 strict lexical gate 变成默认召回路径。
- 每次启用 Elasticsearch，都要能说明 Qdrant hybrid 为什么不够。

## 结论

默认检索由 Qdrant 承担，Elasticsearch 只在精确词面约束足够强、且确实需要额外门控能力时才出现。
