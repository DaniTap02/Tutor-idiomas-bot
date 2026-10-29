
import os
import logging
import random
import unicodedata

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Ejercicios iniciales de español
EJERCICIOS = [
    {
        "pregunta": "¿Cuál es el plural de «casa»?",
        "opciones": ["casaes", "casas", "casess"],
        "respuesta": "casas",
        "explicacion": "La mayoría de los sustantivos terminados en vocal "
                       "forman el plural añadiendo -s: casa → casas."
    },
    {
        "pregunta": "Completa: «Yo ___ estudiante».",
        "opciones": ["soy", "eres", "somos"],
        "respuesta": "soy",
        "explicacion": "Con el pronombre «yo» usamos «soy»: yo soy estudiante."
    },
    {
        "pregunta": "¿Cuál palabra es un verbo?",
        "opciones": ["bonito", "correr", "mesa"],
        "respuesta": "correr",
        "explicacion": "«Correr» es un verbo porque expresa una acción."
    },
    {
        "pregunta": "Completa: «Ayer yo ___ al parque».",
        "opciones": ["voy", "iré", "fui"],
        "respuesta": "fui",
        "explicacion": "«Fui» es una forma del verbo ir en pasado."
    },
    {
        "pregunta": "¿Cuál es el antónimo de «grande»?",
        "opciones": ["enorme", "pequeño", "amplio"],
        "respuesta": "pequeño",
        "explicacion": "«Pequeño» expresa una idea opuesta a «grande»."
    },
]


def normalizar(texto: str) -> str:
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(
        caracter for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "¡Hola! 👋 Soy tu Tutor de Español.\n\n"
        "Aprenderemos vocabulario y gramática con ejercicios "
        "y explicaciones.\n\n"
        "Comandos disponibles:\n"
        "/practicar - Comenzar un ejercicio\n"
        "/siguiente - Cambiar de ejercicio\n"
        "/puntos - Consultar tu puntuación\n"
        "/help - Ver la ayuda\n\n"
        "Escribe /practicar para comenzar. 🇪🇸"
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "📚 ¿Cómo usar el tutor?\n\n"
        "/start - Iniciar\n"
        "/practicar - Resolver una pregunta\n"
        "/siguiente - Obtener otra pregunta\n"
        "/puntos - Ver tus resultados\n\n"
        "Lee la pregunta, escribe tu respuesta y "
        "recibirás una explicación."
    )


async def practicar(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    ejercicio = random.choice(EJERCICIOS)

    context.user_data["ejercicio"] = ejercicio
    context.user_data["respondido"] = False

    opciones = "\n".join(
        f"{i + 1}. {opcion}"
        for i, opcion in enumerate(ejercicio["opciones"])
    )

    await update.message.reply_text(
        f"📝 Ejercicio de español\n\n"
        f"{ejercicio['pregunta']}\n\n"
        f"{opciones}\n\n"
        "Escribe la respuesta o su número (1, 2 o 3)."
    )


async def responder(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    mensaje = update.message.text.strip()
    texto = normalizar(mensaje)

    ejercicio = context.user_data.get("ejercicio")

    if ejercicio and not context.user_data.get("respondido", False):
        respuesta = normalizar(ejercicio["respuesta"])

        if texto in {"1", "2", "3"}:
            texto = normalizar(ejercicio["opciones"][int(texto) - 1])

        if texto == respuesta:
            context.user_data["puntos"] = (
                context.user_data.get("puntos", 0) + 1
            )
            context.user_data["correctas"] = (
                context.user_data.get("correctas", 0) + 1
            )

            await update.message.reply_text(
                "¡Correcto! 🎉\n\n"
                f"{ejercicio['explicacion']}\n\n"
                "Escribe /siguiente para continuar."
            )
        else:
            context.user_data["incorrectas"] = (
                context.user_data.get("incorrectas", 0) + 1
            )

            await update.message.reply_text(
                "¡Casi! 😊 La respuesta correcta es "
                f"«{ejercicio['respuesta']}».\n\n"
                f"{ejercicio['explicacion']}\n\n"
                "Escribe /siguiente para probar otra pregunta."
            )

        context.user_data["respondido"] = True
        return

    if texto in {"hola", "buenas", "buenos dias", "buenas tardes"}:
        await update.message.reply_text(
            "¡Hola! 😊 ¿Lista para aprender español?\n"
            "Escribe /practicar para comenzar."
        )
    else:
        await update.message.reply_text(
            "¡Vamos a aprender juntos! 📚\n\n"
            "Para iniciar un ejercicio, escribe /practicar.\n"
            "Para consultar tus puntos, escribe /puntos."
        )


async def puntos(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    total = context.user_data.get("correctas", 0)
    incorrectas = context.user_data.get("incorrectas", 0)

    await update.message.reply_text(
        "🏆 Tu progreso en esta sesión\n\n"
        f"✅ Respuestas correctas: {total}\n"
        f"❌ Respuestas incorrectas: {incorrectas}\n\n"
        "¡Sigue practicando para mejorar!"
    )


async def siguiente(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await practicar(update, context)


def main():
    if not TOKEN:
        raise RuntimeError(
            "No se encontró TELEGRAM_BOT_TOKEN en el archivo .env"
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("practicar", practicar))
    app.add_handler(CommandHandler("siguiente", siguiente))
    app.add_handler(CommandHandler("puntos", puntos))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, responder)
    )

    print("Tutor de Español iniciado. Presiona Ctrl+C para detenerlo.")
    app.run_polling()


if __name__ == "__main__":
    main()
