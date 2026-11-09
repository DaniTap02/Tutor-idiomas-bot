"""Prueba SIN Ollama de los filtros de la ESCUCHA (modelo simulado):

    python -m exam.test_escucha_validacion

Comprueba que se anula lo que no sirve en un audio (fórmulas de carta, etiquetas de hablante,
comillas, preguntas que hablan de «el texto», respuestas que no se dicen, nivel equivocado...),
que queda registrado y que las versiones correctas sí pasan.
"""
import json
import os
import tempfile

from exam import listening as lis
from exam import question_generator as qg
from exam import questions_a1, questions_b1

qg.VOID_LOG = os.path.join(tempfile.mkdtemp(), "voided_escucha_test.jsonl")

B = questions_a1
CFG = lis.CONFIG["A1"]
REGLAS = lis._reglas(B, CFG)

ok_total = 0
fail_total = 0


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK    " if condicion else "  FALLA ") + nombre)
    ok_total += bool(condicion)
    fail_total += not condicion


# Audio válido de A1 (29 palabras, dentro de 15-40)
TEXTO_OK = ("Hi Ana, it is Tom. I am at the bus station, but the bus is late. "
            "Please wait for me at the cinema. The film starts at seven thirty.")
Q_OK = "Where does Tom want Ana to wait?"
OPCIONES_OK = ["At the cinema", "At the bus station", "At home"]


def audio(text=TEXTO_OK, q=Q_OK, options=None):
    return lis._audio_problem(text, q, options or OPCIONES_OK)


def formato(text=TEXTO_OK, q=Q_OK, options=None, correct=None):
    options = options or OPCIONES_OK
    return qg._format_problem(q, options, "en", REGLAS, text, correct=correct or options[0], topic="t")


print("1) Filtros propios del audio (nada que solo funcione escrito)")
check("audio limpio -> pasa", audio() is None)
check("paréntesis en el texto -> not_speakable",
      audio(text=TEXTO_OK + " (laughs)") == "not_speakable")
check("comillas dobles en el texto -> not_speakable",
      audio(text='Hi Ana, Tom said "the bus is late" and I am waiting for you at the cinema today now.')
      == "not_speakable")
check("fórmula de carta (Dear) -> not_speakable",
      audio(text="Dear Ana, I am at the bus station but the bus is late. Please wait for me at "
                 "the cinema today because the film starts at seven thirty.") == "not_speakable")
check("fórmula de carta en español (Atentamente) -> not_speakable",
      audio(text="Hola Ana, estoy en la estación de buses y el bus viene tarde. Espérame en el "
                 "cine a las siete y media. Atentamente, Tomás.") == "not_speakable")
check("etiqueta de hablante 'Tom:' -> not_speakable",
      audio(text="Tom: Hi Ana, I am at the bus station and the bus is late. Please wait for me "
                 "at the cinema this evening.") == "not_speakable")
check("un correo o un enlace -> not_speakable",
      audio(text="Hi Ana, write to tom@mail.com because the bus is late and I am waiting for "
                 "you at the cinema this evening.") == "not_speakable")
check("una hora con dos puntos (7:30) NO se confunde con una etiqueta",
      audio(text="Hi Ana, it is Tom. The bus is late. Please wait for me at the cinema because "
                 "the film starts at 7:30 today.") is None)
check("pregunta que habla de «the text» -> written_ref",
      audio(q="According to the text, where is Tom?") == "written_ref")
check("pregunta que habla de «el texto» en español -> written_ref",
      audio(q="¿Según el texto, dónde está Tomás?") == "written_ref")
check("pregunta que pide leer -> written_ref",
      audio(q="Read the message and say where Tom is.") == "written_ref")

print("\n2) Filtros de código compartidos con la lectura (con los límites de la escucha)")
check("texto muy corto para A1 -> passage_length",
      formato(text="Hi Ana, the bus is late.") == "passage_length")
check("texto muy largo para A1 -> passage_length",
      formato(text=" ".join(["word"] * 60)) == "passage_length")
check("caracteres no latinos -> non_latin",
      formato(text=TEXTO_OK.replace("cinema", "电影院")) == "non_latin")
check("palabra prohibida en A1 (will) -> forbidden_word",
      formato(text="Hi Ana, it is Tom. I am at the bus station, but the bus is late. I will wait "
                   "for you at the cinema at seven thirty.") == "forbidden_word")
check("en B1 'will' NO está prohibido",
      qg._forbidden_re(questions_b1).search("I will wait for you") is None)
check("pregunta demasiado larga para A1 -> too_long",
      formato(q="Where exactly does Tom say that he wants Ana to wait for him this evening?") == "too_long")
check("opción demasiado larga para A1 -> too_long",
      formato(options=["At the cinema near the old bus station", "At the bus station", "At home"],
              correct="At the cinema near the old bus station") == "too_long")
check("dos opciones iguales -> format",
      formato(options=["At home", "At home", "At the cinema"], correct="At home") == "format")

