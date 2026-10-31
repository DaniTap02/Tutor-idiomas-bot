"""Generador de preguntas de lectura con Ollama.

El CÓDIGO elige los temas (solo los permitidos en el nivel), baraja las opciones y decide cuál es la
correcta; el LLM solo redacta UNA pregunta por tema. Antes de mostrar una pregunta pasa por:

  A) FILTROS DE CÓDIGO (deterministas, no dependen del modelo):
     - formato válido (3 opciones distintas y cortas, sin letras A/B/C, un solo espacio en blanco),
     - alfabeto latino, sin adivinanzas, sin imágenes, largo máximo,
     - palabras prohibidas del nivel (inglés),
     - la respuesta correcta NO puede producir palabras repetidas ("short short hair"),
     - temas que necesitan CONTEXTO (comparativos, pronombres, modales, futuro...): la pregunta debe
       traer una frase de contexto antes de la frase con el espacio en blanco,
     - pronombres con género (he/his/her...): el contexto debe mostrar el género (brother, sister...).
  B) VERIFICACIÓN CON EL MODELO (una sola llamada, temperatura 0): se le muestra la ORACIÓN COMPLETA con
     cada opción puesta en el espacio en blanco y responde: qué oraciones son válidas, si el contexto
     alcanza, si el nivel es correcto y si la pregunta mide el tema. Debe haber EXACTAMENTE una oración
     válida y ser la marcada como correcta.

Lo que no pasa se ANULA: nunca se muestra al estudiante (no se le penaliza), se registra en
voided_questions.jsonl (ver exam/void_report.py) y se genera otra.

Configurable por nivel (atributos opcionales del módulo questions_xx; A1 es el valor por defecto):
  LEVEL, FORBIDDEN_RE, MAX_QUESTION_WORDS, MAX_OPTION_WORDS,
  N_PASSAGE, PASSAGE_TARGETS, PASSAGE_MIN_WORDS, PASSAGE_MAX_WORDS.
Validación (todos opcionales; sin ellos no hay reglas de contexto por código, solo la verificación del modelo):
  CONTEXT_TOPICS      prefijos de temas cuya pregunta DEBE traer una frase de contexto
  GENDER_CUE_TOPICS   prefijos de temas con pronombres de género (el contexto debe mostrar el género)
Añadidos para B1 (todos opcionales; sin ellos el comportamiento es el de A1/A2):
  MAX_QUESTION_CHARS, MAX_OPTION_CHARS            límites en caracteres (140 y 40 por defecto)
  PASSAGE_MAX_OPTION_WORDS, PASSAGE_MAX_OPTION_CHARS   límites de opción solo para mini-textos
  GEN_STYLE, OPTION_LEN, GEN_EXAMPLES             texto del prompt de frases cortas
  PASSAGE_SHAPE, PASSAGE_OPTION_LEN, PASSAGE_Q_WORDS,
  PASSAGE_PROMPT_MIN_WORDS, PASSAGE_PROMPT_MAX_WORDS   texto/medidas del prompt de mini-textos
  PASSAGE_QUESTION_TYPES, PASSAGE_ATTITUDE_RE     tipo de pregunta de comprensión elegido por CÓDIGO
  GRAMMAR_TARGETS_ES, VOCAB_TARGETS_ES, FORBIDDEN_ES   temas/prohibidos propios para examen en español
Las preguntas con MINI-TEXTO (nota, cartel, mensaje, email) llevan además la clave "text"
(y "qtype" si el banco define PASSAGE_QUESTION_TYPES).

Es SÍNCRONO (httpx): llámalo con asyncio.to_thread desde el bot.
"""
import json
import logging
import os
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from exam.grader import LANGUAGE_NAME, _call_ollama

log = logging.getLogger(__name__)

ATTEMPTS_PER_TOPIC = 3
MAX_ROUNDS = 5
MISSING_ALLOWED = 2   # si faltan 1 o 2 preguntas, el examen sigue con las que hay
WORKERS = int(os.getenv("EXAM_WORKERS", "1"))  # en paralelo ahogaba la RAM: 1 por defecto
VOID_LOG = os.getenv("EXAM_VOID_LOG", "voided_questions.jsonl")  # registro de preguntas anuladas
_LOG_LOCK = threading.Lock()

# Valor por defecto (A1). "may" no se incluye: es el mes.
DEFAULT_FORBIDDEN_RE = re.compile(r"\b(will|would|could|should|must|might|been|being|going to)\b", re.I)
FORBIDDEN_EN = DEFAULT_FORBIDDEN_RE  # compatibilidad con la versión anterior

