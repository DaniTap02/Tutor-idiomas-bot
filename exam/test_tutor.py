"""Prueba SIN Telegram, SIN Ollama y SIN Lara del tutor adaptativo (exam/tutor.py y exam/lecciones.py):

    python -m exam.test_tutor

Comprueba que el temario (5 lecciones por nivel e idioma) usa temas que existen en los bancos, la
regla de adaptación (repetir el tema fallado, avanzar con una racha), y simula lecciones completas
con botones y escritura: explicación -> ejercicios -> escritura -> lección siguiente -> oferta de
volver a presentar el examen. También /practicar, /nivel e /idioma.
"""
import asyncio
import logging

from exam import tutor
from exam.lecciones import LECCIONES

logging.disable(logging.CRITICAL)

ok_total = 0
fail_total = 0


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK    " if condicion else "  FALLA ") + nombre)
    ok_total += bool(condicion)
    fail_total += not condicion


# ---------------------------------------------------------------- Telegram simulado

class Mensaje:
    def __init__(self, log, text=None):
        self.log = log
        self.text = text

    async def reply_text(self, texto, reply_markup=None):
        self.log.append(("text", texto, reply_markup))
        return Mensaje(self.log)

    async def edit_text(self, texto, reply_markup=None):
        self.log.append(("edit", texto, reply_markup))

    async def delete(self):
        pass


class Query:
    def __init__(self, log, data):
        self.log = log
        self.data = data
        self.message = Mensaje(log)

    async def answer(self, texto=None, show_alert=False):
        pass

    async def edit_message_reply_markup(self, reply_markup=None):
        pass

    async def edit_message_text(self, texto):
        self.log.append(("edit", texto, None))


class Ctx:
    def __init__(self, nivel=None):
        self.user_data = {}
        if nivel:
            self.user_data["nivel"] = dict(nivel)


def upd_cmd(log, texto=None):
    class U:
        message = Mensaje(log, texto)
        effective_message = message
    return U()


def upd_btn(log, data):
    class U:
        callback_query = Query(log, data)
    return U()


def textos(log):
    return [e[1] for e in log]


# ---------------------------------------------------------------- Dobles de Ollama, grader y Lara

generadas = []


def ejercicio_falso(banco, language, tema, kind="grammar"):
    generadas.append((language, kind, tema))
    return {"q": f"Pregunta de {tema[:20]} ___?", "options": ["a", "b", "c"], "answer": 0, "topic": tema, "kind": kind}


def grade_falso(texto, level, language, checklist, *a, **k):
    if len(texto.split()) < 3:
        return {"score": 0, "task_completed": False, "errors": [], "needs_rewrite": True,
                "feedback": "Your text is too short."}
    return {"score": 85, "task_completed": True, "errors": [], "needs_rewrite": False, "feedback": "Good job!"}


async def idioma_ok(espera, texto, idioma, skill="writing"):
    return False


examenes = []


async def examen_falso(message, context, language, level="A1"):
    examenes.append((language, level))
    context.user_data["examen"] = {"language": language, "level": level, "part": "lectura"}


tutor.generar_ejercicio = ejercicio_falso
tutor.grade = grade_falso
tutor.revisar_idioma = idioma_ok
tutor.iniciar_examen_en = examen_falso
tutor._call_ollama = lambda system, user, temperature=0.1: {
    "explanation": "We use the verb to be to say who we are.", "examples": ["I am Ana.", "She is a teacher."]}


# ---------------------------------------------------------------- 1. Temario como datos

print("\n== Temario")
for level, lecciones in LECCIONES.items():
    check(f"{level}: 5 lecciones", len(lecciones) == 5)
    for lec in lecciones:
        for lang in ("en", "es"):
            try:
                temas = tutor.temas_de_leccion(lec, tutor.banco_de(level), lang)
                existe = bool(temas)
            except KeyError as exc:
                print("      ", exc)
                existe = False
            if not existe:
                check(f"{lec['id']} ({lang}): todos sus temas existen en el banco", False)
        espejo = all(set(lec[c]) == {"en", "es"} for c in ("titulo", "objetivo", "gramatica", "vocabulario", "escritura")) \
            and all(set(c["label"]) == {"en", "es"} for c in lec["checklist"])
        if not espejo:
            check(f"{lec['id']}: estructura espejo inglés/español", False)
check("todos los temas de las lecciones existen en su banco (inglés y español)", fail_total == 0)
ids = [lec["id"] for lecs in LECCIONES.values() for lec in lecs]
check("ids de lección únicos", len(ids) == len(set(ids)))
check("inglés y español tienen las mismas lecciones (espejo)", all(
    set(lec["titulo"]) == {"en", "es"} for lecs in LECCIONES.values() for lec in lecs))

