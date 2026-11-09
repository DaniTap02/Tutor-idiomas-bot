"""Diagnóstico de las partes que fallan "sin motivo":

    python -m exam.diagnostico           revisa todo
    python -m exam.diagnostico audio     solo el audio (texto a voz y voz a texto)
    python -m exam.diagnostico ollama    solo Ollama

Prueba cada componente POR SEPARADO y dice la causa REAL de cada fallo, con el tipo de excepción y
su mensaje original. Es la forma de saber si el problema es el entorno de Python, una dependencia,
el firewall, el reloj del PC, el modelo de voz sin descargar o Telegram.

La prueba de voz a texto usa el audio que acaba de generar la prueba de texto a voz, así que
comprueba las dos partes de punta a punta. Los archivos quedan en diagnostico_audio/ para que los
escuches. No imprime el token de Telegram ni ninguna clave.
"""
import asyncio
import os
import platform
import sys
import time

CARPETA = "diagnostico_audio"
TEXTO_PRUEBA = "Hello, this is a short test of the listening part of the exam."

ok_total = 0
fallo_total = 0
avisos: list[str] = []


def titulo(texto: str) -> None:
    print(f"\n{texto}\n" + "-" * len(texto))


def bien(texto: str) -> None:
    global ok_total
    ok_total += 1
    print(f"  [ok]    {texto}")


def mal(texto: str, arreglo: str = "") -> None:
    global fallo_total
    fallo_total += 1
    print(f"  [FALLA] {texto}")
    if arreglo:
        print(f"          -> {arreglo}")
        avisos.append(arreglo)


def nota(texto: str) -> None:
    print(f"  [nota]  {texto}")


def _version(modulo) -> str:
    for atributo in ("__version__", "version", "VERSION"):
        valor = getattr(modulo, atributo, None)
        if isinstance(valor, str):
            return valor
    return "?"


# ---------------------------------------------------------------- 1. Entorno

def revisar_entorno() -> None:
    titulo("1. Entorno de Python")
    print(f"  Python {platform.python_version()} en {platform.system()} {platform.release()}")
    print(f"  Ejecutable: {sys.executable}")
    print(f"  Carpeta de trabajo: {os.getcwd()}")

    en_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if en_venv:
        bien(f"estás dentro de un entorno virtual ({os.path.basename(sys.prefix)})")
    else:
        mal("NO estás dentro del entorno virtual del proyecto",
            "activa el entorno antes de correr el bot:  .venv\\Scripts\\Activate.ps1")

    if os.path.exists("exam") and os.path.exists("bot.py"):
        bien("se está ejecutando desde la carpeta del proyecto")
    else:
        mal("no parece la carpeta del proyecto (no veo bot.py ni exam/)",
            "entra con cd a la carpeta Tutor-idiomas-bot y vuelve a correr el comando")

    if os.path.exists(".env"):
        from dotenv import load_dotenv

        load_dotenv()
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            bien("el archivo .env tiene TELEGRAM_BOT_TOKEN (no se muestra)")
        else:
            mal("el .env existe pero no tiene TELEGRAM_BOT_TOKEN",
                "añade la línea TELEGRAM_BOT_TOKEN=tu_token al archivo .env")
    else:
        mal("no hay archivo .env en la carpeta del proyecto",
            "crea un .env con TELEGRAM_BOT_TOKEN=tu_token")


# ---------------------------------------------------------------- 2. Dependencias

def revisar_dependencias() -> None:
    titulo("2. Dependencias")
    necesarias = [
        ("telegram", "python-telegram-bot", "el bot"),
        ("dotenv", "python-dotenv", "leer el .env"),
        ("httpx", "httpx", "hablar con Ollama"),
        ("edge_tts", "edge-tts", "los audios de la escucha"),
        ("faster_whisper", "faster-whisper", "transcribir las notas de voz"),
        ("av", "av (PyAV)", "leer y convertir audio; llega con faster-whisper"),
        ("ctranslate2", "ctranslate2", "el motor de Whisper; llega con faster-whisper"),
    ]
    for modulo, paquete, para_que in necesarias:
        try:
            importado = __import__(modulo)
            bien(f"{paquete} {_version(importado)} — {para_que}")
        except Exception as exc:
            mal(f"falta {paquete} ({type(exc).__name__}) — {para_que}",
                "con el entorno activado:  pip install -r requirements.txt")

    try:
        import gtts

        bien(f"gTTS {_version(gtts)} — respaldo opcional del texto a voz")
    except Exception:
        nota("gTTS no está instalado (es opcional: solo es el respaldo si edge-tts falla)")


# ---------------------------------------------------------------- 3. Ollama

