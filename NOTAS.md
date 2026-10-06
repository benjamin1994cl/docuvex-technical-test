# Notas: pendientes, riesgos y qué haría con más tiempo

## 1. Lo que no se implementó

| Punto | Prioridad en el enunciado | Cómo se haría | Riesgo de dejarlo pendiente |
|---|---|---|---|
| LLM real para redactar la respuesta | Opcional | Un generador nuevo que cumpla la interfaz `generate(question, chunks)` de `ask.py`. Recibe los mismos chunks autorizados y su salida pasa por `verified_sources`. Para tests, un modelo simulado determinista | Las respuestas son frases literales del documento, sin redacción ni síntesis de varios chunks |
| Extracción automática de entidades y relaciones | Opcional | Reglas o NER sobre cada chunk al ingresarlo, guardando `extraction_method = 'rule'` o `'llm'` y una `confidence` menor a 1. Las relaciones bajo un umbral quedan pendientes de revisión y no se muestran. Duplicados: resolver contra `entity_aliases` antes de crear un nodo | El grafo solo contiene lo declarado en `graph_seed` |
| Frontend | Opcional | Fuera del alcance | Ninguno para la evaluación |
| Row-Level Security en PostgreSQL | No se pide | Políticas sobre `documents`, `document_versions`, `chunks` y `graph_edges`, con la API conectada con un rol que no sea dueño de las tablas y el usuario fijado por transacción con `set_config` | Hoy la única barrera es el join en las consultas. Una consulta nueva que lo omita filtraría datos. Lo mitiga que todas reutilizan dos fragmentos SQL y que los tests del Anexo B revisan el cuerpo completo |
| Búsqueda híbrida (léxica más vectorial) | No se pide | Columna `embedding` con pgvector, modelo local incluido en la imagen, filtro por OU dentro de la misma consulta y fusión de rankings | No se reconocen sinónimos ni paráfrasis |
| Paginación de vecinos | No se pide | Cursor por (profundidad, identificador de relación) | Con más de 50 vecinos visibles la respuesta se corta sin avisar |

## 2. Riesgos conocidos de lo que sí se implementó

**Umbral de abstención.** El score mide cobertura de términos, no comprensión. Dos efectos:

- Un chunk puede cubrir los términos de la pregunta sin responderla. Para "¿Cuál es la duración del contrato con GPS Legal?", el chunk de comparecencia puntúa 0,625 y también supera el umbral de 0,6; gana el correcto con 0,75, pero el margen es pequeño.
- Una pregunta formulada con sinónimos se abstiene aunque la respuesta exista. Por ejemplo, "¿Cuál es el salario del máximo ejecutivo?" no encuentra el chunk del sueldo del gerente general. Es el error preferible: el enunciado dice que una respuesta sin evidencia es peor que una abstención.

**Datos derivados.** `documents.current_version_id` y `has_version_conflict` se calculan al cargar. Un flujo de ingesta real debe recalcularlos en la misma transacción en que se agrega una versión.

**Procedencia en versiones no vigentes.** Una relación del grafo cuya procedencia es un chunk de una versión antigua sigue siendo visible. Para el dataset no ocurre. En producción habría que decidir si las relaciones caducan con su versión.

**Nombre de entidades compartidas.** El `label` de una empresa compartida es el nombre declarado en el dataset, que no tiene procedencia. Un usuario de OU-002 ve "GPS Legal SpA" aunque su documento la nombre "GPS LEGAL S.p.A.". No revela documentos, pero en producción cada nombre debería tener procedencia y mostrarse solo el autorizado.

**Alias sin procedencia.** El dataset declara los alias de una entidad sin indicar de qué documento salen, y el caso A18 exige que user-a resuelva "GPS LEGAL S.p.A.", una grafía que solo aparece en doc-005 (OU-002). Por eso un alias declarado resuelve para cualquier usuario que ya vea la entidad, tanto en `GET /graph/nodes?name=` como al detectar menciones en `/ask`. Lo que se filtra es acotado: un usuario que ya ve la empresa puede confirmar que también se la conoce con otra grafía. No revela documentos, relaciones ni contenido, y una entidad no visible nunca se resuelve. En producción cada alias tendría procedencia y solo coincidirían los alias atestiguados por un documento autorizado o declarados en un catálogo global.

**Canal lateral de tiempo.** El 404 es idéntico en cuerpo para "no existe" y "no autorizado", y ambos casos ejecutan la misma consulta, pero no se midió si los tiempos de respuesta son indistinguibles.

**Detección de preguntas relacionales.** GraphRAG se activa con `use_graph: true` y una lista corta de raíces ("relacion", "vincul", "asoci", "conect"). Es simple y predecible, y no reconoce otras formulaciones.

**Identidad.** `X-User-Id` es una simulación pedida por el enunciado: cualquiera puede declararse cualquier usuario.

## 3. Qué cambiaría para producción

1. Autenticación real (OIDC o JWT firmado) y permisos sincronizados con el directorio de la organización.
2. Row-Level Security como segunda barrera, con un test que intente leer con un usuario sin alcance directamente en SQL.
3. Migraciones versionadas (Alembic) en lugar de un `schema.sql` idempotente.
4. Ingesta asíncrona de documentos: extracción de texto, división en chunks, indexado y actualización del grafo en una cola.
5. Trazas y métricas por etapa (OpenTelemetry), con los tramos descritos en el análisis de performance.
6. Búsqueda híbrida con evaluación sobre un conjunto de preguntas etiquetadas, para ajustar el umbral con datos y no a mano.
7. Límite de peticiones por usuario y auditoría de accesos al grafo.
8. Retención y control de acceso de `ask_log`, que guarda el texto de las preguntas.

## 4. Con más tiempo, en este orden

1. Row-Level Security.
2. Conjunto de evaluación de preguntas y calibración del umbral de abstención.
3. Generador con LLM detrás de la interfaz existente, con modelo simulado para tests.
4. Extracción de entidades por reglas con `confidence`.
