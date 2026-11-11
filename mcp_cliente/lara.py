"""Cliente MCP del servidor oficial de Lara Translate (github.com/translated/lara-mcp).

El bot es el CLIENTE MCP (SDK oficial de Python, paquete `mcp`) y el servidor de Lara corre en
local por stdio con `npx -y @translated/lara-mcp@<versión>` (necesita Node.js 22.23.4 o superior).
De las 22 herramientas que expone el servidor, el bot usa exactamente DOS:

  detect_language  {"text": str, "hint"?: str, "passlist"?: [str]}
                   -> {"language": "en-US", "contentType": ..., "predictions": [{"language", "confidence"}]}
  translate        {"text": [{"text": str}], "target": str, "source"?: str, ...}
                   -> {"items": [{"text": "..."}]}

Una sola sesión MCP abierta durante toda la vida del bot: la abre una tarea "dueña" (las librerías
de MCP usan anyio y exigen que la sesión se abra y se cierre en la MISMA tarea), y cualquier
manejador del bot la usa con `call_tool`. Si el servidor se cae, la siguiente llamada lo levanta de
nuevo una vez.

Nunca se penaliza al estudiante por una falla de Lara: si no está configurada, no responde o agotó
la cuota, detectar_idioma() devuelve None (el calificador decide como siempre) y traducir() lanza
`Fallo("lara", ...)` con el motivo real (ver exam/registro.py) para que el bot diga que la
traducción no está disponible.

Variables de entorno (.env; ver .env.example):
  LARA_ACCESS_KEY_ID, LARA_ACCESS_KEY_SECRET   credenciales (obligatorias para usar Lara)
  LARA_MCP_PAQUETE      paquete npm del servidor (por defecto @translated/lara-mcp@2.2.0)
  LARA_TIMEOUT          segundos de espera por llamada (por defecto 15)
  LARA_INICIO_TIMEOUT   segundos para arrancar el servidor; la 1.ª vez npx lo descarga (por defecto 90)
  LARA_MIN_PALABRAS     por debajo de esto no se detecta el idioma: no hay confianza (por defecto 4)
"""
import asyncio
import json
import logging
import os
import shutil
from collections import OrderedDict

from exam.registro import Fallo, clasificar_lara, registrar_fallo

log = logging.getLogger(__name__)

PAQUETE = os.getenv("LARA_MCP_PAQUETE", "@translated/lara-mcp@2.2.0")
TIMEOUT = float(os.getenv("LARA_TIMEOUT") or 15)
INICIO_TIMEOUT = float(os.getenv("LARA_INICIO_TIMEOUT") or 90)
MIN_PALABRAS = int(os.getenv("LARA_MIN_PALABRAS") or 4)
MIN_CONFIANZA = 0.60       # por debajo, la detección no es fiable: no se bloquea al estudiante
REINTENTOS = 1             # reintento corto ante un tiempo agotado o una conexión caída
CACHE_MAX = 500            # traducciones guardadas en memoria (el plan gratis tiene poca cuota)

# Códigos de idioma que entiende Lara para los dos idiomas del bot
CODIGO_LARA = {"en": "en-US", "es": "es-ES"}
NOMBRE_IDIOMA = {"en": "inglés", "es": "español"}

# Motivos que no se arreglan reintentando (sí se reintenta un tiempo agotado o la red)
_SIN_REINTENTO = {"lara_sin_config", "lara_credenciales", "lara_cuota", "lara_servidor"}


def idioma_nativo(idioma_estudio: str) -> str:
    """El bot enseña inglés y español: el idioma nativo del estudiante es el otro."""
    return "es" if idioma_estudio == "en" else "en"


def _corto(codigo: str | None) -> str:
    """'en-US' -> 'en'."""
    return (codigo or "").split("-")[0].lower()


def _resultado(res) -> dict:
    """El contenido estructurado de una respuesta de herramienta (structured_content o el JSON del texto)."""
    datos = getattr(res, "structured_content", None)
    if isinstance(datos, dict):
        return datos
    for bloque in getattr(res, "content", None) or []:
        texto = getattr(bloque, "text", None)
        if texto and texto.lstrip().startswith(("{", "[")):
            try:
                cargado = json.loads(texto)
            except ValueError:
                continue
            return cargado if isinstance(cargado, dict) else {"items": cargado}
    raise ValueError("respuesta sin JSON")


def _texto_error(res) -> str:
    return " ".join(getattr(b, "text", "") or "" for b in getattr(res, "content", None) or []).strip()


