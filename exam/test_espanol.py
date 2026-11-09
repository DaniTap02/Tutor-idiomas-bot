"""Prueba SIN Ollama ni Telegram del examen en ESPAÑOL:  python -m exam.test_espanol

Comprueba que A1, A2 y B1 en español usan sus propios temas, filtros, ejemplos y checklists
(y no los de inglés), y que el examen en inglés no cambió."""
import os
import tempfile

from exam import grader
from exam import listening as lis
from exam import question_generator as qg
from exam import questions_a1, questions_a2, questions_b1
from exam import telegram_flow as flow

qg.VOID_LOG = os.path.join(tempfile.mkdtemp(), "voided_test.jsonl")
BANCOS = {"A1": questions_a1, "A2": questions_a2, "B1": questions_b1}
ok_total = 0
fail_total = 0


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK   " if condicion else "  FALLA ") + nombre)
    ok_total += bool(condicion)
    fail_total += not condicion


def tema(banco, prefijo):
    return next(t for t in banco.GRAMMAR_TARGETS_ES if t.startswith(prefijo))


print("1) Bancos: temas propios en español y bien enlazados")
for nivel, b in BANCOS.items():
    check(f"{nivel}: hay temas de gramática y vocabulario en español suficientes",
          len(b.GRAMMAR_TARGETS_ES) >= b.N_GRAMMAR and len(b.VOCAB_TARGETS_ES) >= b.N_VOCAB)
    check(f"{nivel}: los temas en español no son los de inglés",
          not set(b.GRAMMAR_TARGETS_ES) & set(b.GRAMMAR_TARGETS))
    sueltos = [p for p in b.CONTEXT_TOPICS_ES if not any(t.startswith(p) for t in b.GRAMMAR_TARGETS_ES + b.VOCAB_TARGETS_ES)]
    check(f"{nivel}: cada prefijo de CONTEXT_TOPICS_ES corresponde a un tema real {sueltos or ''}", not sueltos)
    check(f"{nivel}: GENDER_CUE_TOPICS_ES está dentro de CONTEXT_TOPICS_ES",
          set(getattr(b, "GENDER_CUE_TOPICS_ES", ())) <= set(b.CONTEXT_TOPICS_ES))
    check(f"{nivel}: tiene FORBIDDEN_ES y FORBIDDEN_RE_ES", b.FORBIDDEN_ES and b.FORBIDDEN_RE_ES is not None)
    n_passage = getattr(b, "N_PASSAGE", 0)
    if n_passage:
        check(f"{nivel}: mini-textos en español suficientes", len(b.PASSAGE_TARGETS_ES) >= n_passage)
check("B1: hay mini-textos en español donde cabe la pregunta de actitud",
      any(questions_b1.PASSAGE_ATTITUDE_RE.search(t) for t in questions_b1.PASSAGE_TARGETS_ES))
check("B1: el subjuntivo presente SÍ es tema (temario B1)",
      any("subjuntivo" in t for t in questions_b1.GRAMMAR_TARGETS_ES))
check("B1: 'si tuviera' / 'si hubiera' ya NO son tema (son B2)",
      not any("tuviera" in t or "hubiera" in t for t in questions_b1.GRAMMAR_TARGETS_ES))
check("A2: el imperativo afirmativo SÍ es tema (temario A2)",
      any(t.startswith("Imperativo afirmativo") for t in questions_a2.GRAMMAR_TARGETS_ES))

