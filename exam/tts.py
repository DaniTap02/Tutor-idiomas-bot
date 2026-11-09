"""Texto a voz para la parte de ESCUCHA del examen.

Motor principal: edge-tts (voces neuronales de Microsoft, por internet). Respaldo opcional: gTTS.
edge-tts entrega .mp3, y la API de Telegram pide .ogg con OPUS para una nota de voz, así que el mp3
se convierte con PyAV (viene con faster-whisper; no hace falta ffmpeg). Si la conversión no se puede
hacer, se devuelve el mp3 y el bot lo envía como archivo de audio en vez de nota de voz.

Cada etapa falla con `Fallo` (ver exam/registro.py), que lleva la etapa y el MOTIVO real:
  generar   -> red | tiempo | reloj | servicio | corte | vacio | escritura
  respaldo  -> lo mismo, con gTTS
  convertir -> convertir | formato | dependencia   (no es grave: se sigue con el mp3)

Así el bot ya NO le dice al estudiante "¿tienes internet?" cuando el problema es otro: solo el
motivo "red" significa que no se pudo conectar.

Variables de entorno (todas opcionales):
  TTS_TIMEOUT    segundos de espera por audio (por defecto 40)
  TTS_INTENTOS   intentos con edge-tts antes de pasar al respaldo (por defecto 3)
  TTS_NOTA_VOZ   "0" para no convertir a OGG/OPUS y enviar siempre el mp3 como audio
"""
import asyncio
import logging
import os

from exam import audio as audio_util
from exam.registro import Fallo, clasificar_tts, medir

log = logging.getLogger(__name__)

# Varias voces para que los audios no suenen todos igual (la elige el código por número de pregunta).
VOICES = {
    "en": ["en-US-JennyNeural", "en-GB-RyanNeural", "en-US-GuyNeural"],
    "es": ["es-CO-SalomeNeural", "es-CO-GonzaloNeural"],
}

TIMEOUT_SECONDS = float(os.getenv("TTS_TIMEOUT") or 40)
INTENTOS = max(1, int(os.getenv("TTS_INTENTOS") or 3))
CONVERTIR_A_NOTA_VOZ = os.getenv("TTS_NOTA_VOZ", "1") != "0"
ESPERA_ENTRE_INTENTOS = 1.5   # segundos; se duplica en cada reintento

# Motivos que pueden ser pasajeros: vale la pena reintentar. "escritura" y "dependencia" no lo son.
REINTENTABLES = {"red", "tiempo", "corte", "servicio", "vacio", "reloj"}

# Host al que se conecta edge-tts (útil para revisar el firewall; ver exam/diagnostico.py)
HOST_EDGE_TTS = "speech.platform.bing.com"


def _borrar(ruta: str) -> None:
    """Borra un audio a medio escribir para que el siguiente paso no lo dé por bueno."""
    try:
        if os.path.exists(ruta):
            os.remove(ruta)
    except OSError:
        pass


def _tamano(ruta: str) -> int:
    try:
        return os.path.getsize(ruta) if os.path.exists(ruta) else 0
    except OSError:
        return 0


def voz_de(language: str, voice_index: int = 0) -> str:
    voces = VOICES.get(language) or VOICES["en"]
    return voces[voice_index % len(voces)]


async def _edge(text: str, voz: str, ruta: str, rate: str) -> None:
    """Un intento con edge-tts. Lanza Fallo("tts", "generar", motivo, causa)."""
    try:
        import edge_tts
    except Exception as exc:
        raise Fallo("tts", "generar", "dependencia", exc) from exc

    try:
        with medir("tts", "generar", voz=voz):
            await asyncio.wait_for(
                edge_tts.Communicate(text, voz, rate=rate).save(ruta), timeout=TIMEOUT_SECONDS
            )
    except Exception as exc:
        _borrar(ruta)
        raise Fallo("tts", "generar", clasificar_tts(exc), exc) from exc

    if _tamano(ruta) == 0:
        _borrar(ruta)
        raise Fallo("tts", "generar", "vacio", detalle="edge-tts devolvió un audio vacío")


