"""Extracción automática de entidades y relaciones por reglas (sección 9.3, opcional).

Dos niveles de confianza:
- Mención de una entidad ya conocida (nombre o alias): confianza alta, visible.
- Entidad descubierta por un patrón ("... SpA", "don ..."): confianza baja. Se
  guarda con su procedencia y con confirmed = false, y no se muestra hasta que
  alguien la revise. Volver a mencionarla no la confirma.

Duplicados: antes de crear nada se resuelve contra los alias existentes, y una
relación no se inserta si ya existe otra igual (la declarada en el seed prevalece).
"""
import logging
import re
from dataclasses import dataclass

from app.text import normalize_name

log = logging.getLogger("docuvex")

KNOWN_CONFIDENCE = 0.9
NEW_CONFIDENCE = 0.6

_CAP = r"[A-ZÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ]*"
_COMPANY = re.compile(rf"(?:{_CAP}\s+){{1,4}}(?:SpA\b|S\.p\.A\.|S\.A\.|Ltda\.?|Limitada\b)")
_NAME = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"
_PERSON = re.compile(rf"\b(?:don|doña)\s+({_NAME}(?:\s+{_NAME}){{1,2}})")
_REPRESENTS = re.compile(r"^,?\s+representad[ao] por (?:don|doña)\s+$")


@dataclass
class Mention:
    start: int
    end: int
    node_type: str            # 'Company' o 'Person'
    name: str                 # texto tal como aparece
    node_id: str | None       # None si la entidad no existía
    confidence: float


def find_mentions(text: str, aliases: list[dict]) -> list[Mention]:
    """Menciones de entidades en un texto. `aliases`: filas node_id, type, normalized, confirmed."""
    tokens = [(m.start(), m.end(), normalize_name(m.group())) for m in re.finditer(r"\S+", text)]
    tokens = [t for t in tokens if t[2]]
    mentions: list[Mention] = []

    def free(start: int, end: int) -> bool:
        return all(end <= m.start or start >= m.end for m in mentions)

    # 1) Entidades conocidas. Los alias más largos primero: "GPS Legal SpA" antes que "GPS Legal".
    for alias in sorted(aliases, key=lambda a: -len(a["normalized"].split())):
        words = alias["normalized"].split()
        for i in range(len(tokens) - len(words) + 1):
            window = tokens[i:i + len(words)]
            if [t[2] for t in window] == words and free(window[0][0], window[-1][1]):
                start, end = window[0][0], window[-1][1]
                # Una entidad aún no revisada no gana confianza por repetirse: si lo
                # hiciera, bastaría mencionarla dos veces para saltarse la revisión.
                confidence = KNOWN_CONFIDENCE if alias.get("confirmed", True) else NEW_CONFIDENCE
                mentions.append(Mention(start, end, alias["type"], text[start:end],
                                        alias["node_id"], confidence))

    # 2) Entidades nuevas por patrón, solo donde no hay ya una entidad conocida.
    for match in _COMPANY.finditer(text):
        if free(match.start(), match.end()):
            mentions.append(Mention(match.start(), match.end(), "Company",
                                    match.group().strip(), None, NEW_CONFIDENCE))
    for match in _PERSON.finditer(text):
        if free(match.start(1), match.end(1)):
            mentions.append(Mention(match.start(1), match.end(1), "Person",
                                    match.group(1), None, NEW_CONFIDENCE))
    return sorted(mentions, key=lambda m: m.start)


def find_representations(text: str, mentions: list[Mention]) -> list[tuple[Mention, Mention]]:
    """Pares (persona, empresa) unidos por "<empresa>, representada por don/doña <persona>"."""
    pairs = []
    for company, person in zip(mentions, mentions[1:]):
        if company.node_type == "Company" and person.node_type == "Person" \
                and _REPRESENTS.match(text[company.end:person.start]):
            pairs.append((person, company))
    return pairs


def extract_all(conn) -> dict:
    stats = {"edges": 0, "entities": 0}
    for row in conn.execute("SELECT id FROM documents ORDER BY id").fetchall():
        result = extract_document(conn, row["id"])
        stats["edges"] += result["edges"]
        stats["entities"] += result["entities"]
    log.info("extraccion por reglas relaciones_nuevas=%d entidades_nuevas=%d",
             stats["edges"], stats["entities"])
    return stats


def extract_document(conn, document_id: str) -> dict:
    """Extrae de los chunks de la versión vigente. Es idempotente."""
    stats = {"edges": 0, "entities": 0}
    chunks = conn.execute(
        """SELECT c.id, c.content FROM chunks c
           JOIN documents d ON d.current_version_id = c.version_id
           WHERE d.id = %s ORDER BY c.id""",
        (document_id,),
    ).fetchall()
    for chunk in chunks:
        aliases = conn.execute(
            """SELECT a.node_id, n.type, a.normalized, n.confirmed
               FROM entity_aliases a JOIN graph_nodes n ON n.id = a.node_id"""
        ).fetchall()
        mentions = find_mentions(chunk["content"], aliases)
        for mention in mentions:
            if mention.node_id is None:
                mention.node_id, created = _resolve_or_create(conn, mention)
                stats["entities"] += created
            stats["edges"] += _add_edge(conn, document_id, mention.node_id, "REFERENCES",
                                        document_id, chunk["id"], mention.confidence)
        for person, company in find_representations(chunk["content"], mentions):
            stats["edges"] += _add_edge(conn, person.node_id, company.node_id, "REPRESENTS",
                                        document_id, chunk["id"],
                                        min(person.confidence, company.confidence))
    return stats


def _resolve_or_create(conn, mention: Mention) -> tuple[str, int]:
    """Busca la entidad por nombre normalizado; si no existe, la crea como pendiente."""
    normalized = normalize_name(mention.name)
    existing = conn.execute(
        "SELECT node_id FROM entity_aliases WHERE normalized = %s ORDER BY node_id LIMIT 1",
        (normalized,),
    ).fetchone()
    if existing:
        return existing["node_id"], 0
    prefix = "ent-company-" if mention.node_type == "Company" else "ent-person-"
    node_id = prefix + normalized.replace(" ", "-")
    conn.execute(
        """INSERT INTO graph_nodes (id, type, label, confirmed) VALUES (%s, %s, %s, false)
           ON CONFLICT DO NOTHING""",
        (node_id, mention.node_type, mention.name),
    )
    conn.execute(
        """INSERT INTO entity_aliases (node_id, alias, normalized) VALUES (%s, %s, %s)
           ON CONFLICT DO NOTHING""",
        (node_id, mention.name, normalized),
    )
    return node_id, 1


def _add_edge(conn, from_id, to_id, relation, document_id, chunk_id, confidence) -> int:
    """Inserta la relación si no existe ya una igual. Devuelve 1 si la insertó."""
    return conn.execute(
        """INSERT INTO graph_edges
               (from_id, to_id, relation, source_document_id, source_chunk_id,
                extraction_method, confidence)
           SELECT %(from_id)s, %(to_id)s, %(relation)s, %(document_id)s, %(chunk_id)s,
                  'rule', %(confidence)s
           WHERE NOT EXISTS (
               SELECT 1 FROM graph_edges
               WHERE from_id = %(from_id)s AND to_id = %(to_id)s AND relation = %(relation)s)""",
        {"from_id": from_id, "to_id": to_id, "relation": relation,
         "document_id": document_id, "chunk_id": chunk_id, "confidence": confidence},
    ).rowcount
