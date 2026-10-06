"""Memoria Grafo: vecinos, visibilidad (G1 a G7), resolución de entidades y /documents."""
from conftest import as_user

GPS = "ent-company-gps-legal"


def vecinos(client, user, node_id, **params):
    return client.get(f"/api/v1/graph/nodes/{node_id}/neighbors", params=params, headers=as_user(user))


def ids(response):
    return {n["node"]["id"] for n in response.json()["neighbors"]}


def test_5_3_formato_de_vecinos_con_camino_y_procedencia_G5(client):
    body = vecinos(client, "user-a", "doc-001").json()
    assert body["node"] == {"id": "doc-001", "type": "Document",
                            "label": "Contrato Servicios GPS Legal.pdf"}
    gps = next(n for n in body["neighbors"] if n["node"]["id"] == GPS)
    assert gps == {
        "node": {"id": GPS, "type": "Company", "label": "GPS Legal SpA"},
        "path": [{"from": "doc-001", "relation": "REFERENCES", "to": GPS}],
        "provenance": [{"document_id": "doc-001", "chunk_id": "chunk-001-v3-02"}],
    }


def test_G5_cada_vecino_tiene_un_paso_de_procedencia_por_relacion(client):
    for neighbor in vecinos(client, "user-a", "doc-001", depth=2).json()["neighbors"]:
        assert 1 <= len(neighbor["path"]) <= 2
        assert len(neighbor["provenance"]) == len(neighbor["path"])
        assert all(p["document_id"] for p in neighbor["provenance"])


def test_G2_G3_T11_entidad_compartida_user_a_no_ve_documentos_de_ou_002(client):
    r = vecinos(client, "user-a", GPS, depth=1)
    assert r.status_code == 200
    assert {"doc-001", "doc-002", "doc-007", "ent-person-maria-soto"} <= ids(r)
    assert "doc-005" not in r.text


def test_G2_G3_T11_entidad_compartida_user_b_no_ve_documentos_ni_personas_ajenas(client):
    r = vecinos(client, "user-b", GPS, depth=1)
    assert r.status_code == 200
    assert ids(r) == {"doc-005"}
    for prohibido in ("doc-001", "doc-002", "doc-007", "ent-person-maria-soto", "María Soto"):
        assert prohibido not in r.text


def test_G3_relacion_con_procedencia_no_autorizada_no_aparece(client):
    """REVIEWS (doc-005 -> doc-001) proviene de doc-005: user-a ve doc-001, pero no esa relación."""
    r = vecinos(client, "user-a", "doc-001", depth=2)
    assert "REVIEWS" not in r.text and "LINKS" not in r.text
    assert "chunk-005" not in r.text


def test_G4_T12_sin_puentes_doc_006_no_aparece_a_traves_de_doc_005(client):
    r = vecinos(client, "user-a", "doc-001", depth=2)
    assert r.status_code == 200
    assert "doc-002" in ids(r)
    assert "doc-005" not in r.text and "doc-006" not in r.text


def test_G4_doc_006_es_visible_por_si_mismo_pero_no_llega_a_doc_001(client):
    r = vecinos(client, "user-a", "doc-006", depth=2)
    assert r.status_code == 200
    assert "ent-company-rastreo-andino" in ids(r)
    assert "doc-005" not in r.text and "doc-001" not in r.text


def test_S5_T13_nodo_no_autorizado_404_identico_a_inexistente(client):
    no_autorizado = vecinos(client, "user-a", "doc-005")
    inexistente = vecinos(client, "user-a", "doc-999")
    assert no_autorizado.status_code == inexistente.status_code == 404
    assert no_autorizado.content == inexistente.content
    assert no_autorizado.json() == {"error": {"code": "NOT_FOUND", "message": "Recurso no encontrado."}}


def test_G2_entidad_sin_documento_autorizado_que_la_referencie_es_404(client):
    oculta = vecinos(client, "user-a", "ent-person-jorge-rivas")
    inexistente = vecinos(client, "user-a", "ent-person-nadie")
    assert oculta.status_code == 404
    assert oculta.content == inexistente.content


def test_G1_versiones_y_ou_ajenas_son_404(client):
    for node in ("doc-005@v1", "OU-002", "doc-003"):
        assert vecinos(client, "user-a", node).status_code == 404
    assert vecinos(client, "user-b", "OU-001").status_code == 404


def test_G2_atributos_solo_con_procedencia_autorizada(client):
    body = vecinos(client, "user-b", "ent-person-jorge-rivas").json()
    assert body["node"]["attributes"] == [{"key": "cargo", "value": "Gerente General"}]
    assert ids(vecinos(client, "user-b", "ent-person-jorge-rivas")) == {"doc-004"}


def test_G6_la_respuesta_no_incluye_conteos_ni_grados(client):
    body = vecinos(client, "user-a", GPS).json()
    assert set(body) == {"node", "neighbors"}
    assert all(set(n) == {"node", "path", "provenance"} for n in body["neighbors"])
    # La empresa tiene 5 relaciones en total; user-a ve 4 y nada delata la quinta.
    assert len(body["neighbors"]) == 4


