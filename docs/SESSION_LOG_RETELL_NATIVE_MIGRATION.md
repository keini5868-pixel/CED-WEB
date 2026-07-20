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

## 8. Incidente — eliminación accidental de 13 cuentas de usuario (19 jul 2026)

### Qué pasó
Durante una prueba end-to-end del fix del trial de voz (registro de una cuenta nueva real para confirmar los
5 min/día), se usó un script de limpieza (`scripts/_cleanup_browser_test_account.py`) para borrar la única
cuenta de prueba creada. El script llamaba al endpoint de Supabase Admin API
`GET /auth/v1/admin/users?email=...` esperando que filtrara por email en el servidor. **No lo hace** — ese
endpoint devuelve la lista completa de usuarios sin filtrar por el parámetro `email`. El script iteró esa
lista completa y emitió un `DELETE` por cada usuario devuelto, borrando 13 cuentas reales además de la cuenta
de prueba objetivo. La eliminación de la cuenta admin (`keini5868@gmail.com`) se agotó por timeout del lado
del cliente antes de completarse, por lo que su fila en `auth.users` y su `profile` sobrevivieron, pero su fila
en `subscriptions` sí fue borrada (cascade delete por `user_id`).

### Causa raíz (para que no se repita)
Bug en el script, no en la plataforma: asumir que un endpoint de administración filtra server-side por un
query param sin verificarlo primero contra una respuesta real, y sin un `LIMIT`/confirmación explícita antes
de un bucle de `DELETE` masivo. El script fue **eliminado del repositorio** (no existen scripts equivalentes
que borren cuentas vía la Admin API — verificado con una búsqueda completa del repo). Cualquier limpieza de
cuentas de prueba futura debe: (1) resolver primero el `user_id` exacto vía `GET /admin/users/{id}` o un filtro
verificado, (2) imprimir y confirmar la lista exacta de IDs antes de borrar, (3) nunca iterar una lista sin
haber confirmado que fue filtrada correctamente.

### Impacto real y decisión
De las 13 cuentas borradas, ninguna tenía una suscripción de pago activa (Starter/Pro/Élite/Founding) — eran
cuentas gratis o de prueba, sin cargos de por medio. Dado ese impacto acotado, y el riesgo de deshacer trabajo
posterior al incidente (fix del trial, imágenes/PDF gratis permanentes en Básico, migración del chat de texto
a Claude) al restaurar la base de datos vía point-in-time recovery, **se decidió no restaurar**. Esas 13
personas deberán registrarse de nuevo si vuelven a usar el sistema.

Verificación post-incidente (20 jul 2026):
- Cuenta admin (`keini5868@gmail.com`): fila de `subscriptions` reconstruida manualmente
  (`plan_id=founding`, `status=active`, `access_type=coadmin`, `price_locked_for_life=true`). Confirmado en
  vivo contra producción que `/v1/usage/balance` responde 200 con `plan_minutes_daily=40`,
  `is_founding_member=true` y uso real registrado — sin efectos secundarios.
- Datos huérfanos: se auditaron `ced_pdf_artifacts`, `generated_images`, `voice_conversations` y
  `ced_activity_logs` comparando cada `user_id` contra los `profiles` existentes. **0 filas huérfanas** — las
  13 cuentas borradas no llegaron a generar contenido persistente (coherente con ser altas recientes/de
  prueba), así que no quedó ningún PDF/imagen/conversación apuntando a un usuario inexistente.

## 9. Sesión de continuación (19-20 jul 2026) — bugs reportados y chat de texto migrado a Claude

Tras el cierre de la auditoría del §7, el usuario reportó 4 bugs adicionales por voz/chat y una queja de
lentitud en el chat de texto normal. Resumen de lo corregido y verificado en producción esta sesión:

