"""Tutor adaptativo: práctica suelta (/practicar) y lecciones por nivel (/leccion).

Nada está escrito a mano: los ejercicios los genera Ollama EN VIVO con el mismo generador y el
mismo validador del examen (question_generator.generar_ejercicio: filtros de código + verificación
con el modelo + evidencia citada). Lo anulado va a voided_questions.jsonl y nunca cuenta en contra.
La escritura corta de cada lección la califica grader.py (antes pasa por detect_language de Lara).

Cada lección (temario en exam/lecciones.py):
    mini explicación generada -> 5 ejercicios generados y validados -> 1 escritura corta calificada

Adaptación (registrar_respuesta):
  - si falla un tema, el siguiente ejercicio es del MISMO tema con otra pregunta;
  - si acierta RACHA_PARA_AVANZAR seguidas, avanza a la escritura sin hacer las 5;
  - nunca pasa de MAX_EJERCICIOS_LECCION, para no dejar al estudiante atascado;
  - /practicar elige más seguido los temas que el estudiante ha fallado.
Al completar las 5 lecciones de un nivel, ofrece volver a presentar el examen de ese nivel para subir.

Los mensajes de práctica y lección van en el idioma que se estudia (TEXTOS); en A1 y A2 llevan el
botón "Ver traducción" (Lara). Estado por idioma en context.user_data["progreso"][idioma].
"""
import asyncio
import logging
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from exam import historial
from exam.grader import LANGUAGE_NAME, _call_ollama, grade
from exam.lecciones import LECCIONES, MIN_PALABRAS_LECCION
from exam.question_generator import NON_LATIN, _forbidden_re, _forbidden_text, generar_ejercicio
from exam.telegram_flow import (
    BANCOS,
    IDIOMAS,
    _opciones_y_filas,
    _responder_largo,
    en_examen,
    guardar_nivel,
    iniciar_examen_en,
)
from exam.traduccion import revisar_idioma, teclado_traduccion

log = logging.getLogger(__name__)

EJERCICIOS_POR_LECCION = 5
MAX_EJERCICIOS_LECCION = 10    # tope si sigue fallando: pasa a la escritura igual
RACHA_PARA_AVANZAR = 3         # aciertos seguidos con los que avanza antes de las 5
PROB_TEMA_FALLADO = 0.5        # en /practicar, probabilidad de repasar un tema que falló
MAX_EXPLICACION = 900          # caracteres

# Usuarios para los que se está generando algo ahora (no se guarda en disco: si el bot se cae a
# mitad, no queda nadie "bloqueado" para siempre).
_generando: set[int] = set()

