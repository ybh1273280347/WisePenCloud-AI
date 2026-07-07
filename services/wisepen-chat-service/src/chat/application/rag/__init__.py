"""WisePen 私有知识库 RAG 应用层能力。

当前包含四个阶段：
- ingestion：Markdown 分块、Context Indexing
- retrieval：从索引召回候选，并在 pipeline 内完成 rerank / 多样性控制
- answerability：硬门控 + 软门控判断是否可答
- context_builder：构造带 citation 的 RAG 上下文
"""
