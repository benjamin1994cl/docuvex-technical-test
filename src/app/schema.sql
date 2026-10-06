-- Esquema de Docuvex Challenge. Se aplica al iniciar la API (idempotente).

CREATE TABLE IF NOT EXISTS organization_units (
    id   text PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id   text PRIMARY KEY,
    name text NOT NULL
);

-- Permisos: qué OU puede ver cada usuario. Toda consulta de lectura hace join aquí.
CREATE TABLE IF NOT EXISTS user_organization_units (
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ou_id   text NOT NULL REFERENCES organization_units(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, ou_id)
);

CREATE TABLE IF NOT EXISTS documents (
    id                   text PRIMARY KEY,
    name                 text NOT NULL,
    ou_id                text NOT NULL REFERENCES organization_units(id),
    -- Derivados al cargar con la regla de versión vigente (app/versions.py).
    current_version_id   text NOT NULL,
    has_version_conflict boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS documents_ou_idx ON documents (ou_id);

CREATE TABLE IF NOT EXISTS document_versions (
    id             text PRIMARY KEY,            -- 'doc-001@v3'
    document_id    text NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version        integer NOT NULL,
    is_current     boolean NOT NULL,            -- marca declarada en el origen
    effective_date date NOT NULL,
    UNIQUE (document_id, version)
);

CREATE TABLE IF NOT EXISTS chunks (
    id          text PRIMARY KEY,
    version_id  text NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    document_id text NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page        integer NOT NULL,
    bbox        integer[] NOT NULL,
    content     text NOT NULL,
    content_tsv tsvector NOT NULL,              -- lexemas del contenido
    title_tsv   tsvector NOT NULL,              -- lexemas del nombre del documento
    tsv         tsvector NOT NULL               -- ambos, para recuperar candidatos
);
CREATE INDEX IF NOT EXISTS chunks_version_idx ON chunks (version_id);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);

-- Memoria Grafo -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS graph_nodes (
    id          text PRIMARY KEY,
    type        text NOT NULL CHECK (type IN
                    ('Document', 'Version', 'OrganizationUnit', 'Company', 'Person')),
    label       text NOT NULL,
    document_id text REFERENCES documents(id) ON DELETE CASCADE,       -- Document y Version
    ou_id       text REFERENCES organization_units(id) ON DELETE CASCADE -- OrganizationUnit
);

CREATE TABLE IF NOT EXISTS entity_aliases (
    node_id    text NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    alias      text NOT NULL,
    normalized text NOT NULL,
    PRIMARY KEY (node_id, normalized)
);
CREATE INDEX IF NOT EXISTS entity_aliases_normalized_idx ON entity_aliases (normalized);

CREATE TABLE IF NOT EXISTS entity_attributes (
    node_id            text NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    key                text NOT NULL,
    value              text NOT NULL,
    source_document_id text NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id    text
);
CREATE INDEX IF NOT EXISTS entity_attributes_node_idx ON entity_attributes (node_id);

CREATE TABLE IF NOT EXISTS graph_edges (
    id                 serial PRIMARY KEY,
    from_id            text NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    to_id              text NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
    relation           text NOT NULL CHECK (relation IN
                           ('BELONGS_TO', 'HAS_VERSION', 'SUPERSEDES',
                            'REFERENCES', 'RELATED_TO', 'REPRESENTS')),
    kind               text,
    -- Procedencia: de qué documento y chunk salió la relación.
    source_document_id text NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id    text,
    extraction_method  text NOT NULL DEFAULT 'seed' CHECK (extraction_method IN
                           ('seed', 'rule', 'llm', 'manual')),
    confidence         real NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS graph_edges_from_idx ON graph_edges (from_id);
CREATE INDEX IF NOT EXISTS graph_edges_to_idx ON graph_edges (to_id, relation);
CREATE INDEX IF NOT EXISTS graph_edges_source_idx ON graph_edges (source_document_id);

-- Registro de consultas /ask y la evidencia que originó cada respuesta -------

CREATE TABLE IF NOT EXISTS ask_log (
    id         bigserial PRIMARY KEY,
    user_id    text NOT NULL,
    question   text NOT NULL,
    abstained  boolean NOT NULL,
    warnings   text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ask_log_sources (
    ask_id   bigint NOT NULL REFERENCES ask_log(id) ON DELETE CASCADE,
    position integer NOT NULL,
    chunk_id text NOT NULL,
    PRIMARY KEY (ask_id, position)
);
