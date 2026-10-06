"""Rutas de la API v1. Validan el request y delegan; no contienen SQL."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints

from app import repo_search
from app.auth import current_user
from app.db import get_conn

log = logging.getLogger("docuvex")
router = APIRouter()
api = APIRouter(prefix="/api/v1")

Text500 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class SearchRequest(BaseModel):
    query: Text500
    limit: int = Field(default=5, ge=1, le=20)
    include_history: bool = False


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


router.include_router(api)
