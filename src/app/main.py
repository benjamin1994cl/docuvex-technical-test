"""Punto de entrada de la API."""
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

from app import config, db, seed
from app.errors import register_handlers
from app.routes import router

logging.basicConfig(level=config.log_level(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("docuvex")

SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")


@asynccontextmanager
async def lifespan(_: FastAPI):
    pool = db.init_pool(config.database_url())
    with pool.connection() as conn:
        conn.execute(SCHEMA_SQL)
        if not seed.is_seeded(conn):
            data = json.loads(Path(config.dataset_path()).read_text(encoding="utf-8"))
            seed.load_dataset(conn, data)
            log.info("dataset cargado documentos=%d", len(data["documents"]))
    yield
    db.close_pool()


app = FastAPI(title="Docuvex Challenge", lifespan=lifespan)
register_handlers(app)
app.include_router(router)


@app.middleware("http")
async def access_log(request: Request, call_next):
    # S6: solo IDs, ruta y tiempos. Nunca el cuerpo, la consulta ni el contenido.
    # El usuario se registra solo si fue validado; el encabezado crudo no se escribe.
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    log.info(
        "request id=%s user=%s method=%s path=%s status=%d ms=%.1f",
        request_id, getattr(request.state, "user_id", "-"), request.method,
        request.url.path, response.status_code, (time.perf_counter() - started) * 1000,
    )
    response.headers["X-Request-Id"] = request_id
    return response
