"""S6: los logs llevan IDs, no contenido de documentos ni datos personales."""
import logging

from conftest import as_user


def test_S6_los_logs_no_registran_contenido_ni_preguntas(client, caplog):
    caplog.set_level(logging.DEBUG)
    client.post("/api/v1/ask", json={"question": "¿Cuál es el sueldo del gerente general?"},
                headers=as_user("user-b"))
    client.post("/api/v1/search", json={"query": "sueldo gerente general"}, headers=as_user("user-b"))
    client.get("/api/v1/graph/nodes/ent-person-jorge-rivas/neighbors", headers=as_user("user-b"))
    texto = "\n".join(record.getMessage() for record in caplog.records)
    assert "chunk-004-v1-01" in texto  # sí hay trazabilidad por ID
    for prohibido in ("9.500.000", "Jorge Rivas", "sueldo", "gerente", "Gerente General"):
        assert prohibido not in texto


def test_S6_un_usuario_no_validado_no_llega_al_log(client, caplog):
    caplog.set_level(logging.DEBUG)
    client.post("/api/v1/search", json={"query": "contrato"},
                headers={"X-User-Id": "intruso\r\nlinea-falsa"})
    texto = "\n".join(record.getMessage() for record in caplog.records)
    assert "intruso" not in texto and "linea-falsa" not in texto
