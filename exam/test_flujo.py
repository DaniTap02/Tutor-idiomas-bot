"""Prueba del FLUJO completo del examen SIN Telegram, SIN Ollama y SIN Whisper:

    python -m exam.test_flujo

Simula a un estudiante haciendo el examen (botones de lectura, botones de escucha, texto de
escritura y nota de voz) y comprueba el orden de las partes, los puntajes, la ubicación final y
los casos raros: sin escucha, audio muy corto, audio sin voz, audio que no se entiende, mensajes
enviados en el momento equivocado y botones viejos.
"""
import asyncio
import logging
import os

from exam import telegram_flow as tf
from exam.registro import Fallo

# Varios casos provocan fallos a propósito (Ollama caído, sin internet para el audio) y el código
# los registra con logging. Se silencian para que la salida de la prueba quede limpia.
logging.disable(logging.CRITICAL)

ok_total = 0
fail_total = 0


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK    " if condicion else "  FALLA ") + nombre)
    ok_total += bool(condicion)
    fail_total += not condicion


# ---------------------------------------------------------------- Telegram simulado

class FakeMessage:
    """Mensaje de Telegram simulado: guarda todo lo enviado en `log`."""

    def __init__(self, log, text=None):
        self.log = log
        self.text = text
        self.voice = None
        self.audio = None
        self.reply_markup = None

    async def reply_text(self, texto, reply_markup=None):
        self.log.append(("text", texto))
        m = FakeMessage(self.log)
        m.reply_markup = reply_markup
        return m

    async def reply_voice(self, voice=None, caption=None):
        self.log.append(("voice", caption or ""))
        return FakeMessage(self.log)

    async def reply_audio(self, audio=None, title=None, caption=None):
        self.log.append(("audio", caption or title or ""))
        return FakeMessage(self.log)

    async def edit_text(self, texto, reply_markup=None):
        self.log.append(("edit", texto))

    async def delete(self):
        self.log.append(("delete", ""))

    async def edit_message_reply_markup(self, reply_markup=None):
        self.reply_markup = reply_markup


class FakeQuery:
    def __init__(self, log, data):
        self.log = log
        self.data = data
        self.message = FakeMessage(log)

    async def answer(self, texto=None, show_alert=False):
        if texto:
            self.log.append(("alert", texto))

    async def edit_message_text(self, texto):
        self.log.append(("edit", texto))

    async def edit_message_reply_markup(self, reply_markup=None):
        self.log.append(("markup", "quitado" if reply_markup is None else "puesto"))


class FakeVoice:
    def __init__(self, duration):
        self.duration = duration

    async def get_file(self):
        return self

    async def download_to_drive(self, ruta):
        with open(ruta, "wb") as f:
            f.write(b"ogg")


class Ctx:
    def __init__(self):
        self.user_data = {}


def update_callback(log, data):
    class U:
        callback_query = FakeQuery(log, data)
        message = None
    return U()


def update_texto(log, texto):
    class U:
        message = FakeMessage(log, texto)
        effective_message = message
    return U()


def update_voz(log, duration=30, como_audio=False):
    m = FakeMessage(log)
    if como_audio:
        m.audio = FakeVoice(duration)   # el usuario adjuntó un archivo en vez de grabar
    else:
        m.voice = FakeVoice(duration)

    class U:
        message = m
    return U()


# ---------------------------------------------------------------- Dobles de los agentes

def preguntas_falsas(n, con_texto=False):
    out = []
    for i in range(n):
        q = {"q": f"Question {i}?", "options": ["a", "b", "c"], "answer": i % 3, "topic": "t"}
        if con_texto:
            q["text"] = f"Un mini-texto numero {i} para la pregunta."
        out.append(q)
    return out


def escuchas_falsas(n):
    return [
        {"text": f"Spoken text {i}.", "q": f"Listen {i}?", "options": ["x", "y", "z"],
         "answer": i % 3, "topic": "t"}
        for i in range(n)
    ]


estado = {
    "reading": lambda banco, lang: preguntas_falsas(banco.N_READING, con_texto=True),
    "listening": lambda banco, lang: escuchas_falsas(3),
    "grade": None,
    "transcribe": None,
    "tts_fallo": None,     # None = funciona; si no, el MOTIVO con el que falla (ver registro.py)
    "tts_formato": "ogg",  # "ogg" = nota de voz; "mp3" = archivo de audio
    "envio_falla": False,  # el audio se genera bien pero Telegram lo rechaza
}


