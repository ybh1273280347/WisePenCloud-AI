# RAG 资源权限模型（第一版）

本文定义 WisePen 私有知识库 RAG 第一版权限模型。结论先行：

- Java `wisepen-resource-service` 是资源权限事实源。
- Chat Service RAG 必须保存预计算权限投影，作为检索强制准入条件。
- 第一版不做段落级、父块级、子块级特殊权限。
- RAG 检索权限直接使用资源 `VIEW` 权限，暂不新增独立 `QUERY` 动作。
- 所有 parent chunk / child chunk 都继承所属 `resource_id` 的权限。
- Qdrant payload filter 必须基于预计算 ACL projection；`ResourceClient.check_res_permission()` 是 prompt 前防陈旧兜底硬鉴权。

## 1. 权限边界

RAG 中的长期对象分为三层：

```text
resource_id
  -> document_id / document_version_id
    -> parent_chunk_id
      -> child_chunk_id
```

第一版只有 `resource_id` 拥有真实权限。`document`、`parent_chunk`、`child_chunk` 都只是资源的派生对象，不单独配置 ACL。

这意味着：

- 用户能 `VIEW resource`，就可以让该资源下的 chunks 参与 RAG。
- 用户不能 `VIEW resource`，该资源下任何 chunk 都不能进入检索结果和 prompt。
- chunk 不允许比父资源权限更宽。
- chunk 也暂不允许比父资源权限更窄。

## 2. VIEW 等价于 RAG 查询权限

第一版不新增 `QUERY`。RAG 检索准入统一使用 `VIEW`。

```text
can_query_resource = has_action(resource, VIEW)
```

这样做的好处：

- 直接复用现有 Java 资源权限系统。
- 不需要修改资源服务动作枚举。
- 权限语义简单：能看原文，就能用于问答；不能看原文，就不能被模型检索到。

后续如果产品需要“能问但不能打开原文”，再单独引入 `QUERY`。

## 3. 动作掩码

当前资源服务已有动作掩码：

```text
DISCOVER              列表可见
VIEW                  在线阅读
EDIT                  协同编辑
DOWNLOAD_WATERMARK    下载带水印
DOWNLOAD_ORIGINAL     下载源文件
```

RAG 第一版只关心：

```text
VIEW
```

检索过滤、prompt 注入、引用生成都以 `VIEW` 为准。

如果用户只有 `DISCOVER`，他可以在某些列表中知道资源存在，但不能让资源内容进入 RAG。

## 4. ACL 授予模式

资源服务侧仍然沿用现有 ACL 授予模式：

```text
ALL         所有小组成员获得标签授予权限
ONLY_ADMIN  只有小组 OWNER / ADMIN 获得权限
WHITELIST   只有白名单用户获得权限
BLACKLIST   黑名单用户不获得权限，其他成员获得权限
```

RAG 不重新解释这些模式。RAG 只消费资源服务已经算好的结果，或者消费投影后的 `acl_projection`。

## 5. 标签层级权限继承

标签/目录权限继承仍然由资源服务负责。

规则是：

```text
当前标签配置
> 最近父级标签配置
> 祖先标签配置
> 小组默认成员掩码
```

RAG 入库和检索阶段不重新向上遍历标签树。原因是：

- 标签继承规则已经在资源服务中实现。
- RAG 重算一套会造成权限解释分叉。
- 检索系统只需要快速判断 chunk 是否可进入候选集。

## 6. 资源级覆盖与用户特权

资源服务侧已有：

```text
overrideGrantedActionsMask
specifiedUsersGrantedActionsMask
```

第一版 RAG 的规则：

- 资源级覆盖影响 RAG，因为它可能移除或授予 `VIEW`。
- 指定用户特权影响 RAG，因为它可能单独授予某个用户 `VIEW`。
- RAG 不自行维护覆盖规则，只保存资源服务输出的权限投影。

优先级仍然是：

```text
资源 owner
> 小组 OWNER / ADMIN
> 指定用户特权
> 资源级覆盖
> 标签继承权限
> 小组默认成员掩码
> 拒绝
```

## 7. 小组默认成员掩码

小组默认成员掩码仍由资源服务管理。

RAG 只关心最终结果是否包含 `VIEW`：

```text
defaultMemberActionsMask 包含 VIEW
  -> 普通成员可检索该小组默认可读资源

defaultMemberActionsMask 不包含 VIEW
  -> 普通成员不能检索该资源内容
```

## 8. 预计算 ACL

RAG 必须保存一份权限投影。向量检索不能先无权限召回再逐条调用资源服务过滤；检索必须先基于预计算 ACL projection 裁剪候选集合。

建议投影结构：

```text
acl_projection:
  acl_version: 12
  owner_id: "10001"
  spaces:
    "20001":
      base_mask: 3
      user_masks:
        "10002": 3
        "10003": 0
  specified_users:
    "10004": 3
  projection_status: active
```

其中 `base_mask` 和 `user_masks` 使用资源动作掩码。第一版检索只判断是否包含 `VIEW`。