print("\n2) Filtro por código de cada nivel (lo permitido pasa, lo de otro nivel se anula)")
CASOS = {
    "A1": {
        "pasa": [
            "Mi hermana es médica y vive en Cali.", "Me gustan las manzanas.", "Hay un banco cerca.",
            "Ellos ven la televisión.", "Él mira por la ventana.", "Voy a la escuela.",
            "Quiero un café, por favor.", "En la cafetería venden pan.", "Me levanto a las siete.",
            "Me gusta el vino tinto.", "Ponemos sal en la sopa.",
        ],
        "anula": [
            "Ayer fui al cine.", "De niño jugaba al fútbol.", "He comido arroz.", "Mañana viajaré a Lima.",
            "Voy a comer pizza.", "Me gustaría un té.", "Ojalá llueva.", "Siga recto.",
        ],
    },
    "A2": {
        "pasa": [
            "Ayer fui al cine con mi hermano.", "Cuando era niño, vivía en Cali.", "Voy a viajar el sábado.",
            "Mañana tendré tiempo.", "Gira a la derecha y siga recto.", "Me gustaría reservar una habitación.",
            "¿Podría traer la cuenta?", "Quisiera un café.", "Se lo compré a mi madre.", "Me duele la cabeza.",
            "La farmacia está en la esquina.",
        ],
        "anula": [
            "He estado en Lima.", "Ya había salido.", "Quiero que vengas.", "Ojalá haga sol.",
            "Deberías descansar.", "Si tuviera dinero, viajaría.",
        ],
    },
    "B1": {
        "pasa": [
            "Quiero que vengas mañana.", "Ojalá llueva.", "No creo que venga.", "He estado en Lima dos veces.",
            "Cuando llegamos, el tren ya había salido.", "Yo que tú, compraría un coche.", "Deberías descansar.",
            "Aquí se habla español.", "Quisiera pedir información.", "Los niños juegan fuera de la casa.",
        ],
        "anula": [
            "Si tuviera dinero, compraría un coche.", "Si hubiera estudiado, habría aprobado.",
            "Para el lunes habrá terminado el informe.", "Me pidió que estuviera allí.",
        ],
    },
}
# "fuera" no se filtra a propósito: también es "afuera" (última frase de B1 que pasa).
for nivel, casos in CASOS.items():
    rx = BANCOS[nivel].FORBIDDEN_RE_ES
    for frase in casos["pasa"]:
        check(f"{nivel} pasa:  {frase}", rx.search(frase) is None)
    for frase in casos["anula"]:
        check(f"{nivel} anula: {frase}", rx.search(frase) is not None)

print("\n3) Filtros de código de la lectura con preguntas en español")
A2 = questions_a2


def problema(q, correct, wrong, topic, banco=A2, language="es"):
    return qg._format_problem(q, [correct] + wrong, language, banco, correct=correct, topic=topic)


T_COMP = tema(A2, "Comparativos")
T_OBJ = tema(A2, "Pronombres de objeto")
check("'Mi hermano es ___ que mi hermana' sin contexto -> no_context",
      problema("Mi hermano es ___ que mi hermana.", "mayor", ["menor", "más alto"], T_COMP) == "no_context")
check("con contexto (edades) -> pasa",
      problema("Mi hermano tiene 10 años y mi hermana 15. Mi hermano es ___ que mi hermana.",
               "menor", ["mayor", "más mayor"], T_COMP) is None)
check("pronombre él/ella sin pista de género -> no_gender_cue",
      problema("Ayer vi a Sam. ___ estaba en el parque.", "Él", ["Ella", "Nosotros"], T_OBJ) == "no_gender_cue")
check("con 'mi hermana' -> pasa",
      problema("Ayer vi a mi hermana. ___ estaba en el parque.", "Ella", ["Él", "Nosotros"], T_OBJ) is None)
check("palabra prohibida en A2 español ('he estado') -> forbidden_word",
      problema("Ya ___ en Lima. He estado allí dos veces.", "estuve", ["estoy", "estaré"],
               tema(A2, "Pretérito indefinido")) == "forbidden_word")
check("el filtro de INGLÉS no se aplica al español (A1: 'will' no existe en español)",
      problema("Mi amigo se llama Will.", "Will", ["Ana", "Luis"], "Saludos", questions_a1) is None)
check("el examen en inglés sigue aplicando su filtro ('would' en A2)",
      problema("I would go there. She ___ swim.", "can", ["is", "are"], "Modals can/could", A2, "en") == "forbidden_word")

print("\n4) Prompts de la lectura en español")
sys_es, _ = qg._build_system("grammar", T_COMP, A2, "es")
sys_en, _ = qg._build_system("grammar", A2.GRAMMAR_TARGETS[0], A2, "en")
check("lleva ejemplos en español", "Mi hermana ___ médica." in sys_es)
check("no lleva los ejemplos en inglés", "My sister ___ a doctor." not in sys_es)
check("lleva la regla de contexto en español (tema de contexto)", "Mi hermano tiene 10 años" in sys_es)
check("lleva la regla de español neutro (ustedes, tildes)", "ustedes" in sys_es and "¿ ¡" in sys_es)
check("lleva lo prohibido en español del banco", A2.FORBIDDEN_ES[:40] in sys_es)
check("el prompt en inglés no cambió (sin regla de español)", "ustedes" not in sys_en and "My sister ___ a doctor." in sys_en)
pas_es, _ = qg._build_system("passage", questions_b1.PASSAGE_TARGETS_ES[0], questions_b1, "es", "detail")
check("B1 mini-texto: ejemplo en español (no la carta en inglés)", "María López" in pas_es and "Dear Mr Evans" not in pas_es)
gen_b1, _ = qg._build_system("grammar", tema(questions_b1, "Presente de subjuntivo para deseos"), questions_b1, "es")
check("B1 frase corta: ejemplos B1 en español", "Espero que ___ pronto." in gen_b1)

