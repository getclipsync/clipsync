"""
Ensamblado del video final a partir de imágenes con duración exacta
y una pista de audio (MoviePy + FFmpeg).
"""

import os
from moviepy import ImageClip, concatenate_videoclips, AudioFileClip


def build_video(scenes, image_paths, audio_path, output_path, fps=24):
    """
    scenes: lista de dicts con al menos 'duration' por escena (salida
        de parse_image_timeline / finalize_single_timestamps)
    image_paths: lista de rutas de imagen, en el mismo orden que scenes
    audio_path: ruta al mp3/wav de narración (puede ser None)
    """
    clips = []
    for scene, img_path in zip(scenes, image_paths):
        clip = ImageClip(img_path).with_duration(scene["duration"])
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")

    if audio_path and os.path.exists(audio_path):
        audio = AudioFileClip(audio_path)
        # Si el audio es más corto que el video, se corta el video a la
        # duración del audio (o viceversa) para que queden sincronizados.
        final_duration = min(video.duration, audio.duration)
        video = video.subclipped(0, final_duration).with_audio(
            audio.subclipped(0, final_duration)
        )

    video.write_videofile(
        output_path, fps=fps, codec="libx264", audio_codec="aac"
    )
    return output_path
