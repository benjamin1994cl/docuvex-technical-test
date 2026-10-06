"""Pool de conexiones a PostgreSQL."""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def init_pool(url: str) -> ConnectionPool:
    global _pool
    _pool = ConnectionPool(
        url, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=True
    )
    _pool.wait(timeout=30)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_conn():
    """Dependencia de FastAPI: una conexión por request, con commit al terminar."""
    with _pool.connection() as conn:
        yield conn
