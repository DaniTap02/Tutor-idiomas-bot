"""Prueba SIN Ollama del evaluador de respuestas abiertas (modelo simulado):

    python -m exam.test_calificador

Comprueba que una respuesta válida dicha de OTRA forma (contracción, sinónimo, errata menor) no se
marca como incorrecta, que una respuesta a medias dice QUÉ falta, y que los mensajes de la parte de
habla hablan de "audio" y no de "texto".
"""
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


def modelo(system, user, temperature=0.1):
    vistos.append(system + "\n" + user)
    if "grammar checker" in system:          # segunda pasada que descarta errores falsos
        return {"items": [True] * len(respuesta.get("errors", []))}
    return respuesta


grader._call_ollama = modelo


def veredicto(requisitos, errores=None, idioma_ok=True, feedback="¡Muy bien!"):
    return {"is_in_language": idioma_ok, "requirements": requisitos,
            "errors": errores or [], "feedback": feedback}


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
# El prompt es lo que decide esto, así que se comprueba que la instrucción esté de verdad.
respuesta = veredicto({c["id"]: {"ok": True, "why": ""} for c in CHECK})
grader.grade("I'm Tapi, I come from Colombia and music is what I love.", "A1", "en", CHECK)
prompt = vistos[-2]   # el system del primer llamado (el último es la segunda pasada)
for regla in ['"I\'m" = "I am"', "synonym", "Judge the MEANING", "regional variant"]:
    check(f"el calificador recibe la regla: {regla}", regla in prompt)
check("se le dice que una errata menor no invalida el requisito",
      "does NOT change the meaning" in prompt and "requirement is true" in prompt)
check("se le prohíbe listar contracciones como error",
      "never list a contraction" in prompt)

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

print("\n4) Erratas menores: cuentan como error, pero el requisito se cumple")
respuesta = veredicto(
    {c["id"]: {"ok": True, "why": ""} for c in CHECK},
    errores=[{"fragment": "Colombya", "type": "spelling", "correction": "Colombia"}],
)
r = grader.grade("My name is Tapi. I am from Colombya. I like music.", "A1", "en", CHECK)
check("la tarea sí está completa", r["task_completed"] is True)
check("el error de ortografía resta, no anula", r["score"] == 100 - grader.PENALTY_PER_ERROR["A1"])

print("\n5) Errores falsos: la segunda pasada los descarta")
respuesta = veredicto(
    {c["id"]: {"ok": True, "why": ""} for c in CHECK},
    errores=[{"fragment": "I'm from Colombia", "type": "grammar", "correction": "I am from Colombia"}],
)


def modelo_descarta(system, user, temperature=0.1):
    if "grammar checker" in system:
        return {"items": [False]}      # no era un error de verdad
    return respuesta


grader._call_ollama = modelo_descarta
r = grader.grade(TEXTO, "A1", "en", CHECK)
check("una 'corrección' que solo cambia la forma no resta puntos", r["score"] == 100)
check("y no aparece en la lista de errores", r["errors"] == [])
grader._call_ollama = modelo

print("\n6) Mensajes de ESCRITURA y de HABLA")
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

print("\n7) El texto se juzga, no se compara con una respuesta esperada")
check("el calificador no recibe ninguna 'respuesta correcta' con la que comparar",
      "expected answer" not in prompt.lower() or "no expected answer" in prompt.lower())
check("B1 tiene tope de errores contados (un modelo pequeño inventa errores en textos largos)",
      grader.MAX_ERRORS_COUNTED.get("B1") == 5)
respuesta = veredicto(
    {c["id"]: {"ok": True, "why": ""} for c in questions_b1.WRITING_TASKS[0]["checklist"]},
    errores=[{"fragment": f"x{i}", "type": "grammar", "correction": f"y{i}"} for i in range(9)],
)
r = grader.grade(" ".join(["word"] * 90), "B1", "en", questions_b1.WRITING_TASKS[0]["checklist"])
check("9 errores en B1 solo descuentan los 5 del tope",
      r["score"] == 100 - grader.PENALTY_PER_ERROR["B1"] * 5)

print(f"\nResultado: {ok_total} OK, {fail_total} con falla")


def test_sin_fallas():
    """pytest: todas las comprobaciones de este archivo pasaron (se ejecutan al importarlo)."""
    assert fail_total == 0, f"{fail_total} comprobaciones con falla (mira la salida con: pytest -s)"


if __name__ == "__main__":
    raise SystemExit(1 if fail_total else 0)
