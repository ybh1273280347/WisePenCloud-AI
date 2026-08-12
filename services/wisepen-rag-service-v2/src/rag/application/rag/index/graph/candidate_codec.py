"""GraphRAG 原始候选图的派生产物序列化。"""

from neo4j_graphrag.experimental.components.types import Neo4jGraph

_STORED_NODE_PREFIX = "stored:"


def encode_candidate_graph(graph: Neo4jGraph, window_id: str) -> str:
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
    if not value.startswith(old):
        raise ValueError("graph node id does not match extraction window")
    return f"{new}{value[len(old):]}"
