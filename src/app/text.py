"""Normalización de texto usada por la búsqueda y la resolución de entidades."""
import re
import unicodedata

# Palabras interrogativas: no aportan contenido y se quitan antes de buscar.
INTERROGATIVES = {
    "que", "cual", "cuales", "quien", "quienes", "como", "cuando", "donde",
    "cuanto", "cuanta", "cuantos", "cuantas",
}


def unaccent(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_name(text: str) -> str:
    """'GPS LEGAL S.p.A.' -> 'gps legal spa'. Base de la resolución de entidades."""
    flat = unaccent(text).lower().replace(".", "")
    return " ".join(re.findall(r"[a-z0-9]+", flat))


def content_words(question: str) -> str:
    """Quita signos e interrogativos; el resto lo analiza PostgreSQL en español."""
    tokens = re.findall(r"\w+", question.lower())
    return " ".join(t for t in tokens if unaccent(t) not in INTERROGATIVES)


def strip_extension(filename: str) -> str:
    """'Contrato GPS Legal.pdf' -> 'Contrato GPS Legal' (evita el lexema 'legal.pdf')."""
    return re.sub(r"\.[A-Za-z0-9]{1,5}$", "", filename)