BLANK = re.compile(r"_{2,}")
INLINE_OPTIONS = re.compile(r"(?:^|\s)[A-Da-d][\).]\s")   # "A) ...", "B. ..." dentro de la pregunta
LETTER_OPTION = re.compile(r"^[A-Da-d][\).]?$")           # opción que es solo "A", "B)", ...
PICTURE = re.compile(r"\b(picture|image|photo|imagen|foto|dibujo)\b", re.I)
# Cualquier carácter fuera del alfabeto latino (chino, japonés, cirílico, árabe, emojis...) invalida la pregunta.
NON_LATIN = re.compile(r"[^\u0000-\u024F\u2000-\u206F]")
RIDDLE = re.compile(r"\b(what|who) am i\b|\bif i am not\b", re.I)   # adivinanzas / preguntas trampa

# Palabra repetida seguida ("short short"). Se excluyen repeticiones legítimas ("had had", "that that").
REPEATED_WORD = re.compile(r"\b(\w+)\s+\1\b", re.I)
ALLOWED_REPEATS = {"had", "that"}
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Pronombres con género y palabras que dejan claro el género en el contexto (inglés / español).
GENDERED_OPTIONS = {"he", "she", "him", "his", "her", "hers", "él", "ella", "su", "sus"}
GENDER_CUES = re.compile(
    r"\b(he|she|his|her|him|mr|mrs|ms|miss|brother|sister|mother|father|mom|mum|dad|"
    r"uncle|aunt|son|daughter|husband|wife|grandmother|grandfather|grandma|grandpa|"
    r"boy|girl|man|woman|boyfriend|girlfriend|él|ella|hermano|hermana|madre|padre|"
    r"tío|tía|hijo|hija|esposo|esposa|abuelo|abuela|niño|niña|hombre|mujer)\b",
    re.I,
)

LEVEL_DESC = {
    "A1": "absolute beginners",
    "A2": "elementary students",
    "B1": "intermediate students",
    "B2": "upper-intermediate students",
}

# Textos del prompt que cambian por nivel. Los valores por defecto son los de A1/A2 (no tocar).
DEFAULT_GEN_STYLE = "Use only very simple, common words and short sentences."
DEFAULT_OPTION_LEN = "short (1 to 4 words)"
DEFAULT_GEN_EXAMPLES = (
    '{"q": "My sister ___ a doctor.", "correct": "is", "wrong": ["are", "am"]}\n'
    '{"q": "What do you wear on your feet?", "correct": "Shoes", "wrong": ["Gloves", "Hats"]}'
)
DEFAULT_PASSAGE_SHAPE = "2 to 4 short sentences with simple, common words"
DEFAULT_PASSAGE_OPTION_LEN = "short (1 to 6 words)"
DEFAULT_PASSAGE_Q_WORDS = 12
DEFAULT_QUESTION_RULE = (
    "The question asks about ONE clear fact that is written in the text (who, what, when, where, why,\n"
    "  how much). It has no blank and is short (at most {q_words} words)."
)

GEN_PROMPT = """You write multiple-choice questions for a CEFR {level} {language} placement exam ({level_desc}).
Write ONE question about this topic: {topic}

Rules:
- Everything (question and options) is written in {language}.
- Write ONLY with the Latin alphabet. NEVER write Chinese, Japanese or characters of any other script.
- {style}
- The question has AT MOST ONE blank written as ___ (never two blanks).
- Do NOT write the options inside the question. No "A)", "B)", "C)" anywhere. Options are separate.
- Options are {option_len}, with NO letters or numbers in front of them.
- Exactly ONE correct answer and exactly 2 wrong answers.
- Read the FULL sentence with EACH option in the blank. The correct option must give a natural, correct
  sentence (no repeated words such as "short short hair"). Each wrong option must be clearly wrong
  because of its FORM (wrong grammar) or because it CONTRADICTS the context. NEVER use a different word
  that would also fit (another adjective, another modal, another pronoun, another tense).
- Never rely on the student guessing what you had in mind: everything needed to find the answer must be
  written in the question.
- When you test a pronoun or possessive, the context must show WHO it refers to, including gender
  (use words like brother, sister, mother, father, he, she).
{context_rule}- The question must make sense by itself: no pictures, no "the girl", no riddles, no trick or
  philosophical questions (for example NOT "What am I if I am not a teacher?").
- If the topic is specific to English (e.g. a/an), use the closest equivalent in {language}.
- NEVER use or test: {forbidden}.

Examples of the format:
{examples}

Reply ONLY with JSON: {{"q": "...", "correct": "...", "wrong": ["...", "..."]}}"""

