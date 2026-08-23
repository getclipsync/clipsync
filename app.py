"""
App gratuita para armar videos automáticamente a partir de:
  1) un .txt con prompts de imagen con timestamps
  2) un .txt con el guion/narración (texto plano)

Stack 100% gratuito:
  - Imágenes: Pollinations.ai (sin API key)
  - Audio (TTS): edge-tts (voz de Microsoft Edge, gratis)
  - Ensamblado: MoviePy + FFmpeg (open source)
  - Interfaz: Streamlit

Este archivo es SOLO la interfaz. Toda la lógica de parseo,
generación, ensamblado y subtítulos vive en el paquete core/, para
poder reusarla después desde una web con cola de trabajos sin
duplicar código.

Formato esperado del .txt de imágenes (una línea por escena):
  [00:00-00:04] doodle de una persona bostezando en un colectivo
  [00:04-00:09] doodle de un cerebro con neuronas activándose

  o, con marca única (la duración se calcula sola):
  [0:00] texto narrado de esa escena
  [0:04] texto narrado de la siguiente escena
"""

import os
import tempfile
import requests
import streamlit as st

from moviepy import AudioFileClip, VideoFileClip

from core.parsing import (
    parse_image_timeline,
    finalize_single_timestamps,
    apply_free_cap,
)
from core.generation import generate_image, generate_audio, concatenate_audio_files
from core.assembly import build_video
from core.subtitles import generate_srt
from core.database import (
    get_or_create_user,
    increment_video_count,
    reset_user,
    is_disposable_email,
)

# URL del formulario de Formspree donde llegan los avisos de interés de
# pago. Gratis hasta 50 envíos/mes.
FORMSPREE_URL = "https://formspree.io/f/xbgrbypl"


def _check_access_code():
    """
    Gate simple con código de invitación, para controlar quién prueba
    la app en esta etapa (evita que cualquiera use tu cuota gratis de
    Pollinations/edge-tts). El código se define en
    .streamlit/secrets.toml (local) o en Settings → Secrets (Streamlit
    Community Cloud), como:
        ACCESS_CODE = "TUCODIGO"
    """
    expected = st.secrets.get("ACCESS_CODE")
    if not expected:
        # Si no configuraste ningún código, no bloquea (útil en local
        # mientras probás vos solo).
        return True

    if st.session_state.get("access_granted"):
        return True

    st.title("🎬 ClipSync")
    st.caption("Acceso solo con invitación durante esta etapa de prueba.")
    code = st.text_input("Código de acceso", type="password")
    if st.button("Entrar"):
        if code == expected:
            st.session_state["access_granted"] = True
            st.rerun()
        else:
            st.error("Código incorrecto.")
    return False


def _check_email_gate():
    """
    Pide el mail antes de dejar generar nada. Es lo que reemplaza al
    contador por sesión de navegador: el uso queda atado a ese mail en
    Supabase, así que cerrar el navegador, probar en otro navegador o
    borrar cookies ya no reinicia el contador.
    """
    if st.session_state.get("user_email"):
        return True

    st.subheader("¿Cuál es tu mail?")
    st.caption(
        "Lo usamos para llevar la cuenta de tu video de prueba gratis, "
        "y para avisarte cuando salga la versión paga si te interesa."
    )
    email = st.text_input("Mail", key="email_gate_input")
    if st.button("Continuar", key="email_gate_button"):
        email = email.strip().lower()
        if not email or "@" not in email or "." not in email.split("@")[-1]:
            st.error("Ingresá un mail válido.")
            return False
        if is_disposable_email(email):
            st.error(
                "Ese dominio de mail temporal/descartable no está "
                "permitido — usá un mail real."
            )
            return False

        try:
            count = get_or_create_user(email)
        except Exception as e:
            st.error(f"No se pudo conectar con la base de datos: {e}")
            return False

        st.session_state["user_email"] = email
        st.session_state["videos_generated_count"] = count
        st.rerun()
    return False


