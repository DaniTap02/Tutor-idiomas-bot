"""Prueba del manejo de audio SIN internet y SIN el modelo de voz:

    python -m exam.test_audio

Comprueba con archivos de audio REALES (los crea PyAV) que:
  - el mp3 de edge-tts se convierte a OGG/OPUS, que es lo que Telegram pide para una nota de voz,
  - un archivo vacío, dañado, inexistente o sin pista de audio da un motivo distinto cada uno,
  - cada tipo de excepción se traduce al motivo REAL (red, reloj, servicio, memoria, dependencia...),
    que es lo que evita decirle al estudiante "¿tienes internet?" cuando el problema es otro,
  - los reintentos y el respaldo del texto a voz funcionan,
  - el registro nunca guarda el token de Telegram.

Necesita PyAV (llega con faster-whisper). NO necesita internet, ni Ollama, ni descargar Whisper.
"""
import asyncio
import fractions
import logging
import os
import sys
import tempfile
import types

# Varios casos provocan fallos a propósito y el código los registra. Se silencian para que la
# salida quede limpia (el registro ya se comprueba aparte, en la sección 6).
logging.disable(logging.CRITICAL)

from exam import audio as audio_util
from exam import registro, tts
from exam.registro import Fallo, clasificar_stt, clasificar_tts, describir, sin_secretos

ok_total = 0
fail_total = 0
CARPETA = tempfile.mkdtemp()


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK    " if condicion else "  FALLA ") + nombre)
    ok_total += bool(condicion)
    fail_total += not condicion


def motivo_de(hacer) -> str:
    """Ejecuta algo que debe fallar con Fallo y devuelve su motivo."""
    try:
        hacer()
    except Fallo as fallo:
        return fallo.motivo
    except Exception as exc:
        return f"excepcion-sin-clasificar:{type(exc).__name__}"
    return "no-fallo"


def crear_audio(ruta, formato, codec, sr, segundos, canales=1):
    """Crea un archivo de audio real con PyAV (un tono)."""
    import av
    import numpy as np

    contenedor = av.open(ruta, "w", format=formato)
    pista = contenedor.add_stream(codec, rate=sr)
    pista.layout = "mono" if canales == 1 else "stereo"
    n = int(sr * segundos)
    t = np.arange(n) / sr
    base = (0.3 * np.sin(2 * np.pi * 300 * t) * 32767).astype(np.int16)
    senal = base.reshape(1, -1) if canales == 1 else np.vstack([base, base]).reshape(1, -1)
    cuadro = av.AudioFrame.from_ndarray(senal, format="s16",
                                        layout="mono" if canales == 1 else "stereo")
    cuadro.sample_rate = sr
    cuadro.pts = 0
    cuadro.time_base = fractions.Fraction(1, sr)
    for paquete in pista.encode(cuadro):
        contenedor.mux(paquete)
    for paquete in pista.encode(None):
        contenedor.mux(paquete)
    contenedor.close()


ruta = lambda nombre: os.path.join(CARPETA, nombre)   # noqa: E731


print("1) Conversión del mp3 de edge-tts a nota de voz (OGG/OPUS)")
if not audio_util.disponible():
    print("  PyAV no está instalado: instala faster-whisper y repite (pip install -r requirements.txt)")
    raise SystemExit(1)

crear_audio(ruta("tts.mp3"), "mp3", "mp3", 24000, 8.0)          # como lo devuelve edge-tts
audio_util.a_nota_de_voz(ruta("tts.mp3"), ruta("tts.ogg"))
info = audio_util.sondear(ruta("tts.ogg"))
check("el mp3 mono de 24 kHz se convierte a opus", info["codec"] == "opus")
check("a 48 kHz, que es lo que usa Telegram", info["sr"] == 48000)
check("en mono", info["canales"] == 1)
check("y conserva la duración", 7.5 <= info["segundos"] <= 8.5)

crear_audio(ruta("st.mp3"), "mp3", "mp3", 44100, 3.0, canales=2)   # por si cambia la voz
audio_util.a_nota_de_voz(ruta("st.mp3"), ruta("st.ogg"))
check("un mp3 estéreo de 44.1 kHz también se convierte",
      audio_util.sondear(ruta("st.ogg"))["codec"] == "opus")

