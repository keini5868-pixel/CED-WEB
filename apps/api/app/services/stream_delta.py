"""Normaliza chunks de streaming — solo deltas incrementales (no texto acumulado)."""

from __future__ import annotations


def stream_piece_delta(accumulated: str, piece: str) -> str:
    """Devuelve solo el texto nuevo si `piece` trae buffer acumulado."""
    incoming = piece or ""
    if not incoming:
        return ""
    prev = accumulated or ""
    if prev and incoming.startswith(prev):
        delta = incoming[len(prev) :]
        return delta if delta else ""
    if prev and len(incoming) <= len(prev) and prev.startswith(incoming):
        return ""
    # No usar «incoming in prev»: un token «C» o «V» ya aparece en
    # «Scarcity» / «Video» y el chat publicaba «ED» / «oz» en lugar de CED / Voz.
    if prev and len(incoming) >= 16 and incoming in prev:
        return ""
    return incoming


def strip_prefix_overlap(prefix: str, text: str) -> str:
    """Quita prefijo ya enviado (p. ej. filler parcial antes del cuerpo final)."""
    p = (prefix or "").strip()
    t = (text or "").strip()
    if not p or not t:
        return t
    if t.startswith(p):
        return t[len(p) :].lstrip()
    pl = p.lower()
    tl = t.lower()
    if tl.startswith(pl):
        return t[len(p) :].lstrip()
    return t