def _show_interest_form():
    """
    Botón + campo de mail para medir interés real de pago, sin tener
    que armar Stripe todavía. Cada envío llega a tu mail vía Formspree.
    """
    st.divider()
    st.subheader("¿Te sirvió esto?")
    st.write(
        "Estamos evaluando lanzar una versión sin límite de duración por "
        "una suscripción mensual (~$19/mes). Si te interesaría, dejanos "
        "tu mail y te avisamos apenas esté disponible."
    )

    if st.session_state.get("interest_sent"):
        st.success("¡Gracias! Te vamos a avisar apenas esté disponible.")
        return

    email = st.text_input("Tu mail", key="interest_email")
    if st.button("Sí, me interesa", key="interest_button"):
        if not email or "@" not in email:
            st.error("Ingresá un mail válido.")
        else:
            try:
                response = requests.post(
                    FORMSPREE_URL,
                    data={
                        "email": email,
                        "mensaje": "Interesado/a en pagar ~$19/mes por ClipSync",
                    },
                    headers={"Accept": "application/json"},
                    timeout=10,
                )
                if response.ok:
                    st.session_state["interest_sent"] = True
                    st.rerun()
                else:
                    st.error(
                        f"Formspree devolvió un error ({response.status_code}): "
                        f"{response.text[:300]}"
                    )
            except requests.RequestException as e:
                st.error(f"No se pudo enviar: {e}")


def _finish_and_show(
    scenes, image_paths, audio_path, workdir, offer_srt=False, offer_audio=False
):
    """
    Genera el video (y opcionalmente subtítulos) UNA VEZ, y guarda las
    rutas resultantes en session_state. El renderizado (video, botones
    de descarga, formulario de interés) se hace aparte, en
    _render_last_result(), para que sobreviva a los reruns que Streamlit
    dispara con cada clic posterior (ej. al usar el formulario de
    interés) — si no, todo lo generado desaparecía de la pantalla.
    """
    st.info("Ensamblando video final...")
    output_path = os.path.join(workdir, "video_final.mp4")
    build_video(scenes, image_paths, audio_path, output_path)

    result = {"video_path": output_path, "audio_path": None, "srt_path": None}

    if offer_audio and audio_path and os.path.exists(audio_path):
        result["audio_path"] = audio_path

    if offer_srt:
        srt_path = os.path.join(workdir, "subtitulos.srt")
        generate_srt(scenes, srt_path)
        result["srt_path"] = srt_path

    st.session_state["last_result"] = result
    try:
        new_count = increment_video_count(st.session_state["user_email"])
        st.session_state["videos_generated_count"] = new_count
    except Exception as e:
        # Si falla la base de datos, no bloqueamos la entrega del video
        # ya generado, pero avisamos para no perder el rastro.
        st.session_state["videos_generated_count"] = (
            st.session_state.get("videos_generated_count", 0) + 1
        )
        st.warning(f"El video se generó bien, pero no se pudo actualizar el contador: {e}")
    st.session_state["interest_sent"] = False
    st.rerun()


def _render_last_result():
    """
    Dibuja el resultado guardado en session_state (si existe). Se llama
    siempre al final de main(), en cada rerun, para que el video y los
    botones no desaparezcan al interactuar con el formulario de interés.
    """
    result = st.session_state.get("last_result")
    if not result:
        return

    st.success("¡Listo!")

    if result.get("video_path"):
        st.video(result["video_path"])
        with open(result["video_path"], "rb") as f:
            st.download_button(
                "Descargar video final", f, file_name="video_final.mp4"
            )

    if result.get("audio_path") and os.path.exists(result["audio_path"]):
        audio_ext = os.path.splitext(result["audio_path"])[1] or ".mp3"
        with open(result["audio_path"], "rb") as f:
            st.download_button(
                "Descargar audio completo",
                f,
                file_name=f"audio_completo{audio_ext}",
            )

    if result.get("srt_path"):
        with open(result["srt_path"], "rb") as f:
            st.download_button(
                "Descargar subtítulos (.srt)", f, file_name="subtitulos.srt"
            )
        st.caption(
            "Subilo en YouTube Studio → Subtítulos → Agregar → Subir "
            "archivo, en vez de usar el automático de YouTube."
        )

    _show_interest_form()

    st.divider()
    if st.button("Empezar de nuevo (generar otro video)"):
        st.session_state["last_result"] = None
        st.session_state["interest_sent"] = False
        st.rerun()


