"""Consultas SQL de documentos y chunks.

Toda función recibe user_id y hace join con user_organization_units: la
autorización ocurre dentro de la consulta, antes del ORDER BY y del LIMIT
(reglas S1 a S3). No existe una función que lea chunks sin alcance de usuario.
"""
from app.text import content_words

# score: fracción de los términos de la consulta presentes en el chunk.
# Un término en el contenido vale 1; si solo está en el nombre del documento, 0,5.
_SCORE = """
    round((
        SELECT sum(CASE WHEN l = ANY(tsvector_to_array(c.content_tsv)) THEN 1.0
                        WHEN l = ANY(tsvector_to_array(c.title_tsv)) THEN 0.5
                        ELSE 0 END) / cardinality(%(lexemes)s::text[])
        FROM unnest(%(lexemes)s::text[]) AS l
    ), 4)::float8
"""

_COLUMNS = """
    d.id AS document_id, d.name AS document_name, v.version,
    (v.id = d.current_version_id) AS is_current_version,
    d.ou_id AS organization_unit, d.has_version_conflict,
    c.id AS chunk_id, c.page, c.bbox, c.content
"""

# AUTORIZACIÓN: el join con user_organization_units limita todo a las OU del usuario.
_SCOPED_FROM = """
    FROM chunks c
    JOIN document_versions v ON v.id = c.version_id
    JOIN documents d ON d.id = v.document_id
    JOIN user_organization_units uo
      ON uo.ou_id = d.ou_id AND uo.user_id = %(user_id)s
"""


def query_lexemes(conn, text: str) -> list[str]:
    """Lexemas en español de la consulta (sin palabras vacías ni interrogativos)."""
    row = conn.execute(
        "SELECT tsvector_to_array(to_tsvector('spanish'::regconfig, %s::text)) AS lexemes",
        (content_words(text),),
    ).fetchone()
    return sorted(row["lexemes"])


def _or_query(lexemes: list[str]) -> str:
    """'a' | 'b': basta un término para ser candidato; el orden lo da el score."""
    quoted = ("'" + l.replace("\\", "\\\\").replace("'", "''") + "'" for l in lexemes)
    return " | ".join(quoted)


def search_chunks(conn, user_id: str, query: str, limit: int,
                  include_history: bool = False) -> list[dict]:
    lexemes = query_lexemes(conn, query)
    if not lexemes:
        return []
    sql = f"""
        SELECT {_COLUMNS}, {_SCORE} AS score
        {_SCOPED_FROM}
        WHERE c.tsv @@ %(tsquery)s::tsquery
          AND (%(include_history)s::boolean OR v.id = d.current_version_id)
        ORDER BY score DESC, ts_rank_cd(c.tsv, %(tsquery)s::tsquery) DESC, c.id
        LIMIT %(limit)s
    """
    return conn.execute(sql, {
        "user_id": user_id, "lexemes": lexemes, "tsquery": _or_query(lexemes),
        "include_history": include_history, "limit": limit,
    }).fetchall()


def current_chunks(conn, user_id: str, document_ids: list[str]) -> list[dict]:
    """Chunks de la versión vigente de documentos visibles para el usuario."""
    sql = f"""
        SELECT {_COLUMNS}
        {_SCOPED_FROM}
        WHERE d.id = ANY(%(document_ids)s::text[]) AND v.id = d.current_version_id
        ORDER BY c.id
    """
    return conn.execute(sql, {"user_id": user_id, "document_ids": document_ids}).fetchall()


def get_document(conn, user_id: str, document_id: str) -> dict | None:
    doc = conn.execute(
        """SELECT d.id, d.name, d.ou_id, d.current_version_id, d.has_version_conflict
           FROM documents d
           JOIN user_organization_units uo
             ON uo.ou_id = d.ou_id AND uo.user_id = %(user_id)s
           WHERE d.id = %(document_id)s""",
        {"user_id": user_id, "document_id": document_id},
    ).fetchone()
    if doc is None:
        return None
    doc["versions"] = conn.execute(
        """SELECT id, version, is_current, effective_date
           FROM document_versions WHERE document_id = %s ORDER BY version""",
        (document_id,),
    ).fetchall()
    return doc


def log_ask(conn, user_id: str, question: str, result: dict) -> int:
    """Guarda la consulta y los chunks que originaron la respuesta (10.2, pregunta 4)."""
    ask_id = conn.execute(
        """INSERT INTO ask_log (user_id, question, abstained, warnings)
           VALUES (%s, %s, %s, %s) RETURNING id""",
        (user_id, question, result["abstained"], result["warnings"]),
    ).fetchone()["id"]
    for position, source in enumerate(result["sources"]):
        conn.execute(
            "INSERT INTO ask_log_sources (ask_id, position, chunk_id) VALUES (%s, %s, %s)",
            (ask_id, position, source["chunk_id"]),
        )
    return ask_id