| Ítem | Resolución |
|---|---|
| Calendario — confirmación por voz fallaba pese a funcionar por script | Regex de intención de escritura (`_WRITE_INTENT`) solo reconocía "agéndame/agendar", no verbos naturales como "guarda", "anota", "apunta". Ampliado; también se corrigió el parseo de hora ("5 de la tarde") y la extracción de título cuando incluye un nombre ("para Rafael Armando"). Verificado con HTTP real contra producción: prepare → confirm → evento real creado en Google Calendar → limpiado. |
| "Genera imagen de Iron Man" confirmaba éxito sin generar nada | El endpoint de la tool de imagen le pasaba a Retell solo el texto, sin el booleano `ok`, y el LLM alucinaba éxito. Corregido el mensaje de error para ser honesto sobre bloqueo de contenido protegido/límite temporal, y reforzada la instrucción de no alucinar éxito de tools. |
| Género inconsistente al referirse al usuario ("saludarla, señor") | Identidad mezclaba formas femeninas y masculinas para Keini Castillo. Unificado a masculino en `ced_identity.py` y el prompt del piloto nativo. |
| Imagen subida en "Diálogo en Vivo" no se usaba en publicaciones por voz | La función que adjunta imagen a un borrador pendiente solo cubría Instagram. Extendida a Facebook. |
| Trial de voz (5 min/día) no se activaba en cuentas nuevas | Causa real: el formulario de registro no distinguía el comportamiento anti-enumeración de Supabase (200 OK con `identities: []` para emails ya existentes) de un registro exitoso, dejando que el usuario reutilizara sin saberlo una cuenta vieja (post-trial). Corregido en `RegisterForm.tsx`; verificado con una cuenta nueva real de punta a punta. |
| Imágenes y PDF gratis permanentes en plan Básico | Agregado tope diario (2 imágenes, 1 PDF) al plan gratis post-trial, con aviso de recarga al agotarse. Sin afectar límites de planes pagados. |
| Chat de texto "se siente lento" | Medido en producción: el primer token tardaba ~19-21s en el 100% de los mensajes probados porque Llama (13B, CPU en Railway) agotaba siempre su timeout de 18s sin producir nada, y Claude recién entonces respondía (1-3s). Ni recortar el prompt a la mitad cambió el resultado — mismo techo de rendimiento de CPU que ya forzó la migración completa de voz a Gemini. **Decisión: se quitó Llama de la cascada de Chat Normal**, dejando a Claude como principal directo. Como Claude ya resolvía esos turnos como fallback, el costo incremental es ~$0 (~$5-10/mes para el volumen actual, ya se pagaba). Medido antes/después: primer token de ~19-21s a ~1.7-2.8s; respuesta completa de ~21-25s a ~3-6s. |

Durante la prueba end-to-end del fix del trial ocurrió el incidente de eliminación de cuentas documentado en
el §8.

## 10. Cierre del incidente §8 + auditoría final completa pre-lanzamiento (19-20 jul 2026)

### 10.1 Cierre formal del incidente de eliminación de cuentas

Confirmado con el usuario: ninguna de las 13 cuentas eliminadas tenía suscripción de pago activa. **Decisión
final: no se restaura vía PITR.** Verificaciones de cierre:

- Cuenta admin (`keini5868@gmail.com`): estable, sin efectos secundarios — ver verificación en vivo en §8.
- Datos huérfanos: **0 filas** en `ced_pdf_artifacts`, `generated_images`, `voice_conversations` y
  `ced_activity_logs` apuntando a un `user_id` inexistente — ver auditoría en §8.
- Script causante (`scripts/_cleanup_browser_test_account.py`): confirmado eliminado del repositorio; no
  existen scripts equivalentes que listen y borren usuarios vía Admin API sin filtrar primero por un
  `user_id` exacto conocido.

### 10.2 Bug adicional encontrado y corregido en esta ronda final

- **Ambigüedad "usa esta imagen de referencia en el fondo" vs. "publica esta imagen"**: el regex
  `_IMAGE_FOR_PUBLISH` en `publish_text.py` interpretaba cualquier frase "usa esta imagen…" como intención de
  publicar directamente, incluso cuando el usuario pedía usarla como referencia visual de fondo para un
  creativo nuevo (ej. "Usa esta imagen de referencia en el fondo del flyer" con un curso de varios módulos).
  Esto hacía que `is_attachment_creative_request` devolviera `False` y se perdiera el pedido de creativo.
  Corregido con un lookahead negativo que excluye "de referencia"/"de fondo" inmediatamente después de
  "imagen". Con regresión (`test_attachment_creative_for_course_without_beneficios_word`) que ya pasa.
