# WisePen RAG Cache Boundary 指导方案

## 1. 背景

WisePen RAG 主链路已经定稿：

```text
user query
  -> optional Elastic strict keyword prefilter
  -> Qdrant dense retrieval
  -> Qdrant BM25 sparse retrieval
  -> WisePen RankingEngine
  -> direct topK evidence
  -> Answerability Hard Gate
  -> Answerability Soft Gate
  -> optional Neo4j Ontology Enhancement
  -> Context Builder
  -> Main Model
```

缓存方案不改变主链路职责，不替代 Qdrant 主召回，不替代 Neo4j 图增强，不替代主模型的短期对话记忆，也不缓存最终答案。

缓存只作为 RAG 运行时优化层，用于减少重复计算、重复图查询和 evidence 回源物化成本。

最高原则：

```text
可以接受一点不新鲜。
可以接受慢一点。
不能接受任何越权风险。
```

因此，任何缓存设计都必须满足：

```text
权限不确定 -> cache miss
版本不确定 -> cache miss
scope 不一致 -> cache miss
不能跨用户 / 跨团队 / 跨 ACL scope 复用
不能缓存 final answer
不能让缓存绕过 evidence 权限校验
```

---

## 2. 核心洞察

RAG 的时间成本不只发生在检索阶段。

在 WisePen 当前链路中，主要成本集中在三类位置：

```text
1. Qdrant dense / sparse 检索与 RankingEngine 重排
2. Neo4j 图增强检索
3. Qdrant / Neo4j 返回 id 后的 evidence 回源物化
```

第 3 点尤其重要。

Qdrant 和 Neo4j 通常返回的是：

```text
chunk_id
relation_evidence_id
concept_id
path_id
score
metadata
```

但 Context Builder 不能只拿 id 构造最终上下文，它还需要继续回源：

```text
evidence id
  -> 回源 child chunk
  -> 根据 child chunk 找 parent chunk
  -> 组织 citation / section path / evidence text
  -> 构造 prompt context
```

所以一次完整 RAG 的成本实际包括：

```text
检索成本
+ 重排成本
+ 图增强成本
+ child chunk 回源成本
+ parent chunk 回源成本
+ context 组装成本
```

缓存的价值不应该只看“能否减少 Qdrant 检索”，而应该看它是否能优化以上任意一个真实高成本环节。

---

## 3. 缓存准入标准

一个缓存层是否值得引入，必须先回答：

```text
1. 它跳过了哪个真实昂贵步骤？
2. 它是否会绕过 ACL？
3. 它是否会绕过 corpus / document version？
4. 它是否会让 answer 和 evidence 不一致？
5. 它是否比直接批量查询更简单？
```

如果不能跳过真实昂贵步骤，只是把一次数据库读取换成另一次数据库读取，就不应该引入。

如果能显著降低重复计算、重复图查询或重复 child / parent chunk 回源，并且不引入越权风险，则可以进入方案。

---

## 4. 当前推荐的缓存层

当前只保留三类缓存边界：

```text
P0: Ingestion Deterministic Cache
P1: Authorized Evidence Materialization Cache
P2: Graph Enhancement Cache
```

其中：

```text
Retrieval Run Idempotency Cache
```

只作为低优先级工程去重能力，不作为主缓存方向。

---

## 5. P0：Ingestion Deterministic Cache

### 5.1 定位

Ingestion Deterministic Cache 用于减少入库阶段重复计算。

它不直接面向用户回答，不参与查询阶段权限判断，因此安全风险最低、收益最稳定。

### 5.2 优化对象

它主要优化：

```text
Markdown 分块重复计算
Context Indexing 小模型重复调用
Embedding API 重复调用
Graph Extraction 重复调用
Kafka 重复消费 / 失败重试 / 重建索引导致的重复工作
```

### 5.3 基本思路

对于同一个文档版本、同一份内容、同一套处理配置，如果已经计算过中间结果，就不重复计算。

可缓存的中间结果包括：

```text
chunking result
context indexing result
embedding result
graph extraction result
```

这些结果应基于：

```text
content hash
document version
chunking config version
context indexing prompt / model version
embedding model version
graph extraction config version
ontology schema version
```

进行版本化。

### 5.4 权限边界

内容派生产物可以复用，但权限投影不能复用。

也就是说：

