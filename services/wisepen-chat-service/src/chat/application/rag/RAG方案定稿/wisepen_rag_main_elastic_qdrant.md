# WisePen RAG 主链路：Elastic + Qdrant + RankingEngine

## 1. 定位

WisePen RAG 主链路采用 **Qdrant 主召回 + WisePen RankingEngine 重排** 的设计。

主链路只负责稳定地产生可引用、可回源、可重排的 `direct_evidence`。Neo4j 不参与主 topK 的竞争，图增强结果单独进入
`graph_evidence` 或 `ontology_hints`。

核心结构：

```text
user query
  -> optional Elastic strict keyword prefilter
  -> Qdrant dense retrieval
  -> Qdrant BM25 sparse retrieval
  -> WisePen RankingEngine
  -> topK direct_evidence
```

---

## 2. Qdrant 是主召回源

Qdrant 同时承担两路召回：

```text
dense vector retrieval:
  负责语义相似召回。

BM25 sparse retrieval:
  负责词法 / 关键词相关召回。
```

查询时两路并行或组合执行：

```text
query
  -> dense candidates
  -> sparse / BM25 candidates
  -> RankingEngine fusion / rerank
  -> topK
```

最终 `topK` 是主上下文来源，称为：

```text
direct_evidence
```

`direct_evidence` 是主模型回答时的第一证据源。

---

## 3. Elastic 是可选前置过滤器

Elastic 不作为一路召回源，不参与最终 topK 融合。

Elastic 的定位是：

```text
strict keyword prefilter
```

它只在需要严格关键词约束时启用，用于在 Qdrant 检索之前缩小候选范围。

典型触发场景：

```text
用户明确指定术语
用户指定标题 / 文件名 / 编号
用户查询代码标识符
用户查询必须精确包含某个关键词的内容
```

执行方式：

```text
query
  -> Elastic strict keyword filter
  -> 得到 candidate scope
  -> Qdrant 在该 scope 内做 dense + sparse retrieval
  -> RankingEngine
  -> topK direct_evidence
```

结论：

```text
Elastic 只负责限定检索范围。
Qdrant 仍然负责主召回。
RankingEngine 仍然负责最终 topK。
```

---

## 4. RankingEngine 职责

RankingEngine 接收 Qdrant 两路候选，负责融合、重排、过滤和多样化。

可综合信号：

```text
dense similarity score
sparse / BM25 score
keyword match signal
field weight
resource / source prior
recency / version signal
reranker score
diversity signal
```

输出：

```text
Ranked topK direct_evidence
```

设计边界：

```text
RankingEngine 只处理主召回候选。
Neo4j 图增强结果不混入主 topK。
```

这样可以保证主召回可评估、可调参、可复现。

---

## 5. direct_evidence 结构建议

`direct_evidence` 应至少包含：

```yaml
direct_evidence:
  - chunk_id: string
    resource_id: string
    document_id: string
    text: string
    section_path: string
    score:
      dense_score: float
      sparse_score: float
      rerank_score: float
      final_score: float
    source:
      retrieval_channels:
        - dense
        - sparse
      elastic_prefiltered: boolean
```

其中：

```text
text:
  用于最终上下文。

chunk_id / resource_id / document_id:
  用于回源、引用、审计。

score:
  用于 Answerability Hard Gate / Soft Gate / 日志评估。
```

---

## 6. 主链路与后续模块的关系

主链路输出后，后续模块依次处理：

```text
direct topK evidence
  -> Answerability Hard Gate
  -> Answerability Soft Gate
  -> optional Neo4j ontology enhancement
  -> Context Builder
  -> main model
```

主链路只回答一个问题：

```text
当前知识库中，最值得作为直接证据的 topK chunks 是哪些？
```

它不负责：

```text
多跳推理
ontology class 对齐
relation type 归纳
最终语义拒答
```

这些由 Answerability Gate、Neo4j Enhancement 和主模型处理。

---

## 7. 设计原则

1. **主召回稳定优先**  
   Qdrant dense + sparse 负责主文本召回，RankingEngine 负责主候选裁判。

2. **Elastic 只做前置过滤**  
   Elastic 不参与最终 topK 融合，不作为独立召回通道。

3. **topK 只来自主召回链路**  
   图增强结果不混入 direct topK。

4. **direct_evidence 是第一证据源**  
   主模型回答时应优先基于 direct_evidence。

5. **主链路不承担图推理职责**  
   概念关联、多跳路径、ontology 增强交给 Neo4j。
