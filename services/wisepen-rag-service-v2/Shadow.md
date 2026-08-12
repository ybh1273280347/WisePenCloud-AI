# RAG v2 Shadow 对照与差异审批

## 1. 比较边界

v1/v2 内部对象和 HTTP 包装不同，shadow 不比较类名、tuple/list 或存储字段。采集端必须将结果归一化为 JSONL，每行包含：

- `case_id`：同一请求在 v1/v2 中共用的稳定 ID。
- `capability`：`document`、`read.page`、`read.section`、`locate`、`expand` 或 `verify`。
- `facts`：结构、正文 offset、decision、Section/node/edge/SourceRef 身份、权限结果和错误码等稳定事实。
- `latency_ms`：可选，只做独立统计，不参与语义相等判断。

排序确有语义时由采集端按公开顺序输出；集合语义由采集端先按稳定 ID 排序。禁止删除权限、revision、正文、evidence 或错误码差异来获得“通过”。

## 2. 执行

```powershell
uv run --project services/wisepen-rag-service-v2 python services/wisepen-rag-service-v2/scripts/compare_shadow_results.py `
  artifacts/rag-shadow/v1.jsonl `
  artifacts/rag-shadow/v2.jsonl `
  --approvals artifacts/rag-shadow/approvals.json `
  --output artifacts/rag-shadow/report.json
```

无差异或所有差异已批准时退出码为 0；存在未批准差异时退出码为 1。审批文件是 JSON 数组，每项必须包含 `case_id`、JSON `path`、`reason` 和 `approved_by`，可额外记录 `approved_at` 与关联提交。

## 3. 已确认的契约变化

以下变化来自 Architecture/Repo 已确认边界，采集端应比较等价领域事实，不要求旧包装继续存在：

| 能力 | v1 | v2 | 理由 |
| --- | --- | --- | --- |
| structure/READ | snapshot service 同时组装结构、正文和 `kind/reason/windows` | structure 与 page/section READ 分离，只返回存在事实 | RAG 不再替 Agent 装配探索语义 |
| page/section 缺失 | item 内 reason | 批量结果缺少对应 key | 缺失由调用方集合差异识别，真实失败抛异常 |
| navigation graph | `cypher` | `expand` | 这是受 state 约束的图扩展，不是开放 Cypher 能力 |
| locate 状态 | `retrieval_status` | ranking `decision` | 去掉只为 Agent 决策创建的 application status model |
| 图结果 | v1 聚合 source view | v2 node/edge/path 与已核验 SourceRef facts | 正文始终由 VERIFY 从 Mongo applied revision 回源 |

## 4. 仍需环境审批

源码集成门不宣称完成真实 shadow。切流前必须由同一批脱敏文档和固定 query 生成 v1/v2 文件，并审批：

- Section 树、页/Section offset、ReadingBlock 和精确 evidence 差异。
- top-k、相关性档位、图节点/关系覆盖差异及其评测依据。
- ACL 允许/拒绝、错误码、revision 并发和删除后结果。
- 错误率与延迟是否满足部署阈值。
- MCP/Agent 已接管缺失页、缺失 Section、空 Section的探索语义。

任何未解释的权限、revision、正文或证据差异都阻止切流。
