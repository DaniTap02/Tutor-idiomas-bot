"""Prueba SIN Ollama del evaluador de respuestas abiertas (modelo simulado):

    python -m exam.test_calificador

Comprueba que una respuesta válida dicha de OTRA forma (contracción, sinónimo, errata menor) no se
marca como incorrecta, que una respuesta a medias dice QUÉ falta, que los mensajes de la parte de
habla hablan de "audio" y no de "texto", y los casos reales de la prueba con Ollama (13 nov 2026):
textos con errores que sacaban 100, "me quedé en casa" como "a dónde fuiste" y una carta sin
solución que contaba como completa.
"""
import re

from exam import grader, questions_a1, questions_b1

CHECK = questions_a1.TASK_CHECKLIST["writing"]
CHECK_HABLA = questions_a1.TASK_CHECKLIST["speaking"]

ok_total = 0
fail_total = 0


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK    " if condicion else "  FALLA ") + nombre)
    ok_total += bool(condicion)
    fail_total += not condicion


# ---------------------------------------------------------------- Modelo simulado

vistos: list[str] = []
respuesta: dict = {}
correcciones: dict = {}      # oración original -> oración corregida (lo que no está aquí no cambia)
revision: list | None = None  # respuesta de la segunda revisión de requisitos (None: todo se cumple)


def modelo(system, user, temperature=0.1):
    vistos.append(system + "\n" + user)
    if "proofreader" in system:              # corrección oración por oración
        oraciones = re.findall(r"^\d+\. (.*)$", user, re.M)
        return {"items": [correcciones.get(o, o) for o in oraciones]}
    if system.startswith("You check if"):    # segunda revisión de requisitos
        n = len(re.findall(r"^\d+\. requirement:", user, re.M))
        return {"items": revision if revision is not None else [{"ok": True, "why": ""}] * n}
    return respuesta


grader._call_ollama = modelo


def veredicto(requisitos, idioma_ok=True, feedback="¡Muy bien!"):
    return {"is_in_language": idioma_ok, "requirements": requisitos, "feedback": feedback}


def prompt_de(fragmento):
    """El system del último llamado que contiene `fragmento`."""
    return next(v for v in reversed(vistos) if fragmento in v)


TEXTO = "My name is Tapi. I'm from Colombia and I really enjoy music."

print("1) Las dos formas de responder los requisitos")
respuesta = veredicto({"req1": True, "req2": True, "req3": True})
r = grader.grade(TEXTO, "A1", "en", CHECK)
check("forma antigua (true/false) -> sigue funcionando", r["score"] == 100 and r["task_completed"])

respuesta = veredicto({c["id"]: {"ok": True, "why": ""} for c in CHECK})
r = grader.grade(TEXTO, "A1", "en", CHECK)
check("forma nueva ({ok, why}) -> funciona igual", r["score"] == 100 and r["task_completed"])

respuesta = veredicto({"req1": "true", "req2": "sí", "req3": {"ok": "yes"}})
r = grader.grade(TEXTO, "A1", "en", CHECK)
check("un modelo pequeño que responde con texto -> se entiende igual", r["task_completed"])

print("\n2) Respuestas equivalentes: no se penaliza decirlo de otra forma")
# Los prompts deciden esto, así que se comprueba que las instrucciones estén de verdad.
respuesta = veredicto({c["id"]: {"ok": True, "why": ""} for c in CHECK})
grader.grade("I'm Tapi, I come from Colombia and music is what I love.", "A1", "en", CHECK)
prompt = prompt_de("fair English examiner")
for regla in ['"I\'m" = "I am"', "synonym", "Judge the MEANING", "regional variant"]:
    check(f"el calificador recibe la regla: {regla}", regla in prompt)
check("se le dice que una errata menor no invalida el requisito",
      "does NOT change the meaning" in prompt and "requirement is true" in prompt)
corrector = prompt_de("proofreader")
check("al corrector se le prohíbe tocar contracciones y sinónimos",
      '"I\'m" and "I am" are both correct' in corrector and "no synonyms" in corrector)
check("al corrector se le pide copiar igual la oración correcta", "copy it EXACTLY" in corrector)