def _instalar_dobles():
    tf.generate_reading = lambda banco, lang: estado["reading"](banco, lang)
    tf.generate_listening = lambda banco, lang: estado["listening"](banco, lang)
    tf.grade = lambda *a, **k: estado["grade"](*a, **k)
    tf.transcribe = lambda ruta, lang=None: estado["transcribe"](ruta, lang)
    tf.modelo_cargado = lambda: True

    async def synthesize(text, language, path, rate="+0%", voice_index=0):
        if estado["tts_fallo"]:
            raise Fallo("tts", "generar", estado["tts_fallo"],
                        detalle="fallo simulado en la prueba")
        formato = estado["tts_formato"]
        ruta = path if formato == "mp3" else os.path.splitext(path)[0] + ".ogg"
        with open(ruta, "wb") as f:
            f.write(b"audio de prueba")
        return {"ruta": ruta, "formato": formato, "motor": "edge-tts",
                "intentos": 1, "bytes": os.path.getsize(ruta)}

    tf.synthesize = synthesize

    enviar_real = tf._enviar_por_telegram

    async def enviar(message, ruta, formato):
        if estado["envio_falla"]:
            raise Fallo("telegram", "enviar", "envio", detalle="Telegram rechazó el archivo")
        await enviar_real(message, ruta, formato)

    tf._enviar_por_telegram = enviar


def nota(score, needs_rewrite=False, feedback="¡Bien!"):
    return {"score": score, "task_completed": True, "errors": [],
            "needs_rewrite": needs_rewrite, "feedback": feedback}


def audio_bueno(texto="I am Tapi and I live in Ibague and I like music a lot"):
    return {"text": texto, "duration": 30.0, "speech": 28.0, "words": len(texto.split()),
            "wpm": 95.0, "confidence": 0.8, "no_speech": 0.05, "codec": "opus", "bytes": 24000}


# ---------------------------------------------------------------- Pasos del examen

async def responder_todas_lectura(log, ctx, correctas=True):
    ex = ctx.user_data["examen"]
    total = len(ex["questions"])
    for i in range(total):
        pregunta = ex["questions"][i]
        elegida = pregunta["answer"] if correctas else (pregunta["answer"] + 1) % 3
        await tf.responder_lectura(update_callback(log, f"ans:{i}:{elegida}"), ctx)


async def responder_todas_escucha(log, ctx, correctas=True):
    ex = ctx.user_data["examen"]
    for i in range(len(ex["listening"])):
        pregunta = ex["listening"][i]
        elegida = pregunta["answer"] if correctas else (pregunta["answer"] + 1) % 3
        await tf.responder_escucha(update_callback(log, f"lis:{i}:{elegida}"), ctx)


async def empezar(log, ctx, idioma="en"):
    await tf.iniciar_examen(update_texto(log, "/start"), ctx)
    await tf.elegir_idioma(update_callback(log, f"lang:{idioma}"), ctx)


# ---------------------------------------------------------------- Casos

async def caso_examen_completo():
    print("1) Examen A1 completo: lectura -> escucha -> escritura -> habla")
    log, ctx = [], Ctx()
    estado["grade"] = lambda *a, **k: nota(90)
    estado["transcribe"] = lambda ruta, lang: audio_bueno()

    await empezar(log, ctx)
    ex = ctx.user_data["examen"]
    check("empieza en lectura con 10 preguntas", ex["part"] == "lectura" and len(ex["questions"]) == 10)
    check("se generaron 3 audios de escucha", len(ex["listening"]) == 3)

    await responder_todas_lectura(log, ctx)
    check("tras la lectura sigue la escucha", ex["part"] == "escucha")
    check("lectura = 100", ex["scores"]["lectura"] == 100)
    check("se envió el primer audio como nota de voz", any(k == "voice" for k, _ in log))

    await responder_todas_escucha(log, ctx)
    check("tras la escucha sigue la escritura", ex["part"] == "escritura")
    check("escucha = 100", ex["scores"]["escucha"] == 100)

    await tf.texto_de_examen(update_texto(log, "My name is Tapi. I am from Colombia."), ctx)
    check("tras la escritura sigue el habla", ex["part"] == "habla")
    check("escritura = 90", ex["scores"]["escritura"] == 90)

    es_habla = [t for k, t in log if k == "text" and "🎤 Habla" in t]
    check("se envió la consigna de habla", len(es_habla) == 1)

    await tf.voz_de_examen(update_voz(log, 30), ctx)
    nuevo = ctx.user_data["examen"]
    check("pasó A1 y arrancó el examen A2", nuevo["level"] == "A2" and nuevo["part"] == "lectura")
    check("el nivel guardado es A2 (provisional)", ctx.user_data["nivel"]["level"] == "A2")
    resumen = [t for k, t in log if "📊 Resultado A1" in t]
    check("el resumen trae las cuatro partes",
          bool(resumen) and all(p in resumen[0] for p in ("Lectura:", "Escucha:", "Escritura:", "Habla:")))
    check("la revisión de escucha se envía al final (con el texto del audio)",
          any("🎧 Revisión de escucha" in t and "Spoken text 0." in t for k, t in log))
    check("el estado del nivel nuevo quedó limpio",
          nuevo["q"] == 0 and nuevo["answers"] == [] and nuevo["l_q"] == 0 and nuevo["scores"] == {})


