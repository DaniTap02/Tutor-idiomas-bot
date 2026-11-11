"""Registro de errores y diagnóstico de las partes de audio.

Antes, cualquier fallo del audio acababa en un `except Exception` y el estudiante veía siempre el
mismo mensaje ("¿tienes internet?", "revisa que faster-whisper esté instalado"), que muchas veces
era FALSO: el error real podía ser el reloj del PC, el servicio de voz respondiendo sin audio, el
envío a Telegram o incluso el borrado de la carpeta temporal.

Este módulo separa las dos cosas:
  - `Fallo`: excepción que lleva la ETAPA, el MOTIVO y la causa original. El flujo la usa para
    decidir qué mensaje sencillo le muestra al estudiante.
  - `clasificar()` y `describir()`: traducen una excepción cualquiera al motivo real y a una línea
    técnica corta para el registro (`logging`), con el tipo de excepción y su mensaje original.
  - `medir()`: mide cuánto tardó cada etapa y lo registra.

Nada de lo que se registra incluye el token de Telegram ni claves: `sin_secretos()` las tapa.
"""
import logging
import re
import time
from contextlib import contextmanager

log = logging.getLogger(__name__)

# Token de bot de Telegram (123456789:AA...) y cabeceras de autorización, por si aparecen en un
# mensaje de error de una librería. No deben quedar en el registro.
_SECRETOS = [
    # Token de bot: sin \b delante, porque en las URLs va pegado a "bot"
    # (api.telegram.org/bot123456789:AAEh.../sendVoice) y entonces no hay límite de palabra.
    (re.compile(r"(?<!\d)\d{6,}:[A-Za-z0-9_-]{30,}"), "<token-oculto>"),
    (re.compile(r"(?i)\b(authorization|api[-_]?key|token|password)\b\s*[:=]\s*\S+"), r"\1=<oculto>"),
]


def sin_secretos(texto: str) -> str:
    """Quita tokens y claves del texto antes de registrarlo."""
    for patron, reemplazo in _SECRETOS:
        texto = patron.sub(reemplazo, texto)
    return texto


def _texto_de(exc: BaseException) -> str:
    """El mensaje de una excepción, sin secretos y sin reventar.

    `str(exc)` puede lanzar a su vez: hay excepciones de librerías cuyo __str__ falla si el objeto
    quedó a medio construir (pasa con aiohttp). Un registro de errores que revienta deja al bot sin
    mensaje y oculta justo lo que se quería ver, así que aquí nunca se propaga nada.
    """
    try:
        return sin_secretos(str(exc)).replace("\n", " ").strip()
    except Exception:
        try:
            return sin_secretos(repr(exc.args)).replace("\n", " ").strip()
        except Exception:
            return "<mensaje ilegible>"


def describir(exc: BaseException, limite: int = 300) -> str:
    """Línea técnica corta de una excepción: módulo, tipo, mensaje y la causa de más abajo."""
    try:
        tipo = f"{type(exc).__module__}.{type(exc).__name__}"
    except Exception:
        return "<excepción ilegible>"
    mensaje = _texto_de(exc)
    linea = f"{tipo}: {mensaje}" if mensaje else tipo
    try:
        causa = exc.__cause__ or exc.__context__
    except Exception:
        causa = None
    if causa is not None and causa is not exc:
        c_tipo = f"{type(causa).__module__}.{type(causa).__name__}"
        c_msg = _texto_de(causa)
        linea += f"  <- {c_tipo}: {c_msg}" if c_msg else f"  <- {c_tipo}"
    return linea[:limite]


class Fallo(Exception):
    """Fallo de una etapa concreta del audio.

    componente: "tts", "stt" o "telegram".
    etapa:      en qué paso ocurrió ("generar", "convertir", "enviar", "descargar", "modelo"...).
    motivo:     código corto de la causa (ver MOTIVOS). Es lo que decide el mensaje al estudiante.
    causa:      la excepción original, para el registro.
    """

    def __init__(self, componente: str, etapa: str, motivo: str,
                 causa: BaseException | None = None, detalle: str = ""):
        self.componente = componente
        self.etapa = etapa
        self.motivo = motivo
        self.causa = causa
        self.detalle = detalle
        tecnico = describir(causa) if causa is not None else detalle
        super().__init__(f"[{componente}/{etapa}] {motivo}: {tecnico}")

    @property
    def tecnico(self) -> str:
        """Lo que se escribe en el registro (nunca se le muestra al estudiante)."""
        if self.causa is not None:
            return describir(self.causa)
        return self.detalle or self.motivo