# ---------------------------------------------------------------- 2. Adaptación

print("\n== Adaptación")
temas = [("grammar", "T1"), ("vocab", "T2"), ("grammar", "T3")]
prog = tutor.progreso_nuevo("A1")
check("empieza por el primer tema", tutor.elegir_tema(prog, temas) == ("grammar", "T1"))
check("si falla, se repite el mismo tema", tutor.registrar_respuesta(prog, "grammar", "T1", False) == "repetir"
      and tutor.elegir_tema(prog, temas) == ("grammar", "T1"))
check("si acierta, sigue con otro tema", tutor.registrar_respuesta(prog, "grammar", "T1", True) == "otro"
      and tutor.elegir_tema(prog, temas) == ("vocab", "T2"))

prog = tutor.progreso_nuevo("A1")
pasos = [tutor.registrar_respuesta(prog, "grammar", "T", True) for _ in range(3)]
check("3 aciertos seguidos: avanza a la escritura antes de las 5", pasos == ["otro", "otro", "escritura"])

prog = tutor.progreso_nuevo("A1")
pasos = [tutor.registrar_respuesta(prog, "grammar", "T", c) for c in (True, False, True, True, False, True)]
check("con fallos: termina al llegar a 5 y acertar la última", pasos[-1] == "escritura" and pasos[3] == "otro")

prog = tutor.progreso_nuevo("A1")
pasos = [tutor.registrar_respuesta(prog, "grammar", "T", False) for _ in range(tutor.MAX_EJERCICIOS_LECCION)]
check(f"nunca más de {tutor.MAX_EJERCICIOS_LECCION} ejercicios aunque siga fallando", pasos[-1] == "escritura")

datos = {"temas_fallados": {"en": [["grammar", tutor.banco_de("A1").GRAMMAR_TARGETS[0]]]}}
tutor.random.seed(1)
elegidos = [tutor.tema_para_practica(datos, tutor.banco_de("A1"), "en") for _ in range(40)]
repasos = sum(1 for e in elegidos if e[1] == tutor.banco_de("A1").GRAMMAR_TARGETS[0])
check("/practicar repasa más seguido el tema fallado", repasos >= 12)


# ---------------------------------------------------------------- 3. Lecciones simuladas

async def responder_actual(log, ctx, correcta=True):
    ej = ctx.user_data["ej_actual"]
    opcion = ej["answer"] if correcta else (ej["answer"] + 1) % 3
    await tutor.responder_ejercicio(upd_btn(log, f"{ej['origen']}:{ej['n']}:{opcion}"), ctx)