async def caso_no_pasa():
    print("\n2) No pasa el nivel: queda en enseñanza de ese nivel")
    log, ctx = [], Ctx()
    estado["grade"] = lambda *a, **k: nota(50)
    estado["transcribe"] = lambda ruta, lang: audio_bueno()

    await empezar(log, ctx)
    await responder_todas_lectura(log, ctx, correctas=False)
    await responder_todas_escucha(log, ctx, correctas=False)
    await tf.texto_de_examen(update_texto(log, "bad text"), ctx)
    await tf.voz_de_examen(update_voz(log, 30), ctx)

    check("el examen terminó", "examen" not in ctx.user_data)
    check("queda en enseñanza de A1", ctx.user_data["nivel"]["level"] == "A1")
    check("no quedó marcado como provisional", ctx.user_data["nivel"]["provisional"] is False)
    check("se le avisa que aprenderá desde A1",
          any("aprendiendo desde el nivel A1" in t for k, t in log))


async def caso_sin_escucha():
    print("\n3) La escucha no se pudo generar: el examen sigue sin ella y no se promedia")
    log, ctx = [], Ctx()

    def falla(banco, lang):
        raise RuntimeError("Ollama lento")

    estado["listening"] = falla
    estado["grade"] = lambda *a, **k: nota(80)
    estado["transcribe"] = lambda ruta, lang: audio_bueno()

    await empezar(log, ctx)
    ex = ctx.user_data["examen"]
    check("el examen arrancó igual", ex["part"] == "lectura")
    check("no hay audios", ex["listening"] == [])

    await responder_todas_lectura(log, ctx)
    check("de la lectura pasa directo a la escritura", ex["part"] == "escritura")

    await tf.texto_de_examen(update_texto(log, "texto"), ctx)
    await tf.voz_de_examen(update_voz(log, 30), ctx)
    resumen = [t for k, t in log if "📊 Resultado A1" in t]
    check("el resumen NO muestra escucha", bool(resumen) and "Escucha:" not in resumen[0])
    check("no se envió revisión de escucha", not any("Revisión de escucha" in t for k, t in log))
    estado["listening"] = lambda banco, lang: escuchas_falsas(3)


