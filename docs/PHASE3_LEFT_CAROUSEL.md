# Fase 3 — Panel izquierdo: carrusel 3D HUD animado

**Estado:** Planificado — **no bloquea Fase 2B**  
**Inicio:** Cuando Keini confirme validación local de 2B (MIC + voz + USAGE subiendo)  
**Duración estimada:** 3–4 semanas (MVP visual + datos mock: ~1,5–2 semanas)

---

## Confirmaciones de producto (aprobadas)

| Tema | Decisión |
|------|----------|
| Prioridad | Terminar **Fase 2B** con calidad antes de este carrusel |
| Tiempo | 3–4 semanas aceptado para implementación completa |
| APIs | Listadas abajo; conexión **una por una** tras MVP mock |
| Riesgos | Aceptados; mitigaciones documentadas |
| Cuadro **SYSTEM** | **Health del API** (SaaS), no CPU/RAM del PC del usuario |

### SYSTEM — contenido realista (SaaS)

Mostrar estado agregado desde backend:

- Latencia media de endpoints críticos
- Uptime / último check
- Status por servicio: **Gemini**, **Claude**, **Stripe**, **Supabase** (+ Redis cuando aplique)
- Borde verde si todo OK; rojo parpadeante en alerta crítica

Endpoint previsto: `GET /v1/health/detailed` (o incluido en `GET /v1/hud/carousel`).

---

## Contexto y objetivo

El **panel izquierdo** del dashboard será uno de los elementos más diferenciadores: un **carrusel 3D ambiental** con cuadros HUD que rotan lentamente mostrando datos **en vivo** del usuario y del sistema.

- **Inspiración:** JARVIS (Iron Man), HUDs Westworld, dashboard Tesla, Vision Pro (transiciones suaves)
- **Rol UX:** Ambiental — no compite con el **orbe central** (foco principal)
- **Legibilidad:** Rotación suave; el usuario debe poder leer cada cuadro al frente

### Layout objetivo del dashboard

```
┌─────────────────────────────────────────┐
│         🏰 CED DASHBOARD                 │
├──────────┬───────────────┬──────────────┤
│  CARRUSEL│     ORBE      │   PANELES    │
│   3D     │    JARVIS     │   HUD        │
│ (izq)    │   (centro)    │  (derecha)   │
│          │               │  GLOBAL      │
│ 7 tipos  │  Gemini Live  │  DRONES      │
│ de card  │               │  WAVES       │
│          │               │  SUMMARY     │
│          │               │  USAGE       │
└──────────┴───────────────┴──────────────┘
```

**Nota layout actual (pre-Fase 3):** CITY / DRONES / ticker 2D en grid actual se **reorganizarán**; el carrusel ocupa la columna izquierda completa.

**Prototipo 2D existente (no sustituto):** `HudDronesPanel`, `HudFeedContext` — feed ticker; se retira o integra al migrar.

---

## Especificación visual

### Arquitectura del carrusel 3D

| Parámetro | Valor |
|-----------|--------|
| Posición | Panel izquierdo, alto ~300–400 px, centrado |
| Stack | Three.js + React Three Fiber (`@react-three/fiber`, `@react-three/drei`) |
| Tarjetas | 5–7 cuadros en círculo 3D (eje Y) |
| Rotación | 1 vuelta cada **30–45 s**; `rotationSpeed ≈ 0.005` en `useFrame` |
| Navegación manual | **No** (ambiental) |

### Apariencia de cada cuadro

- Borde cyan con glow (variante por tipo: pink, naranja, dorado, rojo si alerta)
- Fondo `#0a0a0aDD` semitransparente
- Tamaño ~200×300 px
- Esquinas HUD decorativas (SVG corners)
- Reflejo / glassmorphism sutil en cara frontal
- Frente: más grande, más brillante; laterales: perspectiva + menor opacidad; fondo: casi invisible

### Comportamiento

- Transición suave al cambiar cuadro al frente (`ease-in-out`)
- **Hover:** pausa rotación; zoom sutil en frontal; blur ligero en laterales
- **Click:** modal premium con detalle y acciones
- **Doble click:** fija cuadro al frente (`📌 Fijado`); otro click desfija
- **Auto-pausa** en hover; reanuda al salir