print("\n3) Respuesta parcialmente correcta: se dice QUÉ falta y por qué")
respuesta = veredicto({
    "req1": {"ok": True, "why": ""},
    "req2": {"ok": True, "why": ""},
    "req3": {"ok": False, "why": "no dices nada que te guste"},
})
r = grader.grade("My name is Tapi. I am from Colombia.", "A1", "en", CHECK)
check("no la marca como completa", r["task_completed"] is False)
check("dice qué requisito falta", "algo que te gusta" in r["feedback"])
check("y explica por qué falta", "no dices nada que te guste" in r["feedback"])
check("devuelve los requisitos que faltan", r["missing"] == ["req3"])
check("resta solo por el requisito que falta", r["score"] == 100 - grader.MISSING_PENALTY)

print("\n4) Errores: el modelo corrige cada oración y el código compara")
# Caso real de A1: "My name Laura. I from Colombia. I likes music." sacaba 100.
respuesta = veredicto({c["id"]: {"ok": True, "why": ""} for c in CHECK})
correcciones = {
    "My name Laura.": "My name is Laura.",
    "I from Colombia.": "I am from Colombia.",
    "I likes music.": "I like music.",
}
r = grader.grade("My name Laura. I from Colombia. I likes music.", "A1", "en", CHECK)
check("los 3 errores reales se cuentan", len(r["errors"]) == 3)
check("cada error muestra el trozo y su corrección",
      {"fragment": "name Laura", "type": "grammar", "correction": "name is Laura"} in r["errors"])
check("'likes' -> 'like' se ve como ortografía/forma de una palabra",
      any(e["fragment"] == "I likes music" and e["correction"] == "I like music" for e in r["errors"]))
check("el puntaje resta por cada error", r["score"] == 100 - 3 * grader.PENALTY_PER_ERROR["A1"])

correcciones = {"My name is Tapi.": "My name is Tapi", "I'm from Colombia and I really enjoy music.":
                "i'm from colombia and I really enjoy music!"}
r = grader.grade(TEXTO, "A1", "en", CHECK)
check("puntuación y mayúsculas no cuentan como error", r["errors"] == [] and r["score"] == 100)

correcciones = {}
r = grader.grade(TEXTO, "A1", "en", CHECK)
check("una oración que el corrector deja igual no tiene errores", r["errors"] == [])

print("\n5) Tildes en español: en A1 y A2 no cuentan, desde B1 sí")
TEXTO_ES = "Hola, me llamo Tapi. Soy de Ibague. Me gusta el cafe y la musica."
correcciones = {"Soy de Ibague.": "Soy de Ibagué.", "Me gusta el cafe y la musica.": "Me gusta el café y la música."}
respuesta = veredicto({c["id"]: {"ok": True, "why": ""} for c in CHECK})
r = grader.grade(TEXTO_ES, "A1", "es", CHECK)
check("A1: las tildes que faltan no restan", r["errors"] == [] and r["score"] == 100)
r = grader.grade(TEXTO_ES * 5, "B1", "es", questions_b1.WRITING_TASKS[0]["checklist"])
check("B1: las tildes que faltan sí se listan", any(e["correction"].endswith("Ibagué") for e in r["errors"]))
r = grader.grade(TEXTO_ES * 5, "B1", "es", questions_b1.WRITING_TASKS[0]["checklist"], is_transcript=True)
check("en una transcripción las tildes nunca cuentan (las pone Whisper)", r["errors"] == [])
correcciones = {}

print("\n6) Si el corrector falla, no se castiga al estudiante")


def modelo_falla(system, user, temperature=0.1):
    if "proofreader" in system:
        raise RuntimeError("Ollama no responde")
    return modelo(system, user, temperature)


grader._call_ollama = modelo_falla
r = grader.grade("My name Laura. I from Colombia. I likes music.", "A1", "en", CHECK)
check("Ollama falla al corregir -> no se cuenta ningún error", r["errors"] == [] and r["score"] == 100)
grader._call_ollama = lambda s, u, temperature=0.1: (
    {"items": ["solo una"]} if "proofreader" in s else modelo(s, u, temperature))
r = grader.grade("My name Laura. I from Colombia. I likes music.", "A1", "en", CHECK)
check("el corrector devuelve otra cantidad de oraciones -> no se cuenta ningún error", r["errors"] == [])
grader._call_ollama = modelo

print("\n7) Requisitos con CITA: el código comprueba que lo citado esté en el texto")
# Caso real de B2: una carta que solo se queja se calificaba con "pide una solución" cumplido.
CARTA = ("Estimado señor Pérez: le escribo porque el servicio de limpieza fue muy malo. El equipo llegó "
         "tarde y dejó la cocina sucia. Me sentí muy molesta. Atentamente, Ana Torres")
