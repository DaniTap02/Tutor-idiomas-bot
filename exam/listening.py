"""Parte de ESCUCHA del examen.

Ollama escribe un texto corto que alguien "diría en voz alta" (mensaje de voz, anuncio, relato...) y
UNA pregunta sobre él. El texto se convierte en audio (exam/tts.py) y el estudiante solo lo OYE:
nunca lo ve hasta la revisión final del examen.

Usa los MISMOS filtros y la MISMA verificación que la lectura (question_generator.py), más los
controles propios del audio:

  A) FILTROS DE CÓDIGO (deterministas, no dependen del modelo):
     - los de la lectura: formato, 3 opciones distintas y cortas, alfabeto latino, largo del texto,
       palabras prohibidas del nivel,
     - propios del audio: nada que solo funcione ESCRITO (paréntesis, comillas, enlaces, etiquetas
       de hablante tipo "Tom:", fórmulas de carta como "Dear..."/"Atentamente"),
     - la pregunta no puede hablar de "el texto" ni pedir "leer": el estudiante solo escucha.
  B) VERIFICACIÓN CON EL MODELO (una sola llamada, temperatura 0): debe haber EXACTAMENTE una opción
     válida y ser la marcada como correcta, la respuesta debe DECIRSE en el audio, debe poderse
     captar oyendo una o dos veces, el nivel debe ser correcto y el texto debe sonar a alguien
     hablando de verdad.

Lo que no pasa se ANULA: nunca se le muestra al estudiante (no se le penaliza), se registra en
voided_questions.jsonl con kind="listening" (ver exam/void_report.py) y se genera otro.

La configuración de cada nivel está aquí, en CONFIG, para no tocar los archivos questions_xx.
Variables de entorno (opcionales):
  EXAM_LISTENING_N   cuántos audios por nivel (por defecto el de CONFIG; bájalo a 2 si tu PC sufre)

Es SÍNCRONO (httpx): llámalo con asyncio.to_thread desde el bot.
"""
import logging
import os
import random
import re
from types import SimpleNamespace

from exam.grader import LANGUAGE_NAME, _call_ollama
from exam.question_generator import (
    ATTEMPTS_PER_TOPIC,
    EXIGIR_EVIDENCIA,
    LANG_RULES,
    LEVEL_DESC,
    MAX_ROUNDS,
    _evidencia_ok,
    _format_problem,
    _forbidden_re,
    _forbidden_text,
    _is_false,
    _is_true,
    _log_void,
)

log = logging.getLogger(__name__)

MISSING_ALLOWED = 1   # si de 3 audios solo salen 2, el examen sigue con esos 2

# ---------------------------------------------------------------- Filtros propios del audio

# Signos y fórmulas que solo funcionan por escrito: si aparecen, el texto no suena a alguien hablando.
AUDIO_BANNED = re.compile(
    r"[()\[\]{}*<>|\"“”]"                                   # paréntesis, corchetes, asteriscos, comillas
    r"|https?://|www\.|\S+@\S+|#\w"                          # enlaces, correos, hashtags
    r"|\b(?:dear|yours sincerely|yours faithfully|best regards|kind regards)\b"
    r"|\b(?:estimado|estimada|atentamente|cordialmente|saludos cordiales)\b",
    re.I,
)

# Etiqueta de hablante o encabezado: "Tom:", "Narrator:", "Aviso:" al principio o tras un punto.
SPEAKER_LABEL = re.compile(r"(?:^|[.!?]\s+)[A-ZÁÉÍÓÚÑ][\w'’]{1,20}\s*:")

# La pregunta no puede referirse a un texto escrito ni pedir leer: el estudiante solo oye el audio.
WRITTEN_REF = re.compile(
    r"\baccording to the (?:text|passage|article)\b"
    r"|\bin the (?:text|passage)\b"
    r"|\bthe (?:text|passage) (?:says|mentions|tells)\b"
    r"|\bread the\b|\bas you (?:can )?read\b"
    r"|\bseg[úu]n el (?:texto|art[íi]culo)\b|\ben el texto\b|\bel texto dice\b|\blee el\b",
    re.I,
)