# Qué significa cada motivo. Sirve para el registro y para exam/diagnostico.py.
MOTIVOS = {
    # --- Texto a voz (edge-tts) ---
    "red": "no se pudo conectar con el servicio de voz (DNS, proxy, firewall o sin internet)",
    "tiempo": "el servicio de voz tardó más de lo permitido",
    "reloj": "el servicio rechazó el token horario (reloj del PC desajustado o cambio de la API)",
    "servicio": "el servicio respondió pero no entregó audio (voz inválida, texto rechazado o 403)",
    "corte": "la conexión con el servicio se cortó a mitad del audio",
    "vacio": "el audio generado quedó vacío",
    "escritura": "no se pudo escribir el archivo de audio en el disco",
    # --- Conversión y archivos (PyAV) ---
    "formato": "el audio no se pudo decodificar (archivo dañado o formato inesperado)",
    "convertir": "no se pudo convertir el audio al formato de nota de voz (OGG/OPUS)",
    "archivo_vacio": "el archivo de audio llegó vacío o sin contenido",
    "archivo_falta": "el archivo de audio no existe en la ruta esperada",
    # --- Envío por Telegram ---
    "envio": "el audio se generó bien, pero Telegram no lo aceptó",
    "envio_prohibido": "la cuenta no permite recibir notas de voz",
    # --- Voz a texto (faster-whisper) ---
    "dependencia": "falta una librería en el entorno (faster-whisper o PyAV)",
    "modelo_descarga": "el modelo de voz no está descargado y no se pudo bajar",
    "modelo_carga": "el modelo de voz no se pudo cargar",
    "memoria": "no hubo memoria suficiente para cargar el modelo de voz",
    "transcripcion": "el modelo falló al transcribir el audio",
    "sin_voz": "no se reconoció voz en la grabación",
    # --- Traducción y detección de idioma (servidor MCP de Lara Translate) ---
    "lara_sin_config": "faltan LARA_ACCESS_KEY_ID o LARA_ACCESS_KEY_SECRET en el .env",
    "lara_servidor": "no se pudo arrancar el servidor MCP de Lara (falta Node.js/npx o falló npx)",
    "lara_credenciales": "Lara rechazó las credenciales (Access Key ID o Secret inválidos)",
    "lara_cuota": "se agotó la cuota del plan de Lara o hay demasiadas peticiones seguidas",
    "lara_tiempo": "Lara tardó más de lo permitido en responder",
    "lara_red": "no se pudo conectar con el servicio de Lara",
    "lara_servicio": "Lara respondió con un error o con un formato inesperado",
    # --- Otros ---
    "desconocido": "error no clasificado: revisar el registro",
}


def _es(exc: BaseException, modulo: str, *nombres: str) -> bool:
    """True si la excepción (o su causa) es de ese módulo y nombre, sin importar el módulo."""
    vistos = 0
    actual: BaseException | None = exc
    while actual is not None and vistos < 5:
        tipo = type(actual)
        if tipo.__module__.startswith(modulo) and (not nombres or tipo.__name__ in nombres):
            return True
        siguiente = actual.__cause__ or actual.__context__
        actual = None if siguiente is actual else siguiente
        vistos += 1
    return False


