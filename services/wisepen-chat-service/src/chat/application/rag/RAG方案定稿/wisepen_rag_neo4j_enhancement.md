# WisePen RAG 后置增强：Neo4j Ontology Enhancement

## 1. 定位

Neo4j 在 WisePen RAG 中定位为：

```text
Ontology Enhancement Layer
```

它不作为普通召回通道，不参与主 topK 竞争。

Neo4j 的目标是增强主召回之后的语义结构理解：

```text
实体关联
实体消歧
概念归并
关系抽取
关系类型归纳
ontology class 对齐
多跳路径解释
graph evidence 补充
```

GraphRAG 可以作为后续拓展点，但当前核心目标不是替代 RAG 主召回，而是增强 `direct_evidence` 之后的概念结构和关系推理能力。

---

## 2. Neo4j 存什么

Neo4j 存围绕 child chunk 构建出的 evidence-backed concept graph。

核心对象：

```text
Chunk
Mention
Concept
RelationEvidence
OntologyClass
RelationType
```

---

## 3. 核心对象定义

### 3.1 Chunk

`Chunk` 是 child chunk 的原文证据锚点。

Neo4j 中的 Chunk 应以 raw / evidence chunk 为准，context indexing text 只是辅助属性。

```yaml
Chunk:
  chunk_id: string
  resource_id: string
  document_version: string
  raw_text: string
  evidence_text: string
  context_indexing_text: string
  section_path: string
  parent_summary: string
  offset: object
```

职责：

```text
保留原文证据
支持 evidence 回源
连接 Mention 和 RelationEvidence
作为 graph evidence 的引用锚点
```

结论：

```text
Neo4j 存 raw/evidence chunk 作为证据。
context indexing text 用于抽取、embedding、消歧，不替代原文证据。
```

### 3.2 Mention

`Mention` 是某个 Chunk 中出现的一次实体提及。

例子：

```text
Chunk:
  苹果发布新款 iPhone 后，市场担心供应链压力影响后续出货。

Mention:
  surface = 苹果
  local_context = 苹果发布新款 iPhone 后，市场担心供应链压力影响后续出货。
```

职责：

```text
记录原文中的一次实体出现
保留局部上下文
连接 Chunk 与 Concept
用于实体消歧和 mention-to-concept 归并
```

### 3.3 Concept

`Concept` 是多个 Mention 归并后的概念桶。

例子：

```text
Mention: 苹果 + iPhone + 供应链
Mention: Apple + Mac + 发布会
Mention: 苹果公司 + 股价
  -> Concept: 苹果公司
```

职责：

```text
代表全局概念
聚合多个 Mention
参与 Concept-Concept 关系图
参与 ontology class 对齐
参与多跳路径解释
```

### 3.4 RelationEvidence

`RelationEvidence` 是从 Chunk 中抽出的关系证据。

例子：

```text
原文：
KKT 条件可以看作拉格朗日乘数法在不等式约束下的推广。

RelationEvidence:
  left = KKT 条件
  right = 拉格朗日乘数法
  relation_text = 在不等式约束下的推广
  evidence_text = KKT 条件可以看作拉格朗日乘数法在不等式约束下的推广。
```

职责：

```text
证明两个 Concept 为什么有关
保留关系原文
支持 relation type 归纳
支持 graph path explanation
```

### 3.5 OntologyClass

`OntologyClass` 是概念类型。

例子：

```text
OptimizationMethod
OptimizationCondition
MathematicalTheory
Algorithm
Formula
ProblemType
```

职责：

```text
给 Concept 提供类型归属
支持 Concept -> OntologyClass 对齐
让 typeless concept graph 向 ontology graph 演进
```

### 3.6 RelationType

`RelationType` 是关系类型。

例子：

```text
GENERALIZES
SPECIAL_CASE_OF
PREREQUISITE_OF
APPLIES_TO
CONTRASTS_WITH
PART_OF
CAUSES
```

职责：

```text
给 RelationEvidence 提供类型候选
支持自然语言弱关系向 typed relation 演进
```

---

## 4. 图结构

推荐核心结构：

```text
(:Chunk)
  -[:HAS_MENTION]->
(:Mention)
  -[:REFERS_TO]->
(:Concept)

(:RelationEvidence)
  -[:IN_CHUNK]->(:Chunk)
  -[:LEFT]->(:Concept)
  -[:RIGHT]->(:Concept)

(:Concept)
  -[:RELATED_TO]->
(:Concept)

(:Concept)
  -[:CANDIDATE_CLASS]->
(:OntologyClass)

(:Concept)
  -[:INSTANCE_OF]->
(:OntologyClass)

(:RelationEvidence)
  -[:CANDIDATE_TYPE]->
(:RelationType)
```

语义层次：

```text
Chunk:
  原文证据。

Mention:
  原文里的一次实体提及。

Concept:
  Mention 归并后的概念桶。

RelationEvidence:
  原文支持的关系证据。

OntologyClass / RelationType:
  类型系统。
```

---

## 5. Neo4j Vector 作用在哪里

Neo4j vector 不主要用于找文本。文本主召回由 Qdrant 完成。

Neo4j vector 主要作用在图语义对象上：

```text
Mention
Concept
RelationEvidence
OntologyClass
RelationType
```

### 5.1 Mention Vector

输入：

```text
surface
local_context
section_path
parent_summary
```

功能：

```text
实体消歧
mention -> concept 归并
同义提及发现
```

例子：

```text
苹果 + iPhone + 供应链
  -> 更接近 Concept: 苹果公司

苹果 + 膳食纤维 + 水果
  -> 更接近 Concept: 苹果水果
```

