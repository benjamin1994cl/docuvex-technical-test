"""POST /api/v1/search: relevancia, aislamiento por OU y versión vigente."""
import pytest
from conftest import as_user

from app import seed

DURACION = "¿Cuál es la duración del contrato?"


def search(client, user, **body):
    r = client.post("/api/v1/search", json=body, headers=as_user(user))
    assert r.status_code == 200, r.text
    return r


@pytest.fixture()
def documentos_ajenos(db_conn):
    """Seis documentos de OU-002 que coinciden por completo con la consulta de duración."""
    docs = [
        {
            "document_id": f"decoy-{i}", "name": f"Contrato Ajeno {i}.pdf",
            "organization_unit": "OU-002",
            "versions": [{
                "version": 1, "is_current": True, "effective_date": "2026-01-01",
                "chunks": [{
                    "chunk_id": f"chunk-decoy-{i}", "page": 1, "bbox": [0, 0, 1, 1],
                    "content": f"La duración del contrato ajeno número {i} es de 99 meses.",
                }],
            }],
        }
        for i in range(1, 7)
    ]
    seed.load_documents(db_conn, docs)
    yield docs
    db_conn.execute("DELETE FROM documents WHERE id LIKE 'decoy-%'")


def test_T01_busqueda_devuelve_chunk_correcto_con_metadatos(client):
    results = search(client, "user-a", query=DURACION).json()["results"]
    assert results[0] == {
        "document_id": "doc-001",
        "document_name": "Contrato Servicios GPS Legal.pdf",
        "version": 3,
        "is_current_version": True,
        "organization_unit": "OU-001",
        "chunk_id": "chunk-001-v3-01",
        "page": 1,
        "score": 1.0,
        "content": "El contrato tendrá una duración de 24 meses contados desde el 1 de marzo de 2026.",
    }


def test_5_1_resultados_ordenados_por_score_descendente(client):
    results = search(client, "user-a", query="duración del contrato con GPS Legal", limit=20).json()["results"]
    scores = [r["score"] for r in results]
    assert len(scores) > 1
    assert scores == sorted(scores, reverse=True)
    assert all(0 < s <= 1 for s in scores)


def test_S2_documento_otra_ou_con_score_alto_no_aparece(client):
    """chunk-003 (OU-002) repite la pregunta casi literal: no debe verlo user-a."""
    r = search(client, "user-a", query=DURACION, limit=20)
    assert "chunk-003-v1-01" not in r.text
    assert "doc-003" not in r.text
    assert {x["organization_unit"] for x in r.json()["results"]} <= {"OU-001", "OU-003"}


def test_S1_usuario_de_ou_002_no_ve_documentos_de_ou_001(client):
    r = search(client, "user-b", query=DURACION, limit=20)
    assert "chunk-003-v1-01" in r.text
    assert "doc-001" not in r.text
    assert {x["organization_unit"] for x in r.json()["results"]} == {"OU-002"}


def test_S3_con_documentos_ajenos_mas_relevantes_se_reciben_limit_resultados(client, documentos_ajenos):
    """Seis chunks ajenos puntúan 1.0. Con un filtro posterior al top-k, user-a recibiría menos de 3."""
    r = search(client, "user-a", query="duración del contrato", limit=3)
    results = r.json()["results"]
    assert len(results) == 3
    assert {x["organization_unit"] for x in results} == {"OU-001"}
    assert "decoy" not in r.text


def test_S3_los_documentos_ajenos_si_existen_para_su_dueno(client, documentos_ajenos):
    """Control: el caso anterior no pasa porque los señuelos estén mal cargados."""
    r = search(client, "user-b", query="duración del contrato", limit=20)
    assert r.text.count("chunk-decoy-") == 6


def test_S1_el_cliente_no_puede_ampliar_su_alcance_en_el_body(client):
    r = search(client, "user-a", query=DURACION, limit=20,
               organization_units=["OU-002"], organization_unit="OU-002", user_id="user-b")
    assert "doc-003" not in r.text


def test_S1_el_cliente_no_puede_ampliar_su_alcance_en_la_query(client):
    r = client.post("/api/v1/search?organization_unit=OU-002&ou=OU-002",
                    json={"query": DURACION, "limit": 20}, headers=as_user("user-a"))
    assert r.status_code == 200
    assert "doc-003" not in r.text


def test_seccion8_por_defecto_solo_version_vigente(client):
    r = search(client, "user-a", query="duración del contrato", limit=20)
    assert "chunk-001-v3-01" in r.text
    assert "chunk-001-v1-01" not in r.text and "chunk-001-v2-01" not in r.text
    assert all(x["is_current_version"] for x in r.json()["results"])


def test_seccion8_include_history_trae_versiones_anteriores(client):
    r = search(client, "user-a", query="duración del contrato", limit=20, include_history=True)
    by_chunk = {x["chunk_id"]: x for x in r.json()["results"]}
    assert by_chunk["chunk-001-v1-01"]["is_current_version"] is False
    assert by_chunk["chunk-001-v2-01"]["is_current_version"] is False
    assert by_chunk["chunk-001-v3-01"]["is_current_version"] is True


def test_seccion8_conflicto_la_busqueda_usa_solo_la_version_elegida(client):
    r = search(client, "user-a", query="viático diario nacional")
    assert "chunk-008-v2-01" in r.text
    assert "chunk-008-v1-01" not in r.text


def test_5_1_consulta_sin_terminos_utiles_devuelve_lista_vacia(client):
    for query in ("¿?", "de la", "¿Qué?", "..."):
        assert search(client, "user-a", query=query).json() == {"results": []}


def test_5_1_caracteres_especiales_no_rompen_la_busqueda(client):
    for query in ("contrato' | 'x", "a & b | c:*", "\\ ' \" ; --", "contrato:* !duración", "<->"):
        r = client.post("/api/v1/search", json={"query": query}, headers=as_user("user-a"))
        assert r.status_code == 200, (query, r.text)


def test_5_1_busqueda_sin_tilde_encuentra_igual(client):
    r = search(client, "user-a", query="duracion del contrato")
    assert "chunk-001-v3-01" in r.text
