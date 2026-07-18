# CED — Registro de Sesión de Desarrollo

Migración de sistema de voz artesanal a Retell nativo, construcción de herramientas, y estrategia de precios.

> **Nota de actualización (18 jul 2026, madrugada):** este documento se cerró originalmente con una lista de
> pendientes. Tras una auditoría completa de extremo a extremo (ver `docs/RETELL_NATIVE_PILOT_REPORT.md` para
> el detalle técnico del piloto y el reporte de auditoría — canvas
> `pre-launch-audit-report.canvas.tsx` — para la verificación en vivo), la sección 7 fue actualizada con el
> estado real de cada pendiente. El resto del documento se deja como registro histórico de la sesión.

## 1. Resumen ejecutivo

Esta sesión cubrió la migración completa del sistema de voz de CED (asistente estilo Jarvis), desde una arquitectura artesanal basada en Llama sin GPU (con latencias de minutos y bugs de turnos) hacia un sistema nativo de Retell con Gemini, construido y validado módulo por módulo en un piloto aislado antes de pasar a producción real. Se conectaron progresivamente más de una docena de herramientas de voz, se corrigieron decenas de bugs (falsas confirmaciones, fugas de instrucciones internas, sesiones que se quedaban atascadas), se optimizó el costo por minuto, y se rediseñó completamente la estrategia de precios y límites del producto antes del lanzamiento.

## 2. Evolución de la arquitectura de voz

### 2.1 Punto de partida — Llama en servidor propio
- Sistema corría en Railway sobre CPU sin GPU — respuestas de 8 a 25+ segundos, a veces minutos.
- Se intentó optimizar con mini agentes pasivos, modelo separado para voz (llama3.2:3b) vs texto (llama2:13b), banco de audios de relleno (fillers).
- Se probó separar el servicio de voz (CED-Llama-Voice) del de texto (CED-Llama) — mejoró parcialmente pero seguía siendo demasiado lento para conversación en tiempo real.
- Conclusión: CPU sin GPU es fundamentalmente inviable para inferencia de voz en tiempo real; escalar vCPU no resolvía el problema de fondo.

### 2.2 Decisión de migración — Retell LLM nativo
Se evaluó migrar del "Custom LLM" artesanal (donde el desarrollador programa a mano todo el manejo de turnos, interrupciones y timing de herramientas) al sistema nativo de Retell con Tool Calling y LLM States, que resuelve estos problemas de forma nativa por diseño. Ventajas confirmadas:
- Retell abstrae la alineación de function calling con la transcripción, el timing de cuándo hablar durante/después de ejecutar una herramienta, y el manejo de interrupciones.
- "LLM States" permite dividir la conversación en estados, cada uno con un prompt más corto y menos herramientas visibles — reduce alucinaciones y mejora el seguimiento de instrucciones.
- Se mantiene la voz personalizada de Jarvis (voice_id independiente del motor de conversación).
- Costo de Tool Calling/States sin cargo adicional — el costo real depende del LLM elegido y de los minutos de voz.

### 2.3 Plan de migración por fases
Se construyó un piloto aislado (accesible con `?voicePilot=native`) sin tocar nunca la producción real, siguiendo un protocolo estricto: diseñar cada herramienta, implementarla solo en el piloto, probarla por voz real, y solo si pasaba, avanzar a la siguiente. Orden de implementación:
- Fase 1: Clima, Calendario, Finanzas (lectura y escritura con confirmación)
- Fase 2: Búsqueda web
- Fase 3: Gmail (lectura y envío), Calendario (escritura)
- Fase 4: Escrituras con confirmación explícita (Gmail, luego simplificado a solo lectura por voz)
- Fase 5: Cámara y visión, Modo avanzado (Claude)
- Fase 6: Redes sociales (Facebook/Instagram), Prospección
- Fase 7: Mapa y navegación 3D, YouTube, Generación de imágenes y PDF por voz

