import os
import logging

from dotenv import load_dotenv

# Antes de importar el resto: varios módulos leen sus variables (OLLAMA_*, LARA_*...) al importarse
load_dotenv()

from telegram import Update  # noqa: E402
from telegram.ext import (  # noqa: E402
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PicklePersistence,
    ContextTypes,
    TypeHandler,
    filters,
)

from exam import historial  # noqa: E402

from exam.telegram_flow import (  # noqa: E402
    elegir_idioma,
    en_examen,
    iniciar_examen,
    repetir_audio,
    responder_escucha,
    responder_lectura,
    texto_de_examen,
    tiene_nivel,
    voz_de_examen,
)
from exam.recordatorios import boton_seguir, comando_recordatorio, programar_todos  # noqa: E402
from exam.traduccion import comando_traducir, ver_traduccion  # noqa: E402
from exam.tutor import (  # noqa: E402
    comando_idioma,
    comando_nivel,
    elegir_idioma_tutor,
    leccion,
    practicar,
    responder_ejercicio,
    responder_repaso,
    texto_de_leccion,
)
from mcp_cliente import lara  # noqa: E402

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# httpx registra cada petición (incluida la URL de Telegram, que lleva el token): solo avisos
logging.getLogger("httpx").setLevel(logging.WARNING)

COMANDOS = (
    "/leccion - Seguir tu lección (explicación, ejercicios y escritura)\n"
    "/practicar - Un ejercicio suelto de tu nivel\n"
    "/siguiente - Otro ejercicio\n"
    "/nivel - Tu nivel, idioma y avance\n"
    "/puntos - Tu progreso acumulado (no se borra con /reiniciar)\n"
    "/idioma - Cambiar de idioma (inglés o español)\n"
    "/traducir <texto> - Traducir una palabra o frase\n"
    "/recordatorio HH:MM - Recordatorio diario (hora de Colombia); /recordatorio off lo apaga\n"
    "/reiniciar - Repetir el examen de nivel\n"
    "/help - Ver la ayuda"
)


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    # Primera vez: examen de ubicación
    if en_examen(context):
        await update.message.reply_text(
            "Tienes un examen en curso. ¡Sigue respondiendo! 💪"
        )
        return

    if not tiene_nivel(context):
        await iniciar_examen(update, context)
        return

    # Ya tiene nivel: menú normal
    nivel = context.user_data["nivel"]
    idioma = "inglés" if nivel["language"] == "en" else "español"
    await update.message.reply_text(
        f"¡Hola de nuevo! 👋 Estudias {idioma}, nivel {nivel['level']}.\n\n"
        f"Comandos disponibles:\n{COMANDOS}\n\n"
        "Escribe /leccion para seguir donde ibas."
    )