---

## Contenido de los 7 cuadros (datos en vivo)

| # | Título | Contenido | Fuente | Refresh | Borde |
|---|--------|-----------|--------|---------|-------|
| 1 | 📰 NEWS | Headline ≤60 chars, fuente, “hace X h”, mini imagen opcional | Tavily + keywords nicho | 30 min | Cyan |
| 2 | 📷 INSTAGRAM | Followers, Δ ayer, engagement, último post | Meta Graph API (OAuth) | 15 min | Rosa |
| 3 | 🎯 LEADS HOY | Count hoy, lead reciente @user + score, hot leads, barra cierre | `detected_leads` + SSE/Realtime | Realtime | Rojo si hot |
| 4 | 🔥 TRENDING | Top 3 temas, hashtags, mini sparkline | YouTube API (+ Reddit/X opcional) | 1 h | Naranja |
| 5 | 📊 ACTIVIDAD CED | Últimas 3 acciones CED | `ced_activity_logs` / backend | 1 min | Cyan |
| 6 | 📈 TU NEGOCIO | Conversiones semana, ingresos Stripe, cierre vs semana anterior | Supabase agregados | 5 min | Dorado |
| 7 | ⚡ SYSTEM | Latencia, uptime, status Gemini/Claude/Stripe/Supabase | `GET /v1/health/detailed` | 10 s | Verde OK |

### Modos inteligentes

| Modo | Comportamiento |
|------|----------------|
| **Inicial** (sin datos usuario) | SYSTEM + NEWS/TRENDING genéricos; placeholders “Conecta Instagram…” |
| **Activo** | Todas las tarjetas con datos; prioridad temporal en frontal (leads calientes 2× tiempo) |
| **Prospección** | Tarjetas de leads más visibles; animación más intensa en relevantes |
| **Alerta lead caliente** | Cuadro LEADS pop-out 3 s → vuelve al carrusel |
| **Alerta sistema** | Borde rojo, pausa rotación, notificación extra |

---

## Animaciones cinematográficas

- **Carga dashboard:** fade-in escalonado (200 ms entre tarjetas), entrada desde Z lejana, luego rotación
- **Actualización datos:** glitch sutil + borde cyan 1 s en tarjeta afectada
- **Ambiente:** partículas cyan, líneas de circuito, scan line cada ~10 s, glow pulsante en central
- **Sonido:** opcional, desactivado por defecto

---

## Responsive

| Breakpoint | Comportamiento |
|------------|----------------|
| Desktop >1024px | Carrusel 3D completo, 5–7 caras en perspectiva, 60 fps objetivo |
| Tablet 768–1024px | 3D simplificado, ~3 caras visibles, rotación más lenta |
| Móvil <768px | Carrusel **2D horizontal** + swipe, auto-avance 5 s, **sin** WebGL 3D |

---

## Interacción — acciones en modal (click)

| Tarjeta | Acciones |
|---------|----------|
| NEWS | “Leer artículo completo” → nueva pestaña |
| INSTAGRAM | “Ver detalles” → analytics |
| LEADS | “Ver todos” → kanban leads |
| TRENDING | “Crear contenido sobre esto” → editor |
| ACTIVITY | “Ver log completo” |
| STATS | “Ver analytics completos” |
| SYSTEM | “Ver health check” técnico |

---

## Implementación — estructura de archivos

```
apps/web/src/components/dashboard/
  ├── LeftPanel3DCarousel.tsx
  ├── carousel/
  │   ├── HudCard.tsx
  │   ├── CardContent.tsx
  │   ├── cards/
  │   │   ├── NewsCard.tsx
  │   │   ├── InstagramStatsCard.tsx
  │   │   ├── LeadsCard.tsx
  │   │   ├── TrendingCard.tsx
  │   │   ├── ActivityCard.tsx
  │   │   ├── BusinessStatsCard.tsx
  │   │   └── SystemStatusCard.tsx
  │   ├── HudOverlay.tsx
  │   ├── ParticleField.tsx
  │   └── hooks/
  │       ├── useCarouselRotation.ts
  │       ├── useCardData.ts
  │       └── useCardInteractions.ts
```

