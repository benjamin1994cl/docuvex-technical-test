"""Carga del dataset del Anexo A: tablas documentales y Memoria Grafo."""
from app.text import normalize_name, strip_extension
from app.versions import resolve_current


def is_seeded(conn) -> bool:
    return conn.execute("SELECT 1 FROM organization_units LIMIT 1").fetchone() is not None


def load_dataset(conn, data: dict) -> None:
    for ou in data["organization_units"]:
        conn.execute(
            "INSERT INTO organization_units (id, name) VALUES (%s, %s)",
            (ou["id"], ou["name"]),
        )
        _node(conn, ou["id"], "OrganizationUnit", ou["name"], ou_id=ou["id"])

    for user in data["users"]:
        conn.execute(
            "INSERT INTO users (id, name) VALUES (%s, %s)", (user["id"], user["name"])
        )
        for ou_id in user["organization_units"]:
            conn.execute(
                "INSERT INTO user_organization_units (user_id, ou_id) VALUES (%s, %s)",
                (user["id"], ou_id),
            )

    load_documents(conn, data["documents"])

    seed = data.get("graph_seed", {})
    for entity in seed.get("entities", []):
        _load_entity(conn, entity)
    for rel in seed.get("relations", []):
        _edge(
            conn, rel["from"], rel["to"], rel["relation"],
            source_document_id=rel["source_document_id"],
            source_chunk_id=rel.get("source_chunk_id"),
            kind=rel.get("kind"),
        )


def load_documents(conn, documents: list[dict]) -> None:
    """Inserta documentos, versiones y chunks, y sus nodos y relaciones derivadas."""
    for doc in documents:
        doc_id = doc["document_id"]
        current, conflict = resolve_current(doc["versions"])
        conn.execute(
            """INSERT INTO documents (id, name, ou_id, current_version_id, has_version_conflict)
               VALUES (%s, %s, %s, %s, %s)""",
            (doc_id, doc["name"], doc["organization_unit"], _version_id(doc_id, current), conflict),
        )
        _node(conn, doc_id, "Document", doc["name"], document_id=doc_id)
        _edge(conn, doc_id, doc["organization_unit"], "BELONGS_TO", source_document_id=doc_id)

        title = strip_extension(doc["name"])
        previous = None
        for version in sorted(doc["versions"], key=lambda v: v["version"]):
            version_id = _version_id(doc_id, version["version"])
            conn.execute(
                """INSERT INTO document_versions (id, document_id, version, is_current, effective_date)
                   VALUES (%s, %s, %s, %s, %s)""",
                (version_id, doc_id, version["version"], version["is_current"],
                 version["effective_date"]),
            )
            _node(conn, version_id, "Version", f"{doc['name']} v{version['version']}",
                  document_id=doc_id)
            _edge(conn, doc_id, version_id, "HAS_VERSION", source_document_id=doc_id)
            if previous is not None:
                _edge(conn, version_id, previous, "SUPERSEDES", source_document_id=doc_id)
            previous = version_id

            for chunk in version["chunks"]:
                conn.execute(
                    """INSERT INTO chunks
                           (id, version_id, document_id, page, bbox, content,
                            content_tsv, title_tsv, tsv)
                       VALUES
                           (%(id)s, %(version_id)s, %(document_id)s, %(page)s,
                            %(bbox)s::integer[], %(content)s::text,
                            to_tsvector('spanish'::regconfig, %(content)s::text),
                            to_tsvector('spanish'::regconfig, %(title)s::text),
                            setweight(to_tsvector('spanish'::regconfig, %(content)s::text), 'A')
                              || setweight(to_tsvector('spanish'::regconfig, %(title)s::text), 'B'))""",
                    {
                        "id": chunk["chunk_id"], "version_id": version_id,
                        "document_id": doc_id, "page": chunk["page"],
                        "bbox": chunk["bbox"], "content": chunk["content"], "title": title,
                    },
                )


def _version_id(document_id: str, version: int) -> str:
    return f"{document_id}@v{version}"


def _load_entity(conn, entity: dict) -> None:
    _node(conn, entity["id"], entity["type"], entity["name"])
    names = {normalize_name(n): n for n in [entity["name"], *entity.get("aliases", [])]}
    for normalized, alias in names.items():
        conn.execute(
            "INSERT INTO entity_aliases (node_id, alias, normalized) VALUES (%s, %s, %s)",
            (entity["id"], alias, normalized),
        )
    for attr in entity.get("attributes", []):
        conn.execute(
            """INSERT INTO entity_attributes
                   (node_id, key, value, source_document_id, source_chunk_id)
               VALUES (%s, %s, %s, %s, %s)""",
            (entity["id"], attr["key"], attr["value"],
             attr["source_document_id"], attr.get("source_chunk_id")),
        )


def _node(conn, node_id, node_type, label, document_id=None, ou_id=None) -> None:
    conn.execute(
        "INSERT INTO graph_nodes (id, type, label, document_id, ou_id) VALUES (%s, %s, %s, %s, %s)",
        (node_id, node_type, label, document_id, ou_id),
    )


def _edge(conn, from_id, to_id, relation, source_document_id,
          source_chunk_id=None, kind=None) -> None:
    conn.execute(
        """INSERT INTO graph_edges
               (from_id, to_id, relation, kind, source_document_id, source_chunk_id,
                extraction_method, confidence)
           VALUES (%s, %s, %s, %s, %s, %s, 'seed', 1.0)""",
        (from_id, to_id, relation, kind, source_document_id, source_chunk_id),
    )