### 2.4 Cutover a producción
Se ejecutó un corte controlado (canary) usando la bandera `NEXT_PUBLIC_RETELL_NATIVE_PILOT=true` en lugar de reemplazar directamente el `RETELL_AGENT_ID` de producción, permitiendo rollback instantáneo por sesión (`?voicePilot=prod`) o global si algo fallaba. El sistema Custom LLM anterior (apodado "r7") se mantuvo intacto como respaldo. El cutover se validó con casos reales en producción: envío de correo real recibido, registro de gasto real guardado, publicación real en Facebook e Instagram.

> **Estado del flag al cierre de esta sesión:** por defecto en código, si `NEXT_PUBLIC_RETELL_NATIVE_PILOT` no
> está seteado explícitamente en Railway, el tráfico usa el agente Custom LLM anterior ("r7"), no el nativo. No
> fue posible confirmar el valor real configurado en Railway para el dominio público porque
> `app.castillodigital.com` / `api.castillodigital.com` no resuelven por DNS al momento de esta auditoría (ver
> §7). Verificar directamente en el dashboard de Railway antes de asumir cuál agente recibe tráfico real.

## 3. Bugs principales encontrados y corregidos

Patrón recurrente: el modelo de voz confirmaba verbalmente el éxito de una acción sin que la acción real se hubiera completado ("falsa confirmación"). Se corrigió repetidamente en distintos módulos.

| Bug | Descripción y resolución |
|---|---|
| Turnos solapados / arrastre de audio | Respuestas de turnos distintos se mezclaban o repetían. Causa: condición de carrera entre múltiples `response_required` de Retell. Corregido con lock de ejecución serializado y transición obligatoria de estado. |
| Fuga de instrucciones internas en voz | El sistema decía en voz alta sus propias instrucciones de sistema. Corregido separando las instrucciones del texto hablado. |
| Fuga de instrucciones dentro de imágenes generadas | El prompt interno aparecía dibujado como texto dentro de la imagen generada. Corregido separando el prompt de sistema del contenido visual a generar. |
| Falsa confirmación de imagen/PDF sin generar nada | El chat normal decía "Listo, aquí está su imagen" sin adjuntar nada real. Causa: condición de carrera en el frontend. |
| Detección de intención de PDF demasiado amplia | Mencionar la palabra "PDF" en cualquier contexto disparaba la generación real. Corregido para exigir intención real de creación. |
| Detección de intención de **imagen** demasiado amplia (encontrado en la auditoría final) | Palabras genéricas de negocio/contenido ("ventajas", "beneficios", "evento", "vender") disparaban por sí solas la ruta de imagen incluso en preguntas puramente analíticas (ej. "ventajas y desventajas de X" en modo avanzado generaba un flyer en vez de un análisis de Claude). Corregido moviendo esas palabras a un grupo que solo cuenta combinado con una señal explícita de generación de imagen. Verificado en vivo contra producción. |
| Sesión de voz se queda "pegada" tras una acción exitosa | Tras publicar o confirmar un pago, el modelo quedaba sin herramientas disponibles. Corregido con transición obligatoria + "puerta de escape" con lecturas rápidas en todos los estados. |
| Anchors de detección demasiado estrictos | Frases naturales no activaban el módulo correcto. Corregido ampliando patrones y agregando heurística de tema + intención. |
| YouTube — falsa confirmación sistemática | De 5 intentos, solo 1 reproducía de verdad. **Resuelto y confirmado con evidencia real** — ver §7. |
| Audio de YouTube comprimido | Sonaba con menor potencia por conflicto de categorización de audio con la llamada activa (limitación de plataforma web). Se optó por silenciar solo el agente, no el mic. |
| Mapa — orientación y seguimiento | No rotaba según dirección de marcha ni mantenía zoom cercano. Corregido con fuente única de heading, smoothing de cámara, progreso monotónico sobre la ruta. |
| Costo por minuto elevado (tokens) | Tokens por turno subieron a 6.3k-8.4k, cruzando el umbral de 4,000 de Retell. Corregido eliminando catálogo de texto duplicado, bajando a ~3,691 tokens y el costo de $0.12/min a $0.097/min. |
| Identidad de voz de Jarvis alterada | La voz cambió a una voz femenina genérica. Investigado el origen de dos `voice_id` distintos; resuelto sin cambiar a ElevenLabs (más caro). Ambos agentes (prod y nativo) confirmados usando la misma voz Cartesia personalizada — decisión final de cuál usar sigue pendiente del usuario. |
| Generación de imágenes/PDF bloqueada tras integrar recarga | Tras conectar el sistema de monedero, la generación dejó de funcionar en las tres interfaces (voz, chat, avanzado). **Resuelto** — la causa real no era el monedero ni la cuenta admin, sino un bug de validación de contenido en la composición de PDF (ver §7). |
| Latencia intermitente en generación | 5 a 57 segundos de forma inconsistente en PDF/imágenes/búsqueda. Descartada causa de red del usuario. **Sigue pendiente de investigación** — no se abordó en la auditoría final (ver §7). |