def clasificar_tts(exc: BaseException) -> str:
    """Motivo real de un fallo al generar el audio con edge-tts."""
    import asyncio

    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "tiempo"
    # Las excepciones propias de edge-tts significan que SÍ hubo conexión: el servicio respondió mal.
    if _es(exc, "edge_tts", "SkewAdjustmentError"):
        return "reloj"
    if _es(exc, "edge_tts", "NoAudioReceived", "UnexpectedResponse", "UnknownResponse"):
        return "servicio"
    if _es(exc, "edge_tts", "WebSocketError"):
        return "corte"
    if _es(exc, "edge_tts"):
        return "servicio"
    if _es(exc, "gtts"):           # el respaldo respondió con un error propio
        return "servicio"
    # aiohttp, requests o sockets: aquí sí es un problema de red o de bloqueo
    if _es(exc, "aiohttp") or _es(exc, "socket") or _es(exc, "urllib3") or _es(exc, "requests"):
        return "red"
    if isinstance(exc, ConnectionError):
        return "red"
    if isinstance(exc, (PermissionError, FileNotFoundError, IsADirectoryError)):
        return "escritura"
    if isinstance(exc, ValueError):
        return "servicio"   # edge-tts valida la voz y el rate con ValueError
    if isinstance(exc, OSError):
        return "red"        # errores de socket de más abajo (no los de archivo, ya atrapados)
    return "desconocido"


def clasificar_stt(exc: BaseException) -> str:
    """Motivo real de un fallo al transcribir con faster-whisper."""
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return "dependencia"
    if isinstance(exc, MemoryError):
        return "memoria"
    if _es(exc, "huggingface_hub", "LocalEntryNotFoundError"):
        return "modelo_descarga"
    if _es(exc, "huggingface_hub") or _es(exc, "httpx") or _es(exc, "requests"):
        return "modelo_descarga"
    if _es(exc, "av"):
        return "formato"
    texto = _texto_de(exc).lower()
    if "out of memory" in texto or "cannot allocate" in texto or "bad_alloc" in texto:
        return "memoria"
    if "unable to open" in texto or "no such file" in texto:
        return "archivo_falta"
    return "transcripcion"


def clasificar_lara(error: BaseException | str) -> str:
    """Motivo real de un fallo del servidor MCP de Lara.

    `error` puede ser una excepción (el proceso no arrancó, se agotó el tiempo...) o el texto de
    error que devolvió la herramienta (`isError`), por ejemplo "Unauthorized"."""
    import asyncio

    if isinstance(error, BaseException):
        if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
            return "lara_tiempo"
        if isinstance(error, (FileNotFoundError, NotADirectoryError, PermissionError)):
            return "lara_servidor"   # no se encontró npx / Node.js
        texto = _texto_de(error).lower()
    else:
        texto = str(error).lower()
    if any(p in texto for p in ("unauthorized", "401", "403", "forbidden", "invalid credentials",
                                "access key")):
        return "lara_credenciales"
    if any(p in texto for p in ("quota", "limit", "429", "402", "too many", "exceeded", "payment")):
        return "lara_cuota"
    if any(p in texto for p in ("timeout", "timed out")):
        return "lara_tiempo"
    if any(p in texto for p in ("enotfound", "econnrefused", "econnreset", "network", "getaddrinfo",
                                "fetch failed")):
        return "lara_red"
    if any(p in texto for p in ("connection closed", "npx", "spawn", "enoent")):
        return "lara_servidor"
    return "lara_servicio"


@contextmanager
def medir(componente: str, etapa: str, **datos):
    """Mide y registra cuánto tardó una etapa. Al fallar, registra el error real con su tipo.

        with medir("tts", "generar", nivel="A1"):
            ...
    """
    extra = " ".join(f"{k}={v}" for k, v in datos.items())
    inicio = time.monotonic()
    try:
        yield
    except BaseException as exc:
        ms = (time.monotonic() - inicio) * 1000
        log.warning("[%s/%s] FALLO en %.0f ms %s | %s", componente, etapa, ms, extra, describir(exc))
        raise
    else:
        ms = (time.monotonic() - inicio) * 1000
        log.info("[%s/%s] ok en %.0f ms %s", componente, etapa, ms, extra)


def registrar_fallo(fallo: Fallo) -> None:
    """Deja en el registro el motivo real y el mensaje técnico original de un Fallo."""
    log.error("[%s/%s] %s (%s) | %s", fallo.componente, fallo.etapa, fallo.motivo,
              MOTIVOS.get(fallo.motivo, "sin descripción"), fallo.tecnico)