async def reiniciar(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Borra el nivel del idioma actual y vuelve a lanzar el examen (para pruebas)."""
    nivel = context.user_data.pop("nivel", None)
    if nivel:
        context.user_data.get("niveles", {}).pop(nivel["language"], None)
        context.user_data.get("progreso", {}).pop(nivel["language"], None)
    context.user_data.pop("examen", None)
    context.user_data["esperando"] = None
    await iniciar_examen(update, context)


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "📚 ¿Cómo usar el tutor?\n\n"
        "/start - Iniciar (la primera vez hace el examen de nivel)\n"
        f"{COMANDOS}\n\n"
        "Cada lección tiene una explicación corta, ejercicios con botones y una escritura corta. "
        "Si fallas un tema, lo repasamos con otras preguntas; si aciertas seguido, avanzas. "
        "Al terminar las 5 lecciones de tu nivel puedes volver a presentar el examen para subir."
    )


async def responder(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    # Si el usuario está en el examen o en la escritura de una lección, ese flujo atiende el mensaje
    if await texto_de_examen(update, context):
        return
    if await texto_de_leccion(update, context):
        return

    ej = context.user_data.get("ej_actual")
    if ej and not ej.get("respondida"):
        await update.message.reply_text(
            "Answer with the buttons of the exercise 👆" if ej["language"] == "en"
            else "Responde con los botones del ejercicio 👆"
        )
        return

    await update.message.reply_text(
        "¡Vamos a aprender juntos! 📚\n\n"
        "Escribe /leccion para seguir tu lección o /practicar para un ejercicio suelto.\n"
        "Para ver todos los comandos, escribe /help."
    )


async def recibir_voz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Notas de voz y audios: por ahora solo los usa la parte de habla del examen."""
    if await voz_de_examen(update, context):
        return

    await update.message.reply_text(
        "Gracias por el audio 🎤 Por ahora solo lo uso en la parte de habla "
        "del examen de nivel.\n\nEscribe /leccion para seguir con tu lección."
    )


NOMBRE_IDIOMA = {"en": "Inglés 🇬🇧", "es": "Español 🇪🇸"}
TIPO_ERROR = {"grammar": "gramática", "vocabulary": "vocabulario", "spelling": "ortografía", "otro": "otros"}


def texto_puntos(datos: dict) -> str:
    """Mensaje de /puntos a partir de historial.resumen_usuario()."""
    if not datos:
        return ("🏆 Tu progreso\n\nTodavía no tienes ejercicios guardados. "
                "Escribe /leccion o /practicar para empezar 💪")
    bloques = ["🏆 Tu progreso acumulado"]
    for idioma, d in datos.items():
        lineas = [f"\n{NOMBRE_IDIOMA.get(idioma, idioma)}"]
        ok, total = d.get("ejercicios", (0, 0))
        if total:
            lineas.append(f"✅ {ok}  ❌ {total - ok}  ({100 * ok / total:.0f}% de aciertos en {total} ejercicios)")
        if d.get("lecciones"):
            lineas.append(f"📚 Lecciones completadas: {d['lecciones']}")
        for nivel, aprobado, veces in d.get("examenes", []):
            lineas.append(f"📝 Examen {nivel}: {'aprobado ✅' if aprobado else 'no aprobado todavía'}"
                          f" ({veces} {'vez' if veces == 1 else 'veces'})")
        flojos = [t for t in d.get("temas_flojos", []) if t[1] < t[2]][:3]
        if flojos:
            lineas.append("🔁 Para repasar: " + "; ".join(
                f"{t[0].split('(')[0].strip()[:40]} ({t[1]}/{t[2]})" for t in flojos))
        if d.get("errores"):
            lineas.append("✍️ Errores en tus textos: " + ", ".join(
                f"{TIPO_ERROR.get(tipo, tipo)} {n}" for tipo, n in d["errores"]))
        bloques.append("\n".join(lineas))
    bloques.append("\n¡Sigue practicando para mejorar!")
    return "\n".join(bloques)[:4096]


async def puntos(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Progreso REAL acumulado (SQLite): no se pierde con /reiniciar ni al apagar el bot."""
    datos = historial.resumen_usuario(update.effective_user.id) if update.effective_user else {}
    await update.message.reply_text(texto_puntos(datos))


async def anotar_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Corre ANTES de cualquier manejador: guarda quién es el usuario (para el historial) y su actividad."""
    usuario = update.effective_user
    if usuario is None or context.user_data is None:
        return
    context.user_data["uid"] = usuario.id
    historial.registrar_actividad(usuario.id, "boton" if update.callback_query else "mensaje")


async def al_iniciar(app: Application):
    """Abre UNA sesión con el servidor MCP de Lara para toda la vida del bot (si está configurado)."""
    n = programar_todos(app)   # los recordatorios guardados en SQLite sobreviven al reinicio
    print(f"Recordatorios programados: {n}")
    lara.cliente.al_usar = historial.registrar_uso_lara   # uso de las 2 herramientas de Lara
    if await lara.iniciar():
        print("Lara Translate (MCP) conectado.")
    else:
        print(f"Lara Translate no disponible ({lara.cliente.ultimo_motivo}): el bot sigue sin traducción.")


async def al_apagar(app: Application):
    await lara.cerrar()


def main():
    if not TOKEN:
        raise RuntimeError(
            "No se encontró TELEGRAM_BOT_TOKEN en el archivo .env"
        )

    # Guarda user_data en disco: el nivel del usuario sobrevive al reiniciar el bot
    persistence = PicklePersistence(filepath="datos_bot.pkl")
    app = (
        Application.builder()
        .token(TOKEN)
        .persistence(persistence)
        .post_init(al_iniciar)
        .post_shutdown(al_apagar)
        .build()
    )

    # Grupo -1: se ejecuta antes que los demás manejadores y no los bloquea
    app.add_handler(TypeHandler(Update, anotar_usuario), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reiniciar", reiniciar))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("leccion", leccion))
    app.add_handler(CommandHandler("practicar", practicar))
    app.add_handler(CommandHandler("siguiente", practicar))
    app.add_handler(CommandHandler("nivel", comando_nivel))
    app.add_handler(CommandHandler("idioma", comando_idioma))
    app.add_handler(CommandHandler("puntos", puntos))
    app.add_handler(CommandHandler("traducir", comando_traducir))
    app.add_handler(CommandHandler("recordatorio", comando_recordatorio))
    app.add_handler(CallbackQueryHandler(boton_seguir, pattern=r"^recl:"))
    app.add_handler(CallbackQueryHandler(elegir_idioma, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(responder_lectura, pattern=r"^ans:"))
    app.add_handler(CallbackQueryHandler(responder_escucha, pattern=r"^lis:"))
    app.add_handler(CallbackQueryHandler(repetir_audio, pattern=r"^rep:"))
    app.add_handler(CallbackQueryHandler(ver_traduccion, pattern=r"^tr:"))
    app.add_handler(CallbackQueryHandler(responder_ejercicio, pattern=r"^(pr|lc):"))
    app.add_handler(CallbackQueryHandler(responder_repaso, pattern=r"^rex:"))
    app.add_handler(CallbackQueryHandler(elegir_idioma_tutor, pattern=r"^idioma:"))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, responder)
    )
    # Notas de voz (parte de habla). Se acepta también un archivo de audio adjunto.
    app.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO, recibir_voz)
    )

    print("Tutor de idiomas iniciado. Presiona Ctrl+C para detenerlo.")
    app.run_polling()


if __name__ == "__main__":
    main()
