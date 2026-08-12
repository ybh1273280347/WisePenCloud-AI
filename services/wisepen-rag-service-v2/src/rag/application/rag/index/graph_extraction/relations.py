"""知识关系 profile 和合法端点组合。"""

from rag.domain.models.graph import (
    KnowledgeNodeKind,
    KnowledgeRelationProfile,
    KnowledgeRelationType,
)

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
LEARNING_RELATIONS = {
    KnowledgeRelationType.DEFINES: "主体给出客体的正式定义",
    KnowledgeRelationType.EXPLAINS: "主体解释或推导客体",
    KnowledgeRelationType.EXAMPLE_OF: "主体是客体的实例",
    KnowledgeRelationType.REQUIRES: "理解或使用主体需要客体",
}
SCHOLARLY_RELATIONS = {
    KnowledgeRelationType.CITES: "主体明确引用客体来源",
    KnowledgeRelationType.PUBLISHED_IN: "主体发表于客体",
    KnowledgeRelationType.USES_DATASET: "主体使用客体数据集",
    KnowledgeRelationType.USES_METHOD: "主体使用客体方法",
    KnowledgeRelationType.SUPPLEMENTS: "主体补充客体文档",
    KnowledgeRelationType.RETRACTS: "主体撤销客体先前声明",
}

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
