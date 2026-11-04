"""Transcripción de notas de voz con faster-whisper (local, sin internet)."""
from faster_whisper import WhisperModel 
_model = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:  # se carga una sola vez
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    return _model


def transcribe(path: str) -> tuple[str, str]:
    """Devuelve (texto, idioma_detectado). Es síncrona: llámala con asyncio.to_thread."""
    segments, info = _get_model().transcribe(path, vad_filter=True, beam_size=5)
    texto = " ".join(s.text.strip() for s in segments).strip()
    return texto, info.language