## 4. Herramientas del asistente de voz — estado final

| Herramienta | Estado |
|---|---|
| Charla casual | Validado — fluido, sin cortes ni arrastre |
| Clima y calidad del aire | Validado (responde ocasionalmente en inglés por una condición de carrera con Tavily — detalle menor, no bloqueante) |
| Calendario | **Resuelto y verificado en vivo (18 jul, madrugada).** Causa real encontrada en la auditoría: la Google Calendar API estaba deshabilitada a nivel de proyecto en Google Cloud Console (error 403 en toda llamada), no un permiso OAuth pendiente del usuario. El usuario habilitó la API en el proyecto `119751473819`. Reprobado en vivo tras la habilitación: lectura ("¿qué tengo hoy?") → responde correctamente; escritura con confirmación ("agéndame algo para mañana" → "sí, agéndalo") → crea el evento real en Google Calendar (verificado con `event_id` real, luego eliminado por ser una prueba). |
| Gmail | Lectura y envío validados con casos reales |
| Finanzas | Lectura y escritura validados con registros reales |
| Cámara y visión | Validado a nivel de backend/herramienta; activar la cámara físicamente depende del navegador del usuario, no verificable sin sesión en vivo |
| Modo avanzado (Claude) | Validado |
| Búsqueda web | Validado |
| Publicación Facebook | Validado con publicación real |
| Publicación Instagram (con imagen) | Validado con publicación real |
| Prospección | Validado |
| Mapa y navegación 3D | Backend/cálculo de ruta validado; prueba real manejando durante varios minutos sigue pendiente |
| YouTube | **Resuelto** — confirmado con evidencia real que ya no hay falsa confirmación; audio sigue con volumen reducido por la limitación de plataforma ya documentada (no bloqueante) |
| Generación de imágenes y PDF por voz | **Resuelto y verificado** tras corregir el bug real de validación de contenido en PDF (ver §7) |

## 5. Estructura de costos

### 5.1 Costo por minuto de voz
- Infraestructura Retell: $0.055/min
- TTS (Cartesia, voz Jarvis): $0.015/min
- LLM (Gemini 3.0 Flash): $0.027/min
- **Total confirmado: $0.097/min** (bajado desde $0.122/min)

### 5.2 Otros costos por unidad
- Imagen estándar: $0.02 · Imagen HD: $0.04
- Búsqueda web: $0.01
- PDF: $0.05
- Visión: $0.03
- Modo avanzado: $0.05
- Google Maps: $0.02

### 5.3 Optimización de tokens
El conteo de tokens llegó a 6.3k-8.4k al acumular ~41 herramientas, superando el umbral de 4,000 tokens de Retell que activa un multiplicador de costo. Corregido eliminando un catálogo de texto redundante, bajando a ~3,691 tokens.

## 6. Estrategia de precios y planes

| Plan | Precio | Incluye |
|---|---|---|
| Básico (gratis) | $0 | YouTube, Calendario, Gmail, Memoria, Chat de texto. Sin voz permanente |
| Trial (7 días) | $0 | Acceso completo temporal + 5 min/día de voz. Al vencer pasa a Básico (0 min voz) |
| Starter | $30/mes | + Voz CED, Búsquedas web, Creación de imágenes. Límite voz: 8 min/día |
| Pro | $59/mes | + Cámara, Búsquedas ilimitadas, PDF, Redes sociales. Límite voz: 18 min/día |
| Élite | $99/mes | + Modo avanzado, Prospección, Mapa. Límite voz: 30 min/día |
| Founding | $149/mes | + Precio bloqueado 6 meses, cupos limitados (50). Límite voz: 40 min/día |

