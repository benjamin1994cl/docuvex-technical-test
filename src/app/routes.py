"""Rutas de la API v1. Validan el request y delegan; no contienen SQL."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, StringConstraints

from app import ask, graph, repo_graph, repo_search
from app.auth import current_user
from app.db import get_conn
from app.errors import not_found
from app.text import normalize_name

log = logging.getLogger("docuvex")
router = APIRouter()
api = APIRouter(prefix="/api/v1")

Text500 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class SearchRequest(BaseModel):
    query: Text500
    limit: int = Field(default=5, ge=1, le=20)
    include_history: bool = False


class AskRequest(BaseModel):
    question: Text500
    use_graph: bool = False


@router.get("/health")
def health():
    return {"status": "ok"}


@api.post("/search")
def search(body: SearchRequest, user_id: str = Depends(current_user), conn=Depends(get_conn)):
    rows = repo_search.search_chunks(conn, user_id, body.query, body.limit, body.include_history)
    log.info("search user=%s chunks=%s", user_id, [r["chunk_id"] for r in rows])
    return {"results": [
        {
            "document_id": r["document_id"],
            "document_name": r["document_name"],
            "version": r["version"],
            "is_current_version": r["is_current_version"],
            "organization_unit": r["organization_unit"],
            "chunk_id": r["chunk_id"],
            "page": r["page"],
            "score": r["score"],
            "content": r["content"],
        }
        for r in rows
    ]}


@api.post("/ask")
def ask_question(body: AskRequest, user_id: str = Depends(current_user), conn=Depends(get_conn)):
    return ask.answer_question(conn, user_id, body.question, body.use_graph)


@api.get("/graph/nodes/{node_id}/neighbors")
def graph_neighbors(
    node_id: str,
    depth: int = Query(default=1, ge=1, le=graph.MAX_DEPTH),
    relation: str | None = Query(default=None, min_length=1, max_length=50),
    user_id: str = Depends(current_user),
    conn=Depends(get_conn),
):
    result = graph.neighbors(conn, user_id, node_id, depth, [relation] if relation else None)
    log.info("graph user=%s node=%s depth=%d neighbors=%d", user_id, result["node"]["id"],
             depth, len(result["neighbors"]))
    return result


@api.get("/graph/nodes")
def graph_find_nodes(
    name: str = Query(min_length=1, max_length=200),
    user_id: str = Depends(current_user),
    conn=Depends(get_conn),
):
    """Resolución de entidades: nombre o alias -> nodo visible (sección 9.4)."""
    return {"nodes": repo_graph.find_entities_by_name(conn, user_id, normalize_name(name))}


@api.get("/documents/{document_id}")
def document_metadata(document_id: str, user_id: str = Depends(current_user),
                      conn=Depends(get_conn)):
    doc = repo_search.get_document(conn, user_id, document_id)
    if doc is None:
        raise not_found()
    return {
        "document_id": doc["id"],
        "document_name": doc["name"],
        "organization_unit": doc["ou_id"],
        "current_version": next(
            v["version"] for v in doc["versions"] if v["id"] == doc["current_version_id"]
        ),
        "version_conflict": doc["has_version_conflict"],
        "versions": [
            {
                "version": v["version"],
                "is_current": v["id"] == doc["current_version_id"],
                "declared_current": v["is_current"],
                "effective_date": v["effective_date"].isoformat(),
            }
            for v in doc["versions"]
        ],
    }


router.include_router(api)