class ClienteLara:
    """Una sesión MCP con el servidor de Lara, reutilizable por todo el bot.

    `abrir_sesion` permite cambiar cómo se abre la sesión (las pruebas pasan una falsa, sin red):
    debe ser un async context manager que entregue un objeto con initialize() y call_tool()."""

    def __init__(self, abrir_sesion=None):
        self._abrir_sesion = abrir_sesion or self._sesion_stdio
        self._sesion = None
        self._tarea: asyncio.Task | None = None
        self._lista: asyncio.Event | None = None
        self._parar: asyncio.Event | None = None
        self._candado: asyncio.Lock | None = None
        self._activo = False          # True después de iniciar(): solo entonces se arranca el servidor
        self._ultimo_motivo: str | None = None
        self.cache: OrderedDict = OrderedDict()
        self.al_usar = None           # gancho opcional: al_usar(herramienta, ok, motivo) (historial)

    # ------------------------------------------------------------ configuración y ciclo de vida

    @staticmethod
    def configurado() -> bool:
        return bool(os.getenv("LARA_ACCESS_KEY_ID") and os.getenv("LARA_ACCESS_KEY_SECRET"))

    @property
    def disponible(self) -> bool:
        return self._sesion is not None

    @property
    def ultimo_motivo(self) -> str | None:
        return self._ultimo_motivo

    def _sesion_stdio(self):
        """Abre el servidor de Lara por stdio. Se importa aquí: sin el paquete `mcp`, el bot sigue."""
        from contextlib import asynccontextmanager

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import get_default_environment, stdio_client

        npx = shutil.which("npx")
        if not npx:
            raise FileNotFoundError("npx no está en el PATH: instala Node.js 22.23.4 o superior")
        # Solo las variables básicas del sistema + las de Lara (no se le pasa el token de Telegram)
        env = get_default_environment()
        env.update({
            "LARA_ACCESS_KEY_ID": os.getenv("LARA_ACCESS_KEY_ID", ""),
            "LARA_ACCESS_KEY_SECRET": os.getenv("LARA_ACCESS_KEY_SECRET", ""),
            "DO_NOT_TRACK": "1",   # sin métricas de uso del servidor
        })
        parametros = StdioServerParameters(command=npx, args=["-y", PAQUETE], env=env)

        @asynccontextmanager
        async def abrir():
            # El servidor escribe su registro por stderr: se descarta para no llenar la terminal
            with open(os.devnull, "w", encoding="utf-8") as nulo:
                async with stdio_client(parametros, errlog=nulo) as (lectura, escritura):
                    async with ClientSession(lectura, escritura) as sesion:
                        yield sesion

        return abrir()

    async def _dueno(self):
        """Tarea que abre la sesión, la mantiene viva hasta cerrar() y la cierra en la misma tarea."""
        try:
            async with self._abrir_sesion() as sesion:
                await sesion.initialize()
                self._sesion = sesion
                self._ultimo_motivo = None
                log.info("Lara MCP lista (%s)", PAQUETE)
                self._lista.set()
                await self._parar.wait()
        except asyncio.CancelledError:
            pass
        except BaseException as exc:   # noqa: BLE001 - el bot nunca debe caerse por Lara
            fallo = Fallo("lara", "iniciar", clasificar_lara(exc), exc)
            self._ultimo_motivo = fallo.motivo
            registrar_fallo(fallo)
        finally:
            self._sesion = None
            if self._lista is not None:
                self._lista.set()

    async def iniciar(self) -> bool:
        """Arranca el servidor y abre la sesión. Devuelve True si quedó lista. Nunca lanza."""
        self._activo = True
        if self._candado is None:
            self._candado = asyncio.Lock()
        async with self._candado:
            if self._sesion is not None:
                return True
            if not self.configurado():
                self._ultimo_motivo = "lara_sin_config"
                log.warning("Lara no está configurada (%s): el bot sigue sin traducción ni detección",
                            "faltan LARA_ACCESS_KEY_ID / LARA_ACCESS_KEY_SECRET en el .env")
                return False
            self._lista = asyncio.Event()
            self._parar = asyncio.Event()
            self._tarea = asyncio.create_task(self._dueno(), name="lara-mcp")
            try:
                await asyncio.wait_for(self._lista.wait(), INICIO_TIMEOUT)
            except asyncio.TimeoutError:
                self._ultimo_motivo = "lara_tiempo"
                registrar_fallo(Fallo("lara", "iniciar", "lara_tiempo",
                                      detalle=f"el servidor no respondió en {INICIO_TIMEOUT:.0f} s"))
                self._tarea.cancel()
                return False
            return self._sesion is not None

    async def cerrar(self):
        """Cierra la sesión y el proceso del servidor (al apagar el bot)."""
        self._activo = False
        if self._parar is not None:
            self._parar.set()
        if self._tarea is not None:
            try:
                await asyncio.wait_for(self._tarea, 10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._tarea.cancel()
            except Exception:
                log.debug("Error al cerrar Lara", exc_info=True)
        self._tarea = None
        self._sesion = None

    # ------------------------------------------------------------ llamadas

    def _avisar(self, herramienta: str, ok: bool, motivo: str | None):
        if self.al_usar:
            try:
                self.al_usar(herramienta, ok, motivo)
            except Exception:
                log.debug("El gancho al_usar falló", exc_info=True)

    async def _llamar(self, herramienta: str, argumentos: dict) -> dict:
        """Llama a una herramienta con tiempo de espera y un reintento corto. Lanza Fallo."""
        if not self.configurado():
            raise Fallo("lara", herramienta, "lara_sin_config",
                        detalle="faltan LARA_ACCESS_KEY_ID / LARA_ACCESS_KEY_SECRET")
        ultimo: Fallo | None = None
        for intento in range(REINTENTOS + 1):
            if self._sesion is None:
                if not self._activo or not await self.iniciar():
                    motivo = self._ultimo_motivo or "lara_servidor"
                    raise Fallo("lara", herramienta, motivo, detalle="el servidor de Lara no está disponible")
            sesion = self._sesion
            try:
                res = await asyncio.wait_for(
                    sesion.call_tool(herramienta, argumentos, read_timeout_seconds=TIMEOUT),
                    TIMEOUT + 5,
                )
            except Exception as exc:
                ultimo = Fallo("lara", herramienta, clasificar_lara(exc), exc)
                if self._tarea is not None and self._tarea.done():
                    self._sesion = None   # el servidor se cayó: el reintento lo levanta de nuevo
            else:
                if getattr(res, "is_error", False):
                    texto = _texto_error(res)
                    ultimo = Fallo("lara", herramienta, clasificar_lara(texto), detalle=texto[:200])
                else:
                    try:
                        return _resultado(res)
                    except Exception as exc:
                        ultimo = Fallo("lara", herramienta, "lara_servicio", exc)
            self._ultimo_motivo = ultimo.motivo
            if ultimo.motivo in _SIN_REINTENTO or intento == REINTENTOS:
                break
            log.info("Lara falló (%s); reintento %d", ultimo.motivo, intento + 1)
            await asyncio.sleep(0.5)
        raise ultimo

    async def detectar_idioma(self, texto: str, min_palabras: int | None = None) -> dict | None:
        """{"idioma": "en", "codigo": "en-US", "confianza": 0.98} o None si no se pudo o no conviene
        detectar (texto muy corto, Lara no configurada o caída). Nunca lanza.
        min_palabras: por defecto LARA_MIN_PALABRAS; /traducir pasa 1 para detectar una sola palabra."""
        minimo = MIN_PALABRAS if min_palabras is None else min_palabras
        if len((texto or "").split()) < minimo or not self.configurado():
            return None
        try:
            datos = await self._llamar("detect_language", {"text": texto})
        except Fallo as fallo:
            registrar_fallo(fallo)
            self._avisar("detect_language", False, fallo.motivo)
            return None
        codigo = datos.get("language")
        confianza = None
        for p in datos.get("predictions") or []:
            if isinstance(p, dict) and p.get("language") == codigo:
                confianza = p.get("confidence")
                break
        self._avisar("detect_language", True, None)
        return {"idioma": _corto(codigo), "codigo": codigo,
                "confianza": float(confianza) if isinstance(confianza, (int, float)) else None}

    async def texto_en_idioma(self, texto: str, idioma: str) -> bool | None:
        """True si el texto está en `idioma` ("en"/"es"), False si está CLARAMENTE en otro,
        None si no se sabe (muy corto, poca confianza o Lara no disponible): en ese caso no se
        bloquea al estudiante y el calificador decide como siempre."""
        det = await self.detectar_idioma(texto)
        if not det or not det["idioma"]:
            return None
        if det["idioma"] == idioma:
            return True
        if det["confianza"] is not None and det["confianza"] < MIN_CONFIANZA:
            return None
        return False

    async def traducir(self, texto: str, origen: str | None, destino: str) -> str:
        """Traduce `texto` (origen "en"/"es" o None para que Lara lo detecte) al idioma `destino`.
        Usa la caché en memoria para no gastar cuota. Lanza Fallo si Lara no está disponible."""
        texto = (texto or "").strip()
        clave = (texto.lower(), origen, destino)
        if clave in self.cache:
            self.cache.move_to_end(clave)
            return self.cache[clave]
        argumentos = {"text": [{"text": texto}], "target": CODIGO_LARA.get(destino, destino)}
        if origen:
            argumentos["source"] = CODIGO_LARA.get(origen, origen)
        try:
            datos = await self._llamar("translate", argumentos)
            items = datos.get("items") or []
            traduccion = " ".join(str(i.get("text", "")) for i in items if isinstance(i, dict)).strip()
            if not traduccion:
                raise Fallo("lara", "translate", "lara_servicio", detalle=f"respuesta vacía: {str(datos)[:150]}")
        except Fallo as fallo:
            registrar_fallo(fallo)
            self._avisar("translate", False, fallo.motivo)
            raise
        self._avisar("translate", True, None)
        self.cache[clave] = traduccion
        if len(self.cache) > CACHE_MAX:
            self.cache.popitem(last=False)
        return traduccion


# Cliente único del bot: bot.py lo inicia en post_init y lo cierra en post_shutdown.
cliente = ClienteLara()


async def iniciar() -> bool:
    return await cliente.iniciar()


async def cerrar():
    await cliente.cerrar()


async def detectar_idioma(texto: str, min_palabras: int | None = None) -> dict | None:
    return await cliente.detectar_idioma(texto, min_palabras)


async def texto_en_idioma(texto: str, idioma: str) -> bool | None:
    return await cliente.texto_en_idioma(texto, idioma)


async def traducir(texto: str, origen: str | None, destino: str) -> str:
    return await cliente.traducir(texto, origen, destino)
