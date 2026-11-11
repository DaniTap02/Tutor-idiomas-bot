"""Prueba SIN Ollama de la validación de preguntas (modelo simulado):  python -m exam.test_validacion
Reproduce los errores detectados en la prueba real de A2 y comprueba que se anulan, se registran
y que las versiones corregidas sí pasan."""
import json
import os
import tempfile

from exam import question_generator as qg
from exam import questions_a2

qg.VOID_LOG = os.path.join(tempfile.mkdtemp(), "voided_test.jsonl")
B = questions_a2
ok_total = 0
fail_total = 0


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK   " if condicion else "  FALLA ") + nombre)
    ok_total += condicion
    fail_total += not condicion


def problema(q, correct, wrong, topic):
    return qg._format_problem(q, [correct] + wrong, "en", B, correct=correct, topic=topic)


T_COMP = next(t for t in B.GRAMMAR_TARGETS if t.startswith("Comparatives"))
T_PRON = next(t for t in B.GRAMMAR_TARGETS if t.startswith("Pronouns"))
T_FUT = next(t for t in B.GRAMMAR_TARGETS if t.startswith("Future:"))
T_MUST = next(t for t in B.GRAMMAR_TARGETS if t.startswith("Must / have to"))

print("1) Filtros de código con los errores reales")
check("'My brother is ___ than my sister' sin contexto -> anulada (no_context)",
      problema("My brother is ___ than my sister.", "Taller", ["Younger", "Shorter"], T_COMP) == "no_context")
check("con contexto (edades) -> pasa",
      problema("My brother is 10 and my sister is 15. My brother is ___ than my sister.",
               "younger", ["older", "more young"], T_COMP) is None)
check("'I have ___ short hair' (respuesta Short) -> anulada (redundant)",
      problema("I have ___ short hair.", "Short", ["Brown", "Long"], "Personal information, family, jobs") == "redundant")
check("'I have ___ hair' -> pasa",
      problema("I have ___ hair.", "short", ["brown", "long"], "Personal information, family, jobs") is None)
check("'This book is ___. It belongs to my friend.' (sin género) -> anulada (no_gender_cue)",
      problema("This book is ___. It belongs to my friend.", "his", ["mine", "hers"], T_PRON) == "no_gender_cue")
check("'It belongs to my brother Tom' -> pasa",
      problema("This book is not mine. It belongs to my brother Tom. It is ___.", "his", ["he", "hers"], T_PRON) is None)
check("'I ___ help you later.' sin contexto -> anulada (no_context)",
      problema("I ___ help you later.", "will", ["can", "must"], T_FUT) == "no_context")
check("con situación -> pasa",
      problema("The phone is ringing. I ___ answer it.", "will", ["am", "was"], T_FUT) is None)
check("'You ___ use a seatbelt in a car.' sin contexto -> anulada (no_context)",
      problema("You ___ use a seatbelt when you are in a car.", "must", ["can", "could"], T_MUST) == "no_context")
check("con la regla -> pasa",
      problema("It is the law. You ___ wear a seatbelt in a car.", "must", ["are", "to"], T_MUST) is None)
check("'had had' y 'that that' no se consideran repetición",
      problema("Yesterday I ___ a cold.", "had had", ["have", "has"], "Simple past") is None)

print("\n2) La verificación con el modelo ve la ORACIÓN COMPLETA")
vistos = []


def modelo(system, user, temperature=0.1):
    vistos.append(user)
    return modelo.respuesta


qg._call_ollama = modelo
q = "My brother is 10 and my sister is 15. My brother is ___ than my sister."
opts = ["younger", "older", "more young"]


def veredicto(**extra):
    """Respuesta del modelo simulado. Por defecto, una pregunta correcta."""
    base = {"valid": [True, False, False], "context_enough": True, "level_ok": True,
            "tests_topic": True, "evidence": "my brother is 10 and my sister is 15"}
    base.update(extra)
    return base


modelo.respuesta = veredicto()
check("pregunta buena -> pasa", qg._validate(q, opts, 0, "en", "A2", T_COMP) is None)
check("el modelo recibió 'My brother is younger than my sister.'", "My brother is younger than my sister." in vistos[-1])
check("el modelo recibió 'more young' dentro de la oración", "My brother is more young than my sister." in vistos[-1])

modelo.respuesta = veredicto(valid=[True, True, True])
check("taller/younger/shorter válidas a la vez -> anulada (ambiguous)",
      qg._validate("Ana is ___ than Beatriz today.", ["aaa", "bbb", "ccc"], 0, "en", "A2", "t") == "ambiguous")
modelo.respuesta = veredicto(valid=[False, True, False])
check("la clave guardada no es válida -> anulada (key_invalid)",
      qg._validate("Ana is ___ than Beatriz today.", ["aaa", "bbb", "ccc"], 0, "en", "A2", "t") == "key_invalid")
