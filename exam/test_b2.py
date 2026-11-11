"""Prueba del examen B2 desde terminal.

  python -m exam.test_b2 filtros      -> filtros y configuración (SIN Ollama, instantáneo)
  python -m exam.test_b2 lectura      -> genera y muestra las preguntas de lectura (con Ollama)
  python -m exam.test_b2 lectura es   -> lo mismo para el examen de español
  python -m exam.test_b2 escritura    -> califica las muestras de escritura (con Ollama)
  python -m exam.test_b2              -> todo lo anterior en inglés

B2 es el nivel más exigente para un modelo de 7B: la generación tarda y anula más preguntas.
"""
import sys
import time

from exam import questions_b2 as b2
from exam.grader import grade
from exam.listening import CONFIG as ESCUCHA_CONFIG
from exam.placement import level_passed, next_step
from exam.question_generator import _forbidden_re, generate_reading

ok_total = 0
fail_total = 0


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK    " if condicion else "  FALLA ") + nombre)
    ok_total += bool(condicion)
    fail_total += not condicion


def probar_filtros():
    print("\n== Filtro de palabras prohibidas B2 (inglés)")
    permitidas = [
        "If I had taken that job, I would be living abroad now.",
        "She can't have forgotten the meeting.",
        "I wish I had more time to study.",
        "By 2030 she will have finished her degree.",
        "I had my car repaired last week.",
        "The bridge is being repaired this month.",
        "I have never been to Paris.",
    ]
    prohibidas = [
        "Never have I seen such a beautiful place.",
        "Not only did he forget, but he also lied.",
        "Hardly had we arrived when it started to rain.",
        "No sooner had she left than the phone rang.",
    ]
    for f in permitidas:
        check(f"permite | {f}", not b2.FORBIDDEN_RE.search(f))
    for f in prohibidas:
        check(f"rechaza | {f}", bool(b2.FORBIDDEN_RE.search(f)))

    print("\n== Configuración")
    check("LEVEL es B2", b2.LEVEL == "B2")
    check("10 preguntas repartidas en gramática, vocabulario y textos",
          b2.N_GRAMMAR + b2.N_VOCAB + b2.N_PASSAGE == b2.N_READING == 10)
    for nombre in ("GRAMMAR_TARGETS", "VOCAB_TARGETS", "PASSAGE_TARGETS",
                   "GRAMMAR_TARGETS_ES", "VOCAB_TARGETS_ES", "PASSAGE_TARGETS_ES"):
        check(f"{nombre} tiene temas", len(getattr(b2, nombre)) >= 6)
    check("los CONTEXT_TOPICS existen en GRAMMAR_TARGETS", all(
        any(t.startswith(p) for t in b2.GRAMMAR_TARGETS) for p in b2.CONTEXT_TOPICS))
    check("los CONTEXT_TOPICS_ES existen en los temas en español", all(
        any(t.startswith(p) for t in b2.GRAMMAR_TARGETS_ES + b2.VOCAB_TARGETS_ES) for p in b2.CONTEXT_TOPICS_ES))
    check("los textos de español admiten preguntas de actitud", sum(
        bool(b2.PASSAGE_ATTITUDE_RE.search(t)) for t in b2.PASSAGE_TARGETS_ES) >= 3)
    check("en español no hay filtro de formas por código", _forbidden_re(b2, "es") is None)
    check("cada tarea de escritura tiene prompt en/es y checklist",
          all(set(t["prompt"]) == {"en", "es"} and t["checklist"] for t in b2.WRITING_TASKS))
    check("habla con prompt en/es y checklist", set(b2.SPEAKING_PROMPT) == {"en", "es"}
          and b2.TASK_CHECKLIST["speaking"])
    check("la escucha B2 está configurada", "B2" in ESCUCHA_CONFIG)
    check("aprobar B2 termina el currículo", next_step("B2", True) == {"action": "done", "level": "B2"})
    check("no aprobar B2 deja en enseñanza de B2", next_step("B2", False) == {"action": "teach", "level": "B2"})
    check("reglas de aprobación iguales a los otros niveles", level_passed(70, 70, 70, 70)
          and not level_passed(90, 55, 90, 90))


def test_filtros_b2():
    """pytest: filtros y configuración de B2 (sin Ollama)."""
    probar_filtros()
    assert fail_total == 0, f"{fail_total} comprobaciones con falla"


def probar_lectura(language: str):
    print(f"\n== Lectura B2 ({language}) con Ollama")
    inicio = time.time()
    preguntas = generate_reading(b2, language)
    for i, p in enumerate(preguntas, 1):
        if p.get("text"):
            print(f"\n{i}. 📄 {p['text']}\n   ❓ {p['q']}")
        else:
            print(f"\n{i}. {p['q']}")
        for j, o in enumerate(p["options"]):
            print(f"   {'✅' if j == p['answer'] else '  '} {o}")
    print(f"\n{len(preguntas)} preguntas en {time.time() - inicio:.0f} s")


MUESTRA = (
    "Dear Mr Lopez, I am writing to complain about the cleaning service I booked for my flat last Friday. "
    "The cleaners arrived two hours late and left the kitchen and the bathroom dirty. Because of this, I had "
    "to cancel a dinner with my family and clean everything myself. I have already called your office twice, "
    "but nobody has answered my emails. I would be grateful if you could send a team again this week at no "
    "cost, or refund the money I paid. I look forward to your reply. Yours sincerely, Ana Torres"
)


def probar_escritura():
    print("\n== Escritura B2 con Ollama")
    tarea = b2.WRITING_TASKS[0]
    r = grade(MUESTRA, "B2", "en", tarea["checklist"])
    print(f"puntaje={r['score']} completada={r['task_completed']} reescribir={r['needs_rewrite']}")
    print(r["feedback"])
    for e in r["errors"]:
        print(f"  • {e.get('fragment')} → {e.get('correction')}")


if __name__ == "__main__":
    args = sys.argv[1:]
    modo = args[0] if args else "todo"
    idioma = args[1] if len(args) > 1 else "en"
    if modo in ("filtros", "todo"):
        probar_filtros()
        print(f"\nResultado: {ok_total} OK, {fail_total} con falla")
    if modo in ("lectura", "todo"):
        probar_lectura(idioma)
    if modo in ("escritura", "todo"):
        probar_escritura()