print("\n5) generate_reading usa los temas en español")
usados = []
original = qg._make_question


def falso(kind, topic, banco, language, qtype=None):
    usados.append((kind, topic))
    return {"q": f"{kind} {topic} {len(usados)}", "options": ["a", "b", "c"], "answer": 0, "topic": topic}


qg._make_question = falso
try:
    for nivel, b in BANCOS.items():
        usados.clear()
        preguntas = qg.generate_reading(b, "es")
        es_temas = set(b.GRAMMAR_TARGETS_ES) | set(b.VOCAB_TARGETS_ES) | set(getattr(b, "PASSAGE_TARGETS_ES", []))
        check(f"{nivel}: {len(preguntas)} preguntas, todas de temas en español",
              len(preguntas) == b.N_READING and all(t in es_temas for _, t in usados))
    usados.clear()
    qg.generate_reading(questions_a2, "en")
    check("A2 en inglés sigue usando los temas en inglés",
          all(t in set(A2.GRAMMAR_TARGETS) | set(A2.VOCAB_TARGETS) | set(A2.PASSAGE_TARGETS) for _, t in usados))
finally:
    qg._make_question = original

print("\n6) Escucha en español")
for nivel, b in BANCOS.items():
    cfg = lis._config(b, "es")
    check(f"{nivel}: estilo de la escucha propio del español", cfg["style"] == lis.CONFIG[nivel]["style_es"])
check("A2: la escucha en español no nombra 'going to'", "going to" not in lis._config(A2, "es")["style"])
check("A2: textos de escucha propios del español", lis._config(A2, "es")["targets"] == lis.CONFIG["A2"]["targets_es"])
check("A2 en inglés: la escucha no cambió", lis._config(A2, "en")["style"] == lis.CONFIG["A2"]["style"])
reglas = lis._reglas(questions_a1, lis._config(questions_a1, "es"))
check("las reglas de la escucha traen el filtro en español",
      qg._format_problem("¿Dónde está Ana?", ["En casa", "En el cine", "En el parque"], "es", reglas,
                         "Hola, soy Ana. Ayer fui al cine con mi hermano y después comimos pizza en el centro.",
                         correct="En el cine") == "forbidden_word")
capturado = {}
original_call = lis._call_ollama


def llamada(system, user, temperature=0.1):
    capturado["system"] = system
    raise RuntimeError("sin Ollama en la prueba")


lis._call_ollama = llamada
try:
    lis._make_listening(lis.CONFIG["A2"]["targets_es"][0], A2, "es")
finally:
    lis._call_ollama = original_call
check("el prompt de la escucha trae el ejemplo en español", "soy Tomás" in capturado.get("system", ""))
check("y no el ejemplo en inglés", "it is Tom" not in capturado.get("system", ""))

print("\n7) Calificador en español")
nota_a1 = grader._lang_note("es", "A1", False)
nota_b1 = grader._lang_note("es", "B1", False)
check("acepta variantes de cualquier país (ustedes/vosotros, carro/coche)", "vosotros" in nota_a1 and "carro" in nota_a1)
check("A1: las tildes que faltan NO se listan como error", "Do NOT list it" in nota_a1)
check("B1: las tildes que faltan sí se pueden listar", "You may list it" in nota_b1)
check("habla (transcripción): las tildes nunca cuentan", "Do NOT list it" in grader._lang_note("es", "B1", True))
check("en inglés no se agrega ninguna nota", grader._lang_note("en", "A1", False) == "")
prompt = grader.SYSTEM_PROMPT.format(
    language="Spanish", level="A1", requirements="", shape="", feedback_language="Spanish",
    lang_note=nota_a1, transcript_note="")
check("la nota queda dentro del prompt del calificador", "vosotros" in prompt)

print("\n8) Checklists del flujo en español")
check("A2 habla en español: el plan se acepta con ir a + infinitivo",
      "ir a + infinitive" in flow._checklist(A2, "speaking", "es")[1]["check"])
check("A2 habla en inglés sigue pidiendo going to", "going to" in flow._checklist(A2, "speaking", "en")[1]["check"])
check("A1 en español usa su checklist (no hay versión _ES: es neutral)",
      flow._checklist(questions_a1, "speaking", "es") == questions_a1.TASK_CHECKLIST["speaking"])
prompt_b1, lista_b1 = flow._tarea_escritura(questions_b1, {"language": "es", "writing_task": "opinion"})
check("B1 escritura en español: consigna en español", "redes sociales" in prompt_b1["es"])
check("B1 escritura: el checklist acepta conectores en español", "porque" in lista_b1[2]["label_es"])

print(f"\nResultado: {ok_total} OK, {fail_total} con falla")
raise SystemExit(1 if fail_total else 0)
