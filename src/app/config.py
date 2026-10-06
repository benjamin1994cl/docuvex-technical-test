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


def answer_mode() -> str:
    """extractive (por defecto), llm-fake o llm. Ver app/llm.py."""
    return os.environ.get("ANSWER_MODE", "extractive").strip().lower()


def llm_model() -> str:
    return os.environ.get("LLM_MODEL", "claude-opus-5-5")


def auto_extract() -> bool:
    return os.environ.get("AUTO_EXTRACT", "true").strip().lower() in ("1", "true", "yes")