async def caso_audio_sin_tts():
    print("\n4) El audio no se puede generar: se muestra el texto y queda anotado")
    log, ctx = [], Ctx()
    estado["tts_fallo"] = "red"
    estado["grade"] = lambda *a, **k: nota(80)
    estado["transcribe"] = lambda ruta, lang: audio_bueno()

    await empezar(log, ctx)
    await responder_todas_lectura(log, ctx)
    check("avisa el motivo real (conexión) y muestra el texto de respaldo",
          any("No pude conectarme al servicio de voz" in t and "Spoken text 0." in t for k, t in log))
    check("y NO dice que falte internet sin saberlo (no inventa la causa)",
          not any("¿tienes internet?" in t for k, t in log))
    ex = ctx.user_data["examen"]
    check("la pregunta queda marcada como leída", ex["listening"][0].get("leido") is True)
    check("no se ofrece repetir un audio que no existe",
          not any(k == "voice" for k, _ in log))
    await responder_todas_escucha(log, ctx)
    check("si ningún audio se pudo oír, la escucha queda SIN puntaje (midió lectura)",
          "escucha" not in ex["scores"])
    await tf.texto_de_examen(update_texto(log, "texto"), ctx)
    await tf.voz_de_examen(update_voz(log, 30), ctx)
    check("la revisión avisa que esa se mostró escrita",
          any("se mostró escrito" in t for k, t in log))
    resumen = [t for k, t in log if "📊 Resultado A1" in t]
    check("y el resumen no inventa una nota de escucha",
          bool(resumen) and "Escucha:" not in resumen[0])

    # Con un solo audio fallido, la escucha se promedia solo sobre los que sí se oyeron
    log2, ctx2 = [], Ctx()
    fallos = {"n": 0}
    sintetizar_ok = tf.synthesize

    async def falla_el_primero(text, language, path, rate="+0%", voice_index=0):
        fallos["n"] += 1
        if fallos["n"] == 1:
            raise Fallo("tts", "generar", "servicio", detalle="fallo simulado del servicio")
        return await sintetizar_ok(text, language, path, rate=rate, voice_index=voice_index)

    estado["tts_fallo"] = None
    tf.synthesize = falla_el_primero
    await empezar(log2, ctx2)
    await responder_todas_lectura(log2, ctx2)
    ex2 = ctx2.user_data["examen"]
    # acierta solo el primero (el que se mostró escrito) y falla los otros dos
    await tf.responder_escucha(update_callback(log2, f"lis:0:{ex2['listening'][0]['answer']}"), ctx2)
    await tf.responder_escucha(update_callback(log2, f"lis:1:{(ex2['listening'][1]['answer'] + 1) % 3}"), ctx2)
    await tf.responder_escucha(update_callback(log2, f"lis:2:{(ex2['listening'][2]['answer'] + 1) % 3}"), ctx2)
    check("el acierto del audio que no sonó no sube la nota de escucha (0 de 2 oídos)",
          ex2["scores"]["escucha"] == 0)
    tf.synthesize = sintetizar_ok


async def caso_audio_por_etapas():
    print("\n5) Audio de la escucha: cada etapa falla con su propio aviso")
    estado["grade"] = lambda *a, **k: nota(80)
    estado["transcribe"] = lambda ruta, lang: audio_bueno()

    async def hasta_la_escucha():
        log, ctx = [], Ctx()
        await empezar(log, ctx)
        await responder_todas_lectura(log, ctx)
        return log, ctx

    estado["tts_fallo"], estado["tts_formato"], estado["envio_falla"] = None, "ogg", False
    log, _ = await hasta_la_escucha()
    check("audio OK en OGG/OPUS -> se envía como NOTA DE VOZ", any(k == "voice" for k, _ in log))

    estado["tts_formato"] = "mp3"
    log, _ = await hasta_la_escucha()
    check("si solo hay mp3 -> se envía como ARCHIVO DE AUDIO (formato que Telegram sí acepta)",
          any(k == "audio" for k, _ in log) and not any(k == "voice" for k, _ in log))
    estado["tts_formato"] = "ogg"

    estado["envio_falla"] = True
    log, ctx = await hasta_la_escucha()
    check("si Telegram rechaza el envío -> se distingue de un fallo de generación",
          any("Telegram no lo aceptó" in t for k, t in log))
    check("y el texto de respaldo sigue disponible",
          any("lee el texto" in t and "Spoken text 0." in t for k, t in log))
    estado["envio_falla"] = False

    esperado = {
        "red": "No pude conectarme al servicio de voz",
        "tiempo": "tardó demasiado",
        "reloj": "la hora del computador",
        "servicio": "no entregó el audio",
        "corte": "se cortó a mitad",
        "dependencia": "Falta instalar edge-tts",
    }
    for motivo, trozo in esperado.items():
        estado["tts_fallo"] = motivo
        log, _ = await hasta_la_escucha()
        check(f"motivo '{motivo}' -> aviso propio", any(trozo in t for k, t in log))
    estado["tts_fallo"] = None

    avisos = set()
    for motivo in esperado:
        estado["tts_fallo"] = motivo
        log, _ = await hasta_la_escucha()
        avisos.add(next(t for k, t in log if "lee el texto" in t).split("😕")[0])
    check("los seis motivos dan seis mensajes distintos", len(avisos) == len(esperado))
    estado["tts_fallo"] = None


