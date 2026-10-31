"""Flujo del examen de ubicación en Telegram.

Estado del examen en context.user_data["examen"]; el resultado final en context.user_data["nivel"].
Las preguntas de lectura las genera Ollama al iniciar cada nivel y se guardan en ex["questions"].
Por ahora se evalúan lectura y escritura. La parte de habla se agrega cuando esté la transcripción.
"""
import asyncio
import logging
import random

import httpx

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from exam import questions_a1, questions_a2, questions_b1
from exam.grader import grade
from exam.placement import level_passed, next_step
from exam.question_generator import generate_reading

# Al crear el examen de B2 solo hay que agregarlo aquí.
BANCOS = {"A1": questions_a1, "A2": questions_a2, "B1": questions_b1}

log = logging.getLogger(__name__)

TELEGRAM_MAX = 4000  # el límite de Telegram es 4096 caracteres por mensaje
OPCION_LARGA = 40    # si alguna opción pasa de esto, se listan en el mensaje y los botones son A/B/C
LETRAS = "ABCDEFGH"

IDIOMAS = {"en": "Inglés 🇬🇧", "es": "Español 🇪🇸"}


def en_examen(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return "examen" in context.user_data


def tiene_nivel(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return "nivel" in context.user_data


async def iniciar_examen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("examen", None)
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton(nombre, callback_data=f"lang:{code}") for code, nombre in IDIOMAS.items()]]
    )
    await update.effective_message.reply_text(
        "¡Hola! 👋 Antes de empezar vamos a conocer tu nivel con un examen corto.\n\n"
        "¿Qué idioma quieres aprender?",
        reply_markup=teclado,
    )


async def _preparar_preguntas(message, context: ContextTypes.DEFAULT_TYPE, error_extra: str | None = None) -> bool:
    """Genera con Ollama las preguntas de lectura del nivel actual. Devuelve False si falló.
    error_extra: mensaje de error propio (por ejemplo cuando ya se guardó un nivel provisional)."""
    ex = context.user_data["examen"]
    espera = await message.reply_text("Preparando tu examen… ⏳ (puede tardar un poquito)")
    try:
        # generate_reading() es síncrona: se corre en un hilo para no congelar el bot
        ex["questions"] = await asyncio.to_thread(
            generate_reading, BANCOS[ex["level"]], ex["language"]
        )
    except Exception as exc:
        log.exception("No se pudo generar el examen %s", ex.get("level"))
        context.user_data.pop("examen", None)
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            causa = "No pude conectar con Ollama. ¿Está encendido?"
        else:
            causa = (
                "Ollama responde, pero no logré generar suficientes preguntas válidas "
                "(puede ser lentitud del modelo o filtros muy estrictos)."
            )
        await espera.edit_text(
            f"{causa} {error_extra}" if error_extra
            else f"{causa} Escribe /start para intentarlo de nuevo."
        )
        return False
    await espera.delete()
    return True


async def elegir_idioma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if en_examen(context):  # doble clic mientras se generan las preguntas
        return
    language = query.data.split(":")[1]
    context.user_data["examen"] = {
        "language": language,
        "level": "A1",
        "part": "generando",
        "q": 0,
        "answers": [],
        "scores": {},
        "questions": [],
    }
    await query.edit_message_text(f"Perfecto: {IDIOMAS[language]}. Empezamos con el nivel A1. 💪")
    if not await _preparar_preguntas(query.message, context):
        return
    context.user_data["examen"]["part"] = "lectura"
    await _enviar_pregunta(query.message, context)


def _partir(texto: str, limite: int = TELEGRAM_MAX) -> list[str]:
    """Parte un texto largo en mensajes de Telegram (por líneas, nunca a mitad de línea si se puede)."""
    if len(texto) <= limite:
        return [texto]
    partes, actual = [], ""
    for linea in texto.split("\n"):
        while len(linea) > limite:  # línea gigante: se corta a la fuerza
            if actual:
                partes.append(actual)
                actual = ""
            partes.append(linea[:limite])
            linea = linea[limite:]
        if actual and len(actual) + len(linea) + 1 > limite:
            partes.append(actual)
            actual = linea
        else:
            actual = f"{actual}\n{linea}" if actual else linea
    if actual:
        partes.append(actual)
    return partes