async def lecciones():
    print("\n== Lección completa (inglés A1)")
    log = []
    ctx = Ctx({"language": "en", "level": "A1", "provisional": False})
    await tutor.leccion(upd_cmd(log), ctx)
    t = textos(log)
    check("muestra título, objetivo y explicación en inglés", any("Lesson 1/5" in x and "verb to be" in x for x in t))
    check("la explicación de A1 trae botón Ver traducción", any(
        e[2] is not None and e[2].inline_keyboard[-1][0].callback_data.startswith("tr:") for e in log if "Lesson 1/5" in e[1]))
    check("manda el primer ejercicio con botones lc:", ctx.user_data["ej_actual"]["origen"] == "lc")
    primer_tema = ctx.user_data["ej_actual"]["topic"]

    await responder_actual(log, ctx, correcta=False)
    check("al fallar, el siguiente ejercicio es del mismo tema", ctx.user_data["ej_actual"]["topic"] == primer_tema
          and "practise that topic again" in "".join(textos(log)))
    for _ in range(3):
        await responder_actual(log, ctx, correcta=True)
    prog = ctx.user_data["progreso"]["en"]
    check("con 3 aciertos seguidos pasa a la escritura", prog["paso"] == "escritura"
          and ctx.user_data["esperando"] == "leccion_escritura")
    check("cuenta correctas e incorrectas", ctx.user_data["correctas"] == 3 and ctx.user_data["incorrectas"] == 1)

    log.clear()
    hecho = await tutor.texto_de_leccion(upd_cmd(log, "Hi"), ctx)
    check("escritura muy corta: se pide de nuevo sin completar", hecho and prog["paso"] == "escritura"
          and "Try again" in textos(log)[-1])
    await tutor.texto_de_leccion(upd_cmd(log, "Hello, my name is Ana and I am from Colombia."), ctx)
    check("escritura buena: lección completada y pasa a la 2", prog["completadas"] == ["A1-1"]
          and prog["leccion"] == 1 and prog["paso"] == "inicio" and ctx.user_data["esperando"] is None)
    check("mensaje de lección completada en inglés", "Lesson completed" in textos(log)[-1])

    # Completa las 4 lecciones que faltan
    for _ in range(4):
        await tutor.leccion(upd_cmd(log), ctx)
        for _ in range(3):
            await responder_actual(log, ctx, correcta=True)
        await tutor.texto_de_leccion(upd_cmd(log, "This is my answer for the lesson today."), ctx)
    check("tras las 5 lecciones: fin del nivel", prog["paso"] == "fin_nivel" and len(prog["completadas"]) == 5)
    check("ofrece volver a presentar el examen A1", any("take the A1 test again" in x for x in textos(log)))
    await tutor.responder_repaso(upd_btn(log, "rex:si"), ctx)
    check("rex:si lanza el examen de ESE nivel", examenes[-1] == ("en", "A1"))

    print("\n== Lección en español (A2)")
    log = []
    generadas.clear()
    ctx = Ctx({"language": "es", "level": "A2", "provisional": False})
    await tutor.leccion(upd_cmd(log), ctx)
    check("mensajes de la lección en español", any("Lección 1/5" in x for x in textos(log)))
    check("los ejercicios usan temas del banco en español", generadas and generadas[0][0] == "es"
          and generadas[0][2] in tutor.banco_de("A2").GRAMMAR_TARGETS_ES + tutor.banco_de("A2").VOCAB_TARGETS_ES)

    print("\n== /practicar, /nivel e /idioma")
    log = []
    ctx = Ctx({"language": "en", "level": "B1", "provisional": False})
    await tutor.practicar(upd_cmd(log), ctx)
    check("/practicar genera un ejercicio del nivel e idioma del usuario", ctx.user_data["ej_actual"]["origen"] == "pr"
          and ctx.user_data["ej_actual"]["level"] == "B1" and "Practice · B1" in textos(log)[-1])
    await responder_actual(log, ctx, correcta=False)
    check("al fallar en la práctica, el tema queda para repasar", ctx.user_data["temas_fallados"]["en"])
    check("dice la respuesta correcta en inglés", "The right answer is «a»" in textos(log)[-1])
    await responder_actual(log, ctx, correcta=True)
    check("un botón viejo ya no cuenta dos veces", ctx.user_data.get("correctas", 0) == 0)

    log = []
    ctx = Ctx()
    await tutor.practicar(upd_cmd(log), ctx)
    check("/practicar sin nivel: pide el examen", "examen de nivel" in textos(log)[-1])

    log = []
    ctx = Ctx({"language": "en", "level": "A2", "provisional": True})
    await tutor.comando_nivel(upd_cmd(log), ctx)
    check("/nivel muestra idioma, nivel y lección", "Level: A2 (provisional)" in textos(log)[-1]
          and "Lesson: 1/5" in textos(log)[-1])

    await tutor.comando_idioma(upd_cmd(log), ctx)
    check("/idioma ofrece los dos idiomas", "idioma:es" in str(log[-1][2].inline_keyboard))
    await tutor.elegir_idioma_tutor(upd_btn(log, "idioma:es"), ctx)
    check("idioma sin nivel: lanza el examen desde A1", examenes[-1] == ("es", "A1"))
    ctx.user_data.pop("examen")
    ctx.user_data["niveles"]["es"] = {"language": "es", "level": "B1", "provisional": False}
    await tutor.elegir_idioma_tutor(upd_btn(log, "idioma:en"), ctx)
    check("idioma con nivel: vuelve a ese nivel sin examen", ctx.user_data["nivel"]["level"] == "A2"
          and ctx.user_data["nivel"]["language"] == "en")
    await tutor.elegir_idioma_tutor(upd_btn(log, "idioma:es"), ctx)
    check("y al revés", ctx.user_data["nivel"] == {"language": "es", "level": "B1", "provisional": False})

    print("\n== Explicación")
    lec = LECCIONES["A1"][0]
    tutor._call_ollama = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin Ollama"))
    texto = tutor.generar_explicacion(lec, tutor.banco_de("A1"), "en", "A1")
    check("si Ollama falla, hay explicación de respaldo (no se frena la lección)", texto.startswith("Today you practise"))
    tutor._call_ollama = lambda *a, **k: {"explanation": "Tomorrow I will go to school.", "examples": []}
    texto = tutor.generar_explicacion(lec, tutor.banco_de("A1"), "en", "A1")
    check("explicación con gramática prohibida del nivel (will en A1): se descarta", texto.startswith("Today you practise"))


asyncio.run(lecciones())
print(f"\nResultado: {ok_total} OK, {fail_total} con falla")