def _audio_problem(text: str, q: str, options: list[str]) -> str | None:
    """Filtros que solo tienen sentido en la escucha. None si pasa, o el motivo de la anulación."""
    if AUDIO_BANNED.search(text) or SPEAKER_LABEL.search(text):
        return "not_speakable"
    if AUDIO_BANNED.search(q) or any(AUDIO_BANNED.search(o) for o in options):
        return "not_speakable"
    if WRITTEN_REF.search(q):
        return "written_ref"
    return None


# ---------------------------------------------------------------- Configuración por nivel

# rate: velocidad de la voz (edge-tts). En A1 va más lenta.
# "style_es" y "targets_es" (opcionales) reemplazan a "style" y "targets" en el examen de español:
# el estilo de inglés nombra gramática inglesa ("going to") que no aplica al español.
CONFIG = {
    "A1": {
        "n": 3,
        "min_words": 15,
        "max_words": 40,
        "q_words": 10,
        "opt_words": 4,
        "rate": "-15%",
        "style": "Use only very simple, common words and short sentences (present simple, basic vocabulary).",
        "style_es": (
            "Use only very simple, common words and short sentences in the PRESENT tense "
            "(ser, estar, tener, hay, gustar, regular verbs). No past, no future, no commands."
        ),
        "targets": [
            "a short voice message from a friend or a family member (where they are and what they need)",
            "a simple announcement in a shop, a school or a bus station (a time, a place or a price)",
            "a person introducing themselves (name, age, family, things they like)",
            "a short message about the weather or about plans for today",
        ],
    },
    "A2": {
        "n": 3,
        "min_words": 25,
        "max_words": 60,
        "q_words": 12,
        "opt_words": 6,
        "rate": "-5%",
        "style": "Use simple, common words and short sentences. Past simple and going to are allowed.",
        "style_es": (
            "Use simple, common words and short sentences. Pretérito indefinido, imperfecto, "
            "ir a + infinitivo, futuro simple and simple commands (gira, siga) are allowed. "
            "No subjunctive, no present perfect (he comido)."
        ),
        "targets_es": [
            "a phone message that changes a plan (a new time or a new place for a meeting)",
            "an announcement at an airport or a bus terminal (a delay, a gate or a platform)",
            "a person telling a friend what they did last weekend or on holiday",
            "a person giving simple directions to get somewhere in a town (gira, sigue recto)",
            "a phone message to a hotel, a restaurant or a doctor to book something",
            "a person telling a friend about a health problem (what hurts and what the doctor said)",
        ],
        "targets": [
            "a phone message that changes a plan (a new time or a new place for a meeting)",
            "an announcement at an airport or a train station (a delay, a gate or a platform)",
            "a person telling a friend what they did last weekend or on holiday",
            "a person giving simple directions or instructions to get somewhere",
            "a phone message to a restaurant, a hotel or a doctor to book something",
            "a simple weather forecast for the weekend",
        ],
    },
    "B1": {
        "n": 3,
        "min_words": 45,
        "max_words": 90,
        "q_words": 16,
        "opt_words": 10,
        "rate": "+0%",
        "style": "Use clear, common everyday vocabulary and natural sentences of moderate length.",
        "style_es": (
            "Use clear, common everyday vocabulary and natural sentences of moderate length. Present "
            "subjunctive for wishes and doubts (espero que, ojalá, no creo que), all past tenses, "
            "conditional simple for advice (yo que tú, deberías) and se impersonal are allowed. "
            "No imperfect subjunctive (si tuviera)."
        ),
        "targets": [
            "a voice message about a problem (what happened, why and what the speaker will do next)",
            "a short radio news item about a local event or a simple news story",
            "a person telling a friend about an experience or a trip (what happened and how they felt)",
            "a person giving advice to a friend about health, study or money",
            "an announcement about a course or an event, with requirements and conditions",
            "a person giving an opinion about a film, a restaurant or a place and explaining why",
        ],
    },
    # Listo para cuando se construya el banco B2 (todavía no está en BANCOS de telegram_flow).
    "B2": {
        "n": 3,
        "min_words": 70,
        "max_words": 130,
        "q_words": 20,
        "opt_words": 12,
        "rate": "+0%",
        "style": (
            "Use natural, varied vocabulary and sentences of moderate to long length. The speaker can "
            "explain something, give an opinion with reasons or tell a short account of events."
        ),
        "targets": [
            "a radio news report about a social, environmental or local issue",
            "a long voice message in which a person explains a problem and proposes a solution",
            "a guide or organiser welcoming a group and explaining the schedule, the rules and the conditions",
            "a person giving an opinion about technology, work or education and supporting it with reasons",
            "a person describing an experience (a trip abroad, a job or a course) and what they learned from it",
            "a recorded message from a company that explains a change in a service, with conditions and options",
        ],
    },
}

