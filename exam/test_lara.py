"""Prueba SIN internet ni Node.js del cliente MCP de Lara (sesión MCP simulada):

    python -m exam.test_lara

Comprueba los casos normales (detectar idioma, traducir, caché) y los de falla (sin credenciales,
credenciales malas, cuota agotada, tiempo agotado con reintento, servidor que no arranca), que el
motivo real queda clasificado y que el bot nunca bloquea ni penaliza al estudiante por Lara.
Para probar la conexión REAL con tus credenciales: python -m mcp_cliente.probar_lara
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

from exam import traduccion
from exam.registro import Fallo, clasificar_lara
from mcp_cliente import lara as lara_mod
from mcp_cliente.lara import ClienteLara

logging.disable(logging.CRITICAL)

ok_total = 0
fail_total = 0


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK    " if condicion else "  FALLA ") + nombre)
    ok_total += bool(condicion)
    fail_total += not condicion


def respuesta(datos=None, error=None):
    """Lo que devuelve call_tool en el SDK de MCP (solo los campos que usa el cliente)."""
    if error:
        return SimpleNamespace(is_error=True, content=[SimpleNamespace(text=error)], structured_content=None)
    return SimpleNamespace(is_error=False, content=[SimpleNamespace(text="ok")], structured_content=datos)


class SesionFalsa:
    """Sesión MCP simulada. `guion` decide qué responde cada herramienta."""

    def __init__(self, guion):
        self.guion = guion
        self.llamadas = []

    async def initialize(self):
        return None

    async def call_tool(self, nombre, argumentos=None, read_timeout_seconds=None):
        self.llamadas.append((nombre, argumentos))
        salida = self.guion(nombre, argumentos, len(self.llamadas))
        if isinstance(salida, BaseException):
            raise salida
        return salida


def cliente_con(guion):
    sesion = SesionFalsa(guion)

    @asynccontextmanager
    async def abrir():
        yield sesion

    return ClienteLara(abrir_sesion=abrir), sesion


def deteccion(codigo, confianza=0.97):
    return respuesta({"language": codigo, "contentType": "text/plain",
                      "predictions": [{"language": codigo, "confidence": confianza}]})


def traduccion_ok(texto):
    return respuesta({"items": [{"text": texto}]})


class MensajeFalso:
    def __init__(self):
        self.enviados = []

    async def reply_text(self, texto, reply_markup=None):
        self.enviados.append(texto)
        return self

    async def edit_text(self, texto, reply_markup=None):
        self.enviados.append(texto)


async def casos():
    # ---- 1. Sin credenciales: nada se bloquea y la traducción dice que no está disponible
    print("\n== Sin credenciales")
    os.environ.pop("LARA_ACCESS_KEY_ID", None)
    os.environ.pop("LARA_ACCESS_KEY_SECRET", None)
    c, sesion = cliente_con(lambda *a: deteccion("en-US"))
    check("iniciar() devuelve False sin credenciales", await c.iniciar() is False)
    check("el motivo es lara_sin_config", c.ultimo_motivo == "lara_sin_config")
    check("detectar_idioma devuelve None (no bloquea)", await c.detectar_idioma("I like music very much") is None)
    try:
        await c.traducir("hello", "en", "es")
        check("traducir lanza Fallo", False)
    except Fallo as f:
        check("traducir lanza Fallo lara_sin_config", f.motivo == "lara_sin_config")
    check("no se llamó al servidor", sesion.llamadas == [])

    os.environ["LARA_ACCESS_KEY_ID"] = "id-de-prueba"
    os.environ["LARA_ACCESS_KEY_SECRET"] = "secreto-de-prueba"

    # ---- 2. Casos normales
    print("\n== Detección de idioma")
    c, sesion = cliente_con(lambda n, a, i: deteccion("en-US" if "music" in a["text"] else "es-ES"))
    check("iniciar() abre la sesión", await c.iniciar() is True and c.disponible)
    det = await c.detectar_idioma("I like music very much")
    check("detecta inglés con su confianza", det == {"idioma": "en", "codigo": "en-US", "confianza": 0.97})
    check("texto en el idioma pedido -> True", await c.texto_en_idioma("I like music very much", "en") is True)
    check("texto en otro idioma -> False", await c.texto_en_idioma("me gusta mucho la playa", "en") is False)
    n = len(sesion.llamadas)
    check("texto muy corto -> None sin llamar a Lara", await c.texto_en_idioma("Hola amigo", "en") is None
          and len(sesion.llamadas) == n)
    check("se llamó a la herramienta real detect_language", sesion.llamadas[0][0] == "detect_language")

    c, _ = cliente_con(lambda *a: deteccion("es-ES", confianza=0.4))
    await c.iniciar()
    check("poca confianza -> None (no bloquea)", await c.texto_en_idioma("me gusta mucho la playa", "en") is None)

    print("\n== Traducción y caché")
    c, sesion = cliente_con(lambda *a: traduccion_ok("Me gustaría un café"))
    await c.iniciar()
    usos = []
    c.al_usar = lambda h, ok, motivo: usos.append((h, ok))
    t1 = await c.traducir("I would like a coffee", "en", "es")
    t2 = await c.traducir("i would like a coffee ", "en", "es")
    check("traduce", t1 == "Me gustaría un café")
    check("la 2.ª vez sale de la caché (una sola llamada)", t2 == t1 and len(sesion.llamadas) == 1)
    nombre, args = sesion.llamadas[0]
    check("usa la herramienta translate con text, source y target",
          nombre == "translate" and args == {"text": [{"text": "I would like a coffee"}],
                                             "target": "es-ES", "source": "en-US"})
    check("el gancho al_usar registra el uso", usos == [("translate", True)])

    # ---- 3. Fallas
    print("\n== Fallas de Lara")
    c, sesion = cliente_con(lambda *a: respuesta(error="Unauthorized"))
    await c.iniciar()
    try:
        await c.traducir("hello", "en", "es")
        check("credenciales malas lanzan Fallo", False)
    except Fallo as f:
        check("credenciales malas -> lara_credenciales", f.motivo == "lara_credenciales")
    check("credenciales malas: no se reintenta", len(sesion.llamadas) == 1)
    check("credenciales malas: la detección no bloquea", await c.texto_en_idioma("me gusta mucho la playa", "en") is None)

    c, sesion = cliente_con(lambda *a: respuesta(error="Quota exceeded for this month"))
    await c.iniciar()
    try:
        await c.traducir("hello", "en", "es")
    except Fallo as f:
        check("cuota agotada -> lara_cuota", f.motivo == "lara_cuota")

    c, sesion = cliente_con(lambda n, a, i: TimeoutError("timed out") if i == 1 else traduccion_ok("hola"))
    await c.iniciar()
    check("tiempo agotado: el reintento corto funciona", await c.traducir("hello", "en", "es") == "hola"
          and len(sesion.llamadas) == 2)

    c, sesion = cliente_con(lambda *a: TimeoutError("timed out"))
    await c.iniciar()
    try:
        await c.traducir("hello", "en", "es")
    except Fallo as f:
        check("tiempo agotado dos veces -> lara_tiempo (1 reintento)", f.motivo == "lara_tiempo"
              and len(sesion.llamadas) == 2)

    c, _ = cliente_con(lambda *a: respuesta({"rara": True}))
    await c.iniciar()
    try:
        await c.traducir("hello", "en", "es")
    except Fallo as f:
        check("respuesta sin traducción -> lara_servicio", f.motivo == "lara_servicio")

    @asynccontextmanager
    async def sin_node():
        raise FileNotFoundError("npx no está en el PATH")
        yield  # pragma: no cover

    c = ClienteLara(abrir_sesion=sin_node)
    check("sin Node.js: iniciar() devuelve False", await c.iniciar() is False)
    check("sin Node.js -> lara_servidor", c.ultimo_motivo == "lara_servidor")
    check("sin Node.js: detectar no bloquea", await c.detectar_idioma("I like music very much") is None)

    print("\n== Clasificación de motivos")
    check("401 -> credenciales", clasificar_lara("Request failed with status 401") == "lara_credenciales")
    check("429 -> cuota", clasificar_lara("429 Too Many Requests") == "lara_cuota")
    check("getaddrinfo ENOTFOUND -> red", clasificar_lara("getaddrinfo ENOTFOUND api.laratranslate.com") == "lara_red")
    check("TimeoutError -> tiempo", clasificar_lara(TimeoutError()) == "lara_tiempo")
    check("otro error -> servicio", clasificar_lara("algo raro") == "lara_servicio")

    # ---- 4. Uso dentro del bot (exam/traduccion.py), con el cliente del bot reemplazado
    print("\n== Uso en el bot")
    c, _ = cliente_con(lambda n, a, i: deteccion("es-ES") if n == "detect_language" else traduccion_ok("I live in Cali"))
    await c.iniciar()
    lara_mod.cliente = c
    m = MensajeFalso()
    check("revisar_idioma: texto en otro idioma -> se pide de nuevo",
          await traduccion.revisar_idioma(m, "yo vivo en Cali con mi familia", "en") is True
          and "no está en inglés" in m.enviados[-1] and "no cuenta" in m.enviados[-1])
    m = MensajeFalso()
    check("revisar_idioma: texto corto -> sigue al calificador",
          await traduccion.revisar_idioma(m, "Hola", "en") is False and m.enviados == [])

    ctx = SimpleNamespace(user_data={"nivel": {"language": "en", "level": "A1"}}, args=["vivo", "en", "Cali"])
    m = MensajeFalso()
    await traduccion.comando_traducir(SimpleNamespace(message=m), ctx)
    check("/traducir traduce al idioma que estudia", m.enviados and "I live in Cali" in m.enviados[-1])

    teclado = traduccion.teclado_traduccion(ctx, "Write your name", "en", "en", "A1")
    check("A1: la consigna lleva botón Ver traducción", teclado is not None
          and teclado.inline_keyboard[-1][0].callback_data.startswith("tr:"))
    check("B1: sin botón de traducción", traduccion.teclado_traduccion(ctx, "Write", "en", "en", "B1") is None)
    check("texto ya en el idioma nativo: sin botón",
          traduccion.teclado_traduccion(ctx, "Bien hecho", "es", "en", "A1") is None)

    c, _ = cliente_con(lambda *a: respuesta(error="Quota exceeded"))
    await c.iniciar()
    lara_mod.cliente = c
    m = MensajeFalso()
    await traduccion.comando_traducir(SimpleNamespace(message=m), ctx)
    check("/traducir con Lara caída: dice que no está disponible", m.enviados[-1] == traduccion.NO_DISPONIBLE)
    await c.cerrar()


asyncio.run(casos())
print(f"\nResultado: {ok_total} OK, {fail_total} con falla")
