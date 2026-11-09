"""Manejo de archivos de audio con PyAV: sondeo y conversión a nota de voz.

PyAV viene instalado con faster-whisper (es una de sus dependencias) y trae las librerías de FFmpeg
dentro del paquete, así que NO hace falta instalar ffmpeg aparte.

Dos usos:

1. `sondear()` revisa un archivo ANTES de pasárselo a Whisper: que exista, que no esté vacío, que se
   pueda decodificar y cuánto dura. Así, un archivo dañado o un formato inesperado dan un error
   preciso y rápido, en vez de un "no pude procesar tu audio" después de cargar el modelo.

2. `a_nota_de_voz()` convierte el .mp3 que devuelve edge-tts a .ogg con OPUS. La API de Telegram pide
   ese formato para sendVoice ("your audio must be in an .OGG file encoded with OPUS; other formats
   may be sent as Audio or Document"), así que enviar el mp3 como nota de voz puede ser rechazado.
"""
import os

from exam.registro import Fallo, medir

OPUS_RATE = 48000   # Opus solo acepta 8, 12, 16, 24 o 48 kHz; 48 kHz es el que usa Telegram


def disponible() -> bool:
    """True si PyAV se puede importar (llega con faster-whisper)."""
    try:
        import av  # noqa: F401
        return True
    except Exception:
        return False


def _revisar_archivo(ruta: str, componente: str, etapa: str) -> int:
    if not os.path.exists(ruta):
        raise Fallo(componente, etapa, "archivo_falta", detalle=f"no existe: {os.path.basename(ruta)}")
    tamano = os.path.getsize(ruta)
    if tamano == 0:
        raise Fallo(componente, etapa, "archivo_vacio", detalle="0 bytes")
    return tamano


def sondear(ruta: str, componente: str = "stt") -> dict:
    """Revisa y describe un archivo de audio sin transcribirlo.

    Devuelve {"bytes", "segundos", "codec", "sr", "canales"}.
    Lanza Fallo con motivo archivo_falta, archivo_vacio, dependencia o formato.
    """
    tamano = _revisar_archivo(ruta, componente, "sondear")
    try:
        import av
    except Exception as exc:
        raise Fallo(componente, "sondear", "dependencia", exc) from exc

    try:
        with medir(componente, "sondear", bytes=tamano):
            with av.open(ruta) as contenedor:
                pista = next((s for s in contenedor.streams if s.type == "audio"), None)
                if pista is None:
                    raise Fallo(componente, "sondear", "formato", detalle="el archivo no tiene pista de audio")
                segundos = float(contenedor.duration / av.time_base) if contenedor.duration else 0.0
                cc = pista.codec_context
                return {
                    "bytes": tamano,
                    "segundos": round(segundos, 2),
                    "codec": cc.name,
                    "sr": cc.sample_rate,
                    "canales": cc.channels,
                }
    except Fallo:
        raise
    except Exception as exc:
        # av.error.EOFError (archivo vacío o truncado), av.FFmpegError (formato ilegible)...
        raise Fallo(componente, "sondear", "formato", exc) from exc


def a_nota_de_voz(origen: str, destino: str, componente: str = "tts") -> None:
    """Convierte `origen` (el .mp3 de edge-tts) a `destino` (.ogg con OPUS), que es lo que pide
    Telegram para una nota de voz. Lanza Fallo con motivo convertir, dependencia o formato."""
    _revisar_archivo(origen, componente, "convertir")
    try:
        import av
    except Exception as exc:
        raise Fallo(componente, "convertir", "dependencia", exc) from exc

    try:
        with medir(componente, "convertir"):
            with av.open(origen) as entrada, av.open(destino, "w", format="ogg") as salida:
                pista = next((s for s in entrada.streams if s.type == "audio"), None)
                if pista is None:
                    raise Fallo(componente, "convertir", "formato", detalle="el mp3 no tiene pista de audio")
                destino_pista = salida.add_stream("libopus", rate=OPUS_RATE)
                destino_pista.layout = "mono"
                remuestreador = av.AudioResampler(format="s16", layout="mono", rate=OPUS_RATE)

                for cuadro in entrada.decode(pista):
                    for remuestreado in remuestreador.resample(cuadro):
                        for paquete in destino_pista.encode(remuestreado):
                            salida.mux(paquete)
                for remuestreado in remuestreador.resample(None) or []:   # vaciar el remuestreador
                    for paquete in destino_pista.encode(remuestreado):
                        salida.mux(paquete)
                for paquete in destino_pista.encode(None):                # vaciar el codificador
                    salida.mux(paquete)
    except Fallo:
        raise
    except Exception as exc:
        raise Fallo(componente, "convertir", "convertir", exc) from exc

    if not os.path.exists(destino) or os.path.getsize(destino) == 0:
        raise Fallo(componente, "convertir", "convertir", detalle="la conversión dejó un archivo vacío")


def a_muestras(ruta: str, componente: str = "stt"):
    """Decodifica `ruta` a un arreglo float32 mono a 16 kHz, que es lo que espera Whisper.

    Se hace aquí (con PyAV) en vez de pasarle la ruta a faster-whisper porque su decodificador
    llama a av.open(..., metadata_errors=...), argumento que PyAV 17+ ya no acepta: con
    faster-whisper 1.2.1 y un PyAV nuevo daba "TypeError: open() got an unexpected keyword
    argument 'metadata_errors'". Así funciona con cualquier versión de PyAV.
    Lanza Fallo con motivo dependencia o formato.
    """
    try:
        import av
        import numpy as np
    except Exception as exc:
        raise Fallo(componente, "decodificar", "dependencia", exc) from exc

    try:
        with medir(componente, "decodificar"):
            remuestreador = av.AudioResampler(format="s16", layout="mono", rate=16000)
            trozos = []
            with av.open(ruta) as contenedor:
                pista = next((s for s in contenedor.streams if s.type == "audio"), None)
                if pista is None:
                    raise Fallo(componente, "decodificar", "formato", detalle="el archivo no tiene pista de audio")
                for cuadro in contenedor.decode(pista):
                    for r in remuestreador.resample(cuadro):
                        trozos.append(r.to_ndarray().reshape(-1))
                for r in remuestreador.resample(None) or []:
                    trozos.append(r.to_ndarray().reshape(-1))
    except Fallo:
        raise
    except Exception as exc:
        raise Fallo(componente, "decodificar", "formato", exc) from exc

    if not trozos:
        raise Fallo(componente, "decodificar", "formato", detalle="el audio no tiene muestras")
    return np.concatenate(trozos).astype(np.float32) / 32768.0
