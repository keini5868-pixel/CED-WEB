# Guion video Wave 2 — 2:20

Habla en español o inglés. La UI está en inglés para jueces. No improvises un txid.  
Pantalla: F11 en `/shield/pitch`, luego cambia a `/shield` en el minuto 0:40.

---

**0:00–0:20 — problema (pitch, slide 1–2)**  
CED ya genera PDFs y sesiones para pymes. El problema no es “otra DeFi”. Es: ¿cómo pruebo que ese entregable existió sin publicar el documento en una blockchain pública?

**0:20–0:40 — dual-ledger (slide 3)**  
Midnight ve solo el compromiso: SHA-256, hora, wallet, tipo. El PDF, la voz y el transcript se quedan en CED. Estado público mínimo. Dato privado fuera.

**0:40–1:40 — demo viva (pestaña /shield)**  
1. “Lace Midnight Preview, red preprod.” Conectar.  
2. Hash sample. El SHA-256 no sale de esta página.  
3. Firmar. Si Lace firma, el sello queda atestado. Si `signData` está stub, copio el JSON: wallet viva + hash, `on_chain_txid: null`.  
4. Enseña ON-CHAIN VS OFF-CHAIN. Di: “no hay txid falso. Compact `recordSeal` está en el repo; la tx espera deploy + keys.”

**1:40–2:00 — por qué CED (slide 6)**  
Usuarios reales, no un demo vacío. Un operador puede probar que un reporte existió sin exponer su red. Jarvis no toca este riel.

**2:00–2:20 — Wave 2 / cierre (slide 7–8)**  
Hoy: Lace + hash + firma. Siguiente: una tx preprod cuando existan las keys. Demo: ced-castillo.com/shield — contrato: CedShield.compact.

Corta. No menciones Kraken, Mesa, ni recargas Stripe.