`projection_status=active` 是进入检索索引的前置条件。缺失、过期或刷新失败的 projection 默认不可检索。

投影落点：

```text
kb_documents
kb_document_versions
kb_parent_chunks
kb_child_chunks
Qdrant child chunk payload
```

其中 Qdrant 只需要保存用于过滤的最小字段：

```text
resource_id
owner_id
acl_version
acl_projection
deleted_at
document_version_id
parent_chunk_id
child_chunk_id
projection_status
```

Qdrant point 必须携带 active ACL projection。没有 active projection 的 point 应删除、tombstone 或通过 payload 标记为不可检索。

## 9. 父子块权限处理

当前 `chunking_engine` 的 `nested_markdown` 已经产出：

```text
parent chunk: ChunkLevel.RETRIEVAL
child chunk:  ChunkLevel.SEARCH
```

第一版权限规则：

```text
parent chunk ACL = resource ACL
child chunk ACL = resource ACL
```

不做：

- 段落级敏感权限。
- 子块独立黑名单。
- 父块和子块权限不一致。
- chunk 层白名单/黑名单。

检索流程：

```text
1. Qdrant 检索 child chunk。
2. 用 child payload 中的 acl_projection 过滤 VIEW。
3. 命中 child 后，根据 parent_chunk_id 找 parent chunk。
4. parent chunk 注入 prompt 前，对 resource_id 做硬鉴权。
5. 硬鉴权通过后，parent context 才能进入 prompt。
```

由于 chunk 不做特殊权限，所以多个 child 命中同一个 parent 时，可以安全合并为 parent context。

## 10. 权限校验流程

### 10.1 检索前过滤

RAG 查询时先从安全上下文获取：

```text
user_id
group_role_map
```

然后构造 Qdrant filter。这个 filter 是强制准入，不是可选优化：

```text
deleted_at is null
AND projection_status == active
AND VIEW is allowed by acl_projection
```

逻辑上等价于：

```text
owner_id == current_user
OR specified_users[current_user] contains VIEW
OR user is group OWNER / ADMIN
OR spaces[group_id].user_masks[current_user] contains VIEW
OR spaces[group_id].base_mask contains VIEW
```

如果用户在多个小组中，需要展开多个 `group_id` 条件。

### 10.2 Prompt 前硬鉴权

Qdrant filter 是检索强制准入，但不是最终安全边界。

每个准备进入 prompt 的 `resource_id` 必须调用：

```text
ResourceClient.check_res_permission(resource_id, user_id, group_role_map)
```

只有返回结果包含 `VIEW` 时，该资源对应的 parent/chunk context 才能进入 prompt。

## 11. 访问角色

RAG 可以记录资源服务返回的访问角色：

```text
OWNER
OWNER_SPECIFIED
GROUP_ADMIN
GROUP_MEMBER
NONE
```

访问角色用于解释和审计，不替代动作权限判断。

示例：

```text
resourceAccessRole = GROUP_MEMBER
allowedActions 包含 VIEW
```

表示用户作为普通小组成员获得了 RAG 检索资格。

## 12. 权限变更同步

权限变化后必须刷新 RAG 权限投影。

触发来源：

```text
资源绑定标签变化
标签权限变化
小组默认成员掩码变化
资源级覆盖变化
指定用户特权变化
用户小组角色变化
资源删除或恢复
```

处理流程：

```text
1. 收到 resource_id 的 ACL 变更事件。
2. 查询该 resource_id 关联的 KB documents。
3. 更新 Mongo 中 document / parent chunk / child chunk 的 acl_version。
4. 批量更新 Qdrant child point payload 的 acl_projection。
5. projection_status=active 后，新查询才允许召回。
6. 旧召回结果在 prompt 前仍由硬鉴权兜底。
```

## 13. 当前仓库落点

建议后续新增：

```text
src/chat/application/rag/permission/
  acl_projection.py
  permission_checker.py
  qdrant_acl_filter.py
```

职责划分：

- `acl_projection.py`：定义 RAG 侧权限投影 DTO。
- `permission_checker.py`：封装 `ResourceClient.check_res_permission()`，统一判断 `VIEW`。
- `qdrant_acl_filter.py`：根据 `SecurityContextHolder` 的用户和小组角色生成 Qdrant filter。

边界规则：

- `chunking_engine` 不处理权限。
- `ranking_engine` 不处理权限。
- Qdrant filter 是检索强制准入，硬鉴权是 prompt 前兜底；两者都不能省。
- Java resource-service 是最终权限事实源。

## 14. 第一版定稿

第一版采用以下定稿规则：

```text
VIEW = RAG QUERY
chunk 无特殊权限
parent chunk 继承 resource 权限
child chunk 继承 resource 权限
Qdrant 保存 active ACL 投影并强制过滤
prompt 前调用 resource-service 硬鉴权
```

这能让 RAG 权限模型足够简单，同时不绕过现有资源权限系统。