respuesta = veredicto({
    "req1": {"ok": True, "quote": "Me llamo Ana Torres", "why": ""},   # inventada: no está en el texto
    "req2": {"ok": True, "quote": "", "why": ""},                       # sin cita
    "req3": {"ok": True, "quote": "el equipo llegó tarde y dejó la cocina sucia", "why": ""},
})
r = grader.grade(CARTA, "A1", "es", CHECK)
check("cita inventada -> el requisito falta", "req1" in r["missing"])
check("cita vacía -> el requisito falta", "req2" in r["missing"])
check("cita copiada del texto -> el requisito se cumple", "req3" not in r["missing"])
respuesta = veredicto({"req1": {"ok": True, "quote": "señor Perez, le escribo", "why": ""},
                       "req2": {"ok": True, "why": ""}, "req3": True})
r = grader.grade(CARTA, "A1", "es", CHECK)
check("cita aproximada (sin tilde, otra puntuación) -> vale", "req1" not in r["missing"])
check("sin campo 'quote' (falla de formato del modelo) -> no se castiga", r["task_completed"])

print("\n8) Segunda revisión: ¿la cita de verdad cumple el requisito?")
# Caso real de A2: "I stayed at home" contaba como "a dónde fuiste".
CASA = "Hi Ana! Last weekend I stayed at home with my family. We watched television and we talked a lot."
respuesta = veredicto({
    "req1": {"ok": True, "quote": "I stayed at home with my family", "why": ""},
    "req2": {"ok": True, "quote": "We watched television", "why": ""},
    "req3": {"ok": True, "quote": "we talked a lot", "why": ""},
})
revision = [{"ok": False, "why": "quedarse en casa no es ir a un lugar"}, {"ok": True, "why": ""}, {"ok": True}]
vistos.clear()
r = grader.grade(CASA, "A1", "en", CHECK)
segunda = prompt_de("You check if")
check("la revisión ve el requisito y la cita", "I stayed at home with my family" in segunda
      and CHECK[0]["check"] in segunda)
check("la revisión dice que no lo cumple -> el requisito falta", r["missing"] == ["req1"])
check("y se explica por qué", "quedarse en casa no es ir a un lugar" in r["feedback"])
check("la revisión ve el texto completo", "Full text: " + CASA in segunda)
check("a la revisión se le prohíbe juzgar la gramática (no se castiga dos veces el mismo error)",
      "Do NOT judge grammar" in segunda)
revision = [{"ok": True}]   # cantidad equivocada: falla del sistema
r = grader.grade(CASA, "A1", "en", CHECK)
check("si la revisión responde mal, se respeta la primera respuesta", r["task_completed"])
revision = None

print("\n8b) Requisitos de FORMA que revisa el código (conectores, pasado)")
# Caso real de B1: la segunda revisión decía que «Sin embargo… porque… Además» no tenía conectores.
OPINION = next(t for t in questions_b1.WRITING_TASKS if t["id"] == "opinion")["checklist"]
check("el requisito de conectores de B1 usa el patrón del código",
      OPINION[2].get("patron") == "conectores" and OPINION[2].get("basta"))
TEXTO_OP = ("En mi opinión las redes son útiles porque sirven para aprender. Sin embargo, muchos jóvenes "
            "duermen poco. Además, se comparan con otros. ") * 4
respuesta = veredicto({"req1": {"ok": True, "quote": "En mi opinión las redes son útiles", "why": ""},
                       "req2": {"ok": True, "quote": "sirven para aprender", "why": ""},
                       "req3": {"ok": False, "quote": "", "why": "no usa conectores"}})
revision = [{"ok": True}, {"ok": True}]
vistos.clear()
r = grader.grade(TEXTO_OP, "B1", "es", OPINION)
check("el modelo dice que no hay conectores, pero el código ve 'sin embargo' -> se cumple",
      r["task_completed"])
check("el requisito de conectores no pasa por la segunda revisión",
      "linking word" not in prompt_de("You check if"))
revision = [{"ok": False, "why": "no está en pasado"}]
respuesta = veredicto({"req2": {"ok": True, "quote": "I went to the beach", "why": ""}})
r = grader.grade("My name is Tapi. Last weekend I went to the beach and I ate fish. I liked it a lot.",
                 "A2", "en", [{"id": "req2", "check": "the student says something they did, using the past tense",
                               "label_es": "qué hiciste (en pasado)", "patron": "pasado"}])
