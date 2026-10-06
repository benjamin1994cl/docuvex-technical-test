# Notas: pendientes, riesgos y qué haría con más tiempo

## 1. Estado

Todo lo obligatorio, lo recomendado y lo opcional del enunciado está implementado. Además se agregó Row-Level Security, que el enunciado no pide.

Lo que no se hizo:

| Punto | Cómo se haría | Riesgo de dejarlo pendiente |
|---|---|---|
| Búsqueda híbrida (léxica más vectorial) | Columna `embedding` con pgvector, modelo local incluido en la imagen, filtro por OU dentro de la misma consulta y fusión de rankings | No se reconocen sinónimos ni paráfrasis |
| Paginación de vecinos del grafo | Cursor por (profundidad, identificador de relación) | Con más de 50 vecinos visibles la respuesta se corta sin avisar |
| Flujo de revisión de entidades extraídas | Endpoint de administración para confirmar o descartar entidades con `confirmed = false` | Lo descubierto por patrón queda guardado e invisible indefinidamente |
| Evaluación de la búsqueda | Conjunto de preguntas etiquetadas para calibrar el umbral de abstención con datos | El umbral de 0,6 está ajustado a mano sobre el Anexo A |

## 2. Riesgos conocidos de lo implementado

**El modo `llm` no se probó contra el servicio real.** No había una clave de API disponible. Está probado hasta el borde: el SDK acepta la llamada, y una clave inválida produce un error 401 que se maneja y cae al camino extractivo. Todo lo demás (prompt, verificación, abstención, fallos) está probado con el modelo simulado. Antes de usarlo en serio hay que hacer una llamada real.

**Umbral de abstención.** El score mide cobertura de términos, no comprensión. Dos efectos:

- Un chunk puede cubrir los términos de la pregunta sin responderla. Para "¿Cuál es la duración del contrato con GPS Legal?", el chunk de comparecencia puntúa 0,625 y también supera el umbral de 0,6; gana el correcto con 0,75, pero el margen es pequeño.
- Una pregunta formulada con sinónimos se abstiene aunque la respuesta exista. Por ejemplo, "¿Cuál es el salario del máximo ejecutivo?" no encuentra el chunk del sueldo del gerente general. Es el error preferible: el enunciado dice que una respuesta sin evidencia es peor que una abstención.

**Verificación de respuestas del LLM.** `answer_supported` es léxica: comprueba cifras y vocabulario compartido. No detecta una cifra escrita en palabras ("treinta y seis meses"), una negación ("no se renovará") ni una inferencia errónea con las mismas palabras. Una verificación más fuerte usaría un segundo modelo o un clasificador de implicación, con su propio costo y latencia.

**Extracción por reglas.** Los patrones producen falsos positivos (una palabra con mayúscula al inicio de la oración se toma como parte del nombre) y no reconocen entidades sin sufijo societario ni tratamiento. Por eso lo descubierto no se muestra sin revisión. La mención de entidades conocidas es confiable, pero hereda el riesgo de los alias: un alias demasiado genérico marcaría menciones falsas.

**Row-Level Security.** Cubre documentos, versiones, chunks, relaciones y atributos. No cubre la visibilidad de entidades compartidas (G2), que sigue dependiendo de la consulta. La API se conecta como dueño de la base y cambia de rol por transacción; en producción se conectaría directamente con el rol restringido, para que no exista un momento con privilegios altos.

**Alias sin procedencia.** El dataset declara los alias de una entidad sin indicar de qué documento salen, y el caso A18 exige que user-a resuelva "GPS LEGAL S.p.A.", una grafía que solo aparece en doc-005 (OU-002). Por eso un alias declarado resuelve para cualquier usuario que ya vea la entidad, tanto en `GET /graph/nodes?name=` como al detectar menciones en `/ask`. Lo que se filtra es acotado: un usuario que ya ve la empresa puede confirmar que también se la conoce con otra grafía. No revela documentos, relaciones ni contenido, y una entidad no visible nunca se resuelve. En producción cada alias tendría procedencia y solo coincidirían los alias atestiguados por un documento autorizado o declarados en un catálogo global.

**Nombre de entidades compartidas.** El `label` de una empresa compartida es el nombre declarado en el dataset, que no tiene procedencia. Un usuario de OU-002 ve "GPS Legal SpA" aunque su documento la nombre "GPS LEGAL S.p.A.".

**Datos derivados.** `documents.current_version_id` y `has_version_conflict` se calculan al cargar. Un flujo de ingesta real debe recalcularlos en la misma transacción en que se agrega una versión.

**Procedencia en versiones no vigentes.** Una relación del grafo cuya procedencia es un chunk de una versión antigua sigue siendo visible. Para el dataset no ocurre.

**Canal lateral de tiempo.** El 404 es idéntico en cuerpo para "no existe" y "no autorizado", y ambos casos ejecutan la misma consulta, pero no se midió si los tiempos de respuesta son indistinguibles.

**Detección de preguntas relacionales.** GraphRAG se activa con `use_graph: true` y una lista corta de raíces ("relacion", "vincul", "asoci", "conect").

**Identidad.** `X-User-Id` es una simulación pedida por el enunciado: cualquiera puede declararse cualquier usuario. La página de demostración se apoya en eso.

## 3. Qué cambiaría para producción

1. Autenticación real (OIDC o JWT firmado) y permisos sincronizados con el directorio de la organización.
2. Conexión de la API con el rol restringido, sin pasar por el dueño de la base.
3. Migraciones versionadas (Alembic) en lugar de un `schema.sql` idempotente.
4. Ingesta asíncrona de documentos: extracción de texto, división en chunks, indexado, extracción de entidades y actualización del grafo en una cola.
5. Trazas y métricas por etapa (OpenTelemetry), con los tramos descritos en el análisis de performance.
6. Búsqueda híbrida con evaluación sobre un conjunto de preguntas etiquetadas.
7. Límite de peticiones por usuario, auditoría de accesos al grafo y cabeceras de seguridad en la página.
8. Retención y control de acceso de `ask_log`, que guarda el texto de las preguntas.
9. Para el LLM: límite de gasto, caché de respuestas por usuario y pregunta, y evaluación de alucinaciones antes de activarlo.

## 4. Con más tiempo, en este orden

1. Una llamada real al modo `llm` y un conjunto de evaluación para comparar extractivo contra LLM.
2. Calibración del umbral de abstención con preguntas etiquetadas.
3. Flujo de revisión de entidades extraídas.
4. Búsqueda híbrida.
