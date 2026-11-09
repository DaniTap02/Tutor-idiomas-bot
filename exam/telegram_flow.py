"""Flujo del examen de ubicación en Telegram.

Estado del examen en context.user_data["examen"]; el resultado final en context.user_data["nivel"].

Partes de cada nivel, en orden:
    LECTURA (botones) -> ESCUCHA (audio + botones) -> ESCRITURA (texto) -> HABLA (nota de voz)

Las preguntas de lectura (ex["questions"]) y de escucha (ex["listening"]) las genera Ollama al
iniciar cada nivel. Los audios de la escucha se crean con edge-tts (exam/tts.py) y la nota de voz
del estudiante se transcribe con Whisper en local (exam/stt.py) y se califica con el agente
(exam/grader.py, skill="speaking").

Si la escucha no se puede generar (modelo lento, sin internet para el audio...), el examen SIGUE sin
esa parte y no se promedia: nunca se penaliza al estudiante por un fallo del sistema.
"""
import asyncio
import logging
import os
import random
import tempfile

import httpx

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from exam import questions_a1, questions_a2, questions_b1, questions_b2
from exam.grader import grade
from exam.listening import CONFIG as ESCUCHA_CONFIG
from exam.listening import generate_listening
from exam.placement import level_passed, next_step
from exam.question_generator import generate_reading
from exam.registro import Fallo, describir, medir, registrar_fallo
from exam.stt import modelo_cargado, transcribe
from exam.tts import synthesize

# Al crear el examen de B2 solo hay que agregarlo aquí (su escucha ya está en exam/listening.py).
BANCOS = {"A1": questions_a1, "A2": questions_a2, "B1": questions_b1}

# Al crear el examen de un nivel nuevo solo hay que agregarlo aquí (y su escucha en exam/listening.py).
BANCOS = {"A1": questions_a1, "A2": questions_a2, "B1": questions_b1, "B2": questions_b2}

IDIOMAS = {"en": "Inglés 🇬🇧", "es": "Español 🇪🇸"}

REPETICIONES_AUDIO = 1   # cuántas veces se puede repetir cada audio de la escucha

# Mínimo de segundos de la nota de voz, por nivel (los SPEAKING_PROMPT piden 15-30 s en A1,
# 30-45 s en A2 y 45-60 s en B1). Solo es un filtro rápido para no transcribir audios inservibles:
# el mínimo que de verdad cuenta son las palabras (grader.MIN_WORDS_SPEAKING).
MIN_SEGUNDOS_VOZ = {"A1": 12, "A2": 20, "B1": 30, "B2": 30}

# Calidad mínima de la grabación para que valga la pena calificarla (ver exam/stt.py).
# OJO: esto NO es una nota de pronunciación, solo mide si la grabación se entiende.
MIN_CONFIANZA = 0.35      # por debajo, la transcripción es ruido: se pide grabar de nuevo
MAX_SIN_VOZ = 0.60        # probabilidad de que no haya voz en el audio
WPM_MUY_LENTO = 40        # palabras por minuto: por debajo se sugiere hablar más seguido

# Fallos TÉCNICOS seguidos (Whisper sin instalar, Ollama caído...) tras los cuales el nivel se
# cierra SIN la parte de habla, para que el estudiante no quede atascado por un problema del
# sistema. No cuentan los audios que él puede corregir (muy corto, sin voz, otro idioma).
MAX_FALLOS_HABLA = 3

# ---- Mensajes por MOTIVO real del fallo (ver exam/registro.py) -------------------------------
# El estudiante ve una frase sencilla y DISTINTA según la causa; el motivo técnico va al registro.
# Antes todo caía en "¿tienes internet?" o "revisa que faster-whisper esté instalado", que casi
# siempre era falso.

AVISO_TTS = {
    "red": "No pude conectarme al servicio de voz (revisa la conexión, el proxy o el firewall).",
    "tiempo": "El servicio de voz tardó demasiado en responder.",
    "reloj": "El servicio de voz rechazó la petición; suele ser la hora del computador.",
    "servicio": "El servicio de voz respondió, pero no entregó el audio.",
    "corte": "La conexión con el servicio de voz se cortó a mitad del audio.",
    "vacio": "El servicio de voz devolvió un audio vacío.",
    "escritura": "No pude guardar el audio en el disco.",
    "dependencia": "Falta instalar edge-tts (pip install -r requirements.txt).",
    "envio": "El audio se generó bien, pero Telegram no lo aceptó.",
    "envio_prohibido": "Tu cuenta de Telegram no permite recibir notas de voz.",
    "desconocido": "No pude generar el audio.",
}

