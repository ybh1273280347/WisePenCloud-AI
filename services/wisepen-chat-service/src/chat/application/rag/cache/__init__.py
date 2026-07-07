"""
三个缓存的定位：

- evidence_materialization — 检索管线 → 上下文构建阶段，缓存已 materialize 的直接证据，避免重复计算
- ingestion_deterministic — 文档入库阶段，缓存确定性步骤结果，实现幂等去重
- graph_enhancement — 检索管线 → 图谱增强阶段，缓存 Neo4j 增强结果    
"""
