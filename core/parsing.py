"""
Parseo del .txt de tiempos/prompts de imagen.

Acepta dos formatos, uno por línea:
  - Rango:       [00:00-00:04] texto
  - Marca única: [0:00] texto  (la duración se calcula con la marca de
    la línea siguiente; la última usa la duración total pasada aparte)

No se pueden mezclar los dos formatos en el mismo archivo.
"""

import re

TIMELINE_REGEX = re.compile(
    r"^\[(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\]\s*(.+)$"
)
SINGLE_TIME_REGEX = re.compile(r"^\[(\d{1,2}:\d{2})\]\s*(.+)$")


def time_to_seconds(t: str) -> float:
    mm, ss = t.strip().split(":")
    return int(mm) * 60 + int(ss)


def parse_image_timeline(txt_content: str):
    """
    Devuelve (scenes, needs_duration_fill):
      - Si el archivo usa rangos: scenes ya viene completo con 'end' y
        'duration', needs_duration_fill=False.
      - Si usa marcas únicas: scenes trae solo 'start' y 'prompt',
        needs_duration_fill=True — hay que llamar a
        finalize_single_timestamps() una vez que se sepa la duración
        total (normalmente la del audio o el video ya armado).
    Lanza ValueError con un mensaje claro si algo no matchea o se
    mezclan los dos formatos.
    """
    range_scenes = []
    single_scenes = []

    for i, raw_line in enumerate(txt_content.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        m_range = TIMELINE_REGEX.match(line)
        if m_range:
            start_str, end_str, prompt = m_range.groups()
            start = time_to_seconds(start_str)
            end = time_to_seconds(end_str)
            if end <= start:
                raise ValueError(
                    f"Línea {i}: el tiempo final debe ser mayor al inicial -> {line}"
                )
            range_scenes.append(
                {"start": start, "end": end, "duration": end - start, "prompt": prompt.strip()}
            )
            continue

        m_single = SINGLE_TIME_REGEX.match(line)
        if m_single:
            start_str, prompt = m_single.groups()
            single_scenes.append(
                {"start": time_to_seconds(start_str), "prompt": prompt.strip()}
            )
            continue

        raise ValueError(
            f"Línea {i} no tiene un formato de tiempo reconocido "
            f"('[MM:SS-MM:SS] texto' o '[MM:SS] texto'): -> {line}"
        )

    if range_scenes and single_scenes:
        raise ValueError(
            "El archivo mezcla el formato de rango '[MM:SS-MM:SS]' con el "
            "de marca única '[MM:SS]' — usá un solo formato en todo el archivo."
        )
    if not range_scenes and not single_scenes:
        raise ValueError("El archivo de imágenes no tiene escenas válidas.")

    if range_scenes:
        return range_scenes, False
    return single_scenes, True


def finalize_single_timestamps(scenes, total_duration: float = None):
    """
    Completa 'end' y 'duration' para escenas que solo tienen 'start':
    cada una termina donde empieza la siguiente; la última termina en
    total_duration si se conoce, o usa una duración por defecto de 2s.
    """
    finalized = []
    for i, scene in enumerate(scenes):
        start = scene["start"]
        if i + 1 < len(scenes):
            end = scenes[i + 1]["start"]
        elif total_duration and total_duration > start:
            end = total_duration
        else:
            end = start + 2
        finalized.append(
            {"start": start, "end": end, "duration": max(end - start, 0.1), "prompt": scene["prompt"]}
        )
    return finalized


def apply_free_cap(scenes, apply_cap: bool):
    """Recorta la lista de escenas a 60s si apply_cap es True (plan free)."""
    if not apply_cap:
        return scenes
    scenes = [s for s in scenes if s["start"] < 60]
    if scenes:
        scenes[-1]["duration"] = min(
            scenes[-1]["duration"], 60 - scenes[-1]["start"]
        )
    return scenes