def main():
    st.set_page_config(page_title="ClipSync (beta gratis)", layout="centered")

    if not _check_access_code():
        return

    st.title("🎬 ClipSync")

    if not _check_email_gate():
        return

    st.caption("Beta gratis — armá tu video sincronizado sin límite de duración.")
    st.caption(f"Conectado como: {st.session_state['user_email']}")

    modo = st.radio(
        "¿Qué querés hacer?",
        [
            "Generar todo desde prompts (imágenes + narración nuevas)",
            "Ya tengo las imágenes y el audio generados — solo unirlos",
            "Ya tengo el video — solo generar el archivo de subtítulos (.srt)",
        ],
    )

    def _mostrar_estado_limite():
        ya_uso = st.session_state["videos_generated_count"] >= 1
        if ya_uso:
            st.warning(
                "Ya usaste tu video de prueba sin límite. A partir de "
                "ahora, los videos se generan en el plan **Free (60 "
                "segundos)** — dejanos tu mail en el formulario de más "
                "abajo para avisarte cuando esté disponible la versión "
                "Pro sin límite."
            )
            with st.expander("Soy yo probando la app (reiniciar mi contador)"):
                if st.button("Reiniciar mi contador de prueba"):
                    reset_user(st.session_state["user_email"])
                    st.session_state["videos_generated_count"] = 0
                    st.rerun()
        else:
            st.info(
                "✨ Este es tu **video de prueba gratis, sin límite de "
                "duración**. Del segundo en adelante, se generan en el "
                "plan Free (60 segundos)."
            )
        return ya_uso

    # -------------------------------------------------------------
    # MODO 1: generar todo desde cero
    # -------------------------------------------------------------
    if modo.startswith("Generar todo"):
        max_free_seconds = _mostrar_estado_limite()

        st.caption(
            "Subí el .txt de prompts de imagen (con timestamps) y el .txt "
            "del guion. La app genera las imágenes, la narración y arma el "
            "video sincronizado, sin límite de duración."
        )

        img_file = st.file_uploader(
            "Prompts de imagen (.txt) — formato: [00:00-00:04] prompt",
            type="txt",
        )
        audio_txt_file = st.file_uploader(
            "Guion / narración (.txt) — texto plano", type="txt"
        )
        voice = st.selectbox(
            "Voz de narración",
            ["es-AR-ElenaNeural", "es-MX-DaliaNeural", "es-ES-ElviraNeural"],
            index=0,
        )

        if st.button("Generar video", type="primary"):
            if not img_file or not audio_txt_file:
                st.error("Subí los dos archivos .txt antes de continuar.")
                return

            try:
                scenes, needs_duration = parse_image_timeline(
                    img_file.read().decode("utf-8")
                )
            except ValueError as e:
                st.error(str(e))
                return

            guion_text = audio_txt_file.read().decode("utf-8").strip()

            workdir = tempfile.mkdtemp(prefix="videoapp_")
            st.info(f"Generando {len(scenes)} imágenes...")
            progress = st.progress(0)
            image_paths = []
            for i, scene in enumerate(scenes):
                img_path = os.path.join(workdir, f"scene_{i:03d}.png")
                generate_image(scene["prompt"], img_path)
                image_paths.append(img_path)
                progress.progress((i + 1) / len(scenes))

            st.info("Generando narración...")
            audio_path = os.path.join(workdir, "narracion.mp3")
            generate_audio(guion_text, audio_path, voice=voice)

            if needs_duration:
                audio_duration = AudioFileClip(audio_path).duration
                scenes = finalize_single_timestamps(scenes, audio_duration)

            scenes = apply_free_cap(scenes, max_free_seconds)
            _finish_and_show(scenes, image_paths, audio_path, workdir)

    # -------------------------------------------------------------
    # MODO 2: ya tenés las imágenes y el audio — solo ensamblar
    # -------------------------------------------------------------
    elif modo.startswith("Ya tengo las imágenes"):
        max_free_seconds = _mostrar_estado_limite()

        st.caption(
            "Subí el .txt con los tiempos de cada imagen (mismo formato de "
            "siempre, el texto del prompt no importa acá), las imágenes en "
            "orden, y el archivo de audio ya generado. La app solo las une."
        )

        timing_file = st.file_uploader(
            "Archivo de tiempos (.txt) — '[00:00-00:04] texto' o '[0:00] texto'",
            type="txt",
            key="timing_file",
        )
        image_files = st.file_uploader(
            "Imágenes (en el mismo orden que el .txt de tiempos)",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key="image_files",
        )
        audio_files = st.file_uploader(
            "Audio ya generado — subí un archivo, o varios si te quedó "
            "partido en partes (ej. por el límite de caracteres de "
            "ElevenLabs); se unen en el orden en que los subís",
            type=["mp3", "wav"],
            accept_multiple_files=True,
            key="audio_files",
        )

        if image_files:
            image_files = sorted(image_files, key=lambda f: f.name)
            st.caption(
                f"{len(image_files)} imágenes cargadas. Se van a usar "
                "ordenadas alfabéticamente por nombre de archivo:"
            )
            st.write(", ".join(f.name for f in image_files))
            st.info(
                "Si ese orden no es el correcto, renombrá los archivos con "
                "un prefijo que ordene bien (ej. 00_, 01_, 02_...) y "
                "volvé a subirlos."
            )

        if audio_files and len(audio_files) > 1:
            st.caption(
                "Se van a unir en este orden: "
                + " + ".join(f.name for f in audio_files)
            )
            st.info(
                "Si el orden no es el correcto, subilos de nuevo en el "
                "orden correcto (arrastralos en ese orden al selector)."
            )

        incluir_subtitulos = st.checkbox(
            "Generar también un archivo de subtítulos (.srt) a partir del "
            "texto del .txt de tiempos",
            value=True,
        )

        if st.button("Unir imágenes y audio", type="primary"):
            if not timing_file or not image_files or not audio_files:
                st.error(
                    "Subí el .txt de tiempos, todas las imágenes y al "
                    "menos un archivo de audio antes de continuar."
                )
                return

            try:
                scenes, needs_duration = parse_image_timeline(
                    timing_file.read().decode("utf-8")
                )
            except ValueError as e:
                st.error(str(e))
                return

            if len(scenes) != len(image_files):
                st.error(
                    f"El .txt de tiempos tiene {len(scenes)} escenas, pero "
                    f"subiste {len(image_files)} imágenes. Tienen que ser "
                    f"la misma cantidad."
                )
                return

            workdir = tempfile.mkdtemp(prefix="videoapp_")
            image_paths = []
            for i, img_f in enumerate(image_files):
                ext = os.path.splitext(img_f.name)[1] or ".png"
                img_path = os.path.join(workdir, f"scene_{i:03d}{ext}")
                with open(img_path, "wb") as f:
                    f.write(img_f.read())
                image_paths.append(img_path)

            # Guardar cada parte de audio y unirlas en una sola pista
            part_paths = []
            for i, af in enumerate(audio_files):
                ext = os.path.splitext(af.name)[1] or ".mp3"
                part_path = os.path.join(workdir, f"audio_part_{i:03d}{ext}")
                with open(part_path, "wb") as f:
                    f.write(af.read())
                part_paths.append(part_path)

            if len(part_paths) > 1:
                st.info("Uniendo las partes de audio...")
                audio_path = os.path.join(workdir, "audio_completo.mp3")
                concatenate_audio_files(part_paths, audio_path)
            else:
                audio_path = part_paths[0]

            if needs_duration:
                audio_duration = AudioFileClip(audio_path).duration
                scenes = finalize_single_timestamps(scenes, audio_duration)

            scenes = apply_free_cap(scenes, max_free_seconds)
            image_paths = image_paths[: len(scenes)]

            _finish_and_show(
                scenes,
                image_paths,
                audio_path,
                workdir,
                offer_srt=incluir_subtitulos,
                offer_audio=True,
            )

    # -------------------------------------------------------------
    # MODO 3: ya tenés el video — solo generar los subtítulos (.srt)
    # -------------------------------------------------------------
    else:
        st.caption(
            "Subí el mismo .txt de tiempos que usaste para armar el video "
            "(formato '[00:00-00:04] texto' o '[0:00] texto'). No hace "
            "falta tocar el video para nada — solo se genera el archivo "
            "de subtítulos, que subís aparte en YouTube Studio."
        )

        srt_timing_file = st.file_uploader(
            "Archivo de tiempos (.txt)", type="txt", key="srt_timing_file"
        )

        duracion_modo = st.radio(
            "Para que la última línea de subtítulo termine bien "
            "coordinada, ¿cómo querés indicar la duración total?",
            [
                "Subir el video (la app la calcula sola, más preciso)",
                "Escribirla a mano (MM:SS)",
                "No indicarla (queda un valor por defecto)",
            ],
        )

        video_file_for_duration = None
        manual_duration_str = None

        if duracion_modo.startswith("Subir el video"):
            video_file_for_duration = st.file_uploader(
                "Tu video ya generado (.mp4)", type=["mp4"], key="video_duration_file"
            )
        elif duracion_modo.startswith("Escribirla"):
            manual_duration_str = st.text_input(
                "Duración total del video, formato MM:SS", value="7:34"
            )

        if st.button("Generar subtítulos", type="primary"):
            if not srt_timing_file:
                st.error("Subí el .txt de tiempos antes de continuar.")
                return

            try:
                scenes, needs_duration = parse_image_timeline(
                    srt_timing_file.read().decode("utf-8")
                )
            except ValueError as e:
                st.error(str(e))
                return

            total_duration = None
            if duracion_modo.startswith("Subir el video"):
                if not video_file_for_duration:
                    st.error("Subí el archivo de video para calcular la duración.")
                    return
                workdir_tmp = tempfile.mkdtemp(prefix="videoapp_dur_")
                video_tmp_path = os.path.join(workdir_tmp, "video.mp4")
                with open(video_tmp_path, "wb") as f:
                    f.write(video_file_for_duration.read())
                total_duration = VideoFileClip(video_tmp_path).duration
                st.caption(f"Duración detectada: {total_duration:.1f} segundos")
            elif duracion_modo.startswith("Escribirla"):
                try:
                    mm, ss = manual_duration_str.strip().split(":")
                    total_duration = int(mm) * 60 + int(ss)
                except (ValueError, AttributeError):
                    st.error(
                        "La duración manual tiene que tener formato MM:SS, "
                        "por ejemplo 7:34."
                    )
                    return

            if needs_duration:
                scenes = finalize_single_timestamps(scenes, total_duration=total_duration)

            workdir = tempfile.mkdtemp(prefix="videoapp_")
            srt_path = os.path.join(workdir, "subtitulos.srt")
            generate_srt(scenes, srt_path)

            st.session_state["last_result"] = {
                "video_path": None,
                "audio_path": None,
                "srt_path": srt_path,
            }
            st.session_state["interest_sent"] = False
            st.rerun()

    _render_last_result()


if __name__ == "__main__":
    main()