# En B1 la escucha permite opciones de hasta 10 palabras. Si el tope de caracteres se copiara del
# banco de lectura (40), toda opción larga se anularía por "too_long" sin llegar a contar palabras.
R_B1 = lis._reglas(questions_b1, lis.CONFIG["B1"])
OPCION_B1 = "Because the train to the city was delayed again"   # 9 palabras, 47 caracteres
check("el tope de caracteres de B1 sigue al de palabras, no al del banco de lectura",
      R_B1.MAX_OPTION_CHARS >= lis.CONFIG["B1"]["opt_words"] * 5)
check("una opción de 9 palabras en B1 -> pasa",
      qg._format_problem("Why was the speaker late?",
                         [OPCION_B1, "Because he lost his keys", "Because he woke up late"],
                         "en", R_B1, " ".join(["word"] * 60), correct=OPCION_B1, topic="t") is None)
check("una opción de 14 palabras en B1 -> too_long",
      qg._format_problem("Why was the speaker late?",
                         [" ".join(["word"] * 14), "Because he lost his keys", "Because he woke up late"],
                         "en", R_B1, " ".join(["word"] * 60),
                         correct=" ".join(["word"] * 14), topic="t") == "too_long")

print("\n3) Verificación con el modelo (una sola llamada)")
respuesta = {}


def modelo(system, user, temperature=0.1):
    modelo.visto = user
    return respuesta


lis._call_ollama = modelo


def validar(valid=(True, False, False), **extra):
    global respuesta
    respuesta = {"valid": list(valid), "said_in_audio": True, "one_listen": True,
                 "level_ok": True, "speakable": True,
                 "evidence": "please wait for me at the cinema"}
    respuesta.update(extra)
    return lis._validate(TEXTO_OK, Q_OK, OPCIONES_OK, 0, "en", "A1", "t")


check("audio y pregunta buenos -> pasa", validar() is None)
check("el modelo recibió el texto hablado completo", TEXTO_OK in modelo.visto)
check("dos opciones válidas -> ambiguous", validar(valid=(True, True, False)) == "ambiguous")
check("la clave guardada no responde -> key_invalid", validar(valid=(False, True, False)) == "key_invalid")
check("la respuesta no se dice en el audio -> not_said", validar(said_in_audio=False) == "not_said")
check("no se alcanza a captar -> hard_to_catch", validar(one_listen=False) == "hard_to_catch")
check("nivel inadecuado -> wrong_level", validar(level_ok=False) == "wrong_level")
check("no suena a alguien hablando -> not_speakable", validar(speakable=False) == "not_speakable")
check("el audio no dice nada que descarte las otras -> anulada (no_evidence)",
      validar(evidence="") == "no_evidence")
check("una evidencia que no está en el audio -> anulada (no_evidence)",
      validar(evidence="he said the train leaves from platform nine") == "no_evidence")

respuesta = {"valid": [True, False]}
check("respuesta mal formada -> verify_error",
      lis._validate(TEXTO_OK, Q_OK, OPCIONES_OK, 0, "en", "A1", "t") == "verify_error")

print("\n4) Pipeline completo: lo defectuoso se anula, se registra y se genera otro")
guion = [
    # 1) etiqueta de hablante -> se anula por not_speakable
    {"text": "Tom: Hi Ana, the bus is late today. Please wait for me at the cinema because the "
             "film starts at seven thirty tonight.",
     "q": Q_OK, "correct": "At the cinema", "wrong": ["At the bus station", "At home"]},
    # 2) la pregunta habla de «the text» -> se anula por written_ref
    {"text": TEXTO_OK, "q": "According to the text, where is Tom?",
     "correct": "At the cinema", "wrong": ["At the bus station", "At home"]},
    # 3) correcto
    {"text": TEXTO_OK, "q": Q_OK, "correct": "At the cinema",
     "wrong": ["At the bus station", "At home"]},
]
estado = {"i": 0}


def modelo2(system, user, temperature=0.1):
    if "checking a LISTENING question" in system:
        # verificador razonable: solo "At the cinema" es válida
        return {
            "valid": [("At the cinema" in l) for l in user.splitlines() if l[:2] in ("0.", "1.", "2.")],
            "said_in_audio": True, "one_listen": True, "level_ok": True, "speakable": True,
            "evidence": "please wait for me at the cinema",
        }
    r = guion[min(estado["i"], len(guion) - 1)]
    estado["i"] += 1
    return r


lis._call_ollama = modelo2
res = lis._make_listening("a short voice message from a friend", B, "en")
check("devuelve el audio corregido (tras 2 anulados)", res is not None and res["text"] == TEXTO_OK)
check("la pregunta ya no habla de «the text»", res is not None and res["q"] == Q_OK)
check("la respuesta correcta quedó en la posición indicada",
      res is not None and res["options"][res["answer"]] == "At the cinema")

filas = [json.loads(l) for l in open(qg.VOID_LOG, encoding="utf-8") if l.strip()]
check("quedaron 2 anulados en el registro", len(filas) == 2)
check("motivos registrados: not_speakable y written_ref",
      sorted(f["reason"] for f in filas) == ["not_speakable", "written_ref"])
check("quedaron marcados como parte de escucha",
      all(f["kind"] == "listening" for f in filas))

print(f"\nResultado: {ok_total} OK, {fail_total} con falla")
raise SystemExit(1 if fail_total else 0)