### 5.2 Concept Vector

输入：

```text
display_name
summary
representative_mentions
典型 local_context
主要邻居
```

功能：

```text
相似概念发现
概念合并候选
概念扩展候选
ontology class 对齐
多跳路径排序
```

例子：

```text
Concept: 拉格朗日乘数法
  -> 约束优化
  -> KKT 条件
  -> 约束极值
```

### 5.3 RelationEvidence Vector

输入：

```text
left concept
right concept
relation_text
evidence_text
```

功能：

```text
关系聚类
关系类型归纳
weak relation -> typed relation
多跳路径语义排序
```

例子：

```text
“A 是 B 的推广”
“A 是 B 的一般形式”
“A 在 B 基础上扩展”
  -> RelationType: GENERALIZES
```

### 5.4 OntologyClass Vector

输入：

```text
class name
description
examples
scope note
```

功能：

```text
Concept -> OntologyClass 对齐
```

例子：

```text
KKT 条件 -> OptimizationCondition
拉格朗日乘数法 -> OptimizationMethod
```

### 5.5 RelationType Vector

输入：

```text
type name
description
positive examples
negative examples
```

功能：

```text
RelationEvidence -> RelationType 对齐
```

例子：

```text
“KKT 条件是拉格朗日乘数法在不等式约束下的推广”
  -> GENERALIZES / EXTENDS
```

### 5.6 Chunk Vector

Chunk vector 不是核心。

如果 Neo4j 中保存 Chunk embedding，它只用于：

```text
图内 evidence rerank
图路径返回多个 chunks 时做局部排序
debug / 分析
```

它不承担主文本召回。

最终分工：

```text
Qdrant vector:
  找文本。

Neo4j vector:
  整理图。
```

---

## 6. 抽取服务与轮子

图抽取服务主选：

```text
Neo4j GraphRAG Python Knowledge Graph Builder
```

它负责：

```text
从 chunk 中抽取实体
从 chunk 中抽取关系
构建 chunk/entity/relation 图结构
写入 Neo4j
执行初步 entity resolution / concept bucket
```

底层 LLM 执行器优先：

```text
OpenAI / Azure OpenAI
```

WisePen 侧保留统一服务边界：

```text
GraphExtractionService
```

职责：

```text
组织 raw chunk + context indexing text 输入
调用 Neo4j GraphRAG KG Builder
保留 chunk_id / resource_id / document_version 锚点
校验抽取结果
写入 Neo4j
记录 extraction trace
```

---

## 7. Concept 桶与关系归属

Concept 桶由 entity resolution 过程决定。

```text
MentionCandidate
  -> Mention embedding
  -> 相似 Mention / Concept 候选
  -> entity resolution
  -> existing Concept / new Concept / ambiguous
```

关系由 relation extraction 和 relation resolution 共同决定。

```text
RelationEvidenceCandidate
  -> left / right surface
  -> 解析为 Concept
  -> RelationEvidence
  -> Concept-Concept RELATED_TO
```

关系类型由 RelationEvidence 和 RelationType 对齐决定。

```text
RelationEvidence embedding
  -> RelationType embedding candidates
  -> CANDIDATE_TYPE / typed relation
```

Concept 类型由 Concept 和 OntologyClass 对齐决定。

```text
Concept embedding
  -> OntologyClass embedding candidates
  -> CANDIDATE_CLASS / INSTANCE_OF
```

---

## 8. Neo4j 增强触发

Neo4j 增强主要由 Answerability Soft Gate 触发。

```text
Soft Gate 无 warning:
  可以直接进入 Context Builder。

Soft Gate 有 warning:
  触发 Neo4j Enhancement。
```

Soft Gate 触发意味着 direct evidence 不完美，因此系统需要尝试图增强。

典型触发 warning：

```text
LOW_DIRECTNESS
PARTIAL_COVERAGE
ENTITY_AMBIGUOUS
CONTEXT_MISMATCH
EVIDENCE_CONFLICT
```

Neo4j 对应处理：

```text
LOW_DIRECTNESS:
  证据需两步以上推理，或只给背景、缺少答案所需具体值时，尝试从 seed concept 找更直接的 relation evidence。

PARTIAL_COVERAGE:
  问题有多个明确子项且证据缺失任一子项时，沿相关概念补充 graph evidence。

ENTITY_AMBIGUOUS:
  同一字符串在证据内或证据间指代不同实体时，用 Mention / Concept 图辅助消歧。

CONTEXT_MISMATCH:
  时间、地域、假设前提或数据口径与问题限定条件冲突时，检查 seed concept 与目标 concept 是否路径一致。

EVIDENCE_CONFLICT:
  查找更多 relation evidence / concept path 辅助解释冲突。
```

---

## 9. Neo4j 输出

Neo4j Enhancement 输出不混入主 topK。

输出分为：

```text
graph_evidence:
  由图路径找到的补充证据。

ontology_hints:
  概念类型、关系类型、实体关联、可探索路径等结构提示。

concept_paths:
  多跳概念路径。
```

进入 Context Builder 时保持独立字段：

```yaml
graph_evidence:
  - evidence_text: string
    chunk_id: string
    path: list
    related_concepts: list
    score: float

ontology_hints:
  - concept: string
    class_candidates: list
    relation_type_candidates: list
    path_preview: list

concept_paths:
  - source_concept: string
    target_concept: string
    path: list
    support: list
```

设计原则：

```text
direct_evidence 是主证据。
graph_evidence 是补充证据。
ontology_hints 是非证据结构提示。
```