async def _responder_largo(message, texto: str):
    """Envía `texto` en uno o varios mensajes si pasa el límite de Telegram."""
    for parte in _partir(texto):
        await message.reply_text(parte)


def _tarea_escritura(banco, ex: dict) -> tuple[dict, list[dict]]:
    """(prompt por idioma, checklist) de la tarea de escritura de este examen.
    Si el banco define WRITING_TASKS (B1), usa la tarea elegida al azar y guardada en ex["writing_task"]
    (solo su id, para que sobreviva a la persistencia). Si no (A1, A2), usa WRITING_PROMPT y TASK_CHECKLIST."""
    tareas = getattr(banco, "WRITING_TASKS", None)
    if tareas:
        tarea = next((t for t in tareas if t["id"] == ex.get("writing_task")), None)
        if tarea:
            return tarea["prompt"], tarea["checklist"]
    return banco.WRITING_PROMPT, banco.TASK_CHECKLIST["writing"]


def _elegir_tarea_escritura(banco, ex: dict):
    """Si el banco tiene varias tareas de escritura, el CÓDIGO elige una al azar y guarda su id."""
    tareas = getattr(banco, "WRITING_TASKS", None)
    if tareas:
        ex["writing_task"] = random.choice(tareas)["id"]
    else:
        ex.pop("writing_task", None)


async def _enviar_pregunta(message, context: ContextTypes.DEFAULT_TYPE):
    ex = context.user_data["examen"]
    preguntas = ex["questions"]
    pregunta = preguntas[ex["q"]]
    opciones = pregunta["options"]
    encabezado = f"📖 {ex['level']} · Lectura {ex['q'] + 1}/{len(preguntas)}"
    if pregunta.get("text"):  # pregunta de comprensión con mini-texto
        cuerpo = f"{encabezado}\n\n📄 {pregunta['text']}\n\n❓ {pregunta['q']}"
    else:
        cuerpo = f"{encabezado}\n\n{pregunta['q']}"

    if any(len(op) > OPCION_LARGA for op in opciones):
        # Opciones largas (B1: actitud/intención): no caben en un botón. Se listan en el mensaje y los botones son A/B/C.
        cuerpo += "\n\n" + "\n".join(f"{LETRAS[i]}) {op}" for i, op in enumerate(opciones))
        teclado = InlineKeyboardMarkup(
            [[InlineKeyboardButton(LETRAS[i], callback_data=f"ans:{ex['q']}:{i}") for i in range(len(opciones))]]
        )
    else:
        teclado = InlineKeyboardMarkup(
            [[InlineKeyboardButton(op, callback_data=f"ans:{ex['q']}:{i}")] for i, op in enumerate(opciones)]
        )
    await message.reply_text(cuerpo[:4096], reply_markup=teclado)


async def responder_lectura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ex = context.user_data.get("examen")
    _, q_idx, opcion = query.data.split(":")

    # Ignora botones viejos o repetidos
    if not ex or ex["part"] != "lectura" or int(q_idx) != ex["q"]:
        return

    banco = BANCOS[ex["level"]]
    preguntas = ex["questions"]
    ex["answers"].append(int(opcion))
    ex["q"] += 1
    await query.edit_message_reply_markup(reply_markup=None)

    if ex["q"] < len(preguntas):
        await _enviar_pregunta(query.message, context)
        return

    ex["scores"]["lectura"] = banco.score_reading(preguntas, ex["answers"])
    ex["part"] = "escritura"
    _elegir_tarea_escritura(banco, ex)
    prompt, _ = _tarea_escritura(banco, ex)
    await query.message.reply_text(f"✍️ Escritura\n\n{prompt[ex['language']]}")