LISTEN_PROMPT = """You write listening comprehension questions for a CEFR {level} {language} placement exam ({level_desc}).
Write ONE short spoken text and ONE question about it. The text will be read aloud by a text-to-speech
voice and the student will only HEAR it (never read it). Text type: {topic}

Rules:
- Everything is written in {language}.
- Write ONLY with the Latin alphabet. NEVER write Chinese, Japanese or characters of any other script.
- The text has {min_w} to {max_w} words. {style}
  It is ONE person speaking, written exactly as it is said aloud: plain sentences, no speaker names or
  labels, no stage directions, no parentheses, no quotation marks, no emojis, no line breaks, no blanks
  (___), no greetings or endings from a written letter (no "Dear ...", no "Yours sincerely").
- The question asks about ONE clear fact that is SAID in the text (who, what, when, where, why,
  how much). The answer is said clearly, only once, in plain words: the student must be able to catch
  it listening once or twice. The question has no blank and is short (at most {q_words} words).
- The question NEVER mentions a text and NEVER asks the student to read: talk about "the speaker",
  "the message" or "the announcement".
- Options are short (1 to {opt_words} words), with NO letters or numbers in front of them.
- Exactly ONE correct answer and exactly 2 wrong answers. The wrong answers must be clearly wrong
  according to the text. NEVER use a different but valid answer, and never one that is also said in
  the text as a true fact.
- Never put two similar numbers or two similar names in the text where the student has to tell them
  apart only by one sound.
- No pictures, no riddles, no trick questions.
{lang_rule}- NEVER use or test: {forbidden}.

Example of the format:
{example}

Reply ONLY with JSON: {{"text": "...", "q": "...", "correct": "...", "wrong": ["...", "..."]}}"""

LISTEN_EXAMPLE = {
    "en": (
        '{"text": "Hi Ana, it is Tom. I am at the bus station, but the bus is late. Please wait for me at '
        'the cinema. The film starts at seven thirty.", "q": "Where does Tom want Ana to wait?", '
        '"correct": "At the cinema", "wrong": ["At the bus station", "At home"]}'
    ),
    "es": (
        '{"text": "Hola, Ana, soy Tomás. Estoy en la estación de autobuses, pero el autobús tiene retraso. '
        'Por favor, espérame en el cine. La película empieza a las siete y media.", '
        '"q": "¿Dónde quiere Tomás que lo espere Ana?", "correct": "En el cine", '
        '"wrong": ["En la estación", "En su casa"]}'
    ),
}

LISTEN_VALIDATE_PROMPT = """You are a strict {language} teacher checking a LISTENING question for a CEFR {level} exam.
The student only HEARS the spoken text, once or twice; they never read it. Text type: {topic}
Answer these points:
1. valid: one value per option, in order. true ONLY if the option is a correct answer to the question
   according to the spoken text. Several options may be true if the question is ambiguous: be honest.
2. said_in_audio: false if the correct answer is not clearly SAID in the spoken text (the student would
   have to guess it or work it out).
3. one_listen: false if the answer could not be caught by listening once or twice (for example two
   similar numbers or names, or the key information only hinted at).
4. level_ok: false if the words or the grammar of the spoken text are clearly too difficult for CEFR {level}.
5. speakable: false if the text does not sound like ONE person really speaking (it reads like a written
   letter or a list, or it has labels, headings or stage directions).
6. evidence: COPY the exact words from the spoken text that give the correct answer and rule the other
   options out. Copy them, do not explain them and do not invent them. If the text does not say it,
   answer "" (empty string).

Reply ONLY with JSON:
{{"valid": [true or false, ...], "said_in_audio": true or false, "one_listen": true or false,
  "level_ok": true or false, "speakable": true or false, "evidence": "..."}}"""


