#!/usr/bin/env python3
"""Ejecuta los 19 casos del Anexo B contra una API en ejecución.

Uso: python3 scripts/verificar_anexo_b.py [http://localhost:8000]
Solo usa la biblioteca estándar. Termina con código 1 si algún caso falla.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/") + "/api/v1"
ABSTENCION = "No encontré evidencia suficiente en los documentos disponibles."
DURACION = {"query": "¿Cuál es la duración del contrato?"}
GPS = "/graph/nodes/ent-company-gps-legal/neighbors?depth=1"
SUELDO = {"question": "¿Cuál es el sueldo del gerente general?"}


def call(method, path, user=None, body=None):
    """Devuelve (status, texto del cuerpo, cuerpo como JSON o None)."""
    headers = {"Content-Type": "application/json"}
    if user:
        headers["X-User-Id"] = user
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status, text = response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        status, text = error.code, error.read().decode("utf-8")
    try:
        return status, text, json.loads(text)
    except ValueError:
        return status, text, None


def contiene(text, *esperados):
    return all(e in text for e in esperados)


def no_contiene(text, *prohibidos):
    return not any(p in text for p in prohibidos)


def abstencion_exacta(body):
    return body["answer"] == ABSTENCION and body["abstained"] is True and body["sources"] == []


def a01():
    s, t, _ = call("POST", "/search", "user-a", DURACION)
    return s == 200 and contiene(t, "chunk-001-v3-01") and no_contiene(t, "doc-003", "chunk-003-v1-01")


def a02():
    s, t, _ = call("POST", "/search", "user-b", DURACION)
    return s == 200 and contiene(t, "chunk-003-v1-01") and no_contiene(t, "doc-001")


def a03():
    s, _, b = call("POST", "/search", "user-c", DURACION)
    return s == 200 and b["results"] == []


def a04():
    return call("POST", "/search", None, DURACION)[0] == 401


def a05():
    s, t, _ = call("POST", "/search", "user-a",
                   {"query": "duración del contrato", "include_history": False})
    return s == 200 and no_contiene(t, "chunk-001-v1-01", "chunk-001-v2-01")


def a06():
    _, _, b = call("POST", "/ask", "user-a",
                   {"question": "¿Cuál es la duración del contrato con GPS Legal?"})
    fuentes = [x for x in b["sources"] if x["chunk_id"] == "chunk-001-v3-01"]
    original = "El contrato tendrá una duración de 24 meses contados desde el 1 de marzo de 2026."
    return (b["abstained"] is False and "24 meses" in b["answer"] and bool(fuentes)
            and bool(fuentes[0]["evidence"]) and fuentes[0]["evidence"] in original)


def a07():
    _, t, b = call("POST", "/ask", "user-a", SUELDO)
    return abstencion_exacta(b) and no_contiene(t, "doc-004", "Jorge Rivas", "9.500.000")


def a08():
    _, _, b = call("POST", "/ask", "user-b", SUELDO)
    return b["abstained"] is False and "chunk-004-v1-01" in [x["chunk_id"] for x in b["sources"]]


def a09():
    _, _, b = call("POST", "/ask", "user-a", {"question": "¿Cuál es la capital de Australia?"})
    return abstencion_exacta(b)


def a10():
    pregunta = {"question": "¿Cuál es el viático diario nacional?"}
    cuerpos = [call("POST", "/ask", "user-a", pregunta) for _ in range(3)]
    iguales = cuerpos[0][1] == cuerpos[1][1] == cuerpos[2][1]
    b = cuerpos[0][2]
    ambos = "30.000" in b["answer"] and "45.000" in b["answer"]
    return iguales and "VERSION_CONFLICT:doc-008" in b["warnings"] and not ambos


def a11():
    s, t, _ = call("GET", GPS, "user-a")
    return (s == 200 and contiene(t, "doc-001", "doc-002", "doc-007", "ent-person-maria-soto")
            and no_contiene(t, "doc-005"))


def a12():
    s, t, _ = call("GET", GPS, "user-b")
    return (s == 200 and contiene(t, "doc-005")
            and no_contiene(t, "doc-001", "doc-002", "doc-007", "ent-person-maria-soto"))


def a13():
    s, t, _ = call("GET", "/graph/nodes/doc-001/neighbors?depth=2", "user-a")
    return s == 200 and contiene(t, "doc-002") and no_contiene(t, "doc-005", "doc-006")


def a14():
    s14, t14, _ = call("GET", "/graph/nodes/doc-005/neighbors", "user-a")
    _, t15, _ = call("GET", "/graph/nodes/doc-999/neighbors", "user-a")
    return s14 == 404 and t14 == t15


def a15():
    return call("GET", "/graph/nodes/doc-999/neighbors", "user-a")[0] == 404


def a16():
    return call("GET", "/graph/nodes/ent-person-jorge-rivas/neighbors", "user-a")[0] == 404


def a17():
    _, t, b = call("POST", "/ask", "user-a", {
        "question": "¿Qué documentos están relacionados con el contrato de GPS Legal?",
        "use_graph": True,
    })
    caminos = bool(b["graph_context"]) and all(
        x["path"] and x["provenance"] for x in b["graph_context"])
    return "doc-002" in b["answer"] and caminos and no_contiene(t, "doc-005", "doc-006")


def a18():
    name = urllib.parse.quote("GPS LEGAL S.p.A.")
    s, _, b = call("GET", f"/graph/nodes?name={name}", "user-a")
    return s == 200 and [n["id"] for n in b["nodes"]] == ["ent-company-gps-legal"]


def a19():
    for body in ({"query": ""}, {"query": "x", "limit": 50}):
        s, _, b = call("POST", "/search", "user-a", body)
        if s != 400 or set(b.get("error", {})) != {"code", "message"}:
            return False
    return True


CASOS = [a01, a02, a03, a04, a05, a06, a07, a08, a09, a10,
         a11, a12, a13, a14, a15, a16, a17, a18, a19]


def main():
    fallidos = 0
    for caso in CASOS:
        try:
            ok = caso()
        except Exception as error:  # un caso roto no debe ocultar los demás
            ok = False
            print(f"{caso.__name__.upper()}  ERROR  {type(error).__name__}: {error}")
            fallidos += 1
            continue
        print(f"{caso.__name__.upper()}  {'OK' if ok else 'FALLA'}")
        fallidos += 0 if ok else 1
    print(f"\n{len(CASOS) - fallidos} de {len(CASOS)} casos correctos")
    sys.exit(1 if fallidos else 0)


if __name__ == "__main__":
    main()