```text
chunking / context indexing / embedding / graph extraction:
  可以按 content/version/config 复用。

Qdrant / Neo4j ACL projection:
  必须绑定最新 ACL projection。
```

如果 ACL 变化，不一定需要重新算 embedding 或重新抽取图结构，但必须更新或重建对应的权限投影。

---

## 6. P1：Authorized Evidence Materialization Cache

### 6.1 定位

Authorized Evidence Materialization Cache 是查询阶段的 evidence 物化缓存。

它不是 query cache。
它不是 final answer cache。
它不是主 agent 的短期记忆。
它不负责判断用户是否在追问上一轮内容。
它不负责跳过 Qdrant 检索。

它只负责一件事：

```text
当 RAG 链路已经得到 direct_evidence / graph_evidence ids 后，
在同一 user、session、ACL scope、corpus version 下，
复用已经授权并物化过的 evidence text / citation / parent context。
```

### 6.2 为什么需要它

Qdrant 和 Neo4j 返回的是 evidence ids。
Context Builder 仍然需要根据这些 ids 回源：

```text
child_chunk_id -> child chunk
child chunk -> parent chunk
relation_evidence_id -> support chunk
chunk -> citation metadata
```

如果同一 session 内多次命中相同或重叠的 evidence ids，就会重复进行 child / parent chunk 回源。

该缓存的目标就是降低这部分物化成本。

### 6.3 工作方式

正常查询链路仍然照常执行：

```text
Qdrant retrieval
  -> RankingEngine
  -> direct_evidence ids
```

得到 ids 后进入 evidence materialization：

```text
direct_evidence ids / graph_evidence ids
  -> Authorized Evidence Materialization Cache lookup
  -> hit:
       直接得到已授权、已物化的 child / parent evidence view
  -> miss:
       批量回源 child chunks
       批量回源 parent chunks
       写入 Redis 短 TTL 缓存
```

因此它优化的是：

```text
id -> child chunk
child chunk -> parent chunk
support evidence -> citation/context
```

而不是：

```text
query -> retrieval result
query -> final answer
```

### 6.4 缓存作用域

该缓存必须是受限作用域缓存：

```text
同一 user
同一 session
同一 kb
同一 ACL version / ACL scope
同一 corpus version
短 TTL
```

不能跨用户复用。
不能跨团队复用。
不能跨 ACL scope 复用。
不能跨 corpus version 复用。

Kafka 新广播导致知识库投影变化时，应更新 corpus version / projection epoch，让旧缓存自然 miss。

### 6.5 存储建议

该缓存适合落在 Redis。

原因：

```text
命中目标是短时间内重复 evidence 物化
缓存对象适合短 TTL
可以按 session / ACL / corpus version 做自然隔离
失效可以主要依赖 TTL + version miss
```

缓存 value 应控制大小，只保存 Context Builder 需要的短文本、parent context 摘要或片段、citation 信息和必要 metadata。

不应缓存：

```text
完整文档
完整 markdown
final answer
跨 session 长期 evidence memory
```

### 6.6 安全边界

使用缓存前必须确认：

```text
当前 user/session/ACL/corpus version 与缓存一致
缓存中的 evidence 仍属于当前可访问 scope
document version 仍然有效
```

如果任何条件不确定：

```text
cache miss
fallback batch source loading
```

该缓存遵循：

```text
安全优先。
命中保守。
不确定就回源。
```

---

## 7. P2：Graph Enhancement Cache

### 7.1 定位

Graph Enhancement Cache 用于减少 Neo4j 图增强的重复计算。

它不按 query 字符串缓存，而按图增强的稳定输入缓存：

```text
direct evidence signature
+ answerability warning
+ graph version
+ ontology schema version
+ ACL scope
```

### 7.2 优化对象

它主要优化：

```text
Neo4j concept path expansion
RelationEvidence 查询
OntologyClass / RelationType 对齐
graph evidence 组织
ontology hints 生成
```

### 7.3 工作方式

在 Soft Gate 触发 warning 后：

```text
Soft Gate warning
  -> Graph Enhancement Cache lookup
  -> hit:
       使用已缓存的 graph_evidence ids / ontology_hints
  -> miss:
       执行 Neo4j Ontology Enhancement
       写入缓存
```

Graph Enhancement Cache 不直接缓存最终回答。

