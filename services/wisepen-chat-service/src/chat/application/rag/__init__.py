"""WisePen 私有知识库 RAG 应用层能力。

当前包含四个阶段：
- ingestion：Markdown 分块、Context Indexing
- retrieval：从索引召回 ScoredChunk
- ranking：对候选做 rerank / 多样性控制
- answerability：硬门控 + 软门控判断是否可答

context_builder 阶段待后续补齐。
"""