def revisar_ollama() -> None:
    titulo("3. Ollama (genera y califica)")
    try:
        import httpx

        from exam.grader import OLLAMA_MODEL, OLLAMA_URL
    except Exception as exc:
        mal(f"no pude ni importar el calificador ({type(exc).__name__}: {exc})")
        return

    print(f"  Dirección: {OLLAMA_URL} · modelo configurado: {OLLAMA_MODEL}")
    try:
        inicio = time.monotonic()
        respuesta = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        respuesta.raise_for_status()
        ms = (time.monotonic() - inicio) * 1000
        modelos = [m.get("name", "") for m in respuesta.json().get("models", [])]
        bien(f"Ollama responde en {ms:.0f} ms")
        if OLLAMA_MODEL in modelos:
            bien(f"el modelo {OLLAMA_MODEL} está descargado")
        else:
            mal(f"el modelo {OLLAMA_MODEL} NO aparece en Ollama (hay: {', '.join(modelos) or 'ninguno'})",
                f"descárgalo con:  ollama pull {OLLAMA_MODEL}")
    except Exception as exc:
        mal(f"Ollama no responde ({type(exc).__module__}.{type(exc).__name__}: {str(exc)[:120]})",
            "abre la aplicación Ollama y comprueba con:  ollama list")


# ---------------------------------------------------------------- 4. Texto a voz

async def _probar_tts() -> dict | None:
    from exam.registro import Fallo, MOTIVOS
    from exam.tts import HOST_EDGE_TTS, INTENTOS, TIMEOUT_SECONDS, synthesize

    print(f"  Motor: edge-tts · host: {HOST_EDGE_TTS} · espera: {TIMEOUT_SECONDS:.0f} s · "
          f"intentos: {INTENTOS}")
    os.makedirs(CARPETA, exist_ok=True)
    ruta = os.path.join(CARPETA, "prueba.mp3")
    try:
        inicio = time.monotonic()
        info = await synthesize(TEXTO_PRUEBA, "en", ruta, rate="+0%", voice_index=0)
        segundos = time.monotonic() - inicio
        bien(f"audio generado con {info['motor']} en {segundos:.1f} s "
             f"({info['bytes']} bytes, {info['intentos']} intento(s))")
        if info["formato"] == "ogg":
            bien("convertido a OGG/OPUS: se puede enviar como NOTA DE VOZ en Telegram")
        else:
            mal("no se pudo convertir a OGG/OPUS: se enviará como archivo de audio",
                "revisa que PyAV esté instalado (llega con faster-whisper)")
        print(f"          archivo: {os.path.abspath(info['ruta'])}")
        return info
    except Fallo as fallo:
        mal(f"no se generó el audio — motivo '{fallo.motivo}': {MOTIVOS.get(fallo.motivo, '')}")
        print(f"          error real: {fallo.tecnico}")
        arreglos = {
            "red": f"revisa el firewall, el proxy o el DNS para {HOST_EDGE_TTS} (puerto 443)",
            "tiempo": "sube la espera con  $env:TTS_TIMEOUT=\"90\"  y vuelve a probar",
            "reloj": "sincroniza la hora de Windows (Configuración > Hora e idioma > Sincronizar)",
            "servicio": "actualiza edge-tts:  pip install -U edge-tts",
            "corte": "conexión inestable: vuelve a intentarlo",
            "dependencia": "pip install -r requirements.txt",
        }
        if fallo.motivo in arreglos:
            print(f"          -> {arreglos[fallo.motivo]}")
            avisos.append(arreglos[fallo.motivo])
        return None
    except Exception as exc:
        mal(f"fallo no previsto: {type(exc).__module__}.{type(exc).__name__}: {str(exc)[:150]}")
        return None


def revisar_tts() -> dict | None:
    titulo("4. Texto a voz (los audios de la escucha)")
    try:
        return asyncio.run(_probar_tts())
    except Exception as exc:
        mal(f"no pude ni arrancar la prueba ({type(exc).__name__}: {str(exc)[:120]})")
        return None


# ---------------------------------------------------------------- 5. Voz a texto

