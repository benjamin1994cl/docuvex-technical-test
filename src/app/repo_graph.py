"""Consultas SQL de la Memoria Grafo.

Todas parten del subgrafo visible del usuario (CTE _VISIBLE). El traversal solo
recibe relaciones visibles, así que un nodo o relación oculta no puede servir de
puente (G4): para el recorrido, sencillamente no existe.
"""

MAX_EDGES_PER_LEVEL = 500  # G7: tope de relaciones leídas por nivel del recorrido

# Las relaciones extraídas automáticamente con confianza menor quedan guardadas,
# pero no se muestran hasta ser revisadas (evita relaciones falsas en las respuestas).
MIN_CONFIDENCE = 0.8


def _params(user_id: str, **extra) -> dict:
    return {"user_id": user_id, "min_confidence": MIN_CONFIDENCE, **extra}

_VISIBLE = """
WITH user_ous AS (
    SELECT ou_id FROM user_organization_units WHERE user_id = %(user_id)s
),
visible_docs AS (
    -- AUTORIZACIÓN: documentos de las OU del usuario.
    SELECT d.id FROM documents d WHERE d.ou_id IN (SELECT ou_id FROM user_ous)
),
visible_nodes AS (
    SELECT n.id
    FROM graph_nodes n
    WHERE
        -- G1: Document y Version, solo si su documento está autorizado.
        (n.type IN ('Document', 'Version') AND n.document_id IN (SELECT id FROM visible_docs))
        OR (n.type = 'OrganizationUnit' AND n.ou_id IN (SELECT ou_id FROM user_ous))
        -- G2: una entidad es visible solo si la referencia un documento autorizado.
        OR (n.type IN ('Company', 'Person') AND n.confirmed AND EXISTS (
                SELECT 1 FROM graph_edges r
                WHERE r.to_id = n.id AND r.relation = 'REFERENCES'
                  AND r.from_id IN (SELECT id FROM visible_docs)
                  AND r.source_document_id IN (SELECT id FROM visible_docs)
                  AND r.confidence >= %(min_confidence)s))
)
"""


def visible_nodes(conn, user_id: str, node_ids: list[str]) -> list[dict]:
    """Nodos visibles entre los pedidos, con sus atributos de origen autorizado (G2)."""
    params = _params(user_id, node_ids=node_ids)
    nodes = conn.execute(
        _VISIBLE + """
        SELECT n.id, n.type, n.label FROM graph_nodes n
        WHERE n.id = ANY(%(node_ids)s::text[]) AND n.id IN (SELECT id FROM visible_nodes)
        ORDER BY n.id""",
        params,
    ).fetchall()
    attributes = conn.execute(
        _VISIBLE + """
        SELECT a.node_id, a.key, a.value FROM entity_attributes a
        WHERE a.node_id = ANY(%(node_ids)s::text[])
          AND a.node_id IN (SELECT id FROM visible_nodes)
          AND a.source_document_id IN (SELECT id FROM visible_docs)
        ORDER BY a.node_id, a.key""",
        params,
    ).fetchall()
    by_node = {n["id"]: n for n in nodes}
    for attr in attributes:
        by_node[attr["node_id"]].setdefault("attributes", []).append(
            {"key": attr["key"], "value": attr["value"]}
        )
    return nodes


def visible_edges(conn, user_id: str, frontier: list[str],
                  relations: list[str] | None = None) -> list[dict]:
    """Relaciones visibles que tocan a los nodos de la frontera (G3)."""
    return conn.execute(
        _VISIBLE + """
        SELECT e.id, e.from_id, e.to_id, e.relation, e.kind,
               e.source_document_id, e.source_chunk_id
        FROM graph_edges e
        WHERE (e.from_id = ANY(%(frontier)s::text[]) OR e.to_id = ANY(%(frontier)s::text[]))
          -- G3: procedencia autorizada y los dos extremos visibles.
          AND e.source_document_id IN (SELECT id FROM visible_docs)
          AND e.from_id IN (SELECT id FROM visible_nodes)
          AND e.to_id IN (SELECT id FROM visible_nodes)
          AND e.confidence >= %(min_confidence)s
          AND (%(relations)s::text[] IS NULL OR e.relation = ANY(%(relations)s::text[]))
        ORDER BY e.id
        LIMIT %(max_edges)s""",
        _params(user_id, frontier=frontier, relations=relations,
                max_edges=MAX_EDGES_PER_LEVEL),
    ).fetchall()


def find_entities_by_name(conn, user_id: str, normalized: str) -> list[dict]:
    """Entidades visibles cuyo nombre o alias normalizado coincide exactamente.

    Los alias declarados no tienen procedencia en el dataset y el caso A18 exige
    resolverlos para quien ya ve la entidad. La entidad en sí debe ser visible (G2).
    """
    return conn.execute(
        _VISIBLE + """
        SELECT DISTINCT n.id, n.type, n.label
        FROM graph_nodes n JOIN entity_aliases a ON a.node_id = n.id
        WHERE a.normalized = %(normalized)s AND n.id IN (SELECT id FROM visible_nodes)
        ORDER BY n.id""",
        _params(user_id, normalized=normalized),
    ).fetchall()


def visible_entity_names(conn, user_id: str) -> list[dict]:
    """Nombres y alias normalizados de las entidades visibles (para detectar menciones)."""
    return conn.execute(
        _VISIBLE + """
        SELECT a.node_id, a.normalized
        FROM entity_aliases a
        WHERE a.node_id IN (SELECT id FROM visible_nodes)
        ORDER BY length(a.normalized) DESC, a.node_id""",
        _params(user_id),
    ).fetchall()