# Se inserta solo en los temas de CONTEXT_TOPICS del banco (no afecta a los bancos que no lo definen).
CONTEXT_RULE = (
    "- IMPORTANT: this topic NEEDS CONTEXT. Write a context sentence FIRST (facts such as ages, heights,\n"
    "  prices, names with gender, or the situation) and THEN the sentence with the blank. Only ONE option\n"
    "  may fit that context. Examples with context:\n"
    '  {"q": "My brother is 10 and my sister is 15. My brother is ___ than my sister.", "correct": "younger", "wrong": ["older", "more young"]}\n'
    '  {"q": "My brother Tom lost his book. It is not mine. It is ___.", "correct": "his", "wrong": ["he", "hers"]}\n'
)

DEFAULT_PASSAGE_EXAMPLE = (
    '{"text": "Hi Ana! I am at the supermarket. We need milk and eggs. Please take your keys, '
    'because I am not at home until six.", "q": "What do they need from the supermarket?", '
    '"correct": "Milk and eggs", "wrong": ["Bread and fish", "Rice and apples"]}'
)

PASSAGE_PROMPT = """You write reading comprehension questions for a CEFR {level} {language} placement exam ({level_desc}).
Write ONE short text and ONE question about it. Text type: {topic}

Rules:
- Everything is written in {language}.
- Write ONLY with the Latin alphabet. NEVER write Chinese, Japanese or characters of any other script.
- The text has {min_w} to {max_w} words: {shape}.
  It is ONE paragraph, with no line breaks and no blanks (___).
- {question_rule}
- Options are {option_len}, with NO letters or numbers in front of them.
- Exactly ONE correct answer and exactly 2 wrong answers. The wrong answers must be clearly wrong
  according to the text. NEVER use a different but valid answer.
- No pictures, no riddles, no trick questions.
- NEVER use or test: {forbidden}.

Example of the format:
{example}

Reply ONLY with JSON: {{"text": "...", "q": "...", "correct": "...", "wrong": ["...", "..."]}}"""

VALIDATE_PROMPT = """You are a strict {language} teacher checking a multiple-choice question for a CEFR {level} exam.
The question should test: {topic}
You receive the question and, for each option, the FULL sentence that results (or the option itself).
Answer these points:
1. valid: one value per option, in order. true ONLY if the full sentence is grammatically correct,
   natural and consistent with the context written in the question (a sentence with repeated words,
   or one that contradicts the context, is false). If a text is given, the answer must come from it.
   Several options may be true if the question is ambiguous: be honest.
2. context_enough: false if you would have to guess or assume information that is NOT written in the
   question to find the right answer.
3. level_ok: false if the words or grammar are clearly too difficult for CEFR {level}.
4. tests_topic: false if the question does not really test the topic above.

Reply ONLY with JSON:
{{"valid": [true or false, ...], "context_enough": true or false, "level_ok": true or false, "tests_topic": true or false}}"""


def _is_true(v) -> bool:
    return v is True or str(v).lower() == "true"


def _is_false(v) -> bool:
    return v is False or str(v).lower() == "false"