print("\n2) Sondeo del archivo que llega de Telegram: un motivo distinto por caso")
crear_audio(ruta("voz.ogg"), "ogg", "libopus", 48000, 2.0)         # nota de voz de Telegram
bueno = audio_util.sondear(ruta("voz.ogg"))
check("una nota de voz OGG/OPUS se lee sin convertir nada",
      bueno["codec"] == "opus" and bueno["segundos"] > 0)
check("archivo que no existe -> archivo_falta",
      motivo_de(lambda: audio_util.sondear(ruta("nohay.ogg"))) == "archivo_falta")
open(ruta("vacio.ogg"), "wb").close()
check("archivo vacío (0 bytes) -> archivo_vacio",
      motivo_de(lambda: audio_util.sondear(ruta("vacio.ogg"))) == "archivo_vacio")
with open(ruta("roto.ogg"), "wb") as f:
    f.write(b"esto no es audio" * 50)
check("archivo dañado -> formato",
      motivo_de(lambda: audio_util.sondear(ruta("roto.ogg"))) == "formato")
with open(ruta("texto.ogg"), "wb") as f:
    f.write(b"%PDF-1.4\n" + b"0" * 500)
check("archivo de otro tipo -> formato",
      motivo_de(lambda: audio_util.sondear(ruta("texto.ogg"))) == "formato")
check("convertir algo que no es audio -> convertir",
      motivo_de(lambda: audio_util.a_nota_de_voz(ruta("roto.ogg"), ruta("x.ogg"))) == "convertir")

print("\n3) Cada excepción se traduce al motivo REAL (texto a voz)")
import aiohttp  # noqa: E402
import edge_tts.exceptions as ex_edge  # noqa: E402

casos_tts = [
    ("sin DNS / firewall / proxy", aiohttp.ClientConnectorError(None, OSError("no DNS")), "red"),
    ("se agotó la espera", asyncio.TimeoutError(), "tiempo"),
    ("reloj del PC desajustado", ex_edge.SkewAdjustmentError("skew"), "reloj"),
    ("el servicio no devolvió audio", ex_edge.NoAudioReceived("vacío"), "servicio"),
    ("respuesta inesperada (403...)", ex_edge.UnexpectedResponse("403"), "servicio"),
    ("conexión cortada", ex_edge.WebSocketError("cerrado"), "corte"),
    ("voz o velocidad inválidas", ValueError("invalid rate"), "servicio"),
    ("no se pudo escribir el archivo", PermissionError("en uso"), "escritura"),
]
for nombre, exc, esperado in casos_tts:
    obtenido = clasificar_tts(exc)
    check(f"{nombre} -> '{esperado}'", obtenido == esperado)

check("solo 'red' significa problema de conexión: un error del servicio NO lo es",
      clasificar_tts(ex_edge.NoAudioReceived("x")) != "red")

print("\n4) Cada excepción se traduce al motivo REAL (voz a texto)")
import av  # noqa: E402
from huggingface_hub.errors import LocalEntryNotFoundError  # noqa: E402

casos_stt = [
    ("falta faster-whisper", ModuleNotFoundError("No module named 'faster_whisper'"), "dependencia"),
    ("el modelo no está descargado", LocalEntryNotFoundError("sin caché"), "modelo_descarga"),
    ("sin memoria", MemoryError(), "memoria"),
    ("sin memoria (mensaje del motor)", RuntimeError("CUDA out of memory"), "memoria"),
    ("audio ilegible", av.error.EOFError(541478725, "End of file", "x.ogg"), "formato"),
]
for nombre, exc, esperado in casos_stt:
    check(f"{nombre} -> '{esperado}'", clasificar_stt(exc) == esperado)

print("\n5) Reintentos y respaldo del texto a voz")


class CommunicateFalso:
    """Imita edge_tts.Communicate: falla las primeras veces y luego escribe el audio."""

    fallos_restantes = 0
    excepcion = None

    def __init__(self, text, voice, rate="+0%"):
        self.text = text

    async def save(self, destino):
        if CommunicateFalso.fallos_restantes > 0:
            CommunicateFalso.fallos_restantes -= 1
            raise CommunicateFalso.excepcion
        with open(destino, "wb") as f:
            f.write(b"ID3" + b"\0" * 200)


def instalar_edge_falso():
    modulo = types.ModuleType("edge_tts")
    modulo.Communicate = CommunicateFalso
    sys.modules["edge_tts"] = modulo