async def caso_voz_por_etapas():
    print("\n6) Nota de voz: cada etapa falla con su propio aviso")
    estado["grade"] = lambda *a, **k: nota(85)

    async def hasta_el_habla():
        log, ctx = [], Ctx()
        estado["transcribe"] = lambda ruta, lang: audio_bueno()
        await empezar(log, ctx)
        await responder_todas_lectura(log, ctx)
        await responder_todas_escucha(log, ctx)
        await tf.texto_de_examen(update_texto(log, "texto"), ctx)
        return log, ctx

    def falla_con(motivo, etapa="sondear"):
        def doble(ruta, lang):
            raise Fallo("stt", etapa, motivo, detalle="fallo simulado en la prueba")
        return doble

    casos = [
        ("archivo_vacio", "El audio llegó vacío", False),
        ("formato", "No pude leer ese audio", False),
        ("dependencia", "Falta instalar faster-whisper", True),
        ("modelo_descarga", "no está descargado", True),
        ("memoria", "WHISPER_MODEL=tiny", True),
        ("modelo_carga", "No pude cargar el modelo de voz", True),
        ("transcripcion", "falló al transcribir", True),
    ]
    for motivo, trozo, _ in casos:
        log, ctx = await hasta_el_habla()
        estado["transcribe"] = falla_con(motivo)
        await tf.voz_de_examen(update_voz(log, 30), ctx)
        check(f"motivo '{motivo}' -> aviso propio", any(trozo in t for k, t in log))

    # Los fallos que el estudiante SÍ puede arreglar no deben acercar el cierre del nivel
    log, ctx = await hasta_el_habla()
    estado["transcribe"] = falla_con("formato")
    for _ in range(tf.MAX_FALLOS_HABLA + 2):
        await tf.voz_de_examen(update_voz(log, 30), ctx)
    check("un formato ilegible repetido NO cierra el nivel (lo puede arreglar el estudiante)",
          ctx.user_data["examen"]["part"] == "habla"
          and ctx.user_data["examen"]["habla_fallos"] == 0)

    # Los fallos técnicos sí: a los 3 se cierra el nivel sin la parte de habla
    log, ctx = await hasta_el_habla()
    estado["transcribe"] = falla_con("dependencia", etapa="modelo")
    for _ in range(tf.MAX_FALLOS_HABLA):
        await tf.voz_de_examen(update_voz(log, 30), ctx)
    check("una dependencia ausente sí cierra el nivel a los 3 intentos",
          any("cierro este nivel sin la parte de habla" in t for k, t in log))

    estado["transcribe"] = lambda ruta, lang: audio_bueno()


async def caso_repetir_audio():
    print("\n7) Repetir el audio: solo una vez por pregunta")
    log, ctx = [], Ctx()
    estado["grade"] = lambda *a, **k: nota(80)
    await empezar(log, ctx)
    await responder_todas_lectura(log, ctx)

    voces_antes = sum(1 for k, _ in log if k == "voice")
    await tf.repetir_audio(update_callback(log, "rep:0"), ctx)
    check("la primera repetición envía el audio otra vez",
          sum(1 for k, _ in log if k == "voice") == voces_antes + 1)

    await tf.repetir_audio(update_callback(log, "rep:0"), ctx)
    check("la segunda avisa que ya la usó", any(k == "alert" for k, _ in log))
    check("y no envía otro audio", sum(1 for k, _ in log if k == "voice") == voces_antes + 1)

    await tf.repetir_audio(update_callback(log, "rep:2"), ctx)
    check("un botón de otra pregunta se ignora",
          sum(1 for k, _ in log if k == "voice") == voces_antes + 1)


