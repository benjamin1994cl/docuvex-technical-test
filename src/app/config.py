"""Configuración leída del entorno en cada llamada, para que los tests puedan cambiarla."""
import os


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL", "postgresql://docuvex:cambiar_en_local@db:5432/docuvex"
    )


def dataset_path() -> str:
    return os.environ.get("DATASET_PATH", "data/dataset.json")


def log_level() -> str:
    return os.environ.get("LOG_LEVEL", "INFO")
