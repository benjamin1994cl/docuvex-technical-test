"""Extracción automática de entidades y relaciones por reglas (sección 9.3, opcional)."""
import pytest
from conftest import as_user

from app import extraction, seed

ALIASES = [
    {"node_id": "ent-company-gps-legal", "type": "Company", "normalized": "gps legal spa"},
    {"node_id": "ent-company-gps-legal", "type": "Company", "normalized": "gps legal"},
    {"node_id": "ent-company-inversiones-andes", "type": "Company", "normalized": "inversiones andes ltda"},
    {"node_id": "ent-person-maria-soto", "type": "Person", "normalized": "maria soto"},
]
COMPARECEN = ("Comparecen Inversiones Andes Ltda. y GPS Legal SpA, representada por doña "
              "María Soto, quien presta servicios de asesoría legal.")


def test_9_3_reconoce_entidades_conocidas_por_nombre_y_alias():
    mentions = extraction.find_mentions(COMPARECEN, ALIASES)
    assert [(m.node_id, m.name) for m in mentions] == [
        ("ent-company-inversiones-andes", "Inversiones Andes Ltda."),
        ("ent-company-gps-legal", "GPS Legal SpA,"),
        ("ent-person-maria-soto", "María Soto,"),
    ]
    assert all(m.confidence == extraction.KNOWN_CONFIDENCE for m in mentions)


def test_9_3_variantes_de_escritura_resuelven_a_la_misma_entidad():
    for text in ("Revisión de GPS LEGAL S.p.A. en marzo", "Servicios de GPS Legal por 45 UF"):
        mentions = extraction.find_mentions(text, ALIASES)
        assert [m.node_id for m in mentions] == ["ent-company-gps-legal"]


def test_9_3_detecta_la_relacion_representa():
    mentions = extraction.find_mentions(COMPARECEN, ALIASES)
    pairs = extraction.find_representations(COMPARECEN, mentions)
    assert [(p.node_id, c.node_id) for p, c in pairs] == [
        ("ent-person-maria-soto", "ent-company-gps-legal")
    ]


def test_9_3_entidad_nueva_queda_con_confianza_baja():
    mentions = extraction.find_mentions("Contrato con Transportes Sur SpA firmado hoy.", ALIASES)
    assert [(m.name, m.node_id, m.confidence) for m in mentions] == [
        ("Transportes Sur SpA", None, extraction.NEW_CONFIDENCE)
    ]


def test_9_3_sobre_el_anexo_a_no_agrega_relaciones_y_recupera_las_declaradas(db_conn):
    """El seed prevalece: la extracción no duplica nada sobre el dataset original.
    Además, las reglas recuperan por sí solas 9 de las 12 relaciones declaradas."""
    assert db_conn.execute(
        "SELECT count(*) AS n FROM graph_edges WHERE extraction_method = 'rule'"
    ).fetchone()["n"] == 0

    aliases = db_conn.execute(
        """SELECT a.node_id, n.type, a.normalized
           FROM entity_aliases a JOIN graph_nodes n ON n.id = a.node_id"""
    ).fetchall()
    chunks = db_conn.execute(
        """SELECT c.document_id, c.content FROM chunks c
           JOIN documents d ON d.current_version_id = c.version_id"""
    ).fetchall()
    found = set()
    for chunk in chunks:
        mentions = extraction.find_mentions(chunk["content"], aliases)
        found |= {(chunk["document_id"], "REFERENCES", m.node_id) for m in mentions}
        found |= {(p.node_id, "REPRESENTS", c.node_id)
                  for p, c in extraction.find_representations(chunk["content"], mentions)}
    declared = {
        (r["from_id"], r["relation"], r["to_id"]) for r in db_conn.execute(
            """SELECT from_id, relation, to_id FROM graph_edges
               WHERE relation IN ('REFERENCES', 'REPRESENTS')"""
        ).fetchall()
    }
    assert found == declared and len(found) == 9


@pytest.fixture()
def documento_nuevo(db_conn):
    doc = {
        "document_id": "extra-001", "name": "Contrato Transporte.pdf", "organization_unit": "OU-001",
        "versions": [{
            "version": 1, "is_current": True, "effective_date": "2026-05-01",
            "chunks": [{
                "chunk_id": "chunk-extra-001", "page": 1, "bbox": [0, 0, 1, 1],
                "content": ("Se firma contrato con GPS LEGAL S.p.A. y con Transportes Sur SpA, "
                            "representada por don Pedro Lagos. Comparecen Minera Norte Ltda. como testigo."),
            }],
        }],
    }
    seed.load_documents(db_conn, [doc])
    stats = extraction.extract_document(db_conn, "extra-001")
    yield stats
    db_conn.execute("DELETE FROM documents WHERE id = 'extra-001'")
    db_conn.execute("DELETE FROM graph_nodes WHERE id IN (SELECT node_id FROM entity_aliases "
                    "WHERE normalized IN ('transportes sur spa', 'pedro lagos', 'comparecen minera norte ltda'))")