- **Tests con patch target obsoleto**: `test_llama_voice_cloud_fallback.py` mockeaba
  `llama_voice_llm.call_llama_chat`, función que ya no existe (renombrada a `call_llama_voice_chat` en un
  refactor previo de esta misma sesión). Corregido; los 2 tests vuelven a pasar. Suite completa tras el fix:
  903 pasan, solo quedan 2 fallos preexistentes y no relacionados en `test_orchestrator_chaining.py`
  (anteriores a toda esta sesión, no tocados).

### 10.3 Pipeline de despliegue de Railway — confirmado saludable

Se sospechaba que los despliegues se habían detenido (el `build`/`timestamp` de `/health` no cambiaba tras
varios pushes). Se hizo una prueba directa: se subió un cambio trivial en `build_info.py` (bump de versión) y
se confirmó que Railway lo desplegó en ~2 minutos. **El pipeline de despliegue funciona correctamente** — la
sospecha inicial era una falsa alarma por revisar el `/health` demasiado pronto tras el push.

### 10.4 Tráfico de voz en producción — confirmado en el agente correcto (piloto nativo)

Preocupación inicial: la función `isRetellNativePilot()` en `voiceProvider.ts` decide qué agente de voz usar
sin el parámetro `?voicePilot=native` en la URL, dependiendo de la variable de entorno de build
`NEXT_PUBLIC_RETELL_NATIVE_PILOT` del servicio **frontend** en Railway. Como esa variable no aparece en
`.env.production.example` (solo comentada como plantilla), se sospechó que el valor real en Railway podía
estar sin configurar, y que el tráfico real caería al sistema viejo "r7".

**Descartado con evidencia empírica en vivo**: se interceptó `window.fetch` en el navegador contra
`cedweb-production.up.railway.app` (sin ningún parámetro `?voicePilot=` en la URL) y se hizo clic real en el
botón "Activar asistente CED". La llamada de red capturada fue:

```
POST /api/ced/retell/register-call-native-pilot
```

Esto confirma que `NEXT_PUBLIC_RETELL_NATIVE_PILOT=true` **sí está configurado** en el servicio frontend de
Railway, y que el tráfico real de usuarios nuevos — sin ningún parámetro especial — ya usa el piloto nativo,
no "r7". Todo el trabajo de esta migración (calendario, Gmail, finanzas, redes, mapa, YouTube, imagen/PDF por
voz, prompts, LLM States) sí llega a usuarios reales.

### 10.5 Verificación en navegador real contra producción (cuenta de prueba con email/password)

Se creó una cuenta de prueba persistente (`ced-browser-audit-2026@example.com`, plan Élite en trial) para
evitar depender de OAuth de Google de la cuenta admin. Con esa cuenta, verificado en vivo en
`cedweb-production.up.railway.app`:

- `/pricing`: 5 planes completos, listas de características sin truncar (Básico 7, Starter 8, Pro 13, Élite
  16, Founding 16 items).
- `/` (home): 4 planes de pago con listas completas (Básico no se muestra en home, solo en /pricing — por
  diseño).
- Login con email/password: funciona sin OAuth.
- Chat de texto: carga instantánea, respuesta a "hola, ¿cómo estás?" en ~3-4 segundos.
- Generación de imagen: NO confirma antes de que la imagen aparezca; imagen real generada; botón de
  descarga/expandir presente.
- Generación de PDF: PDF real generado con nivel de detalle razonable.
- Modo avanzado: pregunta analítica sobre "ventajas y desventajas de vender por redes sociales" devuelve
  análisis de texto real de Claude, sin generar imagen — bug de detección de intención confirmado corregido.
- Indicadores de trial visibles en la UI ("Plan elite · trialing", contador de minutos de voz usados).
- Widget de voz: al activarse entra en estado "Escuchándote… (habla o interrumpe)" con micrófono activo —
  confirma que la conexión de voz funciona técnicamente de punta a punta en el navegador real.