def _config(banco, language: str = "en") -> dict:
    cfg = dict(CONFIG.get(getattr(banco, "LEVEL", "A1"), CONFIG["A1"]))
    if language == "es":
        cfg["style"] = cfg.get("style_es", cfg["style"])
        cfg["targets"] = cfg.get("targets_es", cfg["targets"])
    forzado = os.getenv("EXAM_LISTENING_N")
    if forzado and forzado.isdigit() and int(forzado) > 0:
        cfg["n"] = int(forzado)
    return cfg


CHARS_POR_PALABRA = 9   # margen holgado: el límite que manda es el de PALABRAS, no el de caracteres


def _reglas(banco, cfg: dict) -> SimpleNamespace:
    """Banco "falso" con los límites de la escucha, para reutilizar _format_problem de la lectura.

    Los topes en CARACTERES se derivan de los de PALABRAS de CONFIG. Si se copiaran del banco de
    lectura, en B1 (opciones de hasta 10 palabras contra un tope de 40 caracteres) toda opción larga
    se anularía por "too_long" sin que el límite de palabras llegara a aplicarse nunca."""
    max_q_chars = max(getattr(banco, "MAX_QUESTION_CHARS", 140), cfg["q_words"] * CHARS_POR_PALABRA)
    max_o_chars = max(getattr(banco, "MAX_OPTION_CHARS", 40), cfg["opt_words"] * CHARS_POR_PALABRA)
    return SimpleNamespace(
        LEVEL=getattr(banco, "LEVEL", "A1"),
        MAX_QUESTION_WORDS=cfg["q_words"],
        MAX_OPTION_WORDS=cfg["opt_words"],
        MAX_QUESTION_CHARS=max_q_chars,
        MAX_OPTION_CHARS=max_o_chars,
        PASSAGE_MAX_OPTION_WORDS=cfg["opt_words"],
        PASSAGE_MAX_OPTION_CHARS=max_o_chars,
        PASSAGE_MIN_WORDS=cfg["min_words"],
        PASSAGE_MAX_WORDS=cfg["max_words"],
        FORBIDDEN_RE=_forbidden_re(banco, "en"),
        FORBIDDEN_RE_ES=_forbidden_re(banco, "es"),
    )


def _validate(text: str, q: str, options: list[str], answer: int, language: str,
              level: str, topic: str) -> str | None:
    """Verificación con el modelo (1 llamada, temperatura 0). Devuelve None si pasa, o el motivo."""
    listing = (
        f"Spoken text: {text}\n\nQuestion: {q}\nOptions:\n"
        + "\n".join(f"{i}. {o}" for i, o in enumerate(options))
    )
    try:
        verdict = _call_ollama(
            LISTEN_VALIDATE_PROMPT.format(
                language=LANGUAGE_NAME[language], level=level, topic=topic
            ),
            listing,
            temperature=0.0,
        )
    except Exception:
        return "verify_error"

    valid = verdict.get("valid", [])
    if not isinstance(valid, list) or len(valid) != len(options):
        return "verify_error"
    flags = [_is_true(v) for v in valid]
    if not flags[answer]:
        return "key_invalid"        # la clave guardada no responde al audio
    if sum(flags) > 1:
        return "ambiguous"          # hay otra opción válida: pregunta ambigua
    if _is_false(verdict.get("said_in_audio")):
        return "not_said"           # la respuesta no se dice: habría que adivinarla
    if _is_false(verdict.get("one_listen")):
        return "hard_to_catch"      # no se alcanza a captar oyendo una o dos veces
    if _is_false(verdict.get("level_ok")):
        return "wrong_level"
    if _is_false(verdict.get("speakable")):
        return "not_speakable"
    if EXIGIR_EVIDENCIA and not _evidencia_ok(verdict.get("evidence"), q, options, text):
        return "no_evidence"   # no supo señalar qué parte del audio da la respuesta
    return None