def test_9_3_documento_nuevo_registra_metodo_confianza_y_procedencia(db_conn, documento_nuevo):
    edges = db_conn.execute(
        """SELECT from_id, relation, to_id, extraction_method, confidence::float8 AS confidence,
                  source_document_id, source_chunk_id
           FROM graph_edges WHERE source_document_id = 'extra-001' AND extraction_method = 'rule'
           ORDER BY id"""
    ).fetchall()
    assert all(e["source_chunk_id"] == "chunk-extra-001" for e in edges)
    resumen = {(e["from_id"], e["relation"], e["to_id"]): round(e["confidence"], 1) for e in edges}
    assert resumen == {
        ("extra-001", "REFERENCES", "ent-company-gps-legal"): 0.9,
        ("extra-001", "REFERENCES", "ent-company-transportes-sur-spa"): 0.6,
        ("extra-001", "REFERENCES", "ent-person-pedro-lagos"): 0.6,
        ("extra-001", "REFERENCES", "ent-company-comparecen-minera-norte-ltda"): 0.6,
        ("ent-person-pedro-lagos", "REPRESENTS", "ent-company-transportes-sur-spa"): 0.6,
    }
    assert documento_nuevo == {"edges": 5, "entities": 3}


def test_9_3_no_duplica_la_entidad_existente_ni_al_repetir_la_extraccion(db_conn, documento_nuevo):
    assert extraction.extract_document(db_conn, "extra-001") == {"edges": 0, "entities": 0}
    gps = db_conn.execute(
        "SELECT count(*) AS n FROM graph_nodes WHERE label ILIKE 'gps legal%'"
    ).fetchone()["n"]
    assert gps == 1


def test_9_3_solo_se_muestran_relaciones_de_confianza_alta(client, documento_nuevo):
    """La mención de GPS Legal es visible. Lo descubierto por patrón queda pendiente:
    incluye un falso positivo real ("Comparecen Minera Norte Ltda.") que así no llega al usuario."""
    r = client.get("/api/v1/graph/nodes/extra-001/neighbors", headers=as_user("user-a"))
    neighbors = {n["node"]["id"]: n for n in r.json()["neighbors"]}
    assert neighbors["ent-company-gps-legal"]["provenance"] == [
        {"document_id": "extra-001", "chunk_id": "chunk-extra-001"}
    ]
    for pendiente in ("transportes-sur", "pedro-lagos", "minera-norte", "Transportes", "Pedro Lagos"):
        assert pendiente not in r.text
    oculta = client.get("/api/v1/graph/nodes/ent-company-transportes-sur-spa/neighbors",
                        headers=as_user("user-a"))
    assert oculta.status_code == 404
    por_nombre = client.get("/api/v1/graph/nodes", params={"name": "Transportes Sur SpA"},
                            headers=as_user("user-a"))
    assert por_nombre.json() == {"nodes": []}


def test_9_3_G3_la_relacion_extraida_respeta_el_aislamiento(client, documento_nuevo):
    """extra-001 es de OU-001: user-b ve GPS Legal, pero no este documento ni su relación."""
    r = client.get("/api/v1/graph/nodes/ent-company-gps-legal/neighbors", headers=as_user("user-b"))
    assert "extra-001" not in r.text


def test_9_3_una_entidad_pendiente_no_se_confirma_por_mencionarla_otra_vez(client, db_conn, documento_nuevo):
    """Un segundo documento nombra la misma empresa pendiente. Sigue sin mostrarse:
    la revisión no se puede saltar repitiendo la mención."""
    segundo = {
        "document_id": "extra-002", "name": "Orden de Compra.pdf", "organization_unit": "OU-001",
        "versions": [{
            "version": 1, "is_current": True, "effective_date": "2026-06-01",
            "chunks": [{"chunk_id": "chunk-extra-002", "page": 1, "bbox": [0, 0, 1, 1],
                        "content": "Orden de compra emitida a Transportes Sur SpA por servicios de flete."}],
        }],
    }
    seed.load_documents(db_conn, [segundo])
    try:
        assert extraction.extract_document(db_conn, "extra-002") == {"edges": 1, "entities": 0}
        edge = db_conn.execute(
            """SELECT confidence::float8 AS c FROM graph_edges
               WHERE from_id = 'extra-002' AND to_id = 'ent-company-transportes-sur-spa'"""
        ).fetchone()
        assert round(edge["c"], 1) == extraction.NEW_CONFIDENCE
        r = client.get("/api/v1/graph/nodes/extra-002/neighbors", headers=as_user("user-a"))
        assert r.status_code == 200 and "transportes" not in r.text.lower()
        oculta = client.get("/api/v1/graph/nodes/ent-company-transportes-sur-spa/neighbors",
                            headers=as_user("user-a"))
        assert oculta.status_code == 404
    finally:
        db_conn.execute("DELETE FROM documents WHERE id = 'extra-002'")


def test_9_3_G2_entidad_no_confirmada_es_invisible_aunque_la_relacion_tenga_confianza_alta(client, db_conn, documento_nuevo):
    """Defensa en profundidad: aun con una relación de confianza 1.0, sin revisión no se muestra."""
    db_conn.execute(
        "UPDATE graph_edges SET confidence = 1.0 WHERE to_id = 'ent-company-transportes-sur-spa'")
    r = client.get("/api/v1/graph/nodes/ent-company-transportes-sur-spa/neighbors",
                   headers=as_user("user-a"))
    assert r.status_code == 404
    db_conn.execute("UPDATE graph_nodes SET confirmed = true WHERE id = 'ent-company-transportes-sur-spa'")
    r = client.get("/api/v1/graph/nodes/ent-company-transportes-sur-spa/neighbors",
                   headers=as_user("user-a"))
    assert r.status_code == 200  # la revisión manual es lo único que la hace visible
