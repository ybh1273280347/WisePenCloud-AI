# RAG v2 回放、切流与回滚

## 1. 前置条件

- v2 使用独立 Mongo collections、Qdrant collection、Neo4j database/labels 和 Redis prefix；不得复用 v1 派生数据。
- CP29 源码门禁通过，部署配置与三类 Kafka topic 已由环境负责人确认。
- MCP/Agent 调用方已适配 `expand`、LOCATE nodes、READ 缺失 key 和空 Section，不依赖 v1 `reason`。
- 保留可以按能力立即切回 v1 的路由开关。

## 2. 回放

1. 冻结回放水位，记录 document、ACL、destroy 三个 topic 的 partition/offset。
2. 从权威内容源按资源生成 document-ready 事件，从权威 ACL 源生成 ACL-recalculate 事件，写入 v2 专属回放 topic。
3. 启动 v2 consumer；重复、乱序和同 revision 内容修正必须依靠既有幂等/CAS 规则收敛，不能手改 v2 数据。
4. 回放完成后核对资源数、applied revision 数、Qdrant active point 数、Neo4j published/skipped 资源数和本地 ACL 数。
5. 对删除资源回放 destroy 事件，确认 applied state 已先失效，Mongo/Qdrant/Neo4j/ACL 最终全部清理。
6. 接上冻结水位后的增量事件，Kafka lag 归零后进入 shadow。

## 3. Shadow 验收

1. 使用固定脱敏文档、固定身份/群组角色和固定 query，同时调用 v1/v2。
2. 将结果归一化为 [Shadow.md](./Shadow.md) 的 JSONL，运行比较脚本并保存输入、报告和审批文件。
3. 单独记录成功率、业务错误码、P50/P95/P99 延迟、ACL 拒绝率、无证据结果和 state 失效率。
4. 权限、revision、正文或 evidence 存在未批准差异时停止；不得通过扩大容差或删除字段绕过。

## 4. 分阶段切流

按调用依赖顺序分别切换，阶段之间保留观察窗口：

1. document structure 与无状态 page/section READ。
2. LOCATE 与 navigation state 下的 Section READ。
3. EXPAND 与 VERIFY 证据返回。

每阶段确认错误率、延迟、Kafka lag、索引失败、ACL 拒绝率和无证据结果稳定后再进入下一阶段。v1 consumer 在全部阶段和稳定期结束前持续运行。

## 5. 回滚

1. 将当前能力路由切回 v1；不要将 v2 Mongo/Qdrant/Neo4j/Redis 数据反写 v1。
2. 保持 v2 consumer 运行以便诊断；仅当 v2 写入本身扩大故障时暂停对应 v2 consumer，并记录最后成功 offset。
3. 保存触发请求、身份范围、v1/v2 归一化结果、相关事件 offset 和后端 revision 状态。
4. 修复后从已记录水位重放到 v2，重新执行该能力的 shadow 审批，再恢复切流。

稳定期结束且审计确认无未解释差异后，才能另行审批停止 v1 consumer 和清理 v1 派生数据；该动作不属于 CP29。