instalar_edge_falso()
tts.ESPERA_ENTRE_INTENTOS = 0.0     # sin esperas en la prueba
tts.CONVERTIR_A_NOTA_VOZ = False    # el mp3 falso no es convertible

CommunicateFalso.fallos_restantes = 0
info = asyncio.run(tts.synthesize("Hola", "en", ruta("ok.mp3")))
check("a la primera -> un intento", info["intentos"] == 1 and info["motor"] == "edge-tts")
check("devuelve la ruta y el tamaño del audio", info["bytes"] > 0 and os.path.exists(info["ruta"]))

CommunicateFalso.fallos_restantes = 2
CommunicateFalso.excepcion = ex_edge.WebSocketError("se cortó")
info = asyncio.run(tts.synthesize("Hola", "en", ruta("r.mp3")))
check("un fallo pasajero se reintenta y acaba funcionando", info["intentos"] == 3)

CommunicateFalso.fallos_restantes = 99
CommunicateFalso.excepcion = PermissionError("archivo en uso")
check("un fallo que NO es pasajero no se reintenta",
      motivo_de(lambda: asyncio.run(tts.synthesize("Hola", "en", ruta("p.mp3")))) == "escritura")

CommunicateFalso.excepcion = aiohttp.ClientConnectorError(None, OSError("no DNS"))
check("sin conexión y sin gTTS -> motivo 'red' (la causa real, no un mensaje genérico)",
      motivo_de(lambda: asyncio.run(tts.synthesize("Hola", "en", ruta("n.mp3")))) == "red")

modulo_gtts = types.ModuleType("gtts")


class GTTSFalso:
    def __init__(self, text=None, lang=None, slow=False):
        pass

    def save(self, destino):
        with open(destino, "wb") as f:
            f.write(b"ID3" + b"\0" * 100)


modulo_gtts.gTTS = GTTSFalso
sys.modules["gtts"] = modulo_gtts
info = asyncio.run(tts.synthesize("Hola", "en", ruta("g.mp3")))
check("si edge-tts no puede y gTTS está instalado, se usa el respaldo", info["motor"] == "gTTS")
del sys.modules["gtts"]

check("un texto vacío no se manda al servicio",
      motivo_de(lambda: asyncio.run(tts.synthesize("   ", "en", ruta("v.mp3")))) == "vacio")

print("\n6) El registro no guarda secretos y sí guarda la causa")
TOKEN = "123456789:AAEhBOweik6ad9r_Q458PzFBu0ZDWfqlQjA"
check("un token de Telegram se tapa",
      TOKEN not in sin_secretos(f"error al llamar https://api.telegram.org/bot{TOKEN}/sendVoice"))
check("y queda la marca de que se tapó",
      "<token-oculto>" in sin_secretos(f"bot{TOKEN}/sendVoice"))
check("una clave con nombre también se tapa",
      "secreta" not in sin_secretos("Authorization: clave-secreta-123"))

try:
    raise ValueError("fallo de arriba")
except ValueError as arriba:
    try:
        raise RuntimeError("fallo visible") from arriba
    except RuntimeError as visible:
        texto = describir(visible)
check("la descripción lleva el tipo completo de la excepción", "builtins.RuntimeError" in texto)
check("y el mensaje original", "fallo visible" in texto)
check("y la causa de más abajo", "fallo de arriba" in texto)

fallo = Fallo("stt", "modelo", "memoria", MemoryError("sin RAM"))
check("un Fallo dice componente, etapa y motivo",
      fallo.componente == "stt" and fallo.etapa == "modelo" and fallo.motivo == "memoria")
check("y guarda el error técnico original", "MemoryError" in fallo.tecnico)
check("todos los motivos usados están documentados",
      all(m in registro.MOTIVOS for m in
          ("red", "tiempo", "reloj", "servicio", "corte", "vacio", "escritura", "formato",
           "convertir", "archivo_vacio", "archivo_falta", "envio", "envio_prohibido",
           "dependencia", "modelo_descarga", "modelo_carga", "memoria", "transcripcion", "sin_voz")))

print(f"\nResultado: {ok_total} OK, {fail_total} con falla")


def test_sin_fallas():
    """pytest: todas las comprobaciones de este archivo pasaron (se ejecutan al importarlo)."""
    assert fail_total == 0, f"{fail_total} comprobaciones con falla (mira la salida con: pytest -s)"


if __name__ == "__main__":
    raise SystemExit(1 if fail_total else 0)
