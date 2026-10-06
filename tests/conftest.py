"""Los tests corren contra una base de datos propia (docuvex_test) en el PostgreSQL de Compose."""
import json
import os
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

BASE_URL = os.environ.get("DATABASE_URL", "postgresql://docuvex:cambiar_en_local@db:5432/docuvex")
TEST_DB = "docuvex_test"
TEST_URL = BASE_URL.rsplit("/", 1)[0] + "/" + TEST_DB

ABSTENTION = "No encontré evidencia suficiente en los documentos disponibles."


def _reset_database():
    with psycopg.connect(BASE_URL, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
        if not exists:
            conn.execute(f"CREATE DATABASE {TEST_DB}")
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")


@pytest.fixture(scope="session")
def client():
    _reset_database()
    os.environ["DATABASE_URL"] = TEST_URL
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_conn(client):
    with psycopg.connect(TEST_URL, row_factory=dict_row, autocommit=True) as conn:
        yield conn


@pytest.fixture(scope="session")
def dataset():
    return json.loads(Path("data/dataset.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def chunk_content(dataset):
    """chunk_id -> content, tal como viene en el Anexo A."""
    return {
        c["chunk_id"]: c["content"]
        for d in dataset["documents"] for v in d["versions"] for c in v["chunks"]
    }


def as_user(user_id: str) -> dict:
    return {"X-User-Id": user_id}