缓存结果进入 Context Builder 前，仍需进行 evidence 权限校验和 materialization。

### 7.4 适用阶段

该缓存应在 Neo4j enhancement 链路稳定后再引入。

原因：

```text
需要先观察 Neo4j 图增强的真实延迟
需要确认 direct_evidence_hash / warning_hash 的稳定性
需要确认 graph_evidence 的复用率
```

第一阶段不必强行实现。

---

## 8. 降级项：Retrieval Run Idempotency Cache

Retrieval Run Idempotency Cache 不作为 RAG 缓存主方向。

原因是自然语言 query 高度不稳定：

```text
同一意图可以有很多表述
相似 query 不能直接复用
semantic query cache 有 ACL 和证据错配风险
```

因此它只用于工程去重：

```text
同一请求 retry
前端重复提交
agent loop 误重复调用
benchmark replay
短 TTL 内完全相同 normalized query
```

它不承担主要性能优化职责。

---

## 9. 明确不做的缓存

第一阶段不做：

```text
Final Answer Cache
Semantic Query Cache
跨用户 Retrieval Result Cache
跨团队 Evidence Cache
全局 chunk_id -> chunk_text cache
长期 session memory cache
```

原因：

```text
可能绕过 ACL
可能复用旧版本 evidence
可能导致 answer 与 citation 不一致
可能引入跨用户 / 跨团队越权
收益无法覆盖复杂度和风险
```

---

## 10. 查询链路中的缓存位置

加入缓存后的查询链路应保持主链路职责不变：

```text
user query
  -> resolve user / session / kb / ACL / corpus version

  -> optional Elastic strict keyword prefilter
  -> Qdrant dense retrieval
  -> Qdrant BM25 sparse retrieval
  -> WisePen RankingEngine
  -> direct_evidence ids

  -> Authorized Evidence Materialization Cache lookup
       hit:
         load materialized child / parent evidence view
       miss:
         batch load child chunks
         batch load parent chunks
         write materialization cache

  -> Answerability Hard Gate
  -> Answerability Soft Gate

  -> if Soft Gate warning:
       optional Graph Enhancement Cache lookup
       if miss:
          Neo4j Ontology Enhancement
          write graph enhancement cache

       graph_evidence ids
       Authorized Evidence Materialization Cache lookup / batch source loading

  -> Context Builder
  -> Main Model
```

重点：

```text
检索照常发生。
缓存只优化 evidence materialization。
Graph Enhancement Cache 只优化 Neo4j 图增强。
Ingestion Cache 只优化入库计算。
```

---

## 11. 入库链路中的缓存位置

```text
Kafka ingestion event
  -> validate ACL projection / markdown / document version

  -> Ingestion Deterministic Cache lookup

  -> chunking
  -> context indexing
  -> embedding
  -> graph extraction

  -> Qdrant projection with latest ACL
  -> Neo4j projection with latest document/resource/version anchors

  -> update corpus version / projection epoch
```

Kafka 新广播不需要主动清理所有查询缓存。
只要更新 corpus version / projection epoch，旧缓存即可自然 miss，并等待 TTL 过期。

---

## 12. 最终推荐优先级

```text
P0: Ingestion Deterministic Cache
P1: Authorized Evidence Materialization Cache
P2: Graph Enhancement Cache
P3: Retrieval Run Idempotency Cache
```

其中：

```text
P0:
  降低入库重复计算成本。

P1:
  降低 child / parent chunk 回源物化成本。

P2:
  降低 Neo4j 图增强重复计算成本。

P3:
  仅用于短 TTL 重复请求去重。
```

---

## 13. 最终口径

WisePen RAG 缓存不围绕 query 字符串，也不缓存 final answer，而是围绕可校验的中间事实做优化。入库阶段缓存 chunking、context
indexing、embedding 和 graph extraction；查询阶段在 Qdrant / Neo4j 返回 evidence ids 后，通过 Redis 缓存同一
user、session、ACL scope、corpus version 下已经授权并物化过的 child / parent evidence view，从而降低 evidence 回源和 Context
Builder 组装成本；Neo4j 稳定后再引入 Graph Enhancement Cache，减少重复图增强。所有缓存必须绑定权限和版本，任何权限或版本不确定时直接
cache miss，并回退完整、安全的 RAG 链路。
