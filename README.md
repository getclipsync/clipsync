# Auto Video Builder (100% gratis)

App para armar videos automáticamente a partir de dos archivos .txt:
un guion de prompts de imagen con timestamps, y el guion de narración.
Corre en tu propia computadora, sin costos mensuales de ningún tipo.

## Stack usado (todo gratuito)

- **Streamlit** — interfaz web local
- **Pollinations.ai** — generación de imágenes por URL, sin API key
- **edge-tts** — texto a voz gratuito (motor de Microsoft Edge)
- **MoviePy + FFmpeg** — ensamblado del video, sin límite de duración

## Instalación

1. Instalá Python 3.10 o superior (si no lo tenés).
2. Instalá FFmpeg (necesario para MoviePy):
   - Windows: `winget install ffmpeg` o descargalo de ffmpeg.org
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`
3. Instalá las dependencias de Python:

   ```
   pip install -r requirements.txt
   ```

## Uso

1. Corré la app:

   ```
   streamlit run app.py
   ```

2. Se va a abrir en tu navegador (normalmente en `http://localhost:8501`).
3. Subí tu archivo de prompts de imagen (mirá `ejemplo_prompts_imagenes.txt`
   para el formato exacto) y tu archivo de guion (`ejemplo_guion.txt`).
4. Elegí una voz y hacé clic en "Generar video".
5. Descargá el resultado.

## Formato del .txt de prompts de imagen

Una línea por escena, así:

```
[00:00-00:05] doodle de una persona bostezando en un colectivo
[00:05-00:10] doodle de un cerebro con neuronas activándose
```

El primer número es donde empieza esa imagen en el video, el segundo
dónde termina. La duración de cada imagen se calcula automáticamente
a partir de esos tiempos — no hay límite de cantidad de escenas ni de
duración total.

## El .txt de guion/narración

Es simplemente el texto que querés que se narre, en texto plano, sin
timestamps. Se convierte en una sola pista de audio que se sincroniza
con la duración total del video armado por las imágenes.

## Simular la versión Free / Pro

En la app hay un checkbox "Simular versión FREE" que recorta el video
a 60 segundos — así podés probar cómo se sentiría la limitación antes
de decidir si programás esa restricción de verdad en una versión
hospedada más adelante.

## Cuándo pasar a herramientas pagas

Esta versión te sirve para producir tus propios videos gratis y para
mostrarle el producto a otras personas sin gastar un peso. Si en algún
momento empezás a tener usuarios pagando y necesitás más calidad,
velocidad o estabilidad, ahí tiene sentido evaluar:

- Reemplazar Pollinations por una API de imágenes paga (más consistencia
  de estilo).
- Reemplazar edge-tts por ElevenLabs (voces más naturales).
- Migrar el ensamblado a un servicio como Shotstack/JSON2Video si
  necesitás renderizar en la nube en vez de en tu propia máquina.

Pero para arrancar y validar la idea, no hace falta pagar nada de esto.

## Nota honesta sobre las herramientas gratuitas

Pollinations.ai y edge-tts son servicios gratuitos no oficiales/con
límites de uso razonable — pueden tener caídas ocasionales, cambios de
comportamiento o rate limits si generás muchísimo volumen. Para tu uso
personal y para las primeras pruebas con usuarios están perfectos; si
el negocio arranca a facilitar ingresos, ahí conviene reforzar con las
alternativas pagas mencionadas arriba.