TEXTOS = {
    "en": {
        "preparando": "Preparing your exercise… ⏳ (it can take a little while)",
        "preparando_leccion": "Preparing your lesson… ⏳ (it can take a little while)",
        "ocupado": "I'm still preparing it, one moment ⏳",
        "en_examen": "Finish the placement test first 📝",
        "fallo": "I couldn't prepare the exercise this time 😕 (is Ollama on?). It doesn't count against you. "
                 "Try again with {comando}.",
        "practica": "📝 Practice · {level} · {tema}",
        "correcto": "Correct! 🎉",
        "incorrecto": "Not quite 😊 The right answer is «{r}».",
        "otra": "Type /siguiente for another exercise.",
        "leccion": "📚 Lesson {n}/{total} · {titulo}\n🎯 {objetivo}",
        "ejercicio": "✏️ Exercise {i} · {tema}",
        "repetimos": "Let's practise that topic again with a different question 💪",
        "avanzas": "Great streak! 🔥 Let's go to the writing task.",
        "escritura": "✍️ Short writing\n\n{consigna}",
        "calificando": "Checking your text… ⏳",
        "reescribe": "Try again ✍️",
        "mejorar": "To improve:",
        "completa": "✅ Lesson completed! Writing score: {s:.0f}/100.\nType /leccion for the next one.",
        "fin_nivel": "🏆 You finished the {total} lessons of {level}! Do you want to take the {level} test again to move up?",
        "boton_examen": "📝 Take the {level} test",
        "boton_luego": "Later",
        "luego": "OK! You can review with /practicar, or take the test later with /leccion.",
        "sin_lecciones": "The lessons for {level} are coming soon. Meanwhile, practise with /practicar.",
        "no_entendi": "Answer with the buttons of the exercise 👆",
        "nivel": "📊 Your level\n\nLanguage: {idioma}\nLevel: {level}{prov}\nLesson: {n}/{total} · {titulo}\n"
                 "Completed lessons: {hechas}\nPractice: ✅ {ok}  ❌ {mal}",
        "provisional": " (provisional)",
        "idioma_cambiado": "Done! You are now practising {idioma} at level {level}. Type /leccion to continue.",
        "explicacion_respaldo": "Today you practise: {temas}.",
    },
    "es": {
        "preparando": "Preparando tu ejercicio… ⏳ (puede tardar un poquito)",
        "preparando_leccion": "Preparando tu lección… ⏳ (puede tardar un poquito)",
        "ocupado": "Todavía lo estoy preparando, un momento ⏳",
        "en_examen": "Primero termina el examen de nivel 📝",
        "fallo": "Esta vez no pude preparar el ejercicio 😕 (¿está encendido Ollama?). No cuenta en tu contra. "
                 "Inténtalo de nuevo con {comando}.",
        "practica": "📝 Práctica · {level} · {tema}",
        "correcto": "¡Correcto! 🎉",
        "incorrecto": "¡Casi! 😊 La respuesta correcta es «{r}».",
        "otra": "Escribe /siguiente para otro ejercicio.",
        "leccion": "📚 Lección {n}/{total} · {titulo}\n🎯 {objetivo}",
        "ejercicio": "✏️ Ejercicio {i} · {tema}",
        "repetimos": "Practiquemos ese tema otra vez con otra pregunta 💪",
        "avanzas": "¡Qué racha! 🔥 Pasamos a la escritura.",
        "escritura": "✍️ Escritura corta\n\n{consigna}",
        "calificando": "Revisando tu texto… ⏳",
        "reescribe": "Inténtalo de nuevo ✍️",
        "mejorar": "Para mejorar:",
        "completa": "✅ ¡Lección completada! Puntaje de la escritura: {s:.0f}/100.\nEscribe /leccion para la siguiente.",
        "fin_nivel": "🏆 ¡Completaste las {total} lecciones de {level}! ¿Quieres volver a presentar el examen de {level} para subir?",
        "boton_examen": "📝 Presentar el examen {level}",
        "boton_luego": "Más tarde",
        "luego": "¡Listo! Puedes repasar con /practicar o presentar el examen después con /leccion.",
        "sin_lecciones": "Las lecciones de {level} llegan pronto. Mientras tanto, practica con /practicar.",
        "no_entendi": "Responde con los botones del ejercicio 👆",
        "nivel": "📊 Tu nivel\n\nIdioma: {idioma}\nNivel: {level}{prov}\nLección: {n}/{total} · {titulo}\n"
                 "Lecciones completadas: {hechas}\nPráctica: ✅ {ok}  ❌ {mal}",
        "provisional": " (provisional)",
        "idioma_cambiado": "¡Listo! Ahora practicas {idioma} en el nivel {level}. Escribe /leccion para seguir.",
        "explicacion_respaldo": "Hoy practicas: {temas}.",
    },
}

NOMBRE_IDIOMA = {"en": {"en": "English", "es": "Spanish"}, "es": {"en": "inglés", "es": "español"}}

EXPLICACION_PROMPT = """You are a friendly {language} teacher for CEFR {level} students ({level_desc}).
Write a VERY short explanation for today's lesson, in {language}.
Lesson goal: {objetivo}
Topics of the lesson:
{temas}

Rules:
- Write ONLY in {language}, ONLY with the Latin alphabet.
- 3 to 5 short sentences that explain the key idea, then 2 or 3 short example sentences.
- Use only words and grammar that a CEFR {level} student knows. NEVER use: {forbidden}.
- No markdown (no *, #, tables). No questions to the student.

Reply ONLY with JSON: {{"explanation": "...", "examples": ["...", "..."]}}"""

LEVEL_DESC = {"A1": "absolute beginners", "A2": "elementary", "B1": "intermediate", "B2": "upper-intermediate"}


# ---------------------------------------------------------------- Datos del usuario

def _t(language: str, clave: str, **datos) -> str:
    return TEXTOS.get(language, TEXTOS["es"])[clave].format(**datos)


