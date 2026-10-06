"""Traversal acotado de la Memoria Grafo sobre el subgrafo visible del usuario."""
from app import repo_graph
from app.errors import not_found

MAX_DEPTH = 2    # G7
MAX_NODES = 50   # G7: máximo de vecinos devueltos


def neighbors(conn, user_id: str, node_id: str, depth: int = 1,
              relations: list[str] | None = None) -> dict:
    """Vecinos de un nodo hasta `depth` saltos, con camino y procedencia (G5).

    Recorrido en anchura. Las relaciones se guardan con dirección, pero se
    recorren en ambos sentidos; el camino conserva la dirección original.
    """
    start = repo_graph.visible_nodes(conn, user_id, [node_id])
    if not start:
        raise not_found()  # S5: mismo 404 para inexistente y no visible

    paths: dict[str, list[dict]] = {node_id: []}  # nodo -> relaciones del camino más corto
    frontier = [node_id]
    for _ in range(min(depth, MAX_DEPTH)):
        if not frontier or len(paths) > MAX_NODES:
            break
        current = set(frontier)
        frontier = []
        for edge in repo_graph.visible_edges(conn, user_id, sorted(current), relations):
            for src, dst in ((edge["from_id"], edge["to_id"]), (edge["to_id"], edge["from_id"])):
                # "dst not in paths" es el conjunto de visitados: tolera ciclos (G7).
                if src in current and dst not in paths:
                    paths[dst] = paths[src] + [edge]
                    frontier.append(dst)

    found = [n for n in paths if n != node_id][:MAX_NODES]
    nodes = {n["id"]: n for n in repo_graph.visible_nodes(conn, user_id, found)}
    return {
        "node": start[0],
        "neighbors": [
            {
                "node": nodes[n],
                "path": [_step(e) for e in paths[n]],
                "provenance": [
                    {"document_id": e["source_document_id"], "chunk_id": e["source_chunk_id"]}
                    for e in paths[n]
                ],
            }
            for n in found if n in nodes
        ],
    }


def _step(edge: dict) -> dict:
    step = {"from": edge["from_id"], "relation": edge["relation"], "to": edge["to_id"]}
    if edge["kind"]:
        step["kind"] = edge["kind"]
    return step
