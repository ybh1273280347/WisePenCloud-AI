"""知识关系 profile 和合法端点组合。

本模块定义知识图谱中允许的关系类型与端点组合规则：

1. **关系 profile**：把关系按语义分组（CORE / LEARNING / SCHOLARLY），允许按需启用
   不同子集。``relation_descriptions`` 把启用的 profile 合并为
   ``{关系类型: 描述文本}`` 字典，供 GraphRAG schema 使用。
2. **合法端点组合**：``relation_pattern_allowed`` 限制 (source_kind, relation, target_kind)
   三元组，避免模型输出语义错误的关系（如 ENTITY→RESOURCE 没有意义）。
"""

from rag.domain.models.graph import (
    KnowledgeNodeKind,
    KnowledgeRelationProfile,
    KnowledgeRelationType,
)

# CORE profile：覆盖文档中最常见的关系，适用于所有领域。
CORE_RELATIONS = {
    KnowledgeRelationType.ABOUT: "主体内容明确围绕客体",
    KnowledgeRelationType.RELATED_TO: "主体与客体存在正文明确描述的关系",
    KnowledgeRelationType.PART_OF: "主体是客体的组成部分",
    KnowledgeRelationType.USES: "主体明确使用客体",
    KnowledgeRelationType.PRODUCES: "主体明确产生客体",
    KnowledgeRelationType.DEPENDS_ON: "主体明确依赖客体",
    KnowledgeRelationType.DERIVED_FROM: "主体明确来源于客体",
    KnowledgeRelationType.IMPLEMENTS: "主体实现客体",
    KnowledgeRelationType.APPLIES_TO: "主体适用于客体",
    KnowledgeRelationType.CAUSES: "主体导致客体",
    KnowledgeRelationType.COMPARES_WITH: "正文明确比较主体和客体",
    KnowledgeRelationType.CONTRADICTS: "正文明确指出主体和客体冲突",
    KnowledgeRelationType.EXTENDS: "主体扩展客体",
    KnowledgeRelationType.SUPERSEDES: "主体替代客体",
    KnowledgeRelationType.LOCATED_IN: "主体位于客体地点",
    KnowledgeRelationType.AUTHORED_BY: "主体由客体人物或组织创作",
}
# LEARNING profile：教学/解释类关系，适合教材、教程、技术文档。
LEARNING_RELATIONS = {
    KnowledgeRelationType.DEFINES: "主体给出客体的正式定义",
    KnowledgeRelationType.EXPLAINS: "主体解释或推导客体",
    KnowledgeRelationType.EXAMPLE_OF: "主体是客体的实例",
    KnowledgeRelationType.REQUIRES: "理解或使用主体需要客体",
}
# SCHOLARLY profile：学术引用类关系，适合论文、研究报告。
SCHOLARLY_RELATIONS = {
    KnowledgeRelationType.CITES: "主体明确引用客体来源",
    KnowledgeRelationType.PUBLISHED_IN: "主体发表于客体",
    KnowledgeRelationType.USES_DATASET: "主体使用客体数据集",
    KnowledgeRelationType.USES_METHOD: "主体使用客体方法",
    KnowledgeRelationType.SUPPLEMENTS: "主体补充客体文档",
    KnowledgeRelationType.RETRACTS: "主体撤销客体先前声明",
}

# 允许 RESOURCE 作为 source 的关系集合：其它关系不允许从 RESOURCE 出发，
# 因为资源本身是图谱根节点，不能参与任意的语义关系。
_RESOURCE_RELATIONS = frozenset(
    {
        KnowledgeRelationType.ABOUT,
        KnowledgeRelationType.AUTHORED_BY,
        KnowledgeRelationType.DEFINES,
        KnowledgeRelationType.EXPLAINS,
        KnowledgeRelationType.EXAMPLE_OF,
    }
)


def relation_descriptions(
    profiles: frozenset[KnowledgeRelationProfile],
) -> dict[KnowledgeRelationType, str]:
    """按启用的 profile 合并关系描述字典。

    profile 启用顺序：CORE → LEARNING → SCHOLARLY；后启用的 profile 不会覆盖
    已存在的关系（同名关系以 CORE 的描述为准），保持描述稳定。
    """
    descriptions: dict[KnowledgeRelationType, str] = {}
    if KnowledgeRelationProfile.CORE in profiles:
        descriptions.update(CORE_RELATIONS)
    if KnowledgeRelationProfile.LEARNING in profiles:
        descriptions.update(LEARNING_RELATIONS)
    if KnowledgeRelationProfile.SCHOLARLY in profiles:
        descriptions.update(SCHOLARLY_RELATIONS)
    return descriptions


def relation_pattern_allowed(
    source: KnowledgeNodeKind,
    relation: KnowledgeRelationType,
    target: KnowledgeNodeKind,
) -> bool:
    """判断 (source, relation, target) 端点组合是否合法。

    合法组合规则：
    1. ENTITY → ENTITY：允许所有关系（实体间是图谱的主体）。
    2. RESOURCE → ENTITY：仅允许 ``_RESOURCE_RELATIONS`` 中的关系
       （资源到实体的关系受限，避免资源节点被滥用）。
    3. * → EXTERNAL_SOURCE：仅允许 CITES / DERIVED_FROM
       （外部源只能作为引用或来源，不能参与其它语义关系）。
    4. 其它组合（如 ENTITY → RESOURCE）一律不允许。
    """
    if source is KnowledgeNodeKind.ENTITY and target is KnowledgeNodeKind.ENTITY:
        return True
    if source is KnowledgeNodeKind.RESOURCE and target is KnowledgeNodeKind.ENTITY:
        return relation in _RESOURCE_RELATIONS
    if target is KnowledgeNodeKind.EXTERNAL_SOURCE:
        return source in (KnowledgeNodeKind.RESOURCE, KnowledgeNodeKind.ENTITY) and (
            relation
            in (KnowledgeRelationType.CITES, KnowledgeRelationType.DERIVED_FROM)
        )
    return False
