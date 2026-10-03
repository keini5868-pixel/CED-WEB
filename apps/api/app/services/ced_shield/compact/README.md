# CED Shield — Compact (Midnight)

Apache-2.0. Circuit: `recordSeal(contentHash, kind)`.

This folder is the Midnight-related code for the AKINDO technical gate.

| Gate | Status |
|---|---|
| ≥1 Compact contract | `CedShield.compact` · Compact 0.16 |
| Meaningful Midnight use | Dual-ledger: hash + kind public; content stays in CED |
| Apache-2.0 | `LICENSE` + SPDX on the contract |
| `midnightntwrk` topic | Set on the public GitHub repo (Settings → Topics) |

| On Midnight / Lace | Never on-chain |
|---|---|
| SHA-256, timestamp, wallet, kind (`pdf` \| `session`) | PDF bytes, audio, transcript, prompts |

```
pragma language_version 0.16;
export circuit recordSeal(contentHash: Bytes<32>, kind: Uint<8>): []
```

- Source: `CedShield.compact`
- Live demo (Lace preprod, no fake txid): https://ced-castillo.com/shield
- Judge deck: https://ced-castillo.com/shield/pitch
- Compile later with `compactc`. On-chain send waits for deploy + ZK keys.

`CED_SHIELD_ENABLED` stays off in the CED product. Jarvis / voice / Retell never import this path.
