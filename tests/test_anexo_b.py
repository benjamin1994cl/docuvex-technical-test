"""Anexo B: los 19 casos de aceptación, sobre el dataset del Anexo A.

"No contiene" se comprueba sobre el cuerpo completo de la respuesta (r.text),
no solo sobre los campos esperados.
"""
from conftest import ABSTENTION, as_user

DURACION = {"query": "¿Cuál es la duración del contrato?"}
GPS_VECINOS = "/api/v1/graph/nodes/ent-company-gps-legal/neighbors"


def post(client, path, body, user=None):
    return client.post(f"/api/v1{path}", json=body, headers=as_user(user) if user else {})


def get(client, path, user):
    return client.get(path, headers=as_user(user))


def no_contiene(response, *textos):
    for texto in textos:
        assert texto not in response.text, f"filtración: {texto!r}"


def es_abstencion_exacta(response):
    body = response.json()
    assert body["answer"] == ABSTENTION
    assert body["abstained"] is True
    assert body["sources"] == []


def test_A01_user_a_busca_duracion(client):
    r = post(client, "/search", DURACION, "user-a")
    assert r.status_code == 200
    assert "chunk-001-v3-01" in r.text
    no_contiene(r, "doc-003", "chunk-003-v1-01")


def test_A02_user_b_busca_duracion(client):
    r = post(client, "/search", DURACION, "user-b")
    assert r.status_code == 200
    assert "chunk-003-v1-01" in r.text
    no_contiene(r, "doc-001")


def test_A03_user_c_recibe_lista_vacia(client):
    r = post(client, "/search", DURACION, "user-c")
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_A04_sin_header_401(client):
    assert post(client, "/search", DURACION).status_code == 401


def test_A05_sin_historial_no_trae_versiones_anteriores(client):
    r = post(client, "/search", {"query": "duración del contrato", "include_history": False}, "user-a")
    assert r.status_code == 200
    no_contiene(r, "chunk-001-v1-01", "chunk-001-v2-01")


def test_A06_duracion_del_contrato_con_gps_legal(client, chunk_content):
    r = post(client, "/ask", {"question": "¿Cuál es la duración del contrato con GPS Legal?"}, "user-a")
    body = r.json()
    assert body["abstained"] is False
    assert "24 meses" in body["answer"]
    source = next(s for s in body["sources"] if s["chunk_id"] == "chunk-001-v3-01")
    assert source["evidence"] and source["evidence"] in chunk_content["chunk-001-v3-01"]


def test_A07_sueldo_para_user_a_abstencion_sin_filtracion(client):
    r = post(client, "/ask", {"question": "¿Cuál es el sueldo del gerente general?"}, "user-a")
    es_abstencion_exacta(r)
    no_contiene(r, "doc-004", "Jorge Rivas", "9.500.000")


def test_A08_sueldo_para_user_b_responde_con_fuente(client):
    r = post(client, "/ask", {"question": "¿Cuál es el sueldo del gerente general?"}, "user-b")
    body = r.json()
    assert body["abstained"] is False
    assert "chunk-004-v1-01" in [s["chunk_id"] for s in body["sources"]]


def test_A09_capital_de_australia_abstencion_exacta(client):
    r = post(client, "/ask", {"question": "¿Cuál es la capital de Australia?"}, "user-a")
    es_abstencion_exacta(r)


def test_A10_viatico_determinista_con_warning_de_conflicto(client):
    pregunta = {"question": "¿Cuál es el viático diario nacional?"}
    cuerpos = [post(client, "/ask", pregunta, "user-a").content for _ in range(3)]
    assert cuerpos[0] == cuerpos[1] == cuerpos[2]
    body = post(client, "/ask", pregunta, "user-a").json()
    assert "VERSION_CONFLICT:doc-008" in body["warnings"]
    assert not ("30.000" in body["answer"] and "45.000" in body["answer"])


def test_A11_vecinos_de_gps_legal_para_user_a(client):
    r = get(client, GPS_VECINOS + "?depth=1", "user-a")
    assert r.status_code == 200
    for esperado in ("doc-001", "doc-002", "doc-007", "ent-person-maria-soto"):
        assert esperado in r.text
    no_contiene(r, "doc-005")


def test_A12_vecinos_de_gps_legal_para_user_b(client):
    r = get(client, GPS_VECINOS + "?depth=1", "user-b")
    assert r.status_code == 200
    assert "doc-005" in r.text
    no_contiene(r, "doc-001", "doc-002", "doc-007", "ent-person-maria-soto")


def test_A13_vecinos_de_doc_001_a_profundidad_2_sin_puentes(client):
    r = get(client, "/api/v1/graph/nodes/doc-001/neighbors?depth=2", "user-a")
    assert r.status_code == 200
    assert "doc-002" in r.text
    no_contiene(r, "doc-005", "doc-006")


def test_A14_A15_nodo_no_autorizado_404_con_el_mismo_cuerpo_que_inexistente(client):
    a14 = get(client, "/api/v1/graph/nodes/doc-005/neighbors", "user-a")
    a15 = get(client, "/api/v1/graph/nodes/doc-999/neighbors", "user-a")
    assert a14.status_code == 404 and a15.status_code == 404
    assert a14.content == a15.content


def test_A16_entidad_sin_documento_autorizado_404(client):
    r = get(client, "/api/v1/graph/nodes/ent-person-jorge-rivas/neighbors", "user-a")
    assert r.status_code == 404
    no_contiene(r, "Jorge", "Gerente", "doc-004")


def test_A17_graphrag_documentos_relacionados(client):
    r = post(client, "/ask", {
        "question": "¿Qué documentos están relacionados con el contrato de GPS Legal?",
        "use_graph": True,
    }, "user-a")
    body = r.json()
    assert body["abstained"] is False
    assert "doc-002" in body["answer"]
    assert body["graph_context"]
    assert all(item["path"] and item["provenance"] for item in body["graph_context"])
    no_contiene(r, "doc-005", "doc-006")


def test_A18_resolucion_de_entidad_por_alias(client):
    r = client.get("/api/v1/graph/nodes", params={"name": "GPS LEGAL S.p.A."},
                   headers=as_user("user-a"))
    assert r.status_code == 200
    assert [n["id"] for n in r.json()["nodes"]] == ["ent-company-gps-legal"]


def test_A19_validacion_400_con_formato_de_error(client):
    for body in ({"query": ""}, {"query": "x", "limit": 50}):
        r = post(client, "/search", body, "user-a")
        assert r.status_code == 400
        error = r.json()["error"]
        assert set(error) == {"code", "message"} and error["code"] and error["message"]
