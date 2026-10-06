"""POST /api/v1/ask: evidencia literal, abstención y versión vigente."""
from conftest import ABSTENTION, as_user

from app import ask

ABSTENCION_COMPLETA = {
    "answer": ABSTENTION, "abstained": True,
    "sources": [], "graph_context": [], "warnings": [],
}
OU_002_CHUNKS = {"chunk-003-v1-01", "chunk-004-v1-01", "chunk-005-v1-01"}


def preguntar(client, user, question, **extra):
    r = client.post("/api/v1/ask", json={"question": question, **extra}, headers=as_user(user))
    assert r.status_code == 200, r.text
    return r


def test_R1_R2_evidence_es_fragmento_literal_del_chunk_citado(client, chunk_content):
    body = preguntar(client, "user-a", "¿Cuál es la duración del contrato con GPS Legal?").json()
    assert body["abstained"] is False
    assert "24 meses" in body["answer"]
    assert len(body["sources"]) >= 1
    for source in body["sources"]:
        assert source["evidence"]
        assert source["evidence"] in chunk_content[source["chunk_id"]]
    assert body["sources"][0] == {
        "document_id": "doc-001",
        "document_name": "Contrato Servicios GPS Legal.pdf",
        "version": 3,
        "chunk_id": "chunk-001-v3-01",
        "page": 1,
        "bbox": [72, 140, 540, 172],
        "evidence": "El contrato tendrá una duración de 24 meses contados desde el 1 de marzo de 2026.",
    }


def test_R3_pregunta_sin_evidencia_en_el_corpus_abstencion_exacta(client):
    r = preguntar(client, "user-a", "¿Cuál es la capital de Australia?")
    assert r.json() == ABSTENCION_COMPLETA


def test_R3_coincidencia_parcial_debil_tambien_se_abstiene(client):
    """Comparte palabras con el corpus ('contrato', 'GPS Legal') pero no responde la pregunta."""
    r = preguntar(client, "user-a", "¿Quién firmó la carta de despido del proveedor de GPS Legal?")
    assert r.json() == ABSTENCION_COMPLETA


def test_R6_S1_respuesta_solo_en_ou_no_autorizada_abstencion_sin_filtrar(client):
    r = preguntar(client, "user-a", "¿Cuál es el sueldo del gerente general?")
    assert r.json() == ABSTENCION_COMPLETA
    for prohibido in ("doc-004", "chunk-004", "Jorge Rivas", "9.500.000", "Remuneraciones"):
        assert prohibido not in r.text


def test_R6_la_abstencion_es_identica_a_la_de_una_pregunta_sin_respuesta(client):
    """No se insinúa que la información existe en otra OU: ambos cuerpos son iguales."""
    en_otra_ou = preguntar(client, "user-a", "¿Cuál es el sueldo del gerente general?")
    inexistente = preguntar(client, "user-a", "¿Cuál es la capital de Australia?")
    assert en_otra_ou.content == inexistente.content


def test_R1_el_dueno_de_la_informacion_si_recibe_respuesta(client):
    body = preguntar(client, "user-b", "¿Cuál es el sueldo del gerente general?").json()
    assert body["abstained"] is False
    assert "9.500.000" in body["answer"]
    assert [s["chunk_id"] for s in body["sources"]] == ["chunk-004-v1-01"]


def test_seccion4_usuario_sin_ou_se_abstiene(client):
    r = preguntar(client, "user-c", "¿Cuál es la duración del contrato con GPS Legal?")
    assert r.json() == ABSTENCION_COMPLETA


def test_seccion8_T09_se_usa_la_version_vigente_24_meses(client):
    body = preguntar(client, "user-a", "¿Cuál es la duración del contrato con GPS Legal?").json()
    assert "24 meses" in body["answer"]
    assert "12 meses" not in body["answer"] and "18 meses" not in body["answer"]
    assert {s["version"] for s in body["sources"]} == {3}
    assert body["warnings"] == []


def test_seccion8_T10_conflicto_de_versiones_determinista_con_warning(client):
    respuestas = [
        preguntar(client, "user-a", "¿Cuál es el viático diario nacional?").content
        for _ in range(3)
    ]
    assert respuestas[0] == respuestas[1] == respuestas[2]
    body = preguntar(client, "user-a", "¿Cuál es el viático diario nacional?").json()
    assert body["abstained"] is False
    assert body["warnings"] == ["VERSION_CONFLICT:doc-008"]
    # No mezcla versiones: responde con la elegida (v2) y cita solo esa.
    assert "45.000" in body["answer"] and "30.000" not in body["answer"]
    assert [s["chunk_id"] for s in body["sources"]] == ["chunk-008-v2-01"]


def test_S4_T14_el_generador_solo_recibe_chunks_autorizados(client, monkeypatch):
    """Equivalente de T14 sin LLM: lo que llegaría al prompt nunca incluye chunks ajenos."""
    recibidos = []
    original = ask.generator

    class Espia:
        def generate(self, question, chunks):
            recibidos.extend(chunks)
            return original.generate(question, chunks)

    monkeypatch.setattr(ask, "generator", Espia())
    preguntar(client, "user-a", "¿Cuál es la duración del contrato?")
    assert recibidos
    assert not {c["chunk_id"] for c in recibidos} & OU_002_CHUNKS
    assert {c["organization_unit"] for c in recibidos} <= {"OU-001", "OU-003"}


def test_R5_respuesta_no_sustentada_por_la_evidencia_se_convierte_en_abstencion(client, monkeypatch):
    """Si el generador inventa una cita, la verificación posterior obliga a abstenerse."""
    class Inventor:
        def generate(self, question, chunks):
            return {"answer": "El contrato dura 99 años.",
                    "citations": [{"chunk_id": chunks[0]["chunk_id"], "evidence": "dura 99 años"}]}

    monkeypatch.setattr(ask, "generator", Inventor())
    r = preguntar(client, "user-a", "¿Cuál es la duración del contrato?")
    assert r.json() == ABSTENCION_COMPLETA


def test_R5_cita_a_chunk_no_entregado_se_convierte_en_abstencion(client, monkeypatch):
    class CitaAjena:
        def generate(self, question, chunks):
            return {"answer": "36 meses.",
                    "citations": [{"chunk_id": "chunk-003-v1-01", "evidence": "36 meses"}]}

    monkeypatch.setattr(ask, "generator", CitaAjena())
    r = preguntar(client, "user-a", "¿Cuál es la duración del contrato?")
    assert r.json() == ABSTENCION_COMPLETA


def test_10_2_cada_consulta_queda_registrada_con_su_evidencia(client, db_conn):
    preguntar(client, "user-b", "¿Cuál es el sueldo del gerente general?")
    row = db_conn.execute(
        """SELECT l.user_id, l.abstained, s.chunk_id
           FROM ask_log l JOIN ask_log_sources s ON s.ask_id = l.id
           ORDER BY l.id DESC LIMIT 1"""
    ).fetchone()
    assert row == {"user_id": "user-b", "abstained": False, "chunk_id": "chunk-004-v1-01"}


def test_5_2_validacion_de_question(client):
    for body in ({}, {"question": ""}, {"question": "a" * 501}, {"question": "x", "use_graph": "quizas"}):
        r = client.post("/api/v1/ask", json=body, headers=as_user("user-a"))
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_5_2_sin_header_devuelve_401(client):
    r = client.post("/api/v1/ask", json={"question": "¿Cuál es la duración del contrato?"})
    assert r.status_code == 401
