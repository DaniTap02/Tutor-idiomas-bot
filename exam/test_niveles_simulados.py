"""Prueba SIN Ollama de TODOS los niveles (A1, A2, B1, B2) en los dos idiomas, con un modelo simulado:

    python -m exam.test_niveles_simulados      (o con pytest)

Un "Ollama falso" responde como respondería un modelo que hace bien su trabajo. Así se comprueba
que cada banco funciona de punta a punta con el generador y el validador REALES (filtros de código,
verificación, evidencia citada): lectura completa, escucha completa, escritura calificada, y que cada
tema de cada lección del tutor produce un ejercicio válido. Lo que NO mide es la calidad del modelo de
verdad: para eso están test_a1, test_a2, test_b1, test_b2 lectura y test_es (con Ollama).
"""
import logging
import math
import os
import re
import tempfile

from exam import grader, listening, question_generator as qg, tutor
from exam.lecciones import LECCIONES
from exam.telegram_flow import BANCOS, _tarea_escritura

logging.disable(logging.CRITICAL)
qg.VOID_LOG = os.path.join(tempfile.mkdtemp(), "voided_simulado.jsonl")

ok_total = 0
fail_total = 0


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK    " if condicion else "  FALLA ") + nombre)
    ok_total += bool(condicion)
    fail_total += not condicion


# ---------------------------------------------------------------- Ollama simulado

FRASE = {
    "en": "Tom lives in a small house near the park with his family.",
    "es": "Tomás vive en una casa pequeña cerca del parque con su familia.",
}
RESPUESTA = {"en": ("Near the park", ["In the city centre", "At the school"]),
             "es": ("Cerca del parque", ["En el centro", "En la escuela"])}
GRAMATICA = {"en": ("Ana works in hospital number {n}. Ana ___ a doctor.", "is", ["are", "am"]),
             "es": ("Ana trabaja en el hospital número {n}. Ana ___ médica.", "es", ["son", "soy"])}
PREGUNTA = {"en": "Where does Tom live?", "es": "¿Dónde vive Tomás?"}
PREGUNTA_AUDIO = {"en": "Where does the speaker say Tom lives?", "es": "¿Dónde dice la persona que vive Tomás?"}

estado = {"n": 0, "correcta": None}


def _idioma(system: str) -> str:
    return "es" if " Spanish " in system or "in Spanish" in system else "en"


def _texto(system: str, n: int, idioma: str) -> str:
    """Texto con un número de palabras dentro del rango que pide el prompt."""
    lo, hi = map(int, re.search(r"The text has (\d+) to (\d+) words", system).groups())
    k = max(1, math.ceil((lo - 2) / 12))
    texto = f"Mensaje {n}." if idioma == "es" else f"Message {n}."
    texto += " " + " ".join([FRASE[idioma]] * k)
    assert len(texto.split()) <= hi, "el simulador no cabe en el rango"
    return texto


def ollama_falso(system: str, user: str, temperature: float = 0.1) -> dict:
    idioma = _idioma(system)
    estado["n"] += 1
    n = estado["n"]
    if system.startswith("You write multiple-choice"):
        q, correcta, malas = GRAMATICA[idioma]
        estado["correcta"] = correcta
        return {"q": q.format(n=n), "correct": correcta, "wrong": malas}
    if system.startswith("You write reading comprehension"):
        correcta, malas = RESPUESTA[idioma]
        estado["correcta"] = correcta
        return {"text": _texto(system, n, idioma), "q": PREGUNTA[idioma], "correct": correcta, "wrong": malas}
    if system.startswith("You write listening comprehension"):
        correcta, malas = RESPUESTA[idioma]
        estado["correcta"] = correcta
        return {"text": _texto(system, n, idioma), "q": PREGUNTA_AUDIO[idioma], "correct": correcta, "wrong": malas}
    if system.startswith("You are an expert"):   # resolver a ciegas: escoge la opción correcta
        opciones = re.findall(r"^(\d+)\. (.*)$", user, re.M)
        correcta = estado["correcta"]
        elegida = next(i for i, o in opciones if o == correcta or f" {correcta} " in f" {o} ")
        return {"reason": "", "answer": int(elegida)}
    if "checking a LISTENING question" in system or "checking a multiple-choice question" in system:
        opciones = re.findall(r"^(\d+)\. (.*)$", user, re.M)
        correcta = estado["correcta"]
        validas = [(o == correcta) or (f" {correcta} " in f" {o} " and "___" not in o and len(o.split()) > 3)
                   for _, o in opciones]
        evidencia = "Ana works in hospital" if idioma == "en" else "Ana trabaja en el hospital"
        if "Text:" in user or "Spoken text:" in user:
            evidencia = "near the park" if idioma == "en" else "cerca del parque"
        return {"valid": validas, "context_enough": True, "level_ok": True, "tests_topic": True,
                "said_in_audio": True, "one_listen": True, "speakable": True, "evidence": evidencia}
    if "proofreader" in system:     # corrector: deja todas las oraciones como están
        return {"items": re.findall(r"^\d+\. (.*)$", user, re.M)}
    if system.startswith("You check if"):   # segunda revisión de requisitos: todos se cumplen
        return {"items": [{"ok": True, "why": ""}] * len(re.findall(r"^\d+\. requirement:", user, re.M))}
    if system.startswith("You are a fair"):
        ids = re.findall(r"^   (\w+): ", system, re.M)
        return {"is_in_language": True, "requirements": {i: {"ok": True, "why": ""} for i in ids},
                "errors": [], "feedback": "Good job!"}
    if system.startswith("You are a friendly"):
        return {"explanation": "We practise this topic with short and simple sentences.",
                "examples": ["Example one.", "Example two."]}
    raise AssertionError("prompt inesperado: " + system[:60])


