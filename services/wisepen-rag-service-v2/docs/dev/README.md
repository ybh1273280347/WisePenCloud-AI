# RAG v2 开发文档

本目录收纳实现者、reviewer 和运维人员需要的内部资料。面向 API 调用方的稳定契约请阅读 [../API.md](../API.md)，不要从迁移 checklist 或历史 checkpoint 推断当前接口。

## 当前参考

| 文档 | 用途 |
| --- | --- |
| [Architecture.md](Architecture.md) | application 能力、依赖方向和一致性边界 |
| [Repo.md](Repo.md) | Mongo、Qdrant、Neo4j、Redis 的职责和 port 设计 |
| [RAG_V2_REVIEW.md](RAG_V2_REVIEW.md) | 按 locate/read/verify/expand/index 审查当前实现 |
| [Runbook.md](Runbook.md) | 回放、切流、回滚和故障处理步骤 |
| [Shadow.md](Shadow.md) | v1/v2 shadow 输入和差异审批规则 |

## 历史记录

| 文档 | 用途 |
| --- | --- |
| [Migration.md](Migration.md) | v2 从基线到各 checkpoint 的迁移顺序 |
| [TODO.md](TODO.md) | 迁移期完整能力清单与验收记录 |
| [RAG_V2_HANDOFF.md](RAG_V2_HANDOFF.md) | 迁移 checkpoint 结果和阶段性交接记录 |

历史记录保留当时的目录名、checkpoint 和分支约束，用于解释设计来源，不作为当前公开 API 或包路径的权威说明。