async def caso_audios_malos():
    print("\n8) Notas de voz que no se pueden calificar: se piden de nuevo sin penalizar")
    log, ctx = [], Ctx()
    estado["grade"] = lambda *a, **k: nota(85)
    estado["transcribe"] = lambda ruta, lang: audio_bueno()

    await empezar(log, ctx)
    await responder_todas_lectura(log, ctx)
    await responder_todas_escucha(log, ctx)
    await tf.texto_de_examen(update_texto(log, "texto"), ctx)
    ex = ctx.user_data["examen"]

    await tf.voz_de_examen(update_voz(log, 5), ctx)
    check("audio de 5 s en A1 (mínimo 12) -> se pide de nuevo",
          any("muy corto" in t for k, t in log) and "habla" not in ex["scores"])

    estado["transcribe"] = lambda ruta, lang: {**audio_bueno(""), "text": "", "no_speech": 0.9}
    await tf.voz_de_examen(update_voz(log, 30), ctx)
    check("audio sin voz -> se pide de nuevo",
          any("No escuché voz" in t for k, t in log) and "habla" not in ex["scores"])

    estado["transcribe"] = lambda ruta, lang: {**audio_bueno(), "confidence": 0.1}
    await tf.voz_de_examen(update_voz(log, 30), ctx)
    check("audio que no se entiende -> se pide de nuevo",
          any("no entendí lo que dijiste" in t for k, t in log) and "habla" not in ex["scores"])

    estado["transcribe"] = lambda ruta, lang: audio_bueno()
    estado["grade"] = lambda *a, **k: nota(0, needs_rewrite=True, feedback="Debes hablar en inglés.")
    await tf.voz_de_examen(update_voz(log, 30), ctx)
    check("habló en otro idioma -> se pide de nuevo (mensaje de habla, no de escritura)",
          any("Debes hablar en inglés." in t for k, t in log) and "habla" not in ex["scores"])

    estado["grade"] = lambda *a, **k: nota(85)
    await tf.voz_de_examen(update_voz(log, 30), ctx)
    check("el audio bueno sí se califica", "examen" not in ctx.user_data or
          ctx.user_data["examen"]["level"] == "A2")

    log2, ctx2 = [], Ctx()
    estado["transcribe"] = lambda ruta, lang: audio_bueno()
    await empezar(log2, ctx2)
    await responder_todas_lectura(log2, ctx2)
    await responder_todas_escucha(log2, ctx2)
    await tf.texto_de_examen(update_texto(log2, "texto"), ctx2)
    await tf.voz_de_examen(update_voz(log2, 30, como_audio=True), ctx2)
    check("un archivo de audio adjunto también sirve (antes tumbaba el bot)",
          ctx2.user_data["examen"]["level"] == "A2")

    log3, ctx3 = [], Ctx()
    await empezar(log3, ctx3)
    await responder_todas_lectura(log3, ctx3)
    await responder_todas_escucha(log3, ctx3)
    await tf.texto_de_examen(update_texto(log3, "texto"), ctx3)
    u = update_voz(log3, 30)
    u.message.voice = None   # ni nota de voz ni audio
    await tf.voz_de_examen(u, ctx3)
    check("un mensaje de voz vacío no tumba el bot",
          any("No encontré el audio" in t for k, t in log3))


async def caso_fallo_tecnico_habla():
    print("\n9) El habla falla por un problema del sistema: no deja atascado al estudiante")
    log, ctx = [], Ctx()
    estado["grade"] = lambda *a, **k: nota(85)

    def revienta(ruta, lang):
        raise RuntimeError("faster-whisper no instalado")

    estado["transcribe"] = revienta

    await empezar(log, ctx)
    await responder_todas_lectura(log, ctx)
    await responder_todas_escucha(log, ctx)
    await tf.texto_de_examen(update_texto(log, "texto"), ctx)

    await tf.voz_de_examen(update_voz(log, 30), ctx)
    await tf.voz_de_examen(update_voz(log, 30), ctx)
    check("los primeros intentos solo piden el audio de nuevo",
          "examen" in ctx.user_data and ctx.user_data["examen"]["part"] == "habla")
    check("se le avisa del problema",
          sum(1 for k, t in log if "No pude procesar tu audio" in t) == 2)

    await tf.voz_de_examen(update_voz(log, 30), ctx)
    check(f"tras {tf.MAX_FALLOS_HABLA} fallos se cierra el nivel sin la parte de habla",
          any("cierro este nivel sin la parte de habla" in t for k, t in log))
    resumen = [t for k, t in log if "📊 Resultado A1" in t]
    check("el resumen no muestra Habla", bool(resumen) and "Habla:" not in resumen[0])
    check("pero sí muestra las otras tres partes",
          bool(resumen) and all(p in resumen[0] for p in ("Lectura:", "Escucha:", "Escritura:")))
    check("y el nivel se asignó igual (no se penalizó)",
          ctx.user_data["nivel"]["level"] in ("A1", "A2"))

    # Un fallo aislado no debe acumularse para siempre
    log2, ctx2 = [], Ctx()
    estado["transcribe"] = revienta
    await empezar(log2, ctx2)
    await responder_todas_lectura(log2, ctx2)
    await responder_todas_escucha(log2, ctx2)
    await tf.texto_de_examen(update_texto(log2, "texto"), ctx2)
    await tf.voz_de_examen(update_voz(log2, 30), ctx2)
    estado["transcribe"] = lambda ruta, lang: audio_bueno()
    await tf.voz_de_examen(update_voz(log2, 30), ctx2)
    check("un audio bueno reinicia la cuenta de fallos",
          ctx2.user_data["examen"]["level"] == "A2" and ctx2.user_data["examen"]["habla_fallos"] == 0)