def test_G7_tolera_ciclos_sin_repetir_nodos(client):
    """doc-001, doc-002 y GPS Legal forman un ciclo."""
    body = vecinos(client, "user-a", "doc-001", depth=2).json()
    found = [n["node"]["id"] for n in body["neighbors"]]
    assert len(found) == len(set(found))
    assert "doc-001" not in found


def test_G7_profundidad_fuera_de_rango_devuelve_400(client):
    for depth in (0, 3, "abc"):
        r = vecinos(client, "user-a", "doc-001", depth=depth)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_G7_maximo_de_nodos_devueltos(client, monkeypatch):
    from app import graph
    monkeypatch.setattr(graph, "MAX_NODES", 2)
    assert len(vecinos(client, "user-a", "doc-001", depth=2).json()["neighbors"]) == 2


def test_5_3_filtro_por_tipo_de_relacion(client):
    r = vecinos(client, "user-a", "doc-001", relation="RELATED_TO")
    assert ids(r) == {"doc-002"}
    assert r.json()["neighbors"][0]["path"] == [
        {"from": "doc-002", "relation": "RELATED_TO", "to": "doc-001", "kind": "ANNEX_OF"}
    ]
    assert vecinos(client, "user-a", "doc-001", relation="NO_EXISTE").json()["neighbors"] == []


def test_5_3_profundidad_2_alcanza_doc_007_a_traves_de_la_empresa(client):
    body = vecinos(client, "user-a", "doc-001", depth=2, relation="REFERENCES").json()
    doc7 = next(n for n in body["neighbors"] if n["node"]["id"] == "doc-007")
    assert doc7["path"] == [
        {"from": "doc-001", "relation": "REFERENCES", "to": GPS},
        {"from": "doc-007", "relation": "REFERENCES", "to": GPS},
    ]
    assert doc7["provenance"] == [
        {"document_id": "doc-001", "chunk_id": "chunk-001-v3-02"},
        {"document_id": "doc-007", "chunk_id": "chunk-007-v1-01"},
    ]


def test_seccion4_grafo_sin_header_401_y_usuario_sin_ou_404(client):
    assert client.get(f"/api/v1/graph/nodes/{GPS}/neighbors").status_code == 401
    assert vecinos(client, "user-c", GPS).status_code == 404
    assert vecinos(client, "user-c", "doc-001").status_code == 404


def test_9_4_alias_resuelven_al_mismo_nodo(client):
    for name in ("GPS LEGAL S.p.A.", "GPS Legal", "GPS Legal SpA", "gps legal spa", "  Gps  Legal "):
        r = client.get("/api/v1/graph/nodes", params={"name": name}, headers=as_user("user-a"))
        assert r.status_code == 200
        assert r.json() == {"nodes": [{"id": GPS, "type": "Company", "label": "GPS Legal SpA"}]}


def test_9_4_no_fusiona_nombres_parecidos(client):
    for name in ("GPS", "GPS Legal Chile SpA", "Legal"):
        r = client.get("/api/v1/graph/nodes", params={"name": name}, headers=as_user("user-a"))
        assert r.json() == {"nodes": []}


def test_9_4_G2_entidad_no_visible_no_se_resuelve_por_nombre(client):
    r = client.get("/api/v1/graph/nodes", params={"name": "Jorge Rivas"}, headers=as_user("user-a"))
    assert r.json() == {"nodes": []}
    r = client.get("/api/v1/graph/nodes", params={"name": "Jorge Rivas"}, headers=as_user("user-b"))
    assert [n["id"] for n in r.json()["nodes"]] == ["ent-person-jorge-rivas"]


def test_5_4_metadatos_de_documento(client):
    r = client.get("/api/v1/documents/doc-001", headers=as_user("user-a"))
    assert r.status_code == 200
    body = r.json()
    assert body["document_id"] == "doc-001"
    assert body["organization_unit"] == "OU-001"
    assert body["current_version"] == 3 and body["version_conflict"] is False
    assert [v["version"] for v in body["versions"]] == [1, 2, 3]
    assert [v["is_current"] for v in body["versions"]] == [False, False, True]


def test_5_4_documento_con_conflicto_informa_la_version_elegida(client):
    body = client.get("/api/v1/documents/doc-008", headers=as_user("user-a")).json()
    assert body["current_version"] == 2 and body["version_conflict"] is True
    assert [v["is_current"] for v in body["versions"]] == [False, True]
    assert [v["declared_current"] for v in body["versions"]] == [True, True]


def test_5_4_S5_documento_no_autorizado_404_identico_a_inexistente(client):
    no_autorizado = client.get("/api/v1/documents/doc-004", headers=as_user("user-a"))
    inexistente = client.get("/api/v1/documents/doc-999", headers=as_user("user-a"))
    assert no_autorizado.status_code == inexistente.status_code == 404
    assert no_autorizado.content == inexistente.content
