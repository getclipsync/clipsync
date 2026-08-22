"""
Generación de subtítulos (.srt) a partir de las mismas escenas
usadas para armar el video (cuando el texto de cada escena es en
realidad el texto narrado, no un prompt de imagen).
"""


def seconds_to_srt_time(seconds: float) -> str:
    seconds = max(seconds, 0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(scenes, out_path):
    blocks = []
    for i, scene in enumerate(scenes, start=1):
        start = seconds_to_srt_time(scene["start"])
        end = seconds_to_srt_time(scene["end"])
        blocks.append(f"{i}\n{start} --> {end}\n{scene['prompt']}\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks))
    return out_path
