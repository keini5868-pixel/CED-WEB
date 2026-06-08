# CED — Cerebro híbrido premium

## Visión

CED responde **rápido** con conocimiento estable (cerebro interno) e **investiga** solo cuando el dato cambia en el tiempo o el usuario pide profundidad (web + sistema avanzado).

## Capas (nada se elimina)

| Capa | Cuándo | Motor actual |
|------|--------|--------------|
| Memoria usuario | Preferencias, notas | `cognitive_memories` |
| Cerebro interno | Conceptos estables, 40+ ramas | `internal_knowledge` + seed |
| Web | Clima, noticias, precios, hoy | Tavily + Gemini grounded |
| Sistema avanzado | Estrategia, análisis profundo | Gemini Flash (`consultar_sistema_avanzado`) |
| Herramientas | Meta, prospección, cámara | Sin cambios |

## Ramas del conocimiento

Definidas en `apps/api/app/domain/knowledge_domains.py` — negocios, marketing, IA, medicina, derecho, etc.

Contenido inicial: `apps/api/data/knowledge_seed.json` (20 artículos curados).

Expansión en Supabase: migración `009_internal_knowledge.sql` → tabla `internal_knowledge_articles`.

## API

- `POST /v1/cognitive/route` — clasifica y enriquece mensaje
- `GET /v1/cognitive/domains` — catálogo de ramas
- `GET /v1/cognitive/search?q=` — búsqueda en cerebro interno

## Integración actual (v1)

- **Chat texto:** router antes de Claude; inyecta contexto interno/web/memoria
- **Voz:** memoria + política híbrida en token Live; regex cliente sigue activo (v2 unificará a `/cognitive/route`)

## Roadmap para hacerlo “grande”

### Fase 2 — Ingesta masiva
- Script admin: importar Wikipedia/Wikidata **curado por rama** (no dump crudo)
- Embeddings pgvector + búsqueda semántica
- Panel admin: subir PDFs, URLs, notas por dominio

### Fase 3 — Router único en voz
- Cliente voz llama `/cognitive/route` en transcript final
- Menos regex duplicados TS/Python

### Fase 4 — Validación cruzada
- Respuesta interna + muestra web si confianza < umbral
- Coherencia multi-fuente antes de hablar

## Migración requerida

Ejecutar en Supabase SQL Editor:

```
apps/api/migrations/009_internal_knowledge.sql
```

Luego opcional: insertar artículos bulk desde seed o pipeline propio.
