# CED Shield — one-pager (spike)

**Qué es:** un sello verificable de que un PDF o una sesión existió.  
**Qué no es:** privacidad mágica de CED. Voz (Retell), Gemini, Tavily y Meta no cambian.

## Problema
Pymes y operadores (marketing, propuestas, PDFs) necesitan probar *que* un entregable existió, sin publicar el contenido en una blockchain pública.

## Módulo
Tras el flujo normal de CED, el usuario conecta una wallet Midnight y pide sellar. CED calcula SHA-256 **en servidor o en el cliente** y manda a la chain **solo**:

- `content_sha256`
- `sealed_at` (UTC)
- `wallet`
- `kind` (`pdf` | `session`)
- `seal_id`

Nunca: audio, transcript, bytes del PDF, prompts, precios, nombres de clientes.

**Compact (en el repo):** `compact/CedShield.compact` — circuit `recordSeal(contentHash, kind)`.  
**Demo Lace:** `/shield` — `window.midnight`, red `preprod`. No se añade midnight.js al bundle de voz.

## On-chain vs off-chain

| Va a Midnight | Se queda en CED / el dispositivo |
|---|---|
| Hash + fecha + wallet | Chat, voz, PDF, Meta, Tavily |
| Prueba de existencia | El documento real |

## Por qué CED
Ya hay usuarios reales, voz, PDFs y un flujo de negocio. Midnight necesita apps, no más demos DeFi. CED Shield es un caso de *rational privacy* para pymes.
Un caso concreto: socios de PM International, que necesitan mostrar seguimiento de su red y su crecimiento sin exponer los datos de cada referido.
También aplica a cualquier usuario que conecte sus redes sociales a CED: puede probar que cierta cuenta o interacción existió sin exponer sus datos de conexión al resto del sistema.

## Ask (grant / Aliit)
Compact source y demo Lace ya están en el repo. Kill-switch `CED_SHIELD_ENABLED` apagado en producción. Pedimos seed + acceso al equipo Compact para la tx real en preprod (Wave 2).

Kill-switch: `CED_SHIELD_ENABLED=false` (default). Fallo de Midnight ≠ fallo de voz.
