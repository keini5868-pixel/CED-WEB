# Pegar en AKINDO (inglés, jueces)

Copia cada bloque al campo que corresponda. No inventes un txid.

## Title
CED Shield — verifiable seal for a PDF or session (hash only, content stays private)

## One-liner
Prove a deliverable existed on Midnight without putting the document on-chain. Lace attests SHA-256 + time + wallet. Compact `recordSeal` is in the repo. No fake txid.

## Progress this wave
- Live judge demo: https://ced-castillo.com/shield (Lace Midnight Preview, preprod)
- Judge deck: https://ced-castillo.com/shield/pitch
- Compact 0.16 circuit `recordSeal(contentHash, kind)` — Apache-2.0  
  https://github.com/keini5868-pixel/CED-WEB/blob/main/apps/api/app/services/ced_shield/compact/CedShield.compact
- Dual-ledger made explicit: Midnight sees hash / time / wallet / kind. CED keeps PDF bytes, audio, transcript, prompts.
- `signData` attestation. If Lace stubs the method, JSON artifact still has live wallet + hash and `on_chain_txid: null`.
- Kill-switch `CED_SHIELD_ENABLED` off in the product. Jarvis / Retell / Meta never enter this path.
- Tests: `apps/api/tests/test_ced_shield.py`

## Links
- Demo: https://ced-castillo.com/shield
- Deck: https://ced-castillo.com/shield/pitch
- Repo: https://github.com/keini5868-pixel/CED-WEB
- Compact + LICENSE: `apps/api/app/services/ced_shield/compact/`

## What is not claimed
No on-chain txid yet. No Shield inside the voice assistant. No “private buy” button.

## Grant wallet
Already set on the AKINDO profile: USDT on Ethereum (`0x`). Not Lace.
