"""Frontend opcional: una página estática que consume la API pública."""


def test_frontend_se_sirve_en_la_raiz(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "X-User-Id" in r.text and "/api/v1" in r.text


def test_frontend_no_depende_de_internet_ni_interpreta_html_de_la_api(client):
    html = client.get("/").text
    for externo in ("http://", "https://", "<link", "@import"):
        assert externo not in html, externo
    # Todo se inserta con textContent: una respuesta de la API no puede inyectar marcado.
    for peligroso in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert peligroso not in html, peligroso


def test_frontend_no_da_acceso_sin_identidad(client):
    """La página es pública, pero los datos siguen exigiendo X-User-Id."""
    assert client.post("/api/v1/search", json={"query": "contrato"}).status_code == 401
