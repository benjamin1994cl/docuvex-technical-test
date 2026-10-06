"""POST /ask: selección de evidencia, abstención y respuesta extractiva."""
import logging
import os
import re

from app import config, graphrag, repo_search
from app.llm import AnthropicClient, FakeLLMClient, LLMError, LLMGenerator

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


def build_generator():
    """Elige el generador según ANSWER_MODE. Sin clave de API, el modo llm no se activa."""
    mode = config.answer_mode()
    if mode == "llm-fake":
        return LLMGenerator(FakeLLMClient())
    if mode == "llm":
        if os.environ.get("ANTHROPIC_API_KEY"):
            return LLMGenerator(AnthropicClient(config.llm_model()))
        log.warning("ANSWER_MODE=llm sin ANTHROPIC_API_KEY: se usa el modo extractivo")
    return ExtractiveGenerator()


generator = build_generator()


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


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def answer_supported(answer: str, sources: list[dict]) -> bool:
    """R5: toda cifra de la respuesta debe aparecer en la evidencia citada.

    Es una comprobación barata y determinista contra el error más dañino de un
    LLM en este dominio: cambiar un monto, un plazo o una fecha.
    """
    evidence_numbers = set(_NUMBER.findall(" ".join(s["evidence"] for s in sources)))
    return all(number in evidence_numbers for number in _NUMBER.findall(answer))


def conflict_warnings(chunks: list[dict]) -> list[str]:
    docs = sorted({c["document_id"] for c in chunks if c["has_version_conflict"]})
    return [f"VERSION_CONFLICT:{doc}" for doc in docs]


def _answer_from_chunks(question: str, hits: list[dict]) -> dict:
    candidates = [h for h in hits if h["score"] >= MIN_SCORE]
    if not candidates:
        return abstention()
    warnings = []
    try:
        generated = generator.generate(question, candidates)
    except LLMError as error:
        # El modelo falló: se responde con el camino extractivo, que no depende de él.
        log.warning("llm no disponible motivo=%s", error)
        generated = ExtractiveGenerator().generate(question, candidates)
        warnings.append("LLM_UNAVAILABLE")
    sources = verified_sources(generated["citations"], candidates)
    if sources is None or not answer_supported(generated["answer"], sources):
        return abstention()
    cited = {s["chunk_id"] for s in sources}
    return {
        "answer": generated["answer"],
        "abstained": False,
        "sources": sources,
        "graph_context": [],
        "warnings": warnings + conflict_warnings(
            [c for c in candidates if c["chunk_id"] in cited]),
    }


def answer_question(conn, user_id: str, question: str, use_graph: bool = False) -> dict:
    # Los candidatos salen de la consulta con alcance de usuario: lo no autorizado
    # nunca llega a esta capa, por eso R6 produce la misma abstención que R3.
    hits = repo_search.search_chunks(conn, user_id, question, CANDIDATES)
    result = None
    if use_graph and graphrag.is_relational(question):
        result = graphrag.answer(conn, user_id, question, hits, MIN_SCORE)
    if result is None:
        result = _answer_from_chunks(question, hits)
    ask_id = repo_search.log_ask(conn, user_id, question, result)
    log.info("ask id=%s user=%s abstained=%s chunks=%s", ask_id, user_id,
             result["abstained"], [s["chunk_id"] for s in result["sources"]])
    return result