Confirmado en código (`app/domain/plans.py`) al cierre de la auditoría: los límites diarios de voz (8/18/30/40 en
pagados, 5/día en trial, 0 permanente en Básico) coinciden exactamente con esta tabla.

### Principios de diseño
- Límites reales nunca se muestran en la interfaz — solo el nombre de la capacidad.
- Cada plan muestra lista completa y explícita, sin abreviar con "Todo X +".
- Límites calibrados para que ningún plan pierda dinero en el peor caso (margen objetivo ~30%).

### Sistema de recarga
Al alcanzar el límite, se ofrece recargar desde $10, con 60% del pago convertido en crédito real (proporcional, sin expirar), aplicable a cualquier recurso agotado, en los 5 niveles incluido el gratis. Trial ve "suscribirse" + "recargar"; planes pagados solo ven "recargar". Integrado con Stripe existente.

Confirmado en la auditoría final: el monedero multi-recurso es compartido por voz, chat e imágenes/PDF/búsquedas,
y no bloquea incorrectamente cuentas con saldo o con exención de administrador.

## 7. Pendientes al cierre de la sesión — estado real tras auditoría (18 jul 2026)

| Pendiente | Estado final |
|---|---|
| Confirmar con evidencia real que YouTube ya no da falsas confirmaciones | **Resuelto** — confirmado con evidencia real en la auditoría: ya no hay falsa confirmación. |
| Probar el mapa en un trayecto real de varios minutos manejando | **Sigue pendiente** — no verificable sin una sesión de navegador real conduciendo; el backend de cálculo de ruta y orientación fue validado por código, pero el trayecto real en vivo no se probó en esta auditoría. |
| Investigar y corregir el bloqueo de generación de imágenes/PDF tras integrar recarga | **Resuelto y verificado en producción.** Causa real: en `pdf_report.py`, el validador de contenido se re-aplicaba sobre texto ya redactado por Gemini con un umbral más estricto que el usado para redactarlo, rechazando contenido válido de 80-159 caracteres (el caso típico de PDFs "breves" que pide voz). No era el monedero ni la cuenta admin — afectaba también a usuarios normales. Corregido y probado con llamadas HTTP reales contra producción en chat normal, modo avanzado y voz. |
| Investigar la latencia intermitente (5-57s) en PDF, imágenes y búsqueda web | **Sigue pendiente** — no se investigó en esta auditoría; sería el siguiente punto a abordar. |
| Reconectar el permiso de escritura de Google Calendar (OAuth) | **Resuelto.** Era un problema más profundo que un permiso OAuth: la Google Calendar API estaba deshabilitada a nivel de proyecto en Google Cloud Console. El usuario la habilitó en el proyecto `119751473819` y se reprobó lectura + escritura con confirmación en vivo — ambas funcionan correctamente. |
| Auditoría completa solicitada a Cursor antes del lanzamiento público | **Completada.** Ver reporte completo con evidencia de pruebas en vivo en el canvas `pre-launch-audit-report.canvas.tsx`. Incluye dos riesgos críticos nuevos para el lanzamiento no listados aquí: (1) la Calendar API deshabilitada arriba, y (2) el dominio de producción `castillodigital.com` (y subdominios `app.` / `api.`) no resuelve por DNS — hoy solo funciona la URL interna de Railway. |

### Bug adicional encontrado y corregido durante la auditoría (no estaba en la lista de pendientes)

- **Falsa detección de intención de imagen en modo avanzado**: preguntas puramente analíticas con palabras como
  "ventajas" o "beneficios" generaban una imagen en vez de un análisis de Claude. Corregido y verificado en vivo
  (ver tabla de §3).
- **Modelo de respaldo de Claude retirado**: `claude-3-5-haiku-20241022` (usado como respaldo si Llama falla)
  fue retirado por Anthropic (404). Actualizado a `claude-haiku-4-5-20251001`.
