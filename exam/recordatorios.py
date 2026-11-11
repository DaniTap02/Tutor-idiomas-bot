"""Recordatorios diarios de estudio con la JobQueue de python-telegram-bot.

    /recordatorio 19:30   -> todos los días a esa hora (hora de Colombia, America/Bogota)
    /recordatorio off     -> los apaga
    /recordatorio         -> dice cómo está configurado

Se guardan en SQLite (tabla `recordatorios`, en la misma base del historial) para que sobrevivan a
un reinicio del bot: al arrancar, programar_todos() vuelve a crear los trabajos. Cada envío queda en
`recordatorio_envios`, y exam/metricas.py calcula con eso la tasa de retorno (¿volvió a usar el bot
en las 24 horas siguientes?).

El mensaje invita a seguir la lección PENDIENTE (título de la lección actual del tutor), en el idioma
que estudia, con un botón para seguirla. Necesita python-telegram-bot[job-queue] (APScheduler) y,
en Windows, tzdata para la zona horaria.
"""
import logging
import re
from contextlib import closing
from datetime import time
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ContextTypes

from exam import historial
from exam.lecciones import LECCIONES

log = logging.getLogger(__name__)

ZONA = ZoneInfo("America/Bogota")
HORA_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS recordatorios (
    usuario INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    hora TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1,
    actualizado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recordatorio_envios (
    usuario INTEGER NOT NULL,
    fecha TEXT NOT NULL
);
"""

TEXTOS = {
    "en": {
        "leccion": "⏰ Time to practise! Your next lesson is waiting: «{titulo}» ({level}).",
        "sin_leccion": "⏰ Time to practise your {level} English! A few minutes a day makes a big difference.",
        "boton": "📚 Continue my lesson",
    },
    "es": {
        "leccion": "⏰ ¡Hora de practicar! Te espera tu próxima lección: «{titulo}» ({level}).",
        "sin_leccion": "⏰ ¡Hora de practicar tu español {level}! Unos minutos al día hacen la diferencia.",
        "boton": "📚 Seguir mi lección",
    },
}


def _conectar():
    con = historial.conectar()
    con.executescript(ESQUEMA)
    return con


def nombre_trabajo(usuario: int) -> str:
    return f"recordatorio:{usuario}"


def leer_hora(texto: str) -> time | None:
    """'7:05' o '19:30' -> time(19, 30) con la zona de Colombia. None si no es una hora válida."""
    m = HORA_RE.match((texto or "").strip())
    if not m:
        return None
    return time(int(m.group(1)), int(m.group(2)), tzinfo=ZONA)


def guardar(usuario: int, chat_id: int, hora: str | None) -> bool:
    """hora=None apaga el recordatorio. Devuelve False si la base falló."""
    try:
        with closing(_conectar()) as con, con:
            if hora is None:
                con.execute("UPDATE recordatorios SET activo = 0, actualizado = ? WHERE usuario = ?",
                            (historial.ahora(), usuario))
            else:
                con.execute("INSERT INTO recordatorios (usuario, chat_id, hora, activo, actualizado) "
                            "VALUES (?, ?, ?, 1, ?) ON CONFLICT(usuario) DO UPDATE SET "
                            "chat_id = excluded.chat_id, hora = excluded.hora, activo = 1, "
                            "actualizado = excluded.actualizado",
                            (usuario, chat_id, hora, historial.ahora()))
        return True
    except Exception:
        log.warning("No pude guardar el recordatorio", exc_info=True)
        return False


def activos() -> list[tuple[int, int, str]]:
    """[(usuario, chat_id, "HH:MM")] de los recordatorios encendidos."""
    try:
        with closing(_conectar()) as con:
            return [(f["usuario"], f["chat_id"], f["hora"])
                    for f in con.execute("SELECT usuario, chat_id, hora FROM recordatorios WHERE activo = 1")]
    except Exception:
        log.warning("No pude leer los recordatorios", exc_info=True)
        return []


def hora_de(usuario: int) -> str | None:
    try:
        with closing(_conectar()) as con:
            f = con.execute("SELECT hora FROM recordatorios WHERE usuario = ? AND activo = 1", (usuario,)).fetchone()
            return f["hora"] if f else None
    except Exception:
        return None


def mensaje_para(user_data: dict | None) -> tuple[str, str]:
    """(texto, idioma) del recordatorio: invita a seguir la lección pendiente en el idioma que estudia."""
    nivel = (user_data or {}).get("nivel") or {}
    idioma = nivel.get("language", "es")
    level = nivel.get("level", "A1")
    textos = TEXTOS.get(idioma, TEXTOS["es"])
    prog = ((user_data or {}).get("progreso") or {}).get(idioma) or {}
    lecciones = LECCIONES.get(level, [])
    i = prog.get("leccion", 0) if prog.get("level") == level else 0
    if nivel and i < len(lecciones):
        return textos["leccion"].format(titulo=lecciones[i]["titulo"][idioma], level=level), idioma
    return textos["sin_leccion"].format(level=level), idioma


async def enviar_recordatorio(context: ContextTypes.DEFAULT_TYPE):
    """Trabajo diario de la JobQueue. context.user_data es el del usuario (el trabajo lleva user_id)."""
    job = context.job
    texto, idioma = mensaje_para(context.user_data)
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton(TEXTOS[idioma]["boton"], callback_data="recl:seguir")]])
    try:
        await context.bot.send_message(chat_id=job.chat_id, text=texto, reply_markup=teclado)
    except Exception:
        log.warning("No pude enviar el recordatorio a %s", job.chat_id, exc_info=True)
        return
    historial._escribir("INSERT INTO recordatorio_envios VALUES (?, ?)", [(job.user_id, historial.ahora())])


def programar(job_queue, usuario: int, chat_id: int, hora: time) -> None:
    """(Re)programa el recordatorio diario del usuario: nunca quedan dos trabajos para el mismo."""
    cancelar(job_queue, usuario)
    job_queue.run_daily(enviar_recordatorio, time=hora, name=nombre_trabajo(usuario),
                        chat_id=chat_id, user_id=usuario)


def cancelar(job_queue, usuario: int) -> None:
    for job in job_queue.get_jobs_by_name(nombre_trabajo(usuario)):
        job.schedule_removal()


def programar_todos(app: Application) -> int:
    """Al arrancar el bot: vuelve a programar los recordatorios guardados en SQLite."""
    if app.job_queue is None:
        log.warning("Sin JobQueue (falta python-telegram-bot[job-queue]): no hay recordatorios")
        return 0
    n = 0
    for usuario, chat_id, hora in activos():
        t = leer_hora(hora)
        if t:
            programar(app.job_queue, usuario, chat_id, t)
            n += 1
    return n


async def comando_recordatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/recordatorio HH:MM · /recordatorio off · /recordatorio (ver cómo está)."""
    message = update.effective_message
    usuario = update.effective_user.id
    arg = (context.args or [""])[0].strip().lower() if context.args else ""
    if context.job_queue is None:
        await message.reply_text("Los recordatorios no están disponibles: falta instalar "
                                 "python-telegram-bot[job-queue] (pip install -r requirements.txt).")
        return

    if not arg:
        hora = hora_de(usuario)
        await message.reply_text(
            (f"⏰ Tu recordatorio diario está a las {hora} (hora de Colombia).\n" if hora
             else "⏰ No tienes recordatorio diario.\n")
            + "Para cambiarlo: /recordatorio 19:30 · Para apagarlo: /recordatorio off"
        )
        return

    if arg in ("off", "apagar", "no"):
        cancelar(context.job_queue, usuario)
        guardar(usuario, message.chat_id, None)
        await message.reply_text("🔕 Listo, apagué tu recordatorio diario. Lo activas de nuevo con /recordatorio 19:30")
        return

    hora = leer_hora(arg)
    if hora is None:
        await message.reply_text("No entendí la hora 😅 Escríbela en formato 24 horas, por ejemplo: /recordatorio 07:30 "
                                 "o /recordatorio 19:00")
        return
    texto_hora = f"{hora.hour:02d}:{hora.minute:02d}"
    if not guardar(usuario, message.chat_id, texto_hora):
        await message.reply_text("No pude guardar el recordatorio 😕 Inténtalo de nuevo.")
        return
    programar(context.job_queue, usuario, message.chat_id, hora)
    await message.reply_text(f"⏰ ¡Listo! Te recordaré estudiar todos los días a las {texto_hora} (hora de Colombia).")


async def boton_seguir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botón del recordatorio: sigue la lección pendiente."""
    from exam.tutor import leccion   # import aquí: tutor importa telegram_flow, y este módulo es más liviano
    await update.callback_query.answer()
    await leccion(update, context)
