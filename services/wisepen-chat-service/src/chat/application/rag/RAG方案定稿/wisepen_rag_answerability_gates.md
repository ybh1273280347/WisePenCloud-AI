# WisePen RAG 可拒答设计：Answerability Hard Gate + Soft Gate

## 1. 定位

WisePen RAG 的可拒答体系采用：

```text
Answerability Hard Gate
Answerability Soft Gate
Main Model Semantic Judgment
```

三层分工：

```text
Hard Gate:
  判断有没有必要继续。

Soft Gate:
  判断有没有必要增强。

Main Model:
  判断最终怎么回答。
```

一句话：

```text
Hard Gate 是刹车。
Soft Gate 是仪表盘，也是 Neo4j Enhancement 的触发器。
主模型是最终驾驶员。
```

---

## 2. 总体链路

```text
user query
  -> optional Elastic strict keyword prefilter
  -> Qdrant dense retrieval
  -> Qdrant BM25 sparse retrieval
  -> WisePen RankingEngine
  -> direct topK evidence

  -> Answerability Hard Gate
       - EMPTY_RETRIEVAL
       - TOPK_ALL_BELOW_ABSOLUTE_MIN_SCORE

  -> Answerability Soft Gate
       - warning reasons
       - answering guidance

  -> if Soft Gate triggered:
       Neo4j Ontology Enhancement

  -> Context Builder
       - direct_evidence
       - graph_evidence
       - ontology_hints
       - answerability_warning

  -> Main Model
       - answer
       - partial answer
       - clarification
       - refusal
```

---

## 3. Answerability Hard Gate

Hard Gate 是服务端硬拒答。

位置：

```text
RankingEngine 输出 direct topK 之后
Soft Gate 之前
Neo4j Enhancement 之前
```

职责：

```text
只处理极端确定失败。
```

Hard Gate reason：

```text
EMPTY_RETRIEVAL
TOPK_ALL_BELOW_ABSOLUTE_MIN_SCORE
```

### 3.1 EMPTY_RETRIEVAL

含义：

```text
Qdrant dense + sparse 没有返回可用候选。
```

处理：

```text
直接拒答。
不进入 Soft Gate。
不进入 Neo4j Enhancement。
不调用主模型生成知识性答案。
```

建议返回语义：

```text
当前知识库中没有找到与该问题相关的资料。
```

### 3.2 TOPK_ALL_BELOW_ABSOLUTE_MIN_SCORE

含义：

```text
存在召回结果，但所有 topK 的最终分数都低于绝对最低可用阈值。
```

处理：

```text
直接拒答。
不进入 Soft Gate。
不进入 Neo4j Enhancement。
```

注意：

```text
这个阈值必须非常保守。
Hard Gate 宁可少拦，不要误杀。
```

---

## 4. Answerability Soft Gate

Soft Gate 是风险提示器，不做硬拒绝。

位置：

```text
Hard Gate 通过之后
Neo4j Enhancement 之前
Context Builder 之前
```

职责：

```text
判断 direct evidence 是否不完美。
输出 warning 和 guidance。
一旦触发 warning，即触发 Neo4j Enhancement。
```

Soft Gate 不输出：

```text
reject = true
```

它输出：

```yaml
answerability_warning:
  warnings:
    - LOW_DIRECTNESS
    - PARTIAL_COVERAGE
  guidance: "当前证据可能只能支持部分回答，不要过度推断。"
```

`warnings` 是闭集，只允许使用下文列出的 warning reason。

如果 Soft Gate 小模型输出未知 warning，服务端会静默过滤该值；未知值不作为有效 warning，不触发 Neo4j Enhancement，也不让 Soft
Gate 失败。

---

## 5. Soft Gate Warning Reasons

### 5.1 LOW_DIRECTNESS

含义：

```text
证据需两步以上推理才能得出答案，或只提供背景信息，未包含答案所需的具体数值、实体或结论。
```

影响：

```text
触发 Neo4j Enhancement。
提示主模型谨慎回答，不要强推理。
```

Neo4j 尝试：

```text
从 seed concept 找更直接的 relation evidence。
```

### 5.2 PARTIAL_COVERAGE

含义：

```text
问题包含多个明确子项，而 direct evidence 缺失任一子项。
该 warning 优先于 LOW_DIRECTNESS。
```

影响：

