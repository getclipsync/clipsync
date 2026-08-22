"""
Generación de imágenes (Pollinations.ai) y audio (edge-tts), todo gratis.
"""

import asyncio
import requests

try:
    import edge_tts
except ImportError:
    edge_tts = None

from moviepy import AudioFileClip, concatenate_audioclips


def generate_image(prompt: str, out_path: str, width=1024, height=576, seed=None):
    """Descarga una imagen generada por Pollinations.ai para el prompt dado."""
    safe_prompt = requests.utils.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}"
    params = {"width": width, "height": height, "nologo": "true"}
    if seed is not None:
        params["seed"] = seed

    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()

    with open(out_path, "wb") as f:
        f.write(response.content)

    return out_path


async def _generate_audio_async(text: str, out_path: str, voice: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)


def generate_audio(text: str, out_path: str, voice: str = "es-AR-ElenaNeural"):
    """
    Genera un mp3 de narración a partir de texto plano usando edge-tts.
    Voces recomendadas en español: es-AR-ElenaNeural, es-MX-DaliaNeural,
    es-ES-ElviraNeural.
    """
    if edge_tts is None:
        raise RuntimeError("Falta instalar edge-tts. Corré: pip install edge-tts")
    asyncio.run(_generate_audio_async(text, out_path, voice))
    return out_path


def concatenate_audio_files(audio_paths, out_path):
    """
    Une varios archivos de audio (en el orden dado) en uno solo. Útil
    cuando el TTS (ej. ElevenLabs) obligó a partir la narración en
    varias partes por límite de caracteres.
    """
    clips = [AudioFileClip(p) for p in audio_paths]
    combined = concatenate_audioclips(clips)
    combined.write_audiofile(out_path)
    return out_path