async def _gtts(text: str, language: str, ruta: str, lento: bool) -> None:
    """Respaldo con gTTS (opcional: pip install gTTS). Lanza Fallo("tts", "respaldo", ...)."""
    try:
        from gtts import gTTS
    except Exception as exc:
        raise Fallo("tts", "respaldo", "dependencia", exc) from exc

    def guardar() -> None:
        gTTS(text=text, lang=language, slow=lento).save(ruta)

    try:
        with medir("tts", "respaldo"):
            await asyncio.to_thread(guardar)
    except Exception as exc:
        _borrar(ruta)
        raise Fallo("tts", "respaldo", clasificar_tts(exc), exc) from exc

    if _tamano(ruta) == 0:
        _borrar(ruta)
        raise Fallo("tts", "respaldo", "vacio", detalle="gTTS devolvió un audio vacío")


async def synthesize(text: str, language: str, path: str, rate: str = "+0%",
                     voice_index: int = 0) -> dict:
    """Genera el audio del texto y devuelve con qué quedó:

        {"ruta": str,       archivo que hay que enviar (puede ser el .ogg convertido)
         "formato": str,    "ogg" (nota de voz) o "mp3" (archivo de audio)
         "motor": str,      "edge-tts" o "gTTS"
         "intentos": int,   intentos que hizo falta
         "bytes": int}

    `path` es la ruta del .mp3; si se logra convertir, el .ogg queda al lado.
    rate: velocidad de edge-tts, por ejemplo "-15%" (más lento) o "+0%".
    Lanza Fallo("tts", etapa, motivo, causa) si no se pudo generar por ningún medio.
    """
    if not text or not text.strip():
        raise Fallo("tts", "generar", "vacio", detalle="el texto a leer está vacío")

    voz = voz_de(language, voice_index)
    motor = "edge-tts"
    ultimo: Fallo | None = None
    intentos = 0

    for intento in range(1, INTENTOS + 1):
        intentos = intento
        try:
            await _edge(text, voz, path, rate)
            ultimo = None
            break
        except Fallo as fallo:
            ultimo = fallo
            if fallo.motivo not in REINTENTABLES or intento == INTENTOS:
                break
            espera = ESPERA_ENTRE_INTENTOS * (2 ** (intento - 1))
            log.warning("edge-tts falló (%s). Reintento %d/%d en %.1f s | %s",
                        fallo.motivo, intento + 1, INTENTOS, espera, fallo.tecnico)
            await asyncio.sleep(espera)

    if ultimo is not None:
        # edge-tts no pudo: se intenta el respaldo, si está instalado
        log.warning("edge-tts agotó %d intento(s) (%s). Probando gTTS | %s",
                    intentos, ultimo.motivo, ultimo.tecnico)
        try:
            await _gtts(text, language, path, rate.startswith("-"))
            motor = "gTTS"
        except Fallo as respaldo:
            # Se informa del fallo del MOTOR PRINCIPAL, que es el que dice la causa real.
            # El del respaldo queda en el registro (suele ser "no está instalado").
            log.warning("el respaldo gTTS tampoco pudo (%s) | %s", respaldo.motivo, respaldo.tecnico)
            raise ultimo

    ruta, formato = path, "mp3"
    if CONVERTIR_A_NOTA_VOZ and audio_util.disponible():
        ogg = os.path.splitext(path)[0] + ".ogg"
        try:
            audio_util.a_nota_de_voz(path, ogg)
            ruta, formato = ogg, "ogg"
        except Fallo as fallo:
            # No es grave: se envía el mp3 como archivo de audio en vez de nota de voz.
            log.warning("no pude convertir a nota de voz (%s): se enviará como audio | %s",
                        fallo.motivo, fallo.tecnico)

    return {"ruta": ruta, "formato": formato, "motor": motor,
            "intentos": intentos, "bytes": _tamano(ruta)}