check("hay un verbo en pasado ('went') -> la segunda revisión no puede quitar el requisito", r["task_completed"])
respuesta = veredicto({"req2": {"ok": False, "quote": "", "why": "no dices qué hiciste"}})
r = grader.grade("My name is Tapi. Last weekend I went to the beach and I ate fish. I liked it a lot.",
                 "A2", "en", [{"id": "req2", "check": "the student says something they did, using the past tense",
                               "label_es": "qué hiciste (en pasado)", "patron": "pasado"}])
check("pero el pasado no basta por sí solo: si el modelo dice que falta el contenido, falta",
      not r["task_completed"])
revision = None

print("\n9) Idioma: el código detecta el otro idioma sin preguntarle al modelo")
# Caso real de A2: un texto en español en el examen de inglés sacaba 100.
respuesta = veredicto({c["id"]: {"ok": True, "why": ""} for c in CHECK})   # el modelo no lo nota
vistos.clear()
r = grader.grade("Hola Ana! El fin de semana pasado fui a Cartagena con mi familia y comí pescado.",
                 "A1", "en", CHECK)
check("español en el examen de inglés -> se pide reescribir", r["needs_rewrite"] and "inglés" in r["feedback"])
check("y no se gastó una llamada al modelo", vistos == [])
r = grader.grade("My name is Tapi and I live in Bogotá, near Plaza de Bolívar.", "A1", "en", CHECK)
check("unos nombres en español dentro de un texto en inglés -> no molesta", not r["needs_rewrite"])

print("\n10) Mensajes de ESCRITURA y de HABLA")
respuesta = veredicto({}, idioma_ok=False)
r = grader.grade(TEXTO, "A1", "en", CHECK, skill="writing")
check("escritura en otro idioma -> habla de 'texto escrito'",
      "escrito en inglés" in r["feedback"] and r["needs_rewrite"])
r = grader.grade(TEXTO, "A1", "en", CHECK_HABLA, True, "Spanish", "speaking")
check("habla en otro idioma -> habla de 'hablar', no de escribir",
      r["feedback"] == "Debes hablar en inglés." and r["needs_rewrite"])

r = grader.grade("hola", "A1", "en", CHECK, skill="writing")
check("texto muy corto -> 'Escribe al menos N palabras'", "Escribe al menos" in r["feedback"])
r = grader.grade("hola", "A1", "en", CHECK_HABLA, True, "Spanish", "speaking")
check("audio muy corto -> 'Habla al menos N palabras'", "Habla al menos" in r["feedback"])
check("el mínimo de palabras del habla es más bajo que el de escritura",
      grader.MIN_WORDS_SPEAKING["B1"] < grader.MIN_WORDS["B1"])

print("\n11) El texto se juzga, no se compara con una respuesta esperada")
check("el calificador no recibe ninguna 'respuesta correcta' con la que comparar",
      "expected answer" not in prompt.lower() or "no expected answer" in prompt.lower())
check("B1 tiene tope de errores contados (un modelo pequeño inventa errores en textos largos)",
      grader.MAX_ERRORS_COUNTED.get("B1") == 5)
LARGO = " ".join(f"Sentence number {i} is bad." for i in range(9)) + " " + " ".join(["word"] * 60)
correcciones = {f"Sentence number {i} is bad.": f"Sentence number {i} is good." for i in range(9)}
respuesta = veredicto({c["id"]: {"ok": True, "why": ""} for c in questions_b1.WRITING_TASKS[0]["checklist"]})
r = grader.grade(LARGO, "B1", "en", questions_b1.WRITING_TASKS[0]["checklist"])
check("9 errores en B1 solo descuentan los 5 del tope",
      len(r["errors"]) == 9 and r["score"] == 100 - grader.PENALTY_PER_ERROR["B1"] * 5)
correcciones = {}

print(f"\nResultado: {ok_total} OK, {fail_total} con falla")


def test_sin_fallas():
    """pytest: todas las comprobaciones de este archivo pasaron (se ejecutan al importarlo)."""
    assert fail_total == 0, f"{fail_total} comprobaciones con falla (mira la salida con: pytest -s)"


if __name__ == "__main__":
    raise SystemExit(1 if fail_total else 0)
