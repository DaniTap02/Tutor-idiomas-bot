"""Uso de Lara Translate (MCP) dentro del bot de Telegram.

Dos herramientas del servidor MCP de Lara (ver mcp_cliente/lara.py):
  1. detect_language -> revisar_idioma(): antes de mandar una escritura o la transcripción del habla
     al calificador, comprueba que esté en el idioma del examen o de la lección. Si está CLARAMENTE
     en otro, se avisa con amabilidad y se pide de nuevo, sin calificar ni penalizar. Si el texto es
     muy corto o Lara no está disponible, no se bloquea: el calificador decide como siempre.
  2. translate -> /traducir <texto> y el botón "Ver traducción" que se pone en A1 y A2 bajo las
     consignas y la retroalimentación del calificador.

El idioma nativo del estudiante es el otro idioma del bot (estudia inglés -> nativo español).
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from exam.registro import Fallo
from mcp_cliente import lara

log = logging.getLogger(__name__)

NIVELES_CON_BOTON = ("A1", "A2")
MAX_TRADUCIBLES = 15          # textos recordados para el botón (los más viejos se olvidan)
NO_DISPONIBLE = "La traducción no está disponible en este momento 😕 Inténtalo más tarde."

NOMBRE = {"en": "inglés", "es": "español"}


def idioma_de_estudio(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """El idioma que estudia el usuario: el del examen en curso o el de su nivel."""
    ex = context.user_data.get("examen")
    if ex:
        return ex.get("language")
    nivel = context.user_data.get("nivel")
    return nivel.get("language") if nivel else None


def teclado_traduccion(context: ContextTypes.DEFAULT_TYPE, texto: str, idioma_texto: str,
                       idioma_estudio: str, nivel: str, filas_extra=None) -> InlineKeyboardMarkup | None:
    """Botón "Ver traducción" para A1 y A2, solo si el texto NO está ya en el idioma nativo.
    Guarda el texto en user_data (el callback_data de Telegram admite solo 64 bytes)."""
    filas = list(filas_extra or [])
    if nivel in NIVELES_CON_BOTON and idioma_texto != lara.idioma_nativo(idioma_estudio) and texto:
        guardados = context.user_data.setdefault("traducibles", {})
        clave = context.user_data.get("traducible_n", 0) + 1
        context.user_data["traducible_n"] = clave
        guardados[str(clave)] = {"texto": texto, "origen": idioma_texto,
                                 "destino": lara.idioma_nativo(idioma_estudio)}
        for viejo in sorted(guardados, key=int)[:-MAX_TRADUCIBLES]:
            guardados.pop(viejo, None)
        filas.append([InlineKeyboardButton("🌐 Ver traducción", callback_data=f"tr:{clave}")])
    return InlineKeyboardMarkup(filas) if filas else None


async def ver_traduccion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botón "Ver traducción" (callback tr:<n>)."""
    query = update.callback_query
    clave = query.data.split(":", 1)[1]
    guardado = context.user_data.get("traducibles", {}).get(clave)
    if not guardado:
        await query.answer("Ese mensaje ya es muy viejo para traducirlo 🙂", show_alert=True)
        return
    try:
        traduccion = await lara.traducir(guardado["texto"], guardado["origen"], guardado["destino"])
    except Fallo:
        await query.answer(NO_DISPONIBLE, show_alert=True)
        return
    await query.answer()
    await query.message.reply_text(f"🌐 Traducción ({NOMBRE[guardado['destino']]}):\n\n{traduccion}"[:4096])


async def comando_traducir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/traducir <texto>: del idioma que estudia al nativo, y al revés."""
    texto = " ".join(context.args or []).strip()
    if not texto:
        await update.message.reply_text(
            "Escribe la palabra o frase después del comando 🙂\n\n"
            "Ejemplos:\n/traducir I would like a coffee\n/traducir ¿dónde está la estación?"
        )
        return
    if len(texto) > 500:
        await update.message.reply_text("Es un texto muy largo 😅 Traduce frases cortas (máximo 500 caracteres).")
        return

    estudio = idioma_de_estudio(context)
    det = await lara.detectar_idioma(texto, min_palabras=1)
    origen = det["idioma"] if det and det["idioma"] in NOMBRE else None
    if estudio:
        nativo = lara.idioma_nativo(estudio)
        # Si está en el idioma que estudia (o no se supo), va a su idioma nativo; si no, al que estudia.
        destino = nativo if origen in (None, estudio) else estudio
    else:   # todavía sin idioma elegido: se traduce al otro idioma del bot
        destino = "en" if origen == "es" else "es"
    if origen == destino:
        origen = None
    try:
        traduccion = await lara.traducir(texto, origen, destino)
    except Fallo:
        await update.message.reply_text(NO_DISPONIBLE)
        return
    await update.message.reply_text(f"🌐 {texto}\n➡️ {traduccion}"[:4096])


async def revisar_idioma(mensaje_espera, texto: str, idioma: str, skill: str = "writing") -> bool:
    """detect_language antes de calificar. Devuelve True si el texto está CLARAMENTE en otro idioma:
    en ese caso ya se avisó (editando `mensaje_espera`) y NO hay que calificar ni contar el intento."""
    try:
        en_idioma = await lara.texto_en_idioma(texto, idioma)
    except Exception:   # Lara nunca debe frenar el examen
        log.warning("Fallo no previsto al detectar el idioma", exc_info=True)
        return False
    if en_idioma is not False:
        return False
    if skill == "speaking":
        aviso = (f"Parece que hablaste en otro idioma 🙂 Esta parte es en {NOMBRE[idioma]}.\n\n"
                 "Grábalo de nuevo en ese idioma 🎤 (este intento no cuenta).")
    else:
        aviso = (f"Parece que tu texto no está en {NOMBRE[idioma]} 🙂\n\n"
                 f"Escríbelo de nuevo en {NOMBRE[idioma]} ✍️ (este intento no cuenta).")
    await mensaje_espera.edit_text(aviso)
    return True
