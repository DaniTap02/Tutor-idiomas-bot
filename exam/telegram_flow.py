"""Flujo del examen de ubicación en Telegram.

Estado del examen en context.user_data["examen"]; el resultado final en context.user_data["nivel"].
Las preguntas de lectura las genera Ollama al iniciar cada nivel y se guardan en ex["questions"].
Partes de cada nivel: lectura (botones) -> escritura (texto) -> habla (nota de voz, transcrita con Whisper).
"""
import asyncio
import os
import tempfile

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from exam import questions_a1, questions_a2, questions_b1
from exam.grader import grade
from exam.placement import level_passed, next_step
from exam.question_generator import generate_reading
from exam.stt import transcribe

# Al crear los exámenes de B1 y B2 solo hay que agregarlos aquí.
BANCOS = {"A1": questions_a1, "A2": questions_a2, "B1": questions_b1}

IDIOMAS = {"en": "Inglés 🇬🇧", "es": "Español 🇪🇸"}

MIN_SEGUNDOS_VOZ = 8  # audios más cortos se piden de nuevo


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
    except Exception:
        context.user_data.pop("examen", None)
        await espera.edit_text(
            error_extra
            or "No pude preparar el examen. ¿Está encendido Ollama? Escribe /start para intentarlo de nuevo."
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


async def _enviar_pregunta(message, context: ContextTypes.DEFAULT_TYPE):
    ex = context.user_data["examen"]
    preguntas = ex["questions"]
    pregunta = preguntas[ex["q"]]
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton(op, callback_data=f"ans:{ex['q']}:{i}")] for i, op in enumerate(pregunta["options"])]
    )
    encabezado = f"📖 {ex['level']} · Lectura {ex['q'] + 1}/{len(preguntas)}"
    if pregunta.get("text"):  # pregunta de comprensión con mini-texto
        cuerpo = f"{encabezado}\n\n📄 {pregunta['text']}\n\n❓ {pregunta['q']}"
    else:
        cuerpo = f"{encabezado}\n\n{pregunta['q']}"
    await message.reply_text(cuerpo, reply_markup=teclado)


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
    await query.message.reply_text(f"✍️ Escritura\n\n{banco.WRITING_PROMPT[ex['language']]}")


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

    if ex["part"] == "habla":
        await update.message.reply_text("Ahora envíame una nota de voz 🎤 (mantén presionado el micrófono)")
        return True

    banco = BANCOS[ex["level"]]
    espera = await update.message.reply_text("Calificando tu texto… ⏳")
    try:
        # grade() es síncrona: se corre en un hilo para no congelar el bot
        r = await asyncio.to_thread(
            grade,
            update.message.text,
            ex["level"],
            ex["language"],
            banco.TASK_CHECKLIST["writing"],
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

    # Sigue la parte de habla (nota de voz)
    ex["part"] = "habla"
    await update.message.reply_text(f"🎤 Habla\n\n{banco.SPEAKING_PROMPT[ex['language']]}")
    return True


def _feedback_voz(feedback: str) -> str:
    """El calificador habla de 'texto'/'escribe'; en la parte de habla se dice 'audio'/'habla'."""
    return (
        feedback.replace("Tu texto es muy corto. Escribe al menos", "Tu audio es muy corto. Habla al menos")
        .replace("Tu texto debe estar escrito en", "Debes hablar en")
    )


async def voz_de_examen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Se llama cuando llega una nota de voz. Devuelve True si el mensaje era parte del examen."""
    ex = context.user_data.get("examen")
    if not ex:
        return False

    if ex["part"] != "habla":
        await update.message.reply_text("Todavía no es momento de la nota de voz 🙂 Sigue con la parte actual.")
        return True

    voz = update.message.voice
    if voz.duration < MIN_SEGUNDOS_VOZ:
        await update.message.reply_text(
            f"Tu audio es muy corto (mínimo {MIN_SEGUNDOS_VOZ} segundos). Grábalo de nuevo 🎤"
        )
        return True

    banco = BANCOS[ex["level"]]
    espera = await update.message.reply_text("Escuchando tu audio… 🎧")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "nota.ogg")
            archivo = await voz.get_file()
            await archivo.download_to_drive(ruta)
            # transcribe() y grade() son síncronas: se corren en un hilo para no congelar el bot
            texto, idioma = await asyncio.to_thread(transcribe, ruta)

        if idioma != ex["language"]:
            await espera.edit_text(
                f"Parece que hablaste en otro idioma. Habla en {IDIOMAS[ex['language']]} y grábalo de nuevo 🎤"
            )
            return True

        r = await asyncio.to_thread(
            grade,
            texto,
            ex["level"],
            ex["language"],
            banco.TASK_CHECKLIST["speaking"],
            True,  # is_transcript: ignora puntuación y mayúsculas
        )
    except Exception:
        await espera.edit_text("No pude procesar tu audio. ¿Está encendido Ollama? Envíalo de nuevo.")
        return True

    if r["needs_rewrite"]:
        await espera.edit_text(
            f"Entendí: «{texto}»\n\n{_feedback_voz(r['feedback'])}\n\nGrábalo de nuevo 🎤"
        )
        return True

    ex["scores"]["habla"] = r["score"]
    respuesta = f"Esto fue lo que entendí:\n«{texto}»\n\n{r['feedback']}"
    if r["errors"]:
        correcciones = "\n".join(f"• {e['fragment']} → {e['correction']}" for e in r["errors"][:3])
        respuesta += f"\n\nPara mejorar:\n{correcciones}"
    await espera.edit_text(respuesta)

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
        f"Escritura: {s['escritura']:.0f}\n"
        f"Habla: {s['habla']:.0f}\n\n"
        f"📖 Revisión de lectura\n{_revision_lectura(ex)}"
    )

    # Pasó y existe el examen del siguiente nivel: continúa
    if siguiente["action"] == "exam" and siguiente["level"] in BANCOS:
        ex.update(level=siguiente["level"], part="generando", q=0, answers=[], scores={}, questions=[])
        # Si falla la generación, el usuario no pierde lo ganado: queda en el nivel siguiente (provisional)
        context.user_data["nivel"] = {
            "language": ex["language"],
            "level": siguiente["level"],
            "provisional": True,
        }
        await message.reply_text(f"{resumen}\n\n✅ ¡Pasaste {nivel_rendido}! Sigue el examen {siguiente['level']}.")
        if not await _preparar_preguntas(
            message,
            context,
            error_extra=(
                f"No pude preparar el examen {siguiente['level']}. ¿Está encendido Ollama? "
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
    await message.reply_text(f"{resumen}\n\n{mensaje}\n\nEscribe /start para ver el menú.")