```text
触发 Neo4j Enhancement。
提示主模型明确“当前资料只支持某部分”。
```

Neo4j 尝试：

```text
沿相关概念补充 graph evidence。
```

### 5.3 ENTITY_AMBIGUOUS

含义：

```text
仅在同一证据内或跨证据间，同一字符串被用于指代两个不同且无法区分的实体时触发。
```

影响：

```text
触发 Neo4j Enhancement。
提示主模型说明歧义，必要时请求澄清。
```

Neo4j 尝试：

```text
用 Mention / Concept 图辅助实体消歧。
```

### 5.4 CONTEXT_MISMATCH

含义：

```text
证据的时间、地域、假设前提或数据口径，与问题中明确限定的条件存在直接冲突或明确不符。
```

影响：

```text
触发 Neo4j Enhancement。
提示主模型降低确定性。
```

Neo4j 尝试：

```text
检查 seed concept 与目标 concept 是否路径一致。
```

### 5.5 EVIDENCE_CONFLICT

含义：

```text
topK evidence 之间存在明显冲突。
```

影响：

```text
触发 Neo4j Enhancement。
提示主模型列出冲突，不强行统一。
```

Neo4j 尝试：

```text
查找更多 relation evidence / concept path 辅助解释冲突。
```

---

## 6. Soft Gate 与 Neo4j Enhancement 的关系

Soft Gate 一旦触发，就等价于：

```text
必须尝试 Neo4j Enhancement。
```

原因：

```text
Soft Gate 的含义不是“不能答”，而是“当前 direct evidence 不完美”。
direct evidence 不完美，就有理由尝试图增强。
```

执行语义：

```text
Soft Gate triggered
  -> run Neo4j Enhancement
  -> if graph evidence found:
       add graph_evidence
  -> if structural hints found:
       add ontology_hints
  -> if nothing useful found:
       keep answerability_warning only
```

注意：

```text
Neo4j Enhancement 被触发，不代表必须补充 graph_evidence。
如果没有高质量图证据，可以只保留 warning。
```

---

## 7. Context Builder 中的结构

Context Builder 接收：

```yaml
direct_evidence:
  - chunk_id: string
    text: string
    score: object
    citation_anchor: string

graph_evidence:
  - chunk_id: string
    evidence_text: string
    graph_path: list
    citation_anchor: string

ontology_hints:
  - concept: string
    class_candidates: list
    relation_type_candidates: list
    path_preview: list

answerability_warning:
  warnings: list
  guidance: string
```

字段语义：

```text
direct_evidence:
  主证据。

graph_evidence:
  图增强补充证据。

ontology_hints:
  非证据结构提示。

answerability_warning:
  风险提示和回答建议。
```

---

## 8. 主模型职责

主模型不需要猜测检索质量，因为 Soft Gate 已经提供 warning。

主模型根据：

```text
direct_evidence
graph_evidence
ontology_hints
answerability_warning
```

决定：

```text
完整回答
部分回答
带不确定性回答
请求澄清
拒答
```

主模型回答原则：

```text
资料支持什么，就回答什么。
资料不支持的部分，明确说明无法确认。
如果实体歧义明显，先澄清或说明假设。
如果 evidence 冲突，列出冲突，不强行统一。
```

---

## 9. Gate 分工总结

| 层级                | 位置                | 是否中断 | 职责                              |
|-------------------|-------------------|-----:|---------------------------------|
| Hard Gate         | 主召回 topK 后        |    是 | 极端失败直接拒答                        |
| Soft Gate         | Hard Gate 后       |    否 | 给 warning，并触发 Neo4j Enhancement |
| Neo4j Enhancement | Soft Gate 触发后     |    否 | 尝试补强 direct evidence            |
| Main Model        | Context Builder 后 | 最终表达 | 完整答、部分答、澄清或拒答                   |

---

## 10. 最终原则

```text
Hard Gate:
  有没有必要继续。

Soft Gate:
  有没有必要增强。

Neo4j:
  尝试增强。

Main Model:
  怎么回答。
```

最终一句话：

```text
WisePen 的可拒答不是单点二分类，而是分层质量控制。
Hard Gate 只处理空召回和极端低分。
Soft Gate 不拒绝，只输出风险提示，并触发 Neo4j Enhancement。
最终是否完整回答、部分回答或拒答，由主模型基于 direct evidence、graph evidence、ontology hints 和 answerability warning 综合决定。
```
