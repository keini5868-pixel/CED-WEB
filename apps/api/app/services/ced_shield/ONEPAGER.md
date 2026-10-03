# CED Shield — judge one-pager (Wave 2)

**What it is:** a verifiable seal that a PDF or a session existed.  
**What it is not:** magic privacy for all of CED. Voice (Retell), Gemini, Tavily, and Meta do not change.

Live demo: https://ced-castillo.com/shield  
Deck: https://ced-castillo.com/shield/pitch  
Contract: `compact/CedShield.compact` · Apache-2.0

## Problem
Operators need to prove *that* a deliverable existed, without publishing the document on a public chain.

## Dual-ledger (Midnight model)

| Goes to Midnight / Lace | Stays in CED |
|---|---|
| `content_sha256`, `sealed_at`, wallet, `kind` | Chat, voice, PDF bytes, audio, transcript, prompts |

**Compact:** `recordSeal(contentHash, kind)` — Compact 0.16, `disclose()` only on the hash and kind.  
**Lace:** `window.midnight`, network `preprod`. Not bundled into the voice HUD.

## Why CED
Midnight needs apps with a job, not another DeFi demo. CED already has users and PDFs.  
Concrete case: prove a growth report existed without exposing a referral network.

## This wave
Lace live + SHA-256 + `signData`. No invented txid. On-chain send waits for deployed contract + ZK keys.  
Kill-switch `CED_SHIELD_ENABLED` stays off in the product. Midnight failure ≠ voice failure.

## How this maps to judging

| Weight | What we show |
|---|---|
| 40% Engineering | Compact source, Lace connector, SHA-256 in-browser |
| 15% QA | `test_ced_shield.py`, kill-switch default off, no fake txid |
| 15% Product | Real CED job (PDF / session seal), not a DeFi clone |
| 15% UX | `/shield` three-step loop a judge can finish |
| 10% Communication | `/shield/pitch` + this page + video |
| 5% BD | Existing CED users; grant wallet already set (USDT / Ethereum) |

## After this grant
HUD Mesa (identified Kraken) | Midnight (this ZK seal). Never one “private buy” button. Spec: `MARKETS_RAILS.md`.
