"""Carga del Anexo A y regla de versión vigente."""
from app.versions import resolve_current


def test_carga_dataset_conteos(db_conn):
    counts = {
        table: db_conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
        for table in ("organization_units", "users", "documents", "document_versions", "chunks")
    }
    assert counts == {
        "organization_units": 3, "users": 3, "documents": 8,
        "document_versions": 11, "chunks": 13,
    }


def test_carga_grafo_nodos_y_relaciones(db_conn):
    nodes = dict(
        (r["type"], r["n"]) for r in
        db_conn.execute("SELECT type, count(*) AS n FROM graph_nodes GROUP BY type").fetchall()
    )
    assert nodes == {"Document": 8, "Version": 11, "OrganizationUnit": 3, "Company": 3, "Person": 2}
    edges = dict(
        (r["relation"], r["n"]) for r in
        db_conn.execute("SELECT relation, count(*) AS n FROM graph_edges GROUP BY relation").fetchall()
    )
    assert edges == {
        "BELONGS_TO": 8, "HAS_VERSION": 11, "SUPERSEDES": 3,
        "REFERENCES": 8, "RELATED_TO": 3, "REPRESENTS": 1,
    }


def test_carga_toda_relacion_tiene_procedencia(db_conn):
    row = db_conn.execute(
        "SELECT count(*) AS n FROM graph_edges WHERE source_document_id IS NULL"
    ).fetchone()
    assert row["n"] == 0


def test_seccion8_version_vigente_es_la_marcada():
    versions = [
        {"version": 1, "is_current": False, "effective_date": "2024-01-10"},
        {"version": 3, "is_current": True, "effective_date": "2026-02-15"},
    ]
    assert resolve_current(versions) == (3, False)


def test_seccion8_conflicto_elige_fecha_mas_reciente():
    versions = [
        {"version": 1, "is_current": True, "effective_date": "2025-01-01"},
        {"version": 2, "is_current": True, "effective_date": "2026-01-01"},
    ]
    assert resolve_current(versions) == (2, True)


def test_seccion8_conflicto_misma_fecha_elige_version_mayor():
    versions = [
        {"version": 4, "is_current": True, "effective_date": "2026-01-01"},
        {"version": 5, "is_current": True, "effective_date": "2026-01-01"},
    ]
    assert resolve_current(versions) == (5, True)


def test_seccion8_sin_marca_usa_la_mas_reciente():
    versions = [
        {"version": 1, "is_current": False, "effective_date": "2025-01-01"},
        {"version": 2, "is_current": False, "effective_date": "2026-01-01"},
    ]
    assert resolve_current(versions) == (2, False)


def test_seccion8_dataset_marca_vigente_y_conflicto(db_conn):
    rows = {
        r["id"]: r for r in db_conn.execute(
            "SELECT id, current_version_id, has_version_conflict FROM documents"
        ).fetchall()
    }
    assert rows["doc-001"]["current_version_id"] == "doc-001@v3"
    assert rows["doc-001"]["has_version_conflict"] is False
    assert rows["doc-008"]["current_version_id"] == "doc-008@v2"
    assert rows["doc-008"]["has_version_conflict"] is True
