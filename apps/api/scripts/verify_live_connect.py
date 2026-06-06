"""Verifica Gemini Live native audio sin language_code."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from dotenv import load_dotenv

load_dotenv(API_ROOT / ".env")

MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"


async def main() -> int:
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        print("FALLO: GOOGLE_API_KEY vacía")
        return 1

    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(api_version="v1alpha"),
    )

    print(f"Modelo: {MODEL}")
    try:
        async with client.aio.live.connect(
            model=MODEL,
            config=types.LiveConnectConfig(
                response_modalities=[types.Modality.AUDIO],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Charon",
                        ),
                    ),
                ),
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
            ),
        ) as session:
            print("[OK] WebSocket open")
            await asyncio.sleep(2)
            if session.setup_complete is None:
                print("FALLO: sin setupComplete")
                return 1
            sid = session.setup_complete.session_id
            print(f"[OK] setupComplete session_id={sid}")
    except Exception as exc:
        msg = str(exc)
        if "Unsupported language" in msg or "language" in msg.lower():
            print(f"FALLO language config: {msg}")
        else:
            print(f"FALLO: {msg}")
        return 1

    print("PASS: Live connect estable sin language_code")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
