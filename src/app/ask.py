"""POST /ask: selección de evidencia, abstención y respuesta extractiva."""
import logging

from app import graphrag, repo_search

log = logging.getLogger("docuvex")

ABSTENTION_TEXT = "No encontré evidencia suficiente en los documentos disponibles."

# R4: un chunk es evidencia suficiente si cubre al menos el 60% de los términos
# de la pregunta (ver la definición de score en repo_search).
MIN_SCORE = 0.6
CANDIDATES = 5


class ExtractiveGenerator:
    """Responde con el texto literal del chunk mejor puntuado. No usa LLM.

    Es el punto de extensión para un generador con LLM: recibe solo chunks ya
    autorizados (S4) y devuelve la respuesta más las citas que la sustentan.
    """

    def generate(self, question: str, chunks: list[dict]) -> dict:
        top = chunks[0]
        return {
            "answer": top["content"],
            "citations": [{"chunk_id": top["chunk_id"], "evidence": top["content"]}],
        }


generator = ExtractiveGenerator()


def abstention() -> dict:
    return {
        "answer": ABSTENTION_TEXT, "abstained": True,
        "sources": [], "graph_context": [], "warnings": [],
    }


def to_source(chunk: dict, evidence: str) -> dict:
    return {
        "document_id": chunk["document_id"],
        "document_name": chunk["document_name"],
        "version": chunk["version"],
        "chunk_id": chunk["chunk_id"],
        "page": chunk["page"],
        "bbox": chunk["bbox"],
        "evidence": evidence,
    }


def verified_sources(citations: list[dict], chunks: list[dict]) -> list[dict] | None:
    """R5: cada cita debe apuntar a un chunk entregado al generador y su evidencia
    debe ser un fragmento literal de ese chunk. Si algo no calza, no hay respuesta."""
    by_id = {c["chunk_id"]: c for c in chunks}
    sources = []
    for citation in citations:
        chunk = by_id.get(citation.get("chunk_id"))
        evidence = citation.get("evidence")
        if chunk is None or not evidence or evidence not in chunk["content"]:
            return None
        sources.append(to_source(chunk, evidence))
    return sources or None


def conflict_warnings(chunks: list[dict]) -> list[str]:
    docs = sorted({c["document_id"] for c in chunks if c["has_version_conflict"]})
    return [f"VERSION_CONFLICT:{doc}" for doc in docs]


def _extractive(question: str, hits: list[dict]) -> dict:
    candidates = [h for h in hits if h["score"] >= MIN_SCORE]
    if not candidates:
        return abstention()
    generated = generator.generate(question, candidates)
    sources = verified_sources(generated["citations"], candidates)
    if sources is None:
        return abstention()
    cited = {s["chunk_id"] for s in sources}
    return {
        "answer": generated["answer"],
        "abstained": False,
        "sources": sources,
        "graph_context": [],
        "warnings": conflict_warnings([c for c in candidates if c["chunk_id"] in cited]),
    }


def answer_question(conn, user_id: str, question: str, use_graph: bool = False) -> dict:
    # Los candidatos salen de la consulta con alcance de usuario: lo no autorizado
    # nunca llega a esta capa, por eso R6 produce la misma abstención que R3.
    hits = repo_search.search_chunks(conn, user_id, question, CANDIDATES)
    result = None
    if use_graph and graphrag.is_relational(question):
        result = graphrag.answer(conn, user_id, question, hits, MIN_SCORE)
    if result is None:
        result = _extractive(question, hits)
    ask_id = repo_search.log_ask(conn, user_id, question, result)
    log.info("ask id=%s user=%s abstained=%s chunks=%s", ask_id, user_id,
             result["abstained"], [s["chunk_id"] for s in result["sources"]])
    return result
