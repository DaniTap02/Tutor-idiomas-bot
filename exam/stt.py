"""Transcripción de notas de voz con faster-whisper (local, sin internet salvo la primera descarga).

El trabajo va por ETAPAS y cada una falla con `Fallo` (ver exam/registro.py) indicando el MOTIVO
real, para que el bot no muestre siempre el mismo mensaje:

  sondear     -> archivo_falta | archivo_vacio | formato | dependencia
                 (se revisa el archivo con PyAV ANTES de cargar el modelo: es inmediato y así un
                  archivo dañado no se confunde con "faster-whisper no está instalado")
  modelo      -> dependencia | modelo_descarga | memoria | modelo_carga
  transcribir -> transcripcion | memoria
  (sin voz reconocida no es un fallo: se devuelve text="" y lo decide el flujo)

El formato de Telegram (OGG/OPUS) NO necesita conversión: se decodifica con PyAV (exam/audio.py,
a_muestras), que trae las librerías de FFmpeg dentro del paquete, y a Whisper se le pasan las muestras.

IMPORTANTE: el idioma se FUERZA al del examen (`language=`), no se deja que Whisper lo adivine.
Adivinando, un acento marcado hablando inglés se detectaba como otro idioma y se rechazaba una
respuesta correcta. Quien decide si el estudiante habló en el idioma pedido es el calificador
(grader.py, campo is_in_language), que juzga el CONTENIDO y acierta mucho más.

Además de la transcripción se devuelven métricas de la grabación (duración, palabras por minuto,
confianza), que el flujo usa para avisar si el audio es muy corto, muy lento o casi inaudible.

Variables de entorno (todas opcionales):
  WHISPER_MODEL    tiny | base | small | medium  (por defecto "base": buen equilibrio con 8 GB de RAM)
  WHISPER_DEVICE   cpu | cuda                    (por defecto "cpu")
  WHISPER_COMPUTE  int8 | int8_float16 | float16 (por defecto "int8": el más liviano en CPU)
  WHISPER_BEAM     tamaño del beam search        (por defecto 5; bájalo a 1 si tu PC sufre)

Es SÍNCRONO y pesado: llámalo con asyncio.to_thread desde el bot.
"""
import logging
import math
import os
import threading

from exam.audio import a_muestras, sondear
from exam.registro import Fallo, clasificar_stt, medir

log = logging.getLogger(__name__)

MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE", "int8")
BEAM_SIZE = int(os.getenv("WHISPER_BEAM") or 5)

_model = None
_model_lock = threading.Lock()   # dos notas de voz a la vez no deben cargar el modelo dos veces


def modelo_cargado() -> bool:
    """True si el modelo ya está en memoria (la primera transcripción es mucho más lenta)."""
    return _model is not None


def modelo_descargado() -> bool:
    """True si el modelo ya está en el disco y no hace falta internet para usarlo.
    Solo lo usa exam/diagnostico.py: cargar el modelo de verdad consume memoria."""
    try:
        from faster_whisper import WhisperModel

        WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE, local_files_only=True)
        return True
    except Exception:
        return False


def _get_model():
    """Carga el modelo una sola vez. Lanza Fallo("stt", "modelo", motivo, causa)."""
    global _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise Fallo("stt", "modelo", "dependencia", exc) from exc

        try:
            with medir("stt", "modelo", modelo=MODEL_SIZE, device=DEVICE, compute=COMPUTE_TYPE):
                log.info("Cargando Whisper %s (%s, %s)…", MODEL_SIZE, DEVICE, COMPUTE_TYPE)
                _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        except Exception as exc:
            motivo = clasificar_stt(exc)
            if motivo == "transcripcion":      # no encajó en nada conocido: fue al cargar
                motivo = "modelo_carga"
            raise Fallo("stt", "modelo", motivo, exc) from exc
        return _model


def transcribe(path: str, language: str | None = None) -> dict:
    """Transcribe la nota de voz y devuelve:

    {"text": str,            texto reconocido ("" si no se escuchó voz)
     "duration": float,      segundos del audio
     "speech": float,        segundos con voz (sin silencios)
     "words": int,           palabras reconocidas
     "wpm": float,           palabras por minuto de habla (0 si no hay voz)
     "confidence": float,    0.0 a 1.0: qué tan segura fue la transcripción
     "no_speech": float,     0.0 a 1.0: probabilidad de que no haya voz
     "codec": str,           codec del archivo recibido (opus en las notas de voz de Telegram)
     "bytes": int}           tamaño del archivo

    language: código del examen ("en"/"es"). Se fuerza para no depender del detector de Whisper.
    Lanza Fallo("stt", etapa, motivo, causa) con la etapa exacta en la que falló.
    """
    # 1) El archivo: que exista, que no esté vacío y que se pueda decodificar.
    #    Es inmediato y da un motivo preciso sin pagar la carga del modelo.
    info = sondear(path, componente="stt")

    # 2) Decodificar con PyAV propio (evita el choque faster-whisper 1.2.1 / PyAV nuevo)
    muestras = a_muestras(path, componente="stt")

    # 3) El modelo
    modelo = _get_model()

    # 4) La transcripción
    try:
        with medir("stt", "transcribir", segundos=info["segundos"], codec=info["codec"]):
            segments, meta = modelo.transcribe(
                muestras,
                language=language,          # forzado a propósito (ver el comentario del módulo)
                vad_filter=True,            # recorta silencios: mejora el texto y el cálculo de wpm
                beam_size=BEAM_SIZE,
            )

            partes: list[str] = []
            peso_total = 0.0
            suma_conf = 0.0
            suma_no_voz = 0.0
            # el generador se consume aquí: a partir de este punto meta ya está completo
            for s in segments:
                texto = s.text.strip()
                if texto:
                    partes.append(texto)
                dur = max(0.0, float(getattr(s, "end", 0.0)) - float(getattr(s, "start", 0.0)))
                peso = dur or 1.0  # un segmento sin duración válida pesa como uno
                logprob = getattr(s, "avg_logprob", None)
                if logprob is not None:
                    # avg_logprob es el logaritmo de la probabilidad media: exp() lo vuelve 0-1
                    suma_conf += math.exp(max(-10.0, float(logprob))) * peso
                suma_no_voz += float(getattr(s, "no_speech_prob", 0.0) or 0.0) * peso
                peso_total += peso
    except Fallo:
        raise
    except Exception as exc:
        raise Fallo("stt", "transcribir", clasificar_stt(exc), exc) from exc

    text = " ".join(partes).strip()
    duration = float(getattr(meta, "duration", 0.0) or 0.0) or info["segundos"]
    speech = float(getattr(meta, "duration_after_vad", 0.0) or 0.0) or duration
    words = len(text.split())
    return {
        "text": text,
        "duration": duration,
        "speech": speech,
        "words": words,
        "wpm": (words / (speech / 60)) if speech > 0 and words else 0.0,
        "confidence": (suma_conf / peso_total) if peso_total else 0.0,
        "no_speech": (suma_no_voz / peso_total) if peso_total else 1.0,
        "codec": info["codec"],
        "bytes": info["bytes"],
    }