def revisar_stt(audio_tts: dict | None) -> None:
    titulo("5. Voz a texto (la parte de habla)")
    try:
        from exam.audio import sondear
        from exam.registro import Fallo, MOTIVOS
        from exam.stt import (BEAM_SIZE, COMPUTE_TYPE, DEVICE, MODEL_SIZE,
                              modelo_descargado, transcribe)
    except Exception as exc:
        mal(f"falta una dependencia del transcriptor ({type(exc).__name__}: {exc})",
            "pip install -r requirements.txt")
        return

    print(f"  Modelo: {MODEL_SIZE} · dispositivo: {DEVICE} · precisión: {COMPUTE_TYPE} · "
          f"beam: {BEAM_SIZE}")

    if modelo_descargado():
        bien(f"el modelo {MODEL_SIZE} ya está descargado (funciona sin internet)")
    else:
        nota(f"el modelo {MODEL_SIZE} aún no está en el disco: la primera vez se descarga "
             "(hace falta internet y tarda unos minutos)")

    if audio_tts is None:
        nota("sin audio de la prueba anterior no puedo probar la transcripción completa")
        return

    ruta = audio_tts["ruta"]
    try:
        info = sondear(ruta)
        bien(f"el archivo se lee bien: {info['codec']} {info['sr']} Hz, "
             f"{info['canales']} canal(es), {info['segundos']} s")
    except Fallo as fallo:
        mal(f"el archivo de audio no se puede leer — motivo '{fallo.motivo}'")
        print(f"          error real: {fallo.tecnico}")
        return

    try:
        inicio = time.monotonic()
        resultado = transcribe(ruta, "en")
        segundos = time.monotonic() - inicio
        bien(f"transcripción en {segundos:.1f} s (confianza {resultado['confidence']:.2f})")
        print(f"          dijo: «{resultado['text']}»")
        print(f"          esperado: «{TEXTO_PRUEBA}»")
        comunes = set(TEXTO_PRUEBA.lower().replace(".", "").split()) & set(
            resultado["text"].lower().replace(".", "").split()
        )
        if len(comunes) >= 4:
            bien(f"el texto coincide con lo que se dijo ({len(comunes)} palabras en común): "
                 "la escucha y el habla funcionan de punta a punta")
        else:
            mal("la transcripción no se parece al texto original",
                "prueba con un modelo más preciso:  $env:WHISPER_MODEL=\"small\"")
    except Fallo as fallo:
        mal(f"no se pudo transcribir — motivo '{fallo.motivo}': {MOTIVOS.get(fallo.motivo, '')}")
        print(f"          etapa: {fallo.etapa}")
        print(f"          error real: {fallo.tecnico}")
        arreglos = {
            "dependencia": "pip install -r requirements.txt (con el entorno activado)",
            "modelo_descarga": "conéctate a internet la primera vez para que baje el modelo",
            "memoria": "usa un modelo más liviano:  $env:WHISPER_MODEL=\"tiny\"",
            "formato": "el archivo de audio está dañado o en un formato que no se puede leer",
            "modelo_carga": "prueba otra precisión:  $env:WHISPER_COMPUTE=\"int8\"",
        }
        if fallo.motivo in arreglos:
            print(f"          -> {arreglos[fallo.motivo]}")
            avisos.append(arreglos[fallo.motivo])
    except Exception as exc:
        mal(f"fallo no previsto: {type(exc).__module__}.{type(exc).__name__}: {str(exc)[:150]}")


# ---------------------------------------------------------------- Programa

def _preparar_registro() -> str:
    """Manda el registro técnico completo a un archivo, para que el informe en pantalla quede
    limpio sin perder el detalle (tipos de excepción, etapas y tiempos de cada operación)."""
    import logging

    os.makedirs(CARPETA, exist_ok=True)
    ruta = os.path.join(CARPETA, "diagnostico.log")
    raiz = logging.getLogger()
    raiz.handlers.clear()          # sin esto, las librerías escriben en la consola
    raiz.setLevel(logging.DEBUG)
    archivo = logging.FileHandler(ruta, mode="w", encoding="utf-8")
    archivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s"))
    raiz.addHandler(archivo)
    return ruta


def main() -> int:
    que = (sys.argv[1].lower() if len(sys.argv) > 1 else "todo")
    registro = _preparar_registro()
    print("=" * 70)
    print("DIAGNÓSTICO DEL TUTOR DE IDIOMAS")
    print("=" * 70)

    if que in ("todo", "entorno"):
        revisar_entorno()
        revisar_dependencias()
    if que in ("todo", "ollama"):
        revisar_ollama()
    if que in ("todo", "audio", "tts", "stt"):
        audio_tts = revisar_tts()
        revisar_stt(audio_tts)

    titulo("Resumen")
    print(f"  {ok_total} bien · {fallo_total} con falla")
    if avisos:
        print("\n  Qué hacer:")
        for i, aviso in enumerate(dict.fromkeys(avisos), start=1):
            print(f"   {i}. {aviso}")
    elif fallo_total:
        print("\n  Hubo fallas sin una solución conocida: envía el registro técnico de abajo.")
    else:
        print("  No encontré problemas.")
    print(f"\n  Registro técnico completo (con tiempos y tipos de error): {os.path.abspath(registro)}")
    if os.path.isdir(CARPETA):
        print(f"  Los audios de la prueba quedaron en: {os.path.abspath(CARPETA)}")
    return 1 if fallo_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
