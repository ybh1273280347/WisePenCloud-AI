"""GraphRAG 原始候选图的派生产物序列化。

候选图（``Neo4jGraph``）是 GraphRAG SDK 的原始输出，包含节点和关系。
本模块负责：

1. ``encode_candidate_graph``：把节点 ID 从 ``"window_id:..."`` 前缀转换为
   ``"stored:..."`` 前缀后序列化为 JSON 字符串，作为派生产物持久化。
   转换前缀是为了让序列化结果不依赖具体窗口 ID，便于跨 revision 复用判断。
2. ``decode_candidate_graph``：反向把 ``"stored:..."`` 还原为 ``"window_id:..."``，
   恢复节点 ID 的窗口归属，便于 ``KnowledgeCandidateValidator`` 校验。
3. ``slice_candidate_graph``：从一次批量抽取的合并图中按窗口 ID 切出对应子图。

注意：节点 ID 的前缀变换是 strict 的（不匹配会抛错），用以保证派生产物的完整性。
"""

from neo4j_graphrag.experimental.components.types import Neo4jGraph

# 持久化时使用的统一前缀，替代具体的 window_id，使存储格式不依赖窗口身份。
_STORED_NODE_PREFIX = "stored:"


def encode_candidate_graph(graph: Neo4jGraph, window_id: str) -> str:
    """把候选图的节点/关系 ID 前缀从 ``window_id:`` 转换为 ``stored:``，序列化为 JSON。

    转换前缀后，存储的图不再绑定具体窗口身份，仅记录拓扑结构；
    后续读取时再按当前 window_id 还原前缀，便于校验。
    """
    prefix = f"{window_id}:"
    normalized = Neo4jGraph(
        nodes=[
            node.model_copy(
                update={"id": _replace_prefix(node.id, prefix, _STORED_NODE_PREFIX)}
            )
            for node in graph.nodes
        ],
        relationships=[
            relation.model_copy(
                update={
                    "start_node_id": _replace_prefix(
                        relation.start_node_id,
                        prefix,
                        _STORED_NODE_PREFIX,
                    ),
                    "end_node_id": _replace_prefix(
                        relation.end_node_id,
                        prefix,
                        _STORED_NODE_PREFIX,
                    ),
                }
            )
            for relation in graph.relationships
        ],
    )
    return normalized.model_dump_json()


def decode_candidate_graph(payload: str, window_id: str) -> Neo4jGraph | None:
    """把 ``stored:`` 前缀还原为 ``window_id:`` 前缀，恢复节点 ID 的窗口归属。

    返回 ``None`` 表示 payload 不是合法的候选图 JSON（比如旧版本格式），
    调用方应据此重新触发抽取。
    """
    try:
        graph = Neo4jGraph.model_validate_json(payload)
        prefix = f"{window_id}:"
        return Neo4jGraph(
            nodes=[
                node.model_copy(
                    update={
                        "id": _replace_prefix(
                            node.id,
                            _STORED_NODE_PREFIX,
                            prefix,
                        )
                    }
                )
                for node in graph.nodes
            ],
            relationships=[
                relation.model_copy(
                    update={
                        "start_node_id": _replace_prefix(
                            relation.start_node_id,
                            _STORED_NODE_PREFIX,
                            prefix,
                        ),
                        "end_node_id": _replace_prefix(
                            relation.end_node_id,
                            _STORED_NODE_PREFIX,
                            prefix,
                        ),
                    }
                )
                for relation in graph.relationships
            ],
        )
    except ValueError:
        return None


def slice_candidate_graph(graph: Neo4jGraph, window_id: str) -> Neo4jGraph:
    """从一次批量抽取的合并图中按 window_id 切出该窗口对应的子图。

    GraphRAG SDK 一次会处理多个窗口，输出合并图；本函数按 ``window_id:`` 前缀
    过滤节点，并保留两端节点都属于本窗口的关系，丢弃跨窗口关系（不合法）。
    """
    prefix = f"{window_id}:"
    nodes = [node for node in graph.nodes if node.id.startswith(prefix)]
    node_ids = {node.id for node in nodes}
    return Neo4jGraph(
        nodes=nodes,
        relationships=[
            relation
            for relation in graph.relationships
            if relation.start_node_id in node_ids
            and relation.end_node_id in node_ids
        ],
    )


def _replace_prefix(value: str, old: str, new: str) -> str:
    """把字符串前缀 ``old`` 替换为 ``new``；不匹配则抛错。

    严格匹配保证派生产物的完整性——若节点 ID 不符合预期前缀，说明数据被污染，
    应当立即报错而非静默保留错误数据。
    """
    if not value.startswith(old):
        raise ValueError("graph node id does not match extraction window")
    return f"{new}{value[len(old):]}"
