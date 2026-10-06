"""Uso del grafo en /ask (GraphRAG, sección 9.6).

El grafo explica por qué se trae un documento; la evidencia siguen siendo chunks.
"""
from app import graph, repo_graph, repo_search
from app.text import normalize_name, unaccent

# Solo relaciones con significado. Las estructurales se excluyen: un nodo de OU
# conecta todos los documentos de la unidad y todo quedaría "relacionado".
SEMANTIC_RELATIONS = ["REFERENCES", "RELATED_TO", "REPRESENTS"]

_RELATIONAL_HINTS = ("relacion", "vincul", "asoci", "conect")


def is_relational(question: str) -> bool:
    """La pregunta pide relaciones entre documentos (y no un dato puntual)."""
    flat = unaccent(question).lower()
    return any(hint in flat for hint in _RELATIONAL_HINTS)


def mentioned_entities(conn, user_id: str, question: str) -> list[str]:
    """Entidades visibles cuyo nombre o alias aparece en la pregunta."""
    padded = f" {normalize_name(question)} "
    found = []
    for row in repo_graph.visible_entity_names(conn, user_id):
        if f" {row['normalized']} " in padded and row["node_id"] not in found:
            found.append(row["node_id"])
    return found


def _anchor(conn, user_id, question, hits, min_score) -> str | None:
    """Nodo desde el que parte el recorrido: el documento mejor puntuado, siempre
    que la búsqueda sea confiable o la pregunta nombre una entidad visible."""
    entities = mentioned_entities(conn, user_id, question)
    if hits and (hits[0]["score"] >= min_score or entities):
        return hits[0]["document_id"]
    return entities[0] if entities else None


def answer(conn, user_id: str, question: str, hits: list[dict], min_score: float) -> dict | None:
    """Respuesta basada en el grafo, o None si no hay ancla o documentos relacionados."""
    from app.ask import conflict_warnings, to_source  # evita importación circular

    anchor = _anchor(conn, user_id, question, hits, min_score)
    if anchor is None:
        return None
    result = graph.neighbors(conn, user_id, anchor, depth=graph.MAX_DEPTH,
                             relations=SEMANTIC_RELATIONS)
    related = [n for n in result["neighbors"] if n["node"]["type"] == "Document"]
    if not related:
        return None

    chunks_by_doc: dict[str, list[dict]] = {}
    for chunk in repo_search.current_chunks(conn, user_id, [n["node"]["id"] for n in related]):
        chunks_by_doc.setdefault(chunk["document_id"], []).append(chunk)

    cited, context, labels = [], [], []
    for neighbor in related:
        doc_id = neighbor["node"]["id"]
        chunks = chunks_by_doc.get(doc_id)
        if not chunks:
            continue  # sin chunk vigente no hay evidencia que citar (R1)
        # Se prefiere el chunk que originó la relación, si es de este documento.
        origin = neighbor["provenance"][-1]["chunk_id"]
        cited.append(next((c for c in chunks if c["chunk_id"] == origin), chunks[0]))
        context.append({"path": neighbor["path"], "provenance": neighbor["provenance"]})
        labels.append(f"{neighbor['node']['label']} ({doc_id})")
    if not cited:
        return None

    return {
        "answer": f"Documentos relacionados con {result['node']['label']} "
                  f"({result['node']['id']}): " + "; ".join(labels) + ".",
        "abstained": False,
        "sources": [to_source(c, c["content"]) for c in cited],
        "graph_context": context,
        "warnings": conflict_warnings(cited),
    }