def _log_void(reason: str, topic: str, level: str, language: str, kind: str, q: str,
              options: list[str], correct: str | None, text: str | None = None,
              qtype: str | None = None) -> None:
    """Registra una pregunta anulada (JSON por línea) para detectar problemas recurrentes."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "level": level, "language": language, "kind": kind, "qtype": qtype, "reason": reason,
        "topic": topic, "text": text, "q": q, "options": options, "correct": correct,
    }
    try:
        with _LOG_LOCK, open(VOID_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # el registro nunca debe romper el examen


def _forbidden_re(banco):
    return getattr(banco, "FORBIDDEN_RE", DEFAULT_FORBIDDEN_RE)


def _filled(q: str, option: str) -> str:
    """La oración completa con la opción puesta en el espacio en blanco."""
    return BLANK.sub(option, q, count=1)


def _topic_in(topic: str, banco, attr: str) -> bool:
    return any(topic.startswith(p) for p in getattr(banco, attr, ()))


def _n_sentences(q: str) -> int:
    return len([s for s in SENTENCE_SPLIT.split(q.strip()) if s])


def _format_problem(q: str, options: list[str], language: str, banco=None, text: str | None = None,
                    correct: str | None = None, topic: str = "") -> str | None:
    """Devuelve None si la pregunta pasa los filtros de código, o el MOTIVO por el que se anula."""
    max_q = getattr(banco, "MAX_QUESTION_WORDS", 14)
    max_o = getattr(banco, "MAX_OPTION_WORDS", 8)
    max_q_chars = getattr(banco, "MAX_QUESTION_CHARS", 140)
    max_o_chars = getattr(banco, "MAX_OPTION_CHARS", 40)
    if text is not None:   # en mini-textos las opciones pueden tener su propio límite (B1: actitud/intención)
        max_o = getattr(banco, "PASSAGE_MAX_OPTION_WORDS", max_o)
        max_o_chars = getattr(banco, "PASSAGE_MAX_OPTION_CHARS", max_o_chars)
    forbidden = _forbidden_re(banco)

    if not q or any(not o for o in options):
        return "format"
    if len(q) > max_q_chars or any(len(o) > max_o_chars for o in options):
        return "too_long"
    if len({o.lower() for o in options}) != 3:
        return "format"
    if len(BLANK.findall(q)) > 1:
        return "format"
    if INLINE_OPTIONS.search(q) or "\n" in q:
        return "format"
    if any(LETTER_OPTION.match(o) for o in options):
        return "format"
    if PICTURE.search(q):
        return "format"
    if NON_LATIN.search(q) or any(NON_LATIN.search(o) for o in options):
        return "non_latin"
    if RIDDLE.search(q):
        return "format"
    if len(q.split()) > max_q or any(len(o.split()) > max_o for o in options):
        return "too_long"

    if text is not None:   # reglas del mini-texto
        n_words = len(text.split())
        if not (getattr(banco, "PASSAGE_MIN_WORDS", 18) <= n_words <= getattr(banco, "PASSAGE_MAX_WORDS", 65)):
            return "passage_length"
        if "\n" in text or BLANK.search(text) or BLANK.search(q):
            return "format"
        if NON_LATIN.search(text):
            return "non_latin"
        if RIDDLE.search(text) or PICTURE.search(text) or INLINE_OPTIONS.search(text):
            return "format"

    if language == "en":
        joined = " ".join([q] + options + ([text] if text else []))
        if forbidden.search(joined):
            return "forbidden_word"

    if text is None and BLANK.search(q):
        # La respuesta correcta no puede dejar palabras repetidas ("I have short short hair")
        if correct is not None:
            for m in REPEATED_WORD.finditer(_filled(q, correct)):
                if m.group(1).lower() not in ALLOWED_REPEATS:
                    return "redundant"
        # Temas que necesitan contexto: una frase de contexto antes de la frase con el espacio en blanco
        if topic and _topic_in(topic, banco, "CONTEXT_TOPICS") and _n_sentences(q) < 2:
            return "no_context"

    # Pronombres con género: el contexto debe mostrar a quién se refiere
    if topic and _topic_in(topic, banco, "GENDER_CUE_TOPICS"):
        if {o.lower() for o in options} & GENDERED_OPTIONS and not GENDER_CUES.search(q):
            return "no_gender_cue"
    return None


def _format_ok(q: str, options: list[str], language: str, banco=None, text: str | None = None,
               correct: str | None = None, topic: str = "") -> bool:
    return _format_problem(q, options, language, banco, text, correct, topic) is None


def _validate(q: str, options: list[str], answer: int, language: str, level: str, topic: str,
              text: str | None = None) -> str | None:
    """Verificación con el modelo (1 llamada, temperatura 0). Devuelve None si pasa, o el motivo."""
    if BLANK.search(q):
        body = "Question: " + q + "\nFull sentence with each option:\n" + "\n".join(
            f"{i}. {_filled(q, o)}" for i, o in enumerate(options)
        )
    else:
        body = "Question: " + q + "\nOptions:\n" + "\n".join(f"{i}. {o}" for i, o in enumerate(options))
    listing = (f"Text: {text}\n\n" if text else "") + body
    try:
        verdict = _call_ollama(
            VALIDATE_PROMPT.format(language=LANGUAGE_NAME[language], level=level, topic=topic),
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
        return "key_invalid"       # la clave guardada no completa la oración correctamente
    if sum(flags) > 1:
        return "ambiguous"         # hay otra opción válida: pregunta ambigua
    if _is_false(verdict.get("context_enough")):
        return "no_context"
    if _is_false(verdict.get("level_ok")):
        return "wrong_level"
    if _is_false(verdict.get("tests_topic")):
        return "off_topic"
    return None


def _forbidden_text(banco, language: str) -> str:
    """Texto de 'prohibido' para el prompt. En español se usa FORBIDDEN_ES si el banco lo define."""
    if language == "es":
        return getattr(banco, "FORBIDDEN_ES", banco.FORBIDDEN)
    return banco.FORBIDDEN


def _question_rule(banco, qtype: str | None) -> str:
    """Regla del prompt sobre qué pregunta hacer del mini-texto. Si el banco define PASSAGE_QUESTION_TYPES,
    el CÓDIGO ya eligió el tipo (idea principal / detalle / actitud) y se lo dice al modelo."""
    q_words = getattr(banco, "PASSAGE_Q_WORDS", DEFAULT_PASSAGE_Q_WORDS)
    types = getattr(banco, "PASSAGE_QUESTION_TYPES", None)
    if types and qtype in types:
        return f"{types[qtype]} It has no blank and is short (at most {q_words} words)."
    return DEFAULT_QUESTION_RULE.format(q_words=q_words)


def _build_system(kind: str, topic: str, banco, language: str, qtype: str | None = None) -> tuple[str, str]:
    """Devuelve (prompt de sistema, mensaje de usuario) para la pregunta."""
    level = getattr(banco, "LEVEL", "A1")
    common = dict(
        level=level,
        level_desc=LEVEL_DESC.get(level, "students"),
        language=LANGUAGE_NAME[language],
        topic=topic,
        forbidden=_forbidden_text(banco, language),
    )
    if kind == "passage":
        min_w = getattr(banco, "PASSAGE_PROMPT_MIN_WORDS", getattr(banco, "PASSAGE_MIN_WORDS", 18))
        # margen: el modelo suele pasarse del máximo
        max_w = getattr(banco, "PASSAGE_PROMPT_MAX_WORDS", getattr(banco, "PASSAGE_MAX_WORDS", 65) - 10)
        system = PASSAGE_PROMPT.format(
            min_w=min_w,
            max_w=max_w,
            shape=getattr(banco, "PASSAGE_SHAPE", DEFAULT_PASSAGE_SHAPE),
            question_rule=_question_rule(banco, qtype),
            example=getattr(banco, "PASSAGE_EXAMPLE", DEFAULT_PASSAGE_EXAMPLE),
            option_len=getattr(banco, "PASSAGE_OPTION_LEN", DEFAULT_PASSAGE_OPTION_LEN),
            **common,
        )
        return system, "Write the text and the question now."
    system = GEN_PROMPT.format(
        style=getattr(banco, "GEN_STYLE", DEFAULT_GEN_STYLE),
        option_len=getattr(banco, "OPTION_LEN", DEFAULT_OPTION_LEN),
        examples=getattr(banco, "GEN_EXAMPLES", DEFAULT_GEN_EXAMPLES),
        context_rule=CONTEXT_RULE if _topic_in(topic, banco, "CONTEXT_TOPICS") else "",
        **common,
    )
    return system, "Write the question now."


def _make_question(kind: str, topic: str, banco, language: str, qtype: str | None = None) -> dict | None:
    """kind: "grammar" | "vocab" (frase corta) o "passage" (mini-texto + pregunta).
    qtype: tipo de pregunta de comprensión elegido por el código (solo mini-textos de bancos que lo definen)."""
    level = getattr(banco, "LEVEL", "A1")
    system, user_msg = _build_system(kind, topic, banco, language, qtype)

    hint = ""
    for _ in range(ATTEMPTS_PER_TOPIC):
        try:
            data = _call_ollama(system, user_msg + hint, temperature=0.6)
            q = str(data["q"]).strip()
            correct = str(data["correct"]).strip()
            wrong = [str(w).strip() for w in data["wrong"]]
            text = str(data["text"]).strip() if kind == "passage" else None
            options = [correct] + wrong
        except Exception as exc:
            # Antes este error se tragaba en silencio (timeout, Ollama caído, JSON mal formado...)
            log.warning("Fallo del modelo al generar [%s] %s: %r", kind, topic[:40], exc)
            _log_void(f"llm_error:{type(exc).__name__}", topic, level, language, kind, "", [], None, None, qtype)
            continue

        def void(reason: str) -> None:
            _log_void(reason, topic, level, language, kind, q, options, correct, text, qtype)

        if len(wrong) != 2:
            void("format")
            continue
        problem = _format_problem(q, options, language, banco, text, correct=correct, topic=topic)
        if problem:
            void(problem)
            if problem == "passage_length" and text:
                lo = getattr(banco, "PASSAGE_PROMPT_MIN_WORDS", getattr(banco, "PASSAGE_MIN_WORDS", 18))
                hi = getattr(banco, "PASSAGE_PROMPT_MAX_WORDS", getattr(banco, "PASSAGE_MAX_WORDS", 65))
                n_w = len(text.split())
                hint = (f" Your previous text had {n_w} words. It MUST have between {lo} and {hi} words: "
                        f"write {'a longer text with more sentences' if n_w < lo else 'a shorter text'}.")
            continue

        random.shuffle(options)  # el código decide la posición de la respuesta
        answer = options.index(correct)
        problem = _validate(q, options, answer, language, level, topic, text)
        if problem:
            void(problem)
            continue

        result = {"q": q, "options": options, "answer": answer, "topic": topic}
        if text:
            result["text"] = text
            if qtype:
                result["qtype"] = qtype
        return result
    return None


def _pick_qtype(banco, topic: str, planned: dict) -> str | None:
    """El CÓDIGO elige el tipo de pregunta de comprensión (idea principal / detalle / actitud),
    repartiendo los tipos y dejando "attitude" solo en textos de opinión, correo o artículo."""
    types = getattr(banco, "PASSAGE_QUESTION_TYPES", None)
    if not types:
        return None
    allowed = list(types)
    attitude_re = getattr(banco, "PASSAGE_ATTITUDE_RE", None)
    if "attitude" in allowed and attitude_re is not None and not attitude_re.search(topic):
        allowed.remove("attitude")
    least = min(planned.get(t, 0) for t in allowed)
    return random.choice([t for t in allowed if planned.get(t, 0) == least])


def generate_reading(banco, language: str) -> list[dict]:
    """Devuelve hasta banco.N_READING preguntas: [{"q", "options", "answer", "topic"[, "text", "qtype"]}, ...].
    Si faltan 1 o 2, sigue con las que hay; solo falla si logra menos."""
    n = banco.N_READING
    need = {
        "grammar": banco.N_GRAMMAR,
        "vocab": banco.N_VOCAB,
        "passage": getattr(banco, "N_PASSAGE", 0),
    }
    # En español se usan los temas propios del banco (si los define); si no, los mismos de inglés.
    es = language == "es"
    pools = {
        "grammar": getattr(banco, "GRAMMAR_TARGETS_ES", banco.GRAMMAR_TARGETS) if es else banco.GRAMMAR_TARGETS,
        "vocab": getattr(banco, "VOCAB_TARGETS_ES", banco.VOCAB_TARGETS) if es else banco.VOCAB_TARGETS,
        "passage": getattr(banco, "PASSAGE_TARGETS", []),
    }
    have = {k: 0 for k in need}
    type_count: dict[str, int] = {}   # tipos de comprensión ya aceptados

    questions: list[dict] = []
    seen: set[str] = set()
    for _ in range(MAX_ROUNDS):
        jobs = []
        planned = dict(type_count)
        for kind, pool in pools.items():
            missing = need[kind] - have[kind]
            if missing > 0 and pool:
                for t in random.sample(pool, min(missing, len(pool))):
                    qtype = _pick_qtype(banco, t, planned) if kind == "passage" else None
                    if qtype:
                        planned[qtype] = planned.get(qtype, 0) + 1
                    jobs.append((kind, t, qtype))
        if not jobs:
            break
        with ThreadPoolExecutor(max_workers=max(1, WORKERS)) as pool:
            results = list(pool.map(lambda j: _make_question(j[0], j[1], banco, language, j[2]), jobs))
        for (kind, _, qtype), r in zip(jobs, results):
            if not r or have[kind] >= need[kind]:
                continue
            key = (r.get("text", "") + " " + r["q"]).lower()
            if key in seen:
                continue
            seen.add(key)
            questions.append(r)
            have[kind] += 1
            if qtype:
                type_count[qtype] = type_count.get(qtype, 0) + 1
        if len(questions) >= n:
            break

    if len(questions) < max(1, n - MISSING_ALLOWED):
        log.error("Solo se pudieron generar %d/%d preguntas. Faltan por tipo: %s",
                  len(questions), n, {k: need[k] - have[k] for k in need if need[k] - have[k] > 0})
        raise RuntimeError(f"Solo se pudieron generar {len(questions)}/{n} preguntas")
    random.shuffle(questions)
    return questions[:n]