async def caso_mensajes_fuera_de_lugar():
    print("\n10) Mensajes en el momento equivocado y botones viejos")
    log, ctx = [], Ctx()
    estado["grade"] = lambda *a, **k: nota(85)
    estado["transcribe"] = lambda ruta, lang: audio_bueno()

    check("fuera del examen, un texto no lo atiende el examen",
          await tf.texto_de_examen(update_texto(log, "hola"), ctx) is False)
    check("fuera del examen, una nota de voz no la atiende el examen",
          await tf.voz_de_examen(update_voz(log, 30), ctx) is False)

    await empezar(log, ctx)
    await tf.texto_de_examen(update_texto(log, "hola"), ctx)
    check("durante la lectura se le dice que use los botones",
          any("usa los botones" in t.lower() or "Responde con los botones" in t for k, t in log))

    await tf.voz_de_examen(update_voz(log, 30), ctx)
    check("una nota de voz durante la lectura se rechaza",
          any("Todavía no es momento" in t for k, t in log))

    ex = ctx.user_data["examen"]
    antes = ex["q"]
    await tf.responder_lectura(update_callback(log, "ans:7:1"), ctx)
    check("un botón de otra pregunta se ignora", ex["q"] == antes)

    await responder_todas_lectura(log, ctx)
    await tf.texto_de_examen(update_texto(log, "hola"), ctx)
    check("durante la escucha también se le piden los botones",
          sum(1 for k, t in log if "Responde con los botones" in t) == 2)

    antes = ex["l_q"]
    await tf.responder_escucha(update_callback(log, "lis:9:1"), ctx)
    check("un botón de escucha viejo se ignora", ex["l_q"] == antes)

    await responder_todas_escucha(log, ctx)
    await tf.texto_de_examen(update_texto(log, "texto"), ctx)
    await tf.texto_de_examen(update_texto(log, "texto otra vez"), ctx)
    check("un texto durante el habla pide la nota de voz",
          any("envíame una nota de voz" in t for k, t in log))


async def caso_opciones_largas():
    print("\n11) Opciones largas (B1): se listan A/B/C en el mensaje")
    extra, filas = tf._opciones_y_filas(["corta", "otra", "tercera"], "ans", 0)
    check("opciones cortas: un botón por opción", extra == "" and len(filas) == 3)

    larga = "una opción muy larga que no cabe de ninguna manera dentro de un botón de Telegram"
    extra, filas = tf._opciones_y_filas([larga, "corta", "otra"], "lis", 2)
    check("opciones largas: se listan en el mensaje", "A) " + larga in extra)
    check("y los botones quedan en una sola fila con las letras",
          len(filas) == 1 and len(filas[0]) == 3 and filas[0][0].text == "A")
    check("el callback_data mantiene el prefijo y el índice",
          filas[0][2].callback_data == "lis:2:2")


async def main():
    _instalar_dobles()
    await caso_examen_completo()
    await caso_no_pasa()
    await caso_sin_escucha()
    await caso_audio_sin_tts()
    await caso_audio_por_etapas()
    await caso_voz_por_etapas()
    await caso_repetir_audio()
    await caso_audios_malos()
    await caso_fallo_tecnico_habla()
    await caso_mensajes_fuera_de_lugar()
    await caso_opciones_largas()
    print(f"\nResultado: {ok_total} OK, {fail_total} con falla")
    raise SystemExit(1 if fail_total else 0)


if __name__ == "__main__":
    asyncio.run(main())