def _make_listening(topic: str, banco, language: str) -> dict | None:
    cfg = _config(banco, language)
    level = getattr(banco, "LEVEL", "A1")
    reglas = _reglas(banco, cfg)
    system = LISTEN_PROMPT.format(
        level=level,
        level_desc=LEVEL_DESC.get(level, "students"),
        language=LANGUAGE_NAME[language],
        topic=topic,
        min_w=cfg["min_words"],
        max_w=cfg["max_words"] - 6,  # margen: el modelo suele pasarse del máximo
        style=cfg["style"],
        q_words=cfg["q_words"],
        opt_words=cfg["opt_words"],
        forbidden=_forbidden_text(banco, language),
        lang_rule=LANG_RULES.get(language, ""),
        example=LISTEN_EXAMPLE.get(language, LISTEN_EXAMPLE["en"]),
    )

    hint = ""
    for _ in range(ATTEMPTS_PER_TOPIC):
        try:
            data = _call_ollama(system, "Write the text and the question now." + hint, temperature=0.6)
            text = str(data["text"]).strip()
            q = str(data["q"]).strip()
            correct = str(data["correct"]).strip()
            wrong = [str(w).strip() for w in data["wrong"]]
            options = [correct] + wrong
        except Exception as exc:
            log.warning("Fallo del modelo al generar escucha %s: %r", topic[:40], exc)
            _log_void(f"llm_error:{type(exc).__name__}", topic, level, language, "listening",
                      "", [], None, None)
            continue

        def void(reason: str) -> None:
            _log_void(reason, topic, level, language, "listening", q, options, correct, text)

        if len(wrong) != 2:
            void("format")
            continue

        # Mismos filtros de código que la lectura (con los límites de la escucha)
        problem = _format_problem(q, options, language, reglas, text, correct=correct, topic=topic)
        if problem:
            void(problem)
            if problem == "passage_length":
                n_w = len(text.split())
                lo, hi = cfg["min_words"], cfg["max_words"] - 6
                hint = (f" Your previous text had {n_w} words. It MUST have between {lo} and {hi} words: "
                        f"write {'a longer text with more sentences' if n_w < lo else 'a shorter text'}.")
            continue

        # Filtros propios del audio
        problem = _audio_problem(text, q, options)
        if problem:
            void(problem)
            continue

        random.shuffle(options)  # el código decide la posición de la respuesta
        answer = options.index(correct)
        problem = _validate(text, q, options, answer, language, level, topic)
        if problem:
            void(problem)
            continue

        return {"text": text, "q": q, "options": options, "answer": answer, "topic": topic}
    return None


def generate_listening(banco, language: str) -> list[dict]:
    """Devuelve hasta N audios: [{"text", "q", "options", "answer", "topic"}, ...].
    "text" es lo que se convierte en audio. Si falta 1, sigue con los que hay;
    lanza RuntimeError si logra menos."""
    cfg = _config(banco, language)
    n = cfg["n"]
    questions: list[dict] = []
    seen: set[str] = set()
    usados: set[str] = set()

    for _ in range(MAX_ROUNDS):
        faltan = n - len(questions)
        if faltan <= 0:
            break
        libres = [t for t in cfg["targets"] if t not in usados] or cfg["targets"]
        for topic in random.sample(libres, min(faltan, len(libres))):
            usados.add(topic)
            r = _make_listening(topic, banco, language)
            if not r:
                continue
            key = r["text"].lower()
            if key in seen:
                continue
            seen.add(key)
            questions.append(r)

    if len(questions) < max(1, n - MISSING_ALLOWED):
        log.error("Solo se pudieron generar %d/%d audios de escucha (nivel %s)",
                  len(questions), n, getattr(banco, "LEVEL", "?"))
        raise RuntimeError(f"Solo se pudieron generar {len(questions)}/{n} audios")
    return questions[:n]
