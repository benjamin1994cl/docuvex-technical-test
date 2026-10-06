"""Sección 4 (identidad) y 5.5 (formato de error)."""
from conftest import as_user

QUERY = {"query": "¿Cuál es la duración del contrato?"}


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == code


def test_T05_sin_header_devuelve_401(client):
    assert_error(client.post("/api/v1/search", json=QUERY), 401, "UNAUTHORIZED")


def test_T05_usuario_inexistente_devuelve_401(client):
    r = client.post("/api/v1/search", json=QUERY, headers=as_user("user-zzz"))
    assert_error(r, 401, "UNAUTHORIZED")


def test_T05_sin_header_y_usuario_inexistente_responden_igual(client):
    sin_header = client.post("/api/v1/search", json=QUERY)
    inexistente = client.post("/api/v1/search", json=QUERY, headers=as_user("user-zzz"))
    assert sin_header.content == inexistente.content


def test_T04_usuario_sin_ou_recibe_200_y_lista_vacia(client):
    r = client.post("/api/v1/search", json=QUERY, headers=as_user("user-c"))
    assert r.status_code == 200
    assert r.json() == {"results": []}


def test_5_1_query_vacia_devuelve_400(client):
    r = client.post("/api/v1/search", json={"query": ""}, headers=as_user("user-a"))
    assert_error(r, 400, "VALIDATION_ERROR")


def test_5_1_query_solo_espacios_devuelve_400(client):
    r = client.post("/api/v1/search", json={"query": "   "}, headers=as_user("user-a"))
    assert_error(r, 400, "VALIDATION_ERROR")


def test_5_1_query_de_501_caracteres_devuelve_400(client):
    r = client.post("/api/v1/search", json={"query": "a" * 501}, headers=as_user("user-a"))
    assert_error(r, 400, "VALIDATION_ERROR")


def test_5_1_limit_fuera_de_rango_devuelve_400(client):
    for limit in (0, 21, 50):
        r = client.post("/api/v1/search", json={"query": "x", "limit": limit},
                        headers=as_user("user-a"))
        assert_error(r, 400, "VALIDATION_ERROR")


def test_5_5_json_malformado_devuelve_400(client):
    r = client.post("/api/v1/search", content=b"{no es json",
                    headers={**as_user("user-a"), "Content-Type": "application/json"})
    assert_error(r, 400, "VALIDATION_ERROR")


def test_5_5_ruta_inexistente_devuelve_404_con_formato(client):
    assert_error(client.get("/api/v1/no-existe", headers=as_user("user-a")), 404, "NOT_FOUND")


def test_5_5_error_interno_no_expone_detalles(client, monkeypatch):
    """Un fallo inesperado responde 500 genérico, sin traza ni mensaje interno."""
    from fastapi.testclient import TestClient

    from app import repo_search
    from app.main import app

    def boom(*args, **kwargs):
        raise RuntimeError("detalle interno secreto en tabla chunks")

    monkeypatch.setattr(repo_search, "search_chunks", boom)
    # Sin "with": reutiliza el pool ya abierto por la fixture client.
    failing = TestClient(app, raise_server_exceptions=False)
    r = failing.post("/api/v1/search", json=QUERY, headers=as_user("user-a"))
    assert_error(r, 500, "INTERNAL_ERROR")
    assert "secreto" not in r.text and "Traceback" not in r.text