def _nivel(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """Nivel activo. Migra los datos viejos (antes solo había un nivel) al registro por idioma."""
    nivel = context.user_data.get("nivel")
    if nivel and nivel.get("language") not in context.user_data.get("niveles", {}):
        context.user_data.setdefault("niveles", {})[nivel["language"]] = dict(nivel)
    return nivel


def banco_de(level: str):
    """Banco del nivel. Si todavía no existe (B2 provisional), se usa el más alto que haya."""
    if level in BANCOS:
        return BANCOS[level]
    return BANCOS[sorted(BANCOS)[-1]]


def _pool(banco, language: str, kind: str) -> list[str]:
    nombre = "GRAMMAR_TARGETS" if kind == "grammar" else "VOCAB_TARGETS"
    if language == "es":
        return getattr(banco, nombre + "_ES", getattr(banco, nombre))
    return getattr(banco, nombre)


def resolver_tema(banco, language: str, kind: str, inicio: str) -> str:
    """El tema COMPLETO del banco (con su alcance) que empieza por `inicio`. Lanza KeyError si no está."""
    for tema in _pool(banco, language, kind):
        if tema.startswith(inicio):
            return tema
    raise KeyError(f"El banco {getattr(banco, 'LEVEL', 'A1')} ({language}) no tiene el tema «{inicio}»")


def temas_de_leccion(leccion: dict, banco, language: str) -> list[tuple[str, str]]:
    """[(kind, tema completo)] intercalando gramática y vocabulario."""
    gram = [("grammar", resolver_tema(banco, language, "grammar", t)) for t in leccion["gramatica"][language]]
    voc = [("vocab", resolver_tema(banco, language, "vocab", t)) for t in leccion["vocabulario"][language]]
    out = []
    while gram or voc:
        if gram:
            out.append(gram.pop(0))
        if voc:
            out.append(voc.pop(0))
    return out


def _tema_corto(tema: str) -> str:
    """'Verb To Be (I am, ...): ...' -> 'Verb To Be'."""
    corto = tema.split("(")[0].split(":")[0].strip()
    return corto[:50] or tema[:50]


def progreso_nuevo(level: str) -> dict:
    return {"level": level, "leccion": 0, "paso": "inicio", "completadas": [], **estado_ejercicios()}


def estado_ejercicios() -> dict:
    return {"respondidas": 0, "racha": 0, "repetir": None, "cola": 0}


def progreso(context: ContextTypes.DEFAULT_TYPE, language: str, level: str) -> dict:
    """Progreso de las lecciones en ese idioma. Si el nivel cambió (subió o bajó), empieza de cero."""
    todos = context.user_data.setdefault("progreso", {})
    prog = todos.get(language)
    if not prog or prog.get("level") != level:
        prog = todos[language] = progreso_nuevo(level)
    return prog


# ---------------------------------------------------------------- Adaptación (funciones puras)

def elegir_tema(prog: dict, temas: list[tuple[str, str]]) -> tuple[str, str]:
    """Si falló el último, repite ese tema; si no, el siguiente de la lección en orden."""
    if prog.get("repetir"):
        kind, tema = prog["repetir"]
        return kind, tema
    kind, tema = temas[prog["cola"] % len(temas)]
    prog["cola"] += 1
    return kind, tema


def registrar_respuesta(prog: dict, kind: str, tema: str, correcta: bool) -> str:
    """Actualiza el progreso y devuelve qué sigue: "otro", "repetir" o "escritura"."""
    prog["respondidas"] += 1
    if correcta:
        prog["racha"] += 1
        prog["repetir"] = None
    else:
        prog["racha"] = 0
        prog["repetir"] = [kind, tema]
    if prog["respondidas"] >= MAX_EJERCICIOS_LECCION:
        return "escritura"
    if correcta and prog["racha"] >= RACHA_PARA_AVANZAR:
        return "escritura"
    if correcta and prog["respondidas"] >= EJERCICIOS_POR_LECCION:
        return "escritura"
    return "otro" if correcta else "repetir"


def tema_para_practica(user_data: dict, banco, language: str) -> tuple[str, str]:
    """Tema de /practicar: a veces repasa uno que el estudiante falló en este nivel e idioma."""
    fallados = [tuple(t) for t in user_data.get("temas_fallados", {}).get(language, [])
                if t[1] in _pool(banco, language, t[0])]
    if fallados and random.random() < PROB_TEMA_FALLADO:
        return random.choice(fallados)
    kind = "grammar" if random.random() < 0.6 else "vocab"
    return kind, random.choice(_pool(banco, language, kind))


def _anotar_tema(user_data: dict, language: str, kind: str, tema: str, correcta: bool):
    """Temas fallados por idioma: entran al fallar y salen al acertar."""
    fallados = user_data.setdefault("temas_fallados", {}).setdefault(language, [])
    item = [kind, tema]
    if not correcta and item not in fallados:
        fallados.append(item)
    elif correcta and item in fallados:
        fallados.remove(item)


def checklist_de(leccion: dict, language: str) -> list[dict]:
    """Checklist para grader.py: label_es es lo que ve el estudiante si le falta (aquí, en su idioma de estudio)."""
    return [{"id": c["id"], "check": c["check"], "label_es": c["label"][language]} for c in leccion["checklist"]]


def generar_explicacion(leccion: dict, banco, language: str, level: str) -> str:
    """Mini explicación con Ollama. Pasa por filtros de código (alfabeto, largo, prohibidos del nivel);
    si no pasa en 2 intentos o Ollama falla, se usa un texto de respaldo con el objetivo y los temas."""
    temas = temas_de_leccion(leccion, banco, language)
    system = EXPLICACION_PROMPT.format(
        language=LANGUAGE_NAME[language], level=level, level_desc=LEVEL_DESC.get(level, ""),
        objetivo=leccion["objetivo"][language],
        temas="\n".join(f"- {t}" for _, t in temas),
        forbidden=_forbidden_text(banco, language),
    )
    prohibido = _forbidden_re(banco, language)
    for _ in range(2):
        try:
            data = _call_ollama(system, "Write the explanation now.", temperature=0.4)
            texto = str(data.get("explanation", "")).strip()
            ejemplos = [str(e).strip() for e in data.get("examples", []) if str(e).strip()][:3]
        except Exception as exc:
            log.warning("Fallo del modelo al generar la explicación de %s: %r", leccion["id"], exc)
            continue
        completo = texto + ("\n\n" + "\n".join(f"• {e}" for e in ejemplos) if ejemplos else "")
        if not texto or len(completo) > MAX_EXPLICACION or NON_LATIN.search(completo) or "*" in completo:
            log.info("Explicación de %s descartada por formato", leccion["id"])
            continue
        if prohibido is not None and prohibido.search(completo):
            log.info("Explicación de %s descartada: usa gramática de otro nivel", leccion["id"])
            continue
        return completo
    return _t(language, "explicacion_respaldo", temas=", ".join(_tema_corto(t) for _, t in temas))


# ---------------------------------------------------------------- Envío de ejercicios

async def _nuevo_ejercicio(message, context: ContextTypes.DEFAULT_TYPE, origen: str, banco,
                           language: str, level: str, kind: str, tema: str, encabezado: str) -> bool:
    """Genera UNA pregunta validada y la envía con botones. origen: "pr" (práctica) o "lc" (lección)."""
    clave = id(context.user_data)
    if clave in _generando:
        await message.reply_text(_t(language, "ocupado"))
        return False
    _generando.add(clave)
    espera = await message.reply_text(_t(language, "preparando"))
    try:
        # generar_ejercicio() es síncrona (httpx): se corre en un hilo para no congelar el bot
        pregunta = await asyncio.to_thread(generar_ejercicio, banco, language, tema, kind)
    except Exception:
        log.warning("No se pudo generar el ejercicio (%s, %s)", level, tema[:50], exc_info=True)
        await espera.edit_text(_t(language, "fallo", comando="/leccion" if origen == "lc" else "/practicar"))
        return False
    finally:
        _generando.discard(clave)
    try:
        await espera.delete()
    except Exception:
        log.debug("No pude borrar el mensaje de espera", exc_info=True)

    n = context.user_data.get("ej_n", 0) + 1
    context.user_data["ej_n"] = n
    context.user_data["ej_actual"] = {
        "origen": origen, "n": n, "language": language, "level": level, "kind": kind, "topic": tema,
        "q": pregunta["q"], "options": pregunta["options"], "answer": pregunta["answer"], "respondida": False,
    }
    extra, filas = _opciones_y_filas(pregunta["options"], origen, n)
    await message.reply_text(f"{encabezado}\n\n{pregunta['q']}{extra}"[:4096],
                             reply_markup=InlineKeyboardMarkup(filas))
    return True


# ---------------------------------------------------------------- /practicar

async def practicar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/practicar y /siguiente: un ejercicio del nivel e idioma del usuario."""
    message = update.effective_message
    nivel = _nivel(context)
    if en_examen(context):
        await message.reply_text(_t(context.user_data["examen"]["language"], "en_examen"))
        return
    if not nivel:
        await message.reply_text("Primero haz el examen de nivel 📝 Escribe /start para empezar.")
        return
    language, level = nivel["language"], nivel["level"]
    context.user_data["esperando"] = None   # sale de la escritura de la lección, si estaba en ella
    banco = banco_de(level)
    kind, tema = tema_para_practica(context.user_data, banco, language)
    await _nuevo_ejercicio(message, context, "pr", banco, language, level, kind, tema,
                           _t(language, "practica", level=level, tema=_tema_corto(tema)))


async def responder_ejercicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botones de los ejercicios: pr:<n>:<opción> (práctica) y lc:<n>:<opción> (lección)."""
    query = update.callback_query
    await query.answer()
    origen, n, opcion = query.data.split(":")
    ej = context.user_data.get("ej_actual")
    if not ej or ej["respondida"] or ej["n"] != int(n) or ej["origen"] != origen:
        return   # botón viejo o repetido
    ej["respondida"] = True
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        log.debug("No pude quitar los botones", exc_info=True)

    language = ej["language"]
    correcta = int(opcion) == ej["answer"]
    clave = "correctas" if correcta else "incorrectas"
    context.user_data[clave] = context.user_data.get(clave, 0) + 1
    _anotar_tema(context.user_data, language, ej["kind"], ej["topic"], correcta)
    historial.registrar_ejercicio(context.user_data, "practica" if origen == "pr" else "leccion",
                                  language, ej["level"], ej["topic"], correcta)

    resultado = _t(language, "correcto") if correcta else _t(language, "incorrecto", r=ej["options"][ej["answer"]])
    if origen == "pr":
        await query.message.reply_text(f"{resultado}\n\n{_t(language, 'otra')}")
        return

    # Lección: decide qué sigue según la respuesta
    nivel = _nivel(context)
    prog = progreso(context, language, ej["level"])
    if not nivel or prog.get("paso") != "ejercicios":
        await query.message.reply_text(resultado)
        return
    siguiente = registrar_respuesta(prog, ej["kind"], ej["topic"], correcta)
    if siguiente == "escritura":
        aviso = _t(language, "avanzas") if correcta and prog["racha"] >= RACHA_PARA_AVANZAR \
            and prog["respondidas"] < EJERCICIOS_POR_LECCION else ""
        await query.message.reply_text(f"{resultado}\n\n{aviso}".strip())
        await _pasar_a_escritura(query.message, context, language, ej["level"])
        return
    if siguiente == "repetir":
        resultado += "\n\n" + _t(language, "repetimos")
    await query.message.reply_text(resultado)
    await _siguiente_ejercicio(query.message, context, language, ej["level"])


# ---------------------------------------------------------------- /leccion

def _leccion_actual(level: str, prog: dict) -> dict | None:
    lecciones = LECCIONES.get(level, [])
    return lecciones[prog["leccion"]] if prog["leccion"] < len(lecciones) else None


async def _siguiente_ejercicio(message, context, language: str, level: str):
    prog = progreso(context, language, level)
    leccion = _leccion_actual(level, prog)
    banco = banco_de(level)
    kind, tema = elegir_tema(prog, temas_de_leccion(leccion, banco, language))
    encabezado = _t(language, "ejercicio", i=prog["respondidas"] + 1, tema=_tema_corto(tema))
    await _nuevo_ejercicio(message, context, "lc", banco, language, level, kind, tema, encabezado)


async def _pasar_a_escritura(message, context, language: str, level: str):
    prog = progreso(context, language, level)
    leccion = _leccion_actual(level, prog)
    prog["paso"] = "escritura"
    context.user_data["esperando"] = "leccion_escritura"
    consigna = leccion["escritura"][language]
    await message.reply_text(_t(language, "escritura", consigna=consigna),
                             reply_markup=teclado_traduccion(context, consigna, language, language, level))


async def _ofrecer_examen(message, language: str, level: str):
    total = len(LECCIONES.get(level, []))
    teclado = InlineKeyboardMarkup([[
        InlineKeyboardButton(_t(language, "boton_examen", level=level), callback_data="rex:si"),
        InlineKeyboardButton(_t(language, "boton_luego"), callback_data="rex:no"),
    ]])
    await message.reply_text(_t(language, "fin_nivel", total=total, level=level), reply_markup=teclado)


async def leccion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/leccion: sigue la lección actual desde donde iba."""
    message = update.effective_message
    nivel = _nivel(context)
    if en_examen(context):
        await message.reply_text(_t(context.user_data["examen"]["language"], "en_examen"))
        return
    if not nivel:
        await message.reply_text("Primero haz el examen de nivel 📝 Escribe /start para empezar.")
        return
    language, level = nivel["language"], nivel["level"]
    if level not in LECCIONES or level not in BANCOS:
        await message.reply_text(_t(language, "sin_lecciones", level=level))
        return
    prog = progreso(context, language, level)
    if id(context.user_data) in _generando:
        await message.reply_text(_t(language, "ocupado"))
        return
    if prog["paso"] == "fin_nivel":
        await _ofrecer_examen(message, language, level)
        return

    actual = _leccion_actual(level, prog)
    if prog["paso"] == "escritura":
        await _pasar_a_escritura(message, context, language, level)
        return
    ej = context.user_data.get("ej_actual")
    if prog["paso"] == "ejercicios" and ej and ej["origen"] == "lc" and not ej["respondida"]:
        extra, filas = _opciones_y_filas(ej["options"], "lc", ej["n"])   # repite el ejercicio pendiente
        await message.reply_text(f"{ej['q']}{extra}"[:4096], reply_markup=InlineKeyboardMarkup(filas))
        return
    if prog["paso"] == "inicio":
        banco = banco_de(level)
        total = len(LECCIONES[level])
        espera = await message.reply_text(_t(language, "preparando_leccion"))
        _generando.add(id(context.user_data))
        try:
            explicacion = await asyncio.to_thread(generar_explicacion, actual, banco, language, level)
        finally:
            _generando.discard(id(context.user_data))
        try:
            await espera.delete()
        except Exception:
            log.debug("No pude borrar el mensaje de espera", exc_info=True)
        cabecera = _t(language, "leccion", n=prog["leccion"] + 1, total=total,
                      titulo=actual["titulo"][language], objetivo=actual["objetivo"][language])
        texto = f"{cabecera}\n\n{explicacion}"
        await message.reply_text(texto[:4096], reply_markup=teclado_traduccion(context, texto, language, language, level))
        prog.update(estado_ejercicios())
        prog["paso"] = "ejercicios"
    await _siguiente_ejercicio(message, context, language, level)


async def texto_de_leccion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Se llama desde responder() en bot.py. Devuelve True si el mensaje era la escritura de la lección."""
    if context.user_data.get("esperando") != "leccion_escritura":
        return False
    nivel = _nivel(context)
    if not nivel:
        context.user_data["esperando"] = None
        return False
    language, level = nivel["language"], nivel["level"]
    prog = progreso(context, language, level)
    actual = _leccion_actual(level, prog)
    if prog["paso"] != "escritura" or not actual:
        context.user_data["esperando"] = None
        return False

    texto = update.message.text
    espera = await update.message.reply_text(_t(language, "calificando"))
    # Lara (detect_language): si está claramente en otro idioma, se pide de nuevo sin calificar
    if await revisar_idioma(espera, texto, language, "writing"):
        return True
    try:
        r = await asyncio.to_thread(
            grade, texto, level, language, checklist_de(actual, language),
            False, LANGUAGE_NAME[language], "writing", MIN_PALABRAS_LECCION.get(level), language,
        )
    except Exception:
        log.exception("Fallo al calificar la escritura de la lección")
        await espera.edit_text(_t(language, "fallo", comando="/leccion"))
        return True

    if r["needs_rewrite"]:
        await espera.edit_text(f"{r['feedback']}\n\n{_t(language, 'reescribe')}")
        return True

    respuesta = r["feedback"]
    if r["errors"]:
        correcciones = "\n".join(f"• {e['fragment']} → {e['correction']}" for e in r["errors"][:3])
        respuesta += f"\n\n{_t(language, 'mejorar')}\n{correcciones}"
    respuesta += "\n\n" + _t(language, "completa", s=r["score"])
    await espera.edit_text(respuesta[:4096],
                           reply_markup=teclado_traduccion(context, r["feedback"], language, language, level))

    historial.registrar_leccion(context.user_data, language, level, actual["id"], r["score"])
    historial.registrar_errores(context.user_data, language, level, "leccion", "writing", r["errors"])

    context.user_data["esperando"] = None
    prog["completadas"].append(actual["id"])
    prog["leccion"] += 1
    prog.update(estado_ejercicios())
    if prog["leccion"] >= len(LECCIONES[level]):
        prog["paso"] = "fin_nivel"
        await _ofrecer_examen(update.message, language, level)
    else:
        prog["paso"] = "inicio"
    return True


async def responder_repaso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botones rex:si / rex:no al terminar las 5 lecciones de un nivel."""
    query = update.callback_query
    await query.answer()
    nivel = _nivel(context)
    if not nivel or en_examen(context):
        return
    language, level = nivel["language"], nivel["level"]
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        log.debug("No pude quitar los botones", exc_info=True)
    if query.data.endswith(":no"):
        await query.message.reply_text(_t(language, "luego"))
        return
    # Si no lo pasa, vuelve a hacer las lecciones del nivel (con preguntas nuevas)
    context.user_data.setdefault("progreso", {})[language] = progreso_nuevo(level)
    await iniciar_examen_en(query.message, context, language, level)


# ---------------------------------------------------------------- /nivel e /idioma

async def comando_nivel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nivel = _nivel(context)
    if not nivel:
        await update.effective_message.reply_text("Todavía no tienes nivel 📝 Escribe /start para hacer el examen.")
        return
    language, level = nivel["language"], nivel["level"]
    prog = progreso(context, language, level)
    total = len(LECCIONES.get(level, []))
    actual = _leccion_actual(level, prog) if total else None
    titulo = actual["titulo"][language] if actual else "—"
    await update.effective_message.reply_text(_t(
        language, "nivel",
        idioma=NOMBRE_IDIOMA[language][language], level=level,
        prov=_t(language, "provisional") if nivel.get("provisional") else "",
        n=min(prog["leccion"] + 1, total) if total else 0, total=total, titulo=titulo,
        hechas=", ".join(prog["completadas"]) or "—",
        ok=context.user_data.get("correctas", 0), mal=context.user_data.get("incorrectas", 0),
    ))


async def comando_idioma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if en_examen(context):
        await update.effective_message.reply_text("Primero termina el examen de nivel 📝")
        return
    niveles = context.user_data.get("niveles", {})
    _nivel(context)
    botones = []
    for code, nombre in IDIOMAS.items():
        extra = f" · {niveles[code]['level']}" if code in niveles else " · examen"
        botones.append(InlineKeyboardButton(nombre + extra, callback_data=f"idioma:{code}"))
    await update.effective_message.reply_text(
        "¿Qué idioma quieres practicar? 🌍\nSi todavía no tienes nivel en ese idioma, primero haces el examen.",
        reply_markup=InlineKeyboardMarkup([botones]),
    )


async def elegir_idioma_tutor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if en_examen(context):
        return
    language = query.data.split(":")[1]
    context.user_data["esperando"] = None
    niveles = context.user_data.get("niveles", {})
    if language in niveles:
        guardar_nivel(context, niveles[language])
        await query.edit_message_text(_t(language, "idioma_cambiado",
                                         idioma=NOMBRE_IDIOMA[language][language],
                                         level=niveles[language]["level"]))
        return
    await query.edit_message_text(f"Perfecto: {IDIOMAS[language]}. Primero el examen de nivel, desde A1. 💪")
    await iniciar_examen_en(query.message, context, language, "A1")
