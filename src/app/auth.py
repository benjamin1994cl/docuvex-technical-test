"""Identidad simulada: el usuario llega en X-User-Id y su alcance se resuelve en el servidor."""
from fastapi import Depends, Header, Request

from app.db import get_conn
from app.errors import unauthorized


def current_user(
    request: Request,
    x_user_id: str | None = Header(default=None),
    conn=Depends(get_conn),
) -> str:
    """Devuelve el user_id si existe. Nunca se aceptan OU enviadas por el cliente."""
    if not x_user_id:
        raise unauthorized()
    row = conn.execute("SELECT id FROM users WHERE id = %s", (x_user_id,)).fetchone()
    if row is None:
        raise unauthorized()
    request.state.user_id = row["id"]  # para el log de acceso: solo IDs validados
    # Segunda barrera (Row-Level Security): el resto del request corre con un rol
    # restringido y con el usuario fijado. LOCAL: se revierte al cerrar la transacción,
    # así la conexión vuelve limpia al pool.
    conn.execute("SELECT set_config('app.user_id', %s, true)", (row["id"],))
    conn.execute("SET LOCAL ROLE docuvex_app")
    return row["id"]