async def texto_de_examen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Se llama al inicio de responder(). Devuelve True si el mensaje era parte del examen."""
    ex = context.user_data.get("examen")
    if not ex:
        return False

    if ex["part"] == "generando":
        await update.message.reply_text("Estoy preparando tu examen, un momento ⏳")
        return True

    if ex["part"] == "lectura":
        await update.message.reply_text("Responde con los botones de la pregunta 👆")
        return True

    banco = BANCOS[ex["level"]]
    _, checklist = _tarea_escritura(banco, ex)
    espera = await update.message.reply_text("Calificando tu texto… ⏳")
    try:
        # grade() es síncrona: se corre en un hilo para no congelar el bot
        r = await asyncio.to_thread(
            grade,
            update.message.text,
            ex["level"],
            ex["language"],
            checklist,
        )
    except Exception:
        await espera.edit_text("No pude calificar tu texto. ¿Está encendido Ollama? Envíalo de nuevo.")
        return True

    if r["needs_rewrite"]:
        await espera.edit_text(f"{r['feedback']}\n\nInténtalo de nuevo ✍️")
        return True

    ex["scores"]["escritura"] = r["score"]

    texto = r["feedback"]
    if r["errors"]:
        correcciones = "\n".join(f"• {e['fragment']} → {e['correction']}" for e in r["errors"][:3])
        texto += f"\n\nPara mejorar:\n{correcciones}"
    await espera.edit_text(texto)

    await _cerrar_nivel(update.message, context)
    return True


def _revision_lectura(ex: dict) -> str:
    """Resumen de lo que eligió el usuario en cada pregunta de lectura (se muestra al final)."""
    lineas = []
    for i, (pregunta, elegida) in enumerate(zip(ex["questions"], ex["answers"]), start=1):
        correcta = pregunta["answer"]
        # En las preguntas con mini-texto solo se muestra el inicio del texto, para no alargar el mensaje
        if pregunta.get("text"):
            inicio = " ".join(pregunta["text"].split()[:6])
            etiqueta = f"📄 «{inicio}…» {pregunta['q']}"
        else:
            etiqueta = pregunta["q"]
        if elegida == correcta:
            lineas.append(f"{i}. {etiqueta} → ✅ {pregunta['options'][elegida]}")
        else:
            lineas.append(
                f"{i}. {etiqueta} → ❌ {pregunta['options'][elegida]} "
                f"(correcta: {pregunta['options'][correcta]})"
            )
    return "\n".join(lineas)


async def _cerrar_nivel(message, context: ContextTypes.DEFAULT_TYPE):
    ex = context.user_data["examen"]
    nivel_rendido = ex["level"]
    s = ex["scores"]
    paso = level_passed(s["lectura"], s["escritura"], s.get("habla"))
    siguiente = next_step(nivel_rendido, paso)

    resumen = (
        f"📊 Resultado {nivel_rendido}\n"
        f"Lectura: {s['lectura']:.0f}\n"
        f"Escritura: {s['escritura']:.0f}\n\n"
        f"📖 Revisión de lectura\n{_revision_lectura(ex)}"
    )

    # Pasó y existe el examen del siguiente nivel: continúa
    if siguiente["action"] == "exam" and siguiente["level"] in BANCOS:
        ex.update(level=siguiente["level"], part="generando", q=0, answers=[], scores={}, questions=[])
        ex.pop("writing_task", None)
        # Si falla la generación, el usuario no pierde lo ganado: queda en el nivel siguiente (provisional)
        context.user_data["nivel"] = {
            "language": ex["language"],
            "level": siguiente["level"],
            "provisional": True,
        }
        await _responder_largo(message, f"{resumen}\n\n✅ ¡Pasaste {nivel_rendido}! Sigue el examen {siguiente['level']}.")
        if not await _preparar_preguntas(
            message,
            context,
            error_extra=(
                f"No pude preparar el examen {siguiente['level']}. "
                f"Tu nivel queda como {siguiente['level']} (provisional). "
                "Cuando Ollama esté listo, escribe /reiniciar para repetir el examen."
            ),
        ):
            return
        context.user_data["examen"]["part"] = "lectura"
        await _enviar_pregunta(message, context)
        return

    provisional = False
    if siguiente["action"] == "teach":
        mensaje = f"Empezarás aprendiendo desde el nivel {siguiente['level']}. ¡Vamos paso a paso! 📚"
    elif siguiente["action"] == "exam":
        # Pasó, pero el examen del siguiente nivel todavía no está construido
        provisional = True
        mensaje = (
            f"✅ ¡Pasaste {nivel_rendido}! El examen de {siguiente['level']} aún está en construcción, "
            f"así que tu nivel queda como {siguiente['level']} (provisional)."
        )
    else:
        mensaje = "🎉 ¡Completaste todos los niveles del examen!"

    context.user_data["nivel"] = {
        "language": ex["language"],
        "level": siguiente["level"],
        "provisional": provisional,
    }
    context.user_data.pop("examen", None)
    await _responder_largo(message, f"{resumen}\n\n{mensaje}\n\nEscribe /start para ver el menú.")