# (mensaje para el estudiante, ¿es un fallo que él NO puede arreglar?)
AVISO_STT = {
    "archivo_falta": ("No me llegó el archivo del audio. Grábalo otra vez 🎤", False),
    "archivo_vacio": ("El audio llegó vacío. Grábalo otra vez 🎤", False),
    "formato": ("No pude leer ese audio. Mándame una nota de voz grabada en Telegram "
                "(mantén presionado el micrófono) 🎤", False),
    "sin_voz": ("No escuché voz en el audio 😕 Grábalo otra vez, más cerca del micrófono 🎤", False),
    "dependencia": ("Falta instalar faster-whisper en el entorno del proyecto "
                    "(pip install -r requirements.txt).", True),
    "modelo_descarga": ("El modelo de voz todavía no está descargado y no pude bajarlo. "
                        "La primera vez hace falta internet.", True),
    "modelo_carga": ("No pude cargar el modelo de voz.", True),
    "memoria": ("No hay memoria suficiente para el modelo de voz. "
                "Prueba con un modelo más liviano (WHISPER_MODEL=tiny).", True),
    "transcripcion": ("El modelo falló al transcribir tu audio.", True),
    "desconocido": ("No pude procesar tu audio.", True),
}


def en_examen(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return "examen" in context.user_data


def tiene_nivel(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return "nivel" in context.user_data


def _estado_inicial(language: str, level: str) -> dict:
    """Estado de un nivel que empieza. Se usa al iniciar el examen y al pasar al nivel siguiente."""
    return {
        "language": language,
        "level": level,
        "part": "generando",
        # Lectura
        "q": 0,
        "answers": [],
        "questions": [],
        # Escucha
        "listening": [],
        "l_q": 0,
        "l_answers": [],
        "l_rep": 0,
        # Habla
        "habla_fallos": 0,
        # Resultado
        "scores": {},
    }


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
    """Genera con Ollama las preguntas de lectura y de escucha del nivel actual.
    Devuelve False solo si falló la LECTURA (sin ella no hay examen).
    error_extra: mensaje de error propio (por ejemplo cuando ya se guardó un nivel provisional)."""
    ex = context.user_data["examen"]
    banco = BANCOS[ex["level"]]
    espera = await message.reply_text("Preparando tu examen… ⏳ (puede tardar un poquito)")
    try:
        # generate_reading() es síncrona: se corre en un hilo para no congelar el bot
        ex["questions"] = await asyncio.to_thread(generate_reading, banco, ex["language"])
    except Exception as exc:
        log.exception("No se pudo generar el examen %s", ex.get("level"))
        context.user_data.pop("examen", None)
        await espera.edit_text(
            error_extra
            or "No pude preparar el examen. ¿Está encendido Ollama? Escribe /start para intentarlo de nuevo."
        )
        return False

    try:   # avisar del cambio de etapa es opcional: si falla, no debe afectar al examen
        await espera.edit_text("Preparando la parte de escucha… 🎧")
    except Exception:
        log.debug("No pude editar el mensaje de espera", exc_info=True)

    # Escucha: si no se logra generar, el examen sigue sin esa parte (no se penaliza al estudiante)
    try:
        ex["listening"] = await asyncio.to_thread(generate_listening, banco, ex["language"])
    except Exception:
        log.warning("No se pudo generar la escucha de %s; el examen sigue sin ella", ex["level"], exc_info=True)
        ex["listening"] = []

    try:
        await espera.delete()
    except Exception:
        log.debug("No pude borrar el mensaje de espera", exc_info=True)
    return True


async def elegir_idioma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if en_examen(context):  # doble clic mientras se generan las preguntas
        return
    language = query.data.split(":")[1]
    context.user_data["examen"] = _estado_inicial(language, "A1")
    await query.edit_message_text(f"Perfecto: {IDIOMAS[language]}. Empezamos con el nivel A1. 💪")
    if not await _preparar_preguntas(query.message, context):
        return
    context.user_data["examen"]["part"] = "lectura"
    await _enviar_pregunta(query.message, context)


# ---------------------------------------------------------------- Utilidades de mensajes

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


def _opciones_y_filas(opciones: list[str], prefijo: str, indice: int) -> tuple[str, list[list[InlineKeyboardButton]]]:
    """Devuelve (texto extra para el mensaje, filas de botones).
    Si alguna opción no cabe en un botón (B1: actitud/intención), se listan A/B/C en el mensaje
    y los botones quedan solo con la letra. Lo usan la lectura y la escucha."""
    if any(len(op) > OPCION_LARGA for op in opciones):
        extra = "\n\n" + "\n".join(f"{LETRAS[i]}) {op}" for i, op in enumerate(opciones))
        filas = [[
            InlineKeyboardButton(LETRAS[i], callback_data=f"{prefijo}:{indice}:{i}")
            for i in range(len(opciones))
        ]]
        return extra, filas
    filas = [
        [InlineKeyboardButton(op, callback_data=f"{prefijo}:{indice}:{i}")]
        for i, op in enumerate(opciones)
    ]
    return "", filas


def _checklist(banco, skill: str, language: str) -> list[dict]:
    """Checklist de la tarea (skill "writing" o "speaking") para el idioma del examen.
    En español usa TASK_CHECKLIST_ES si el banco lo define (algunos requisitos nombran gramática
    inglesa, como "going to"); si no, el de inglés."""
    if language == "es" and skill in getattr(banco, "TASK_CHECKLIST_ES", {}):
        return banco.TASK_CHECKLIST_ES[skill]
    return banco.TASK_CHECKLIST[skill]


def _tarea_escritura(banco, ex: dict) -> tuple[dict, list[dict]]:
    """(prompt por idioma, checklist) de la tarea de escritura de este examen.
    Si el banco define WRITING_TASKS (B1), usa la tarea elegida al azar y guardada en ex["writing_task"]
    (solo su id, para que sobreviva a la persistencia). Si no (A1, A2), usa WRITING_PROMPT y TASK_CHECKLIST.
    En español, una tarea puede traer "checklist_es" y el banco TASK_CHECKLIST_ES."""
    es = ex.get("language") == "es"
    tareas = getattr(banco, "WRITING_TASKS", None)
    if tareas:
        tarea = next((t for t in tareas if t["id"] == ex.get("writing_task")), None)
        if tarea:
            checklist = tarea.get("checklist_es", tarea["checklist"]) if es else tarea["checklist"]
            return tarea["prompt"], checklist
    return banco.WRITING_PROMPT, _checklist(banco, "writing", ex.get("language", "en"))


def _elegir_tarea_escritura(banco, ex: dict):
    """Si el banco tiene varias tareas de escritura, el CÓDIGO elige una al azar y guarda su id."""
    tareas = getattr(banco, "WRITING_TASKS", None)
    if tareas:
        ex["writing_task"] = random.choice(tareas)["id"]
    else:
        ex.pop("writing_task", None)


# ---------------------------------------------------------------- Lectura

async def _enviar_pregunta(message, context: ContextTypes.DEFAULT_TYPE):
    ex = context.user_data["examen"]
    preguntas = ex["questions"]
    pregunta = preguntas[ex["q"]]
    encabezado = f"📖 {ex['level']} · Lectura {ex['q'] + 1}/{len(preguntas)}"
    if pregunta.get("text"):  # pregunta de comprensión con mini-texto
        cuerpo = f"{encabezado}\n\n📄 {pregunta['text']}\n\n❓ {pregunta['q']}"
    else:
        cuerpo = f"{encabezado}\n\n{pregunta['q']}"

    extra, filas = _opciones_y_filas(pregunta["options"], "ans", ex["q"])
    await message.reply_text((cuerpo + extra)[:4096], reply_markup=InlineKeyboardMarkup(filas))


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

    # Sigue la escucha (si se pudo generar); si no, pasa directo a la escritura
    if ex.get("listening"):
        ex["part"] = "escucha"
        ex["l_q"] = 0
        ex["l_answers"] = []
        repeticion = "una vez" if REPETICIONES_AUDIO == 1 else f"{REPETICIONES_AUDIO} veces"
        await query.message.reply_text(
            f"🎧 Escucha\n\nVas a oír {len(ex['listening'])} audios cortos. Después de cada uno, "
            f"responde la pregunta. Puedes repetir cada audio {repeticion}."
        )
        await _enviar_escucha(query.message, context)
        return

    await _pasar_a_escritura(query.message, ex)


# ---------------------------------------------------------------- Escucha

async def _enviar_por_telegram(message, ruta: str, formato: str) -> None:
    """Envía el audio ya generado. Lanza Fallo("telegram", "enviar", ...) si Telegram no lo acepta.

    Telegram pide .ogg con OPUS para una nota de voz; exam/tts.py ya convierte el mp3 de edge-tts.
    Si solo hay mp3, se manda como archivo de audio, que sí es un formato aceptado."""
    if formato == "ogg":
        try:
            with medir("telegram", "enviar_voz", bytes=os.path.getsize(ruta)):
                with open(ruta, "rb") as archivo:
                    await message.reply_voice(voice=archivo, caption="🎧 Escucha con atención")
            return
        except Exception as exc:
            if "VOICE_MESSAGES_FORBIDDEN" in describir(exc).upper():
                raise Fallo("telegram", "enviar", "envio_prohibido", exc) from exc
            log.warning("La nota de voz no se pudo enviar; va como archivo de audio | %s", describir(exc))

    try:   # mp3, o la nota de voz que Telegram rechazó
        with medir("telegram", "enviar_audio", bytes=os.path.getsize(ruta)):
            with open(ruta, "rb") as archivo:
                await message.reply_audio(audio=archivo, title="Audio", caption="🎧 Escucha con atención")
    except Exception as exc:
        raise Fallo("telegram", "enviar", "envio", exc) from exc


async def _enviar_audio(message, context: ContextTypes.DEFAULT_TYPE, pregunta: dict, indice: int):
    """Genera el audio del texto y lo envía. Devuelve True si el estudiante pudo OÍRLO.

    Las etapas (generar el audio / convertirlo / enviarlo por Telegram) fallan por separado y cada
    una tiene su propio aviso: el bot ya no dice "¿tienes internet?" cuando la causa es otra.
    Si no hay audio, se muestra el texto escrito para no frenar el examen y queda anotado: esa
    pregunta midió lectura, no escucha, y no cuenta en el puntaje (ver responder_escucha)."""
    ex = context.user_data["examen"]
    velocidad = ESCUCHA_CONFIG.get(ex["level"], ESCUCHA_CONFIG["A1"])["rate"]
    aviso = None
    try:
        # ignore_cleanup_errors: en Windows, borrar la carpeta temporal puede fallar si el archivo
        # quedó abierto, y ese error NO debe confundirse con un fallo al generar el audio.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            info = await synthesize(
                pregunta["text"], ex["language"], os.path.join(tmp, "audio.mp3"),
                rate=velocidad, voice_index=indice,
            )
            await _enviar_por_telegram(message, info["ruta"], info["formato"])
            log.info("Escucha %s enviada como %s por %s (%d intento(s), %d bytes)",
                     indice + 1, info["formato"], info["motor"], info["intentos"], info["bytes"])
    except Fallo as fallo:
        registrar_fallo(fallo)
        aviso = AVISO_TTS.get(fallo.motivo, AVISO_TTS["desconocido"])
    except Exception as exc:
        log.exception("Fallo no previsto al preparar el audio de la escucha")
        aviso = f"{AVISO_TTS['desconocido']} ({type(exc).__name__})"

    if aviso is None:
        pregunta["oido"] = True
        return True

    # Solo cuenta como "leída" si NUNCA se pudo oír: si falla al repetirla, ya la había oído.
    if not pregunta.get("oido"):
        pregunta["leido"] = True   # queda registrado en la revisión final
    await _responder_largo(
        message,
        f"{aviso} 😕\n\nPara no frenar el examen, lee el texto:\n\n«{pregunta['text']}»"
    )
    return False


async def _enviar_escucha(message, context: ContextTypes.DEFAULT_TYPE):
    ex = context.user_data["examen"]
    preguntas = ex["listening"]
    i = ex["l_q"]
    pregunta = preguntas[i]
    ex["l_rep"] = 0

    hay_audio = await _enviar_audio(message, context, pregunta, i)

    extra, filas = _opciones_y_filas(pregunta["options"], "lis", i)
    if hay_audio:
        filas = filas + [[InlineKeyboardButton("🔁 Escuchar otra vez", callback_data=f"rep:{i}")]]
    cuerpo = f"🎧 {ex['level']} · Escucha {i + 1}/{len(preguntas)}\n\n❓ {pregunta['q']}{extra}"
    await message.reply_text(cuerpo[:4096], reply_markup=InlineKeyboardMarkup(filas))


async def responder_escucha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ex = context.user_data.get("examen")
    _, q_idx, opcion = query.data.split(":")

    # Ignora botones viejos o repetidos
    if not ex or ex["part"] != "escucha" or int(q_idx) != ex["l_q"]:
        return

    preguntas = ex["listening"]
    ex["l_answers"].append(int(opcion))
    ex["l_q"] += 1
    await query.edit_message_reply_markup(reply_markup=None)

    if ex["l_q"] < len(preguntas):
        await _enviar_escucha(query.message, context)
        return

    # Solo cuentan las que de verdad se OYERON. Si el audio falló y hubo que mostrar el texto,
    # esa pregunta midió lectura, no escucha: no se incluye en el puntaje. Si ninguna tuvo audio,
    # la escucha queda sin evaluar y el promedio del nivel no la tiene en cuenta.
    evaluables = [(p, a) for p, a in zip(preguntas, ex["l_answers"]) if not p.get("leido")]
    if evaluables:
        correctas = sum(1 for p, a in evaluables if p["answer"] == a)
        ex["scores"]["escucha"] = 100 * correctas / len(evaluables)
    else:
        log.warning("Ningún audio de la escucha se pudo generar: el nivel se evalúa sin esa parte")

    await _pasar_a_escritura(query.message, ex)


async def repetir_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ex = context.user_data.get("examen")
    _, q_idx = query.data.split(":")

    if not ex or ex["part"] != "escucha" or int(q_idx) != ex["l_q"]:
        await query.answer()
        return

    if ex["l_rep"] >= REPETICIONES_AUDIO:
        await query.answer("Ya usaste la repetición de este audio ✋", show_alert=True)
        return

    ex["l_rep"] += 1
    await query.answer()
    await _enviar_audio(query.message, context, ex["listening"][ex["l_q"]], ex["l_q"])


def _revision_escucha(ex: dict) -> str:
    """Revisión de la escucha con lo que decía cada audio. Se muestra al FINAL del nivel:
    antes sería hacer trampa, porque el estudiante vería el texto que debía oír."""
    preguntas = ex.get("listening") or []
    respuestas = ex.get("l_answers") or []
    if not preguntas or not respuestas:
        return ""
    bloques = ["🎧 Revisión de escucha"]
    for i, (p, elegida) in enumerate(zip(preguntas, respuestas), start=1):
        correcta = p["answer"]
        if elegida == correcta:
            resultado = f"✅ {p['options'][elegida]}"
        else:
            resultado = f"❌ {p['options'][elegida]} (correcta: {p['options'][correcta]})"
        nota = " (se mostró escrito: no hubo audio)" if p.get("leido") else ""
        bloques.append(f"{i}. {p['q']} → {resultado}{nota}\n📝 «{p['text']}»")
    return "\n\n".join(bloques)


# ---------------------------------------------------------------- Escritura

async def _pasar_a_escritura(message, ex: dict):
    banco = BANCOS[ex["level"]]
    ex["part"] = "escritura"
    _elegir_tarea_escritura(banco, ex)
    prompt, _ = _tarea_escritura(banco, ex)
    await message.reply_text(f"✍️ Escritura\n\n{prompt[ex['language']]}")


async def _pasar_a_habla(message, ex: dict):
    banco = BANCOS[ex["level"]]
    ex["part"] = "habla"
    aviso = "" if modelo_cargado() else "\n\n(La primera nota de voz tarda más: se carga el modelo de voz.)"
    await message.reply_text(f"🎤 Habla\n\n{banco.SPEAKING_PROMPT[ex['language']]}{aviso}")


async def texto_de_examen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Se llama al inicio de responder(). Devuelve True si el mensaje era parte del examen."""
    ex = context.user_data.get("examen")
    if not ex:
        return False

    if ex["part"] == "generando":
        await update.message.reply_text("Estoy preparando tu examen, un momento ⏳")
        return True

    if ex["part"] in ("lectura", "escucha"):
        await update.message.reply_text("Responde con los botones de la pregunta 👆")
        return True

    if ex["part"] == "habla":
        await update.message.reply_text(
            "Ahora envíame una nota de voz 🎤 (mantén presionado el micrófono en Telegram)"
        )
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
        log.exception("Fallo al calificar la escritura")
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

    await _pasar_a_habla(update.message, ex)
    return True


# ---------------------------------------------------------------- Habla

def _adjunto_de_voz(message):
    """La nota de voz o, si el usuario mandó un archivo de audio en vez de grabar, ese archivo."""
    return getattr(message, "voice", None) or getattr(message, "audio", None)


async def _fallo_tecnico_habla(message, context: ContextTypes.DEFAULT_TYPE, aviso: str) -> None:
    """Un fallo que el estudiante NO puede arreglar (Whisper sin instalar, Ollama caído...).
    Tras varios seguidos se cierra el nivel sin la parte de habla, para no dejarlo atascado."""
    ex = context.user_data["examen"]
    ex["habla_fallos"] = ex.get("habla_fallos", 0) + 1
    if ex["habla_fallos"] < MAX_FALLOS_HABLA:
        await message.edit_text(aviso)
        return
    log.error("La parte de habla falló %d veces en %s: se cierra el nivel sin ella",
              ex["habla_fallos"], ex["level"])
    await message.edit_text(
        "Sigo sin poder procesar las notas de voz 😕 Para no dejarte esperando, cierro este nivel "
        "sin la parte de habla: no te resta puntos."
    )
    await _cerrar_nivel(message, context)


async def voz_de_examen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Se llama cuando llega una nota de voz o un audio. Devuelve True si era parte del examen."""
    ex = context.user_data.get("examen")
    if not ex:
        return False

    if ex["part"] != "habla":
        await update.message.reply_text("Todavía no es momento de la nota de voz 🙂 Sigue con la parte actual.")
        return True

    voz = _adjunto_de_voz(update.message)
    if voz is None:   # no debería pasar, pero antes esto tumbaba el bot
        await update.message.reply_text("No encontré el audio 😕 Graba una nota de voz e inténtalo otra vez 🎤")
        return True

    minimo = MIN_SEGUNDOS_VOZ.get(ex["level"], 12)
    duracion = getattr(voz, "duration", None) or 0
    if 0 < duracion < minimo:
        await update.message.reply_text(
            f"Tu audio es muy corto ({duracion} s; mínimo {minimo} s). Grábalo de nuevo 🎤"
        )
        return True

    banco = BANCOS[ex["level"]]
    espera = await update.message.reply_text(
        "Escuchando tu audio… 🎧" if modelo_cargado()
        else "Escuchando tu audio… 🎧 (la primera vez tarda más: se carga el modelo de voz)"
    )
    try:
        # ignore_cleanup_errors: en Windows el borrado de la carpeta temporal puede fallar si el
        # archivo quedó abierto, y ese error NO debe confundirse con un fallo de la transcripción.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            ruta = os.path.join(tmp, "nota.ogg")
            # Etapa 1: bajar el archivo de Telegram (su propio fallo, con su propio aviso)
            try:
                with medir("telegram", "descargar_voz", segundos=duracion):
                    archivo = await voz.get_file()
                    await archivo.download_to_drive(ruta)
            except Exception as exc:
                log.warning("No pude descargar la nota de voz de Telegram | %s", exc)
                await espera.edit_text(
                    "No pude descargar tu audio de Telegram 😕 Vuelve a enviarlo 🎤"
                )
                return True

            # Etapas 2 a 4 (revisar el archivo, cargar el modelo, transcribir): exam/stt.py las
            # separa y dice en cuál falló. El idioma se FUERZA al del examen; quién juzga si habló
            # en el idioma correcto es el calificador, que mira el contenido.
            audio = await asyncio.to_thread(transcribe, ruta, ex["language"])
    except Fallo as fallo:
        registrar_fallo(fallo)
        mensaje, es_tecnico = AVISO_STT.get(fallo.motivo, AVISO_STT["desconocido"])
        if es_tecnico:
            await _fallo_tecnico_habla(espera, context, f"{mensaje} 😕")
        else:
            await espera.edit_text(mensaje)
        return True
    except Exception as exc:
        log.exception("Fallo no previsto al procesar la nota de voz")
        await _fallo_tecnico_habla(
            espera, context, f"{AVISO_STT['desconocido'][0]} ({type(exc).__name__}) 😕"
        )
        return True

    log.info("Nota de voz transcrita: %d palabras, %.1f s, confianza %.2f, codec %s",
             audio["words"], audio["duration"], audio["confidence"], audio["codec"])

    texto = audio["text"]
    # Grabación inservible: se pide de nuevo SIN calificar (no se penaliza al estudiante)
    if not texto or audio["no_speech"] > MAX_SIN_VOZ:
        await espera.edit_text(AVISO_STT["sin_voz"][0])
        return True
    if audio["confidence"] < MIN_CONFIANZA:
        await espera.edit_text(
            "Se escucha muy bajo o con mucho ruido y no entendí lo que dijiste 😕\n"
            "Grábalo otra vez en un lugar silencioso y hablando claro 🎤"
        )
        return True

    try:
        r = await asyncio.to_thread(
            grade,
            texto,
            ex["level"],
            ex["language"],
            _checklist(banco, "speaking", ex["language"]),
            True,        # is_transcript: ignora puntuación y mayúsculas
            "Spanish",   # feedback_language
            "speaking",  # skill: los mensajes hablan de "audio" y "habla"
        )
    except Exception:
        log.exception("Fallo al calificar el habla")
        await _fallo_tecnico_habla(
            espera, context,
            "No pude calificar tu audio. ¿Está encendido Ollama? Envíalo de nuevo.",
        )
        return True

    if r["needs_rewrite"]:
        await espera.edit_text(f"Entendí: «{texto}»\n\n{r['feedback']}\n\nGrábalo de nuevo 🎤")
        return True

    ex["habla_fallos"] = 0   # funcionó: se reinicia la cuenta de fallos técnicos
    ex["scores"]["habla"] = r["score"]
    respuesta = f"Esto fue lo que entendí:\n«{texto}»\n\n{r['feedback']}"
    if r["errors"]:
        correcciones = "\n".join(f"• {e['fragment']} → {e['correction']}" for e in r["errors"][:3])
        respuesta += f"\n\nPara mejorar:\n{correcciones}"
    if audio["wpm"] and audio["wpm"] < WPM_MUY_LENTO:
        respuesta += "\n\n💡 Hablaste con muchas pausas. Intenta decir frases seguidas, sin parar tanto."
    await espera.edit_text(respuesta[:4096])

    await _cerrar_nivel(update.message, context)
    return True


# ---------------------------------------------------------------- Resultado

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


def _puntajes(s: dict) -> str:
    """Las partes evaluadas, en el orden del examen. La escucha puede no estar."""
    lineas = [f"Lectura: {s['lectura']:.0f}"]
    if "escucha" in s:
        lineas.append(f"Escucha: {s['escucha']:.0f}")
    lineas.append(f"Escritura: {s['escritura']:.0f}")
    if "habla" in s:
        lineas.append(f"Habla: {s['habla']:.0f}")
    return "\n".join(lineas)


async def _cerrar_nivel(message, context: ContextTypes.DEFAULT_TYPE):
    ex = context.user_data["examen"]
    nivel_rendido = ex["level"]
    s = ex["scores"]
    paso = level_passed(s["lectura"], s["escritura"], s.get("habla"), s.get("escucha"))
    siguiente = next_step(nivel_rendido, paso)

    resumen = (
        f"📊 Resultado {nivel_rendido}\n"
        f"{_puntajes(s)}\n\n"
        f"📖 Revisión de lectura\n{_revision_lectura(ex)}"
    )
    # Se calcula ANTES de reiniciar el estado para el nivel siguiente
    revision_escucha = _revision_escucha(ex)

    # Pasó y existe el examen del siguiente nivel: continúa
    if siguiente["action"] == "exam" and siguiente["level"] in BANCOS:
        ex.update(_estado_inicial(ex["language"], siguiente["level"]))
        ex.pop("writing_task", None)
        # Si falla la generación, el usuario no pierde lo ganado: queda en el nivel siguiente (provisional)
        context.user_data["nivel"] = {
            "language": ex["language"],
            "level": siguiente["level"],
            "provisional": True,
        }
        await _responder_largo(message, f"{resumen}\n\n✅ ¡Pasaste {nivel_rendido}! Sigue el examen {siguiente['level']}.")
        if revision_escucha:
            await _responder_largo(message, revision_escucha)
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
    await _responder_largo(message, f"{resumen}\n\n{mensaje}\n\nEscribe /start para ver el menú.")
    if revision_escucha:
        await _responder_largo(message, revision_escucha)
