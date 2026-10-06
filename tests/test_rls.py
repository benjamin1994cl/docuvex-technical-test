"""Segunda barrera: Row-Level Security en PostgreSQL.

La primera barrera es el join de alcance en cada consulta. Estos tests prueban
que, si esa barrera faltara, la base de datos igual no entrega filas ajenas.
"""
from conftest import as_user

from app import repo_search


def como_app(conn, user_id, sql):
    """Ejecuta una consulta SIN filtro de alcance, con el rol y el usuario que usa la API."""
    with conn.transaction():
        conn.execute("SET LOCAL ROLE docuvex_app")
        if user_id is not None:
            conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))
        return conn.execute(sql).fetchall()


def test_RLS_consulta_sin_filtro_solo_ve_chunks_de_las_ou_del_usuario(db_conn):
    ous = lambda user: {r["ou_id"] for r in como_app(  # noqa: E731
        db_conn, user, "SELECT DISTINCT d.ou_id FROM chunks c JOIN documents d ON d.id = c.document_id")}
    assert ous("user-a") == {"OU-001", "OU-003"}
    assert ous("user-b") == {"OU-002"}
    assert ous("user-c") == set()


def test_RLS_el_sueldo_no_es_legible_para_user_a_ni_con_sql_directo(db_conn):
    sql = "SELECT id FROM chunks WHERE content ILIKE '%sueldo%'"
    assert como_app(db_conn, "user-a", sql) == []
    assert [r["id"] for r in como_app(db_conn, "user-b", sql)] == ["chunk-004-v1-01"]


def test_RLS_sin_usuario_fijado_no_se_ve_nada(db_conn):
    for table in ("documents", "document_versions", "chunks", "graph_edges", "entity_attributes"):
        assert como_app(db_conn, None, f"SELECT 1 FROM {table}") == [], table


def test_RLS_relaciones_y_atributos_con_procedencia_ajena_no_son_legibles(db_conn):
    edges = como_app(db_conn, "user-a", "SELECT DISTINCT source_document_id AS d FROM graph_edges")
    assert not {e["d"] for e in edges} & {"doc-003", "doc-004", "doc-005"}
    assert como_app(db_conn, "user-a", "SELECT 1 FROM entity_attributes") == []
    assert len(como_app(db_conn, "user-b", "SELECT 1 FROM entity_attributes")) == 1


def test_RLS_el_rol_de_la_api_no_puede_modificar_documentos(db_conn):
    import psycopg
    import pytest
    for sql in ("DELETE FROM chunks", "UPDATE documents SET ou_id = 'OU-001'",
                "INSERT INTO user_organization_units VALUES ('user-a', 'OU-002')"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            como_app(db_conn, "user-a", sql)


def test_RLS_si_una_consulta_olvida_el_join_de_alcance_la_api_igual_no_filtra(client, monkeypatch):
    """Simula el error de programación más temido: una consulta sin el filtro por OU."""
    monkeypatch.setattr(repo_search, "_SCOPED_FROM", """
        FROM chunks c
        JOIN document_versions v ON v.id = c.version_id
        JOIN documents d ON d.id = v.document_id
    """)
    r = client.post("/api/v1/search", json={"query": "¿Cuál es la duración del contrato?", "limit": 20},
                    headers=as_user("user-a"))
    assert r.status_code == 200
    assert "chunk-001-v3-01" in r.text
    assert "doc-003" not in r.text and "chunk-003" not in r.text
    r = client.post("/api/v1/ask", json={"question": "¿Cuál es el sueldo del gerente general?"},
                    headers=as_user("user-a"))
    assert r.json()["abstained"] is True and "9.500.000" not in r.text
