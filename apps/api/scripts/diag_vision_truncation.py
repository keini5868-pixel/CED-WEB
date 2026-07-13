"""Diagnostic: Gemini vision truncation with thinking vs budget=0."""

from __future__ import annotations

import io
import os
from pathlib import Path

from PIL import Image, ImageDraw

# load .env
for line in Path(__file__).resolve().parents[1].joinpath(".env").read_text(
    encoding="utf-8", errors="ignore"
).splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
client = genai.Client(api_key=api_key)


def make_jpeg(label: str, size=(480, 360), quality=62) -> bytes:
    img = Image.new("RGB", size, (40, 90, 160))
    d = ImageDraw.Draw(img)
    d.ellipse([size[0] // 2 - 40, 60, size[0] // 2 + 40, 140], fill=(210, 180, 140))
    d.rectangle([size[0] // 2 - 50, 140, size[0] // 2 + 50, 280], fill=(180, 140, 100))
    d.text((20, size[1] - 40), label, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


PROMPT = (
    "Visión CED. Español latino, MÁX 2 oraciones cortas:\n"
    "1) Qué es el objeto — nombre concreto del producto o texto principal.\n"
    "2) Marca y nombre del producto si aparecen en la etiqueta (texto legible entre comillas).\n"
    "Directo. Si no puedes leer la marca, dilo y ofrece buscarla en internet.\n"
    "PROHIBIDO: 'parece', 'podría ser', 'no estoy seguro'."
)


def run(name: str, image_bytes: bytes, max_tokens: int, thinking_budget: int | None) -> None:
    cfg_kwargs: dict = {"temperature": 0.12, "max_output_tokens": max_tokens}
    if thinking_budget is not None:
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    types.Part.from_text(text=PROMPT + "\n\nPregunta: qué es esto"),
                ],
            )
        ],
        config=types.GenerateContentConfig(**cfg_kwargs),
    )
    text = (getattr(response, "text", None) or "").strip()
    finish = "?"
    usage: dict = {}
    if response.candidates:
        finish = str(getattr(response.candidates[0], "finish_reason", None))
    um = getattr(response, "usage_metadata", None)
    if um:
        usage = {
            "prompt": getattr(um, "prompt_token_count", None),
            "candidates": getattr(um, "candidates_token_count", None),
            "thoughts": getattr(um, "thoughts_token_count", None),
            "total": getattr(um, "total_token_count", None),
        }
    print(f"--- {name} ---")
    print(f"finish={finish} text_len={len(text)} usage={usage}")
    print(f"text={text[:400]!r}")
    print()


def main() -> None:
    jpeg_compact = make_jpeg("FIGURA RESINA", size=(480, 360), quality=62)
    jpeg_better = make_jpeg("FIGURA RESINA", size=(960, 720), quality=85)
    jpeg_bottle = make_jpeg("COCA-COLA 500ml", size=(480, 360), quality=62)
    jpeg_phone = make_jpeg("iPhone 15 Pro", size=(640, 480), quality=72)
    jpeg_book = make_jpeg("BOOK: Clean Code", size=(960, 720), quality=85)

    print("IMAGE sizes bytes:", len(jpeg_compact), len(jpeg_better))
    print()
    run("CURRENT analyze 180 tokens thinking=DEFAULT", jpeg_compact, 180, None)
    run("FIX thinking=0 + 180 tokens", jpeg_compact, 180, 0)
    run("FIX thinking=0 + 512 tokens", jpeg_compact, 512, 0)
    run("CURRENT on better jpeg 180 default thinking", jpeg_better, 180, None)
    run("FIX thinking=0 + 512 better jpeg", jpeg_better, 512, 0)
    run("CURRENT bottle compact", jpeg_bottle, 180, None)
    run("FIX bottle thinking=0 512", jpeg_bottle, 512, 0)
    run("CURRENT phone 640x480@72 thinking default 180", jpeg_phone, 180, None)
    run("FIX phone thinking=0 512", jpeg_phone, 512, 0)
    run("FIX book HD thinking=0 512", jpeg_book, 512, 0)


if __name__ == "__main__":
    main()