ESCRITO = {
    "en": ("My name is Laura and I am from Colombia. I like music, books and long walks in the park. "
           "Last year I visited my family and we had a great time together. ") * 3,
    "es": ("Me llamo Laura y soy de Colombia. Me gusta la música, los libros y caminar por el parque. "
           "El año pasado visité a mi familia y lo pasamos muy bien juntos. ") * 3,
}


def _instalar():
    qg._call_ollama = ollama_falso
    listening._call_ollama = ollama_falso
    grader._call_ollama = ollama_falso
    tutor._call_ollama = ollama_falso


# ---------------------------------------------------------------- Casos

def caso_examen_por_nivel():
    print("\n== Examen por nivel e idioma (lectura, escucha y escritura)")
    for level, banco in BANCOS.items():
        for idioma in ("en", "es"):
            preguntas = qg.generate_reading(banco, idioma)
            con_texto = sum(1 for p in preguntas if p.get("text"))
            check(f"{level} {idioma}: lectura con {banco.N_READING} preguntas ({con_texto} con texto)",
                  len(preguntas) == banco.N_READING and con_texto == getattr(banco, "N_PASSAGE", 0))
            audios = listening.generate_listening(banco, idioma)
            check(f"{level} {idioma}: escucha con {listening._config(banco, idioma)['n']} audios",
                  len(audios) == listening._config(banco, idioma)["n"])
            ex = {"language": idioma}
            prompt, checklist = _tarea_escritura(banco, ex)
            r = grader.grade(ESCRITO[idioma], level, idioma, checklist)
            check(f"{level} {idioma}: la escritura se califica (consigna en {idioma})",
                  not r["needs_rewrite"] and r["score"] == 100 and bool(prompt[idioma]))
            r = grader.grade(ESCRITO[idioma], level, idioma, banco.TASK_CHECKLIST["speaking"],
                             True, "Spanish", "speaking")
            check(f"{level} {idioma}: el habla se califica", not r["needs_rewrite"] and r["score"] == 100)


def caso_lecciones():
    print("\n== Cada tema de cada lección genera un ejercicio válido")
    for level, lecciones in LECCIONES.items():
        banco = tutor.banco_de(level)
        for idioma in ("en", "es"):
            malos = []
            for lec in lecciones:
                for kind, tema in tutor.temas_de_leccion(lec, banco, idioma):
                    try:
                        qg.generar_ejercicio(banco, idioma, tema, kind)
                    except RuntimeError:
                        malos.append(f"{lec['id']}: {tema[:40]}")
                explicacion = tutor.generar_explicacion(lec, banco, idioma, level)
                if not explicacion.startswith("We practise"):
                    malos.append(f"{lec['id']}: explicación de respaldo")
            check(f"{level} {idioma}: 5 lecciones sin temas inválidos" + (f" ({malos})" if malos else ""), not malos)


def correr():
    _instalar()
    caso_examen_por_nivel()
    caso_lecciones()
    print(f"\nResultado: {ok_total} OK, {fail_total} con falla")
    return fail_total


def test_todos_los_niveles_con_ollama_simulado():
    """pytest: todos los bancos y lecciones funcionan con el generador y el validador reales."""
    assert correr() == 0, "hay comprobaciones con falla (mira la salida con: pytest -s)"


if __name__ == "__main__":
    raise SystemExit(1 if correr() else 0)
