"""Texto a voz para la parte de escucha del examen.

Usa edge-tts (voces neuronales de Microsoft; necesita internet, igual que Telegram).
Si edge-tts falla y tienes instalado gTTS (opcional: pip install gTTS), se usa como respaldo.
Genera archivos .mp3, que Telegram acepta como nota de voz sin convertir nada (no necesitas ffmpeg).
"""
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# Varias voces para que los audios no suenen todos igual (se elige por número de pregunta).
VOICES = {
    "en": ["en-US-JennyNeural", "en-GB-RyanNeural", "en-US-GuyNeural"],
    "es": ["es-CO-SalomeNeural", "es-CO-GonzaloNeural"],
}

TIMEOUT_SECONDS = 40


def _gtts(text: str, language: str, path: str, slow: bool) -> None:
    from gtts import gTTS  # opcional: solo se importa si edge-tts falló

    gTTS(text=text, lang=language, slow=slow).save(path)


async def synthesize(text: str, language: str, path: str, rate: str = "+0%", voice_index: int = 0) -> None:
    """Guarda en `path` (.mp3) el texto leído en voz alta.
    rate: velocidad de edge-tts, por ejemplo "-15%" (más lento) o "+0%".
    Lanza RuntimeError si no se pudo generar el audio por ningún medio."""
    voces = VOICES[language]
    voz = voces[voice_index % len(voces)]
    try:
        import edge_tts

        await asyncio.wait_for(edge_tts.Communicate(text, voz, rate=rate).save(path), timeout=TIMEOUT_SECONDS)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise RuntimeError("edge-tts devolvió un audio vacío")
        return
    except Exception as error_edge:
        logger.warning("edge-tts falló (%s); intentando con gTTS", error_edge)
        try:
            await asyncio.to_thread(_gtts, text, language, path, rate.startswith("-"))
        except Exception as error_gtts:
            raise RuntimeError(f"No se pudo generar el audio (edge-tts: {error_edge}; gTTS: {error_gtts})") from error_edge