modelo.respuesta = veredicto(context_enough=False)
check("contexto insuficiente según el modelo -> anulada (no_context)",
      qg._validate("Ana is ___ than Beatriz today.", ["aaa", "bbb", "ccc"], 0, "en", "A2", "t") == "no_context")
modelo.respuesta = veredicto(level_ok=False)
check("nivel inadecuado -> anulada (wrong_level)",
      qg._validate("Ana is ___ than Beatriz today.", ["aaa", "bbb", "ccc"], 0, "en", "A2", "t") == "wrong_level")
modelo.respuesta = {"valid": [True, False], "context_enough": True}  # mal formada a propósito
check("respuesta mal formada -> anulada (verify_error)",
      qg._validate("Ana is ___ than Beatriz today.", ["aaa", "bbb", "ccc"], 0, "en", "A2", "t") == "verify_error")

print("\n3) La EVIDENCIA: el modelo debe citar qué descarta las otras opciones")
# Es el filtro más fuerte contra preguntas ambiguas: si no hay nada escrito que descarte las demás
# opciones, el modelo no puede citar nada y la pregunta se anula. La cita se comprueba por CÓDIGO.
Q_LIBRO = "It is a ___ book."
OP_LIBRO = ["old", "new", "big"]
Q_HERMANO = "My brother is 10 and my sister is 15. My brother is ___ than my sister."

modelo.respuesta = veredicto(evidence="")
check("'It is a ___ book' (old/new/big) sin evidencia -> anulada (no_evidence)",
      qg._validate(Q_LIBRO, OP_LIBRO, 0, "en", "A1", "adjetivos") == "no_evidence")

modelo.respuesta = veredicto(evidence="the book is from 1902 and the cover is torn")
check("una evidencia INVENTADA (no está en la pregunta) -> anulada (no_evidence)",
      qg._validate(Q_LIBRO, OP_LIBRO, 0, "en", "A1", "adjetivos") == "no_evidence")

modelo.respuesta = veredicto(evidence="my brother is 10 and my sister is 15")
check("con contexto real y evidencia citada -> pasa",
      qg._validate(Q_HERMANO, ["younger", "older", "more young"], 0, "en", "A2", T_COMP) is None)

check("una sola palabra no es evidencia suficiente",
      qg._evidencia_ok("book", Q_LIBRO, OP_LIBRO) is False)
check("una cita reordenada sigue valiendo (el modelo no copia literal)",
      qg._evidencia_ok("sister is 15, brother is 10", Q_HERMANO, ["younger"]) is True)
check("la evidencia puede estar en la opción correcta",
      qg._evidencia_ok("brother younger", Q_HERMANO, ["younger", "older", "more young"]) is True)
check("si el modelo no devuelve el campo -> anulada",
      qg._evidencia_ok(None, Q_HERMANO, ["younger"]) is False)

print("\n4) Pipeline completo: lo defectuoso se anula, se registra y se genera otra")
guion = [
    {"q": "My brother is ___ than my sister.", "correct": "Taller", "wrong": ["Younger", "Shorter"]},
    {"q": "I have ___ short hair.", "correct": "Short", "wrong": ["Brown", "Long"]},
    {"q": "My brother is 10 and my sister is 15. My brother is ___ than my sister.",
     "correct": "younger", "wrong": ["older", "more young"]},
]
estado = {"i": 0}


def modelo2(system, user, temperature=0.1):
    if "checking a multiple-choice question" in system:
        # simula un verificador razonable: solo la opción 'younger' es válida
        return {"valid": [("younger" in line) for line in user.splitlines() if line[:2] in ("0.", "1.", "2.")],
                "context_enough": True, "level_ok": True, "tests_topic": True,
                "evidence": "my brother is 10 and my sister is 15"}
    r = guion[min(estado["i"], len(guion) - 1)]
    estado["i"] += 1
    return r


qg._call_ollama = modelo2
res = qg._make_question("grammar", T_COMP, B, "en")
check("devuelve la pregunta corregida (tras 2 anuladas)", res is not None and "10" in res["q"])
check("la respuesta correcta quedó en la posición indicada", res is not None and res["options"][res["answer"]] == "younger")
filas = [json.loads(l) for l in open(qg.VOID_LOG, encoding="utf-8")]
check("quedaron 2 preguntas anuladas en el registro", len(filas) == 2)
check("motivos registrados: no_context y redundant", sorted(f["reason"] for f in filas) == ["no_context", "redundant"])

print(f"\nResultado: {ok_total} OK, {fail_total} con falla")


def test_sin_fallas():
    """pytest: todas las comprobaciones de este archivo pasaron (se ejecutan al importarlo)."""
    assert fail_total == 0, f"{fail_total} comprobaciones con falla (mira la salida con: pytest -s)"


if __name__ == "__main__":
    raise SystemExit(1 if fail_total else 0)