### Data fetching (frontend)

Hooks SWR / polling por tarjeta, preferible **un BFF**:

- `useCardData()` → `GET /v1/hud/carousel` (snapshot de las 7)
- Throttle UI: máx **1 actualización/s** en canvas
- Lazy: texturas solo para caras frontal + adyacentes

### Backend (nuevo — `apps/api`)

| Endpoint | Uso |
|----------|-----|
| `GET /v1/hud/carousel` | Snapshot agregado para el carrusel |
| `GET /v1/hud/news` | Tavily cache Redis 30 min |
| `GET /v1/hud/instagram` | Meta Graph |
| `GET /v1/hud/leads` | Supabase + SSE |
| `GET /v1/hud/trending` | YouTube (+ fuentes extra) |
| `GET /v1/hud/activity` | Logs CED |
| `GET /v1/hud/business-stats` | Stripe + métricas usuario |
| `GET /v1/health/detailed` | SYSTEM card |

### Supabase / migraciones futuras

- `detected_leads` (prospección)
- `ced_activity_logs`
- `meta_connections` (tokens IG)
- Campos perfil: `niche`, `news_keywords`, `prospection_enabled`

### Variables de entorno (API)

```
TAVILY_API_KEY          # previsto en config
META_APP_ID / SECRET
YOUTUBE_API_KEY
REDIS_URL               # cache + rate limit
```

---

## APIs adicionales — resumen

| Servicio | Propósito | Estado en repo (mar 2026) |
|----------|-----------|---------------------------|
| Tavily | NEWS | Key en `config.py`; router pendiente |
| Meta Graph | INSTAGRAM | OAuth pendiente (prompt CED ya documenta `connect_instagram`) |
| YouTube Data | TRENDING | Pendiente |
| Reddit / X | TRENDING opcional | Fase 2 trending; evaluar coste |
| Supabase Realtime | LEADS | Tabla `detected_leads` pendiente |
| Stripe | TU NEGOCIO | Parcial (suscripciones/recargas) |
| Redis | Cache BFF | `REDIS_URL` previsto; uso mínimo hoy |

---

## Riesgos técnicos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Doble WebGL (carrusel + orbe) | `dpr` cap, pausar carrusel con mic activo, offscreen pause |
| 7 texturas HTML vivas | Solo 1–2 texturas activas; resto estáticas o 2.5D CSS en tablet |
| Cuotas APIs | BFF + Redis cache; refresh server-side, no 7 polls cliente |
| Instagram OAuth largo | Placeholders elegantes en MVP |
| CPU% en web | **Descartado** — usar health API (confirmado) |
| Legibilidad vs rotación | 30–45 s/vuelta; dwell variable en alertas |

---

## Plan de ejecución (orden aprobado)

1. **Fase 2B** — validación Keini: MIC, voz bidireccional, cámara, USAGE en vivo, HIST  
2. **Fase 3A — Shell** — `LeftPanel3DCarousel` + rotación + modales + mock data + responsive móvil 2D  
3. **Fase 3B — BFF MVP** — `health/detailed` + NEWS (Tavily) + ACTIVITY  
4. **Fase 3C — Datos** — Instagram, leads+SSE, trending, business stats  
5. **Fase 3D — Pulido** — glitch, pin, prospección, alertas, QA 60 fps  

---

## Criterios de “listo para producción”

- [ ] Desktop ≥60 fps con orbe + carrusel simultáneos (laptop media)
- [ ] Hover pausa / click modal / doble click pin
- [ ] Móvil 2D sin regresión de estética cyan
- [ ] BFF con cache; sin tormenta de requests al abrir dashboard
- [ ] SYSTEM muestra health real de integraciones
- [ ] Modo inicial vs activo documentado para soporte

---

## Referencias

- Fase 2B (prerequisito): [PHASE2B.md](./PHASE2B.md)
- Fase 2 base (orbe, voz): [PHASE2.md](./PHASE2.md)
- Env keys: [ENV_SETUP.md](./ENV_SETUP.md)

---

*Documento creado a partir de la especificación de Keini (jun 2026). Implementación inicia tras confirmación explícita de Fase 2B en máquina local.*
