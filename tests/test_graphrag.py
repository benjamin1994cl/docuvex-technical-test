"""Uso del grafo en /ask (sección 9.6)."""
from conftest import ABSTENTION, as_user

RELACIONADOS = "¿Qué documentos están relacionados con el contrato de GPS Legal?"


def preguntar(client, user, question, **extra):
    r = client.post("/api/v1/ask", json={"question": question, **extra}, headers=as_user(user))
    assert r.status_code == 200, r.text
    return r


def test_9_6_documentos_relacionados_con_evidencia_y_caminos(client, chunk_content):
    r = preguntar(client, "user-a", RELACIONADOS, use_graph=True)
    body = r.json()
    assert body["abstained"] is False
    assert "doc-002" in body["answer"] and "Anexo Tarifas GPS Legal.pdf" in body["answer"]
    # R1 y R2: la respuesta sigue citando chunks con evidencia literal.
    assert {s["document_id"] for s in body["sources"]} == {"doc-002", "doc-007"}
    for source in body["sources"]:
        assert source["evidence"] in chunk_content[source["chunk_id"]]
    # graph_context: caminos con procedencia, mismo formato que /neighbors.
    assert len(body["graph_context"]) == len(body["sources"])
    for item in body["graph_context"]:
        assert set(item) == {"path", "provenance"}
        assert len(item["path"]) == len(item["provenance"]) >= 1
    assert body["graph_context"][0] == {
        "path": [{"from": "doc-002", "relation": "RELATED_TO", "to": "doc-001", "kind": "ANNEX_OF"}],
        "provenance": [{"document_id": "doc-002", "chunk_id": "chunk-002-v1-01"}],
    }


def test_9_6_G4_graphrag_no_filtra_documentos_ajenos_ni_puentes(client):
    r = preguntar(client, "user-a", RELACIONADOS, use_graph=True)
    for prohibido in ("doc-005", "doc-006", "chunk-005", "Acta Comité", "REVIEWS", "LINKS"):
        assert prohibido not in r.text


def test_9_6_user_b_solo_ve_su_parte_del_grafo(client):
    r = preguntar(client, "user-b", "¿Qué documentos están relacionados con GPS Legal?", use_graph=True)
    for prohibido in ("doc-001", "doc-002", "doc-006", "doc-007", "María Soto"):
        assert prohibido not in r.text


def test_9_6_sin_use_graph_no_hay_contexto_de_grafo(client):
    assert preguntar(client, "user-a", RELACIONADOS).json()["graph_context"] == []


def test_9_6_pregunta_puntual_con_use_graph_responde_igual_que_sin_grafo(client):
    pregunta = "¿Cuál es la duración del contrato con GPS Legal?"
    con = preguntar(client, "user-a", pregunta, use_graph=True).json()
    sin = preguntar(client, "user-a", pregunta).json()
    assert con == sin and "24 meses" in con["answer"]


def test_9_6_pregunta_relacional_sin_ancla_se_abstiene(client):
    body = preguntar(client, "user-a", "¿Qué documentos están relacionados con Australia?",
                     use_graph=True).json()
    assert body["abstained"] is True and body["answer"] == ABSTENTION
    assert body["sources"] == [] and body["graph_context"] == []


def test_9_6_usuario_sin_ou_se_abstiene(client):
    body = preguntar(client, "user-c", RELACIONADOS, use_graph=True).json()
    assert body["abstained"] is True and body["graph_context"] == []
