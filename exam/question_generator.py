"""Generador de preguntas de lectura con Ollama.

El CÓDIGO elige los temas (solo los permitidos en el nivel), baraja las opciones y decide cuál es la
correcta; el LLM solo redacta UNA pregunta por tema. Cada pregunta pasa por filtros:
  1) formato válido (3 opciones distintas, cortas, sin letras A/B/C, un solo espacio en blanco),
  2) filtro de palabras prohibidas del nivel (inglés),
  3) verificación: el modelo marca qué opciones son válidas y debe haber EXACTAMENTE una,
     la marcada como correcta (descarta preguntas ambiguas).
Lo que no pasa se descarta y se genera de nuevo con otro intento/tema.

Configurable por nivel (atributos opcionales del módulo questions_aX; A1 es el valor por defecto):
  LEVEL, FORBIDDEN_RE, MAX_QUESTION_WORDS, MAX_OPTION_WORDS,
  N_PASSAGE, PASSAGE_TARGETS, PASSAGE_MIN_WORDS, PASSAGE_MAX_WORDS.
Las preguntas con MINI-TEXTO (nota, cartel, mensaje, email) llevan además la clave "text".

Es SÍNCRONO (httpx): llámalo con asyncio.to_thread desde el bot.
"""
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor

from exam.grader import LANGUAGE_NAME, _call_ollama

ATTEMPTS_PER_TOPIC = 3
MAX_ROUNDS = 5
MISSING_ALLOWED = 2   # si faltan 1 o 2 preguntas, el examen sigue con las que hay
WORKERS = int(os.getenv("EXAM_WORKERS", "1"))  # en paralelo ahogaba la RAM: 1 por defecto

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

LEVEL_DESC = {
    "A1": "absolute beginners",
    "A2": "elementary students",
}

GEN_PROMPT = """You write multiple-choice questions for a CEFR {level} {language} placement exam ({level_desc}).
Write ONE question about this topic: {topic}

Rules:
- Everything (question and options) is written in {language}.
- Write ONLY with the Latin alphabet. NEVER write Chinese, Japanese or characters of any other script.
- Use only very simple, common words and short sentences.
- The question has AT MOST ONE blank written as ___ (never two blanks).
- Do NOT write the options inside the question. No "A)", "B)", "C)" anywhere. Options are separate.
- Options are short (1 to 4 words), with NO letters or numbers in front of them.
- Exactly ONE correct answer and exactly 2 wrong answers. Wrong answers must be clearly wrong in
  the sentence (grammatically incorrect or factually false). NEVER use a different but valid answer.
- The question must make sense by itself: no pictures, no "the girl", no riddles, no trick or
  philosophical questions (for example NOT "What am I if I am not a teacher?").
- If the topic is specific to English (e.g. a/an), use the closest equivalent in {language}.
- NEVER use or test: {forbidden}.

Examples of the format:
{{"q": "My sister ___ a doctor.", "correct": "is", "wrong": ["are", "am"]}}
{{"q": "What do you wear on your feet?", "correct": "Shoes", "wrong": ["Gloves", "Hats"]}}

Reply ONLY with JSON: {{"q": "...", "correct": "...", "wrong": ["...", "..."]}}"""

PASSAGE_PROMPT = """You write reading comprehension questions for a CEFR {level} {language} placement exam ({level_desc}).
Write ONE short text and ONE question about it. Text type: {topic}

Rules:
- Everything is written in {language}.
- Write ONLY with the Latin alphabet. NEVER write Chinese, Japanese or characters of any other script.
- The text has {min_w} to {max_w} words: 2 to 4 short sentences with simple, common words.
  It is ONE paragraph, with no line breaks and no blanks (___).
- The question asks about ONE clear fact that is written in the text (who, what, when, where, why,
  how much). It has no blank and is short (at most 12 words).
- Options are short (1 to 6 words), with NO letters or numbers in front of them.
- Exactly ONE correct answer and exactly 2 wrong answers. The wrong answers must be clearly wrong
  according to the text. NEVER use a different but valid answer.
- No pictures, no riddles, no trick questions.
- NEVER use or test: {forbidden}.

Example of the format:
{{"text": "Hi Ana! I am at the supermarket. We need milk and eggs. Please take your keys, because I am not at home until six.", "q": "What do they need from the supermarket?", "correct": "Milk and eggs", "wrong": ["Bread and fish", "Rice and apples"]}}

Reply ONLY with JSON: {{"text": "...", "q": "...", "correct": "...", "wrong": ["...", "..."]}}"""

SOLVE_PROMPT = """You are a strict {language} teacher. For the multiple-choice question below,
decide for EACH option whether it is a correct answer (true) or not (false).
If a text is given, the answer must come from the text.
Several options may be true if the question is ambiguous: be honest.

Reply ONLY with JSON: {{"valid": [true or false, ...]}} with one value per option, in the same order."""


def _is_true(v) -> bool:
    return v is True or str(v).lower() == "true"


def _solves_correctly(q: str, options: list[str], answer: int, language: str, text: str | None = None) -> bool:
    """Pasa solo si EXACTAMENTE una opción es válida y es la marcada como correcta."""
    listing = (f"Text: {text}\n\n" if text else "") + q + "\n" + "\n".join(
        f"{i}. {o}" for i, o in enumerate(options)
    )
    try:
        verdict = _call_ollama(
            SOLVE_PROMPT.format(language=LANGUAGE_NAME[language]), listing, temperature=0.0
        )
        valid = verdict.get("valid", [])
        if len(valid) != len(options):
            return False
        return [_is_true(v) for v in valid] == [i == answer for i in range(len(options))]
    except Exception:
        return False


def _forbidden_re(banco):
    return getattr(banco, "FORBIDDEN_RE", DEFAULT_FORBIDDEN_RE)


def _format_ok(q: str, options: list[str], language: str, banco=None, text: str | None = None) -> bool:
    max_q = getattr(banco, "MAX_QUESTION_WORDS", 14)
    max_o = getattr(banco, "MAX_OPTION_WORDS", 8)
    forbidden = _forbidden_re(banco)

    if not q or len(q) > 140 or any(not o or len(o) > 40 for o in options):
        return False
    if len({o.lower() for o in options}) != 3:
        return False
    if len(BLANK.findall(q)) > 1:
        return False
    if INLINE_OPTIONS.search(q) or "\n" in q:
        return False
    if any(LETTER_OPTION.match(o) for o in options):
        return False
    if PICTURE.search(q):
        return False
    if NON_LATIN.search(q) or any(NON_LATIN.search(o) for o in options):
        return False
    if RIDDLE.search(q):
        return False
    if len(q.split()) > max_q or any(len(o.split()) > max_o for o in options):
        return False

    if text is not None:   # reglas del mini-texto
        n_words = len(text.split())
        if not (getattr(banco, "PASSAGE_MIN_WORDS", 18) <= n_words <= getattr(banco, "PASSAGE_MAX_WORDS", 65)):
            return False
        if "\n" in text or BLANK.search(text) or BLANK.search(q):
            return False
        if NON_LATIN.search(text) or RIDDLE.search(text) or PICTURE.search(text):
            return False
        if INLINE_OPTIONS.search(text):
            return False

    if language == "en":
        joined = " ".join([q] + options + ([text] if text else []))
        if forbidden.search(joined):
            return False
    return True


def _make_question(kind: str, topic: str, banco, language: str) -> dict | None:
    """kind: "grammar" | "vocab" (frase corta) o "passage" (mini-texto + pregunta)."""
    level = getattr(banco, "LEVEL", "A1")
    common = dict(
        level=level,
        level_desc=LEVEL_DESC.get(level, "students"),
        language=LANGUAGE_NAME[language],
        topic=topic,
        forbidden=banco.FORBIDDEN,
    )
    if kind == "passage":
        system = PASSAGE_PROMPT.format(
            min_w=getattr(banco, "PASSAGE_MIN_WORDS", 18),
            max_w=getattr(banco, "PASSAGE_MAX_WORDS", 65) - 10,  # margen: el modelo suele pasarse
            **common,
        )
        user_msg = "Write the text and the question now."
    else:
        system = GEN_PROMPT.format(**common)
        user_msg = "Write the question now."

    for _ in range(ATTEMPTS_PER_TOPIC):
        try:
            data = _call_ollama(system, user_msg, temperature=0.6)
            q = str(data["q"]).strip()
            correct = str(data["correct"]).strip()
            wrong = [str(w).strip() for w in data["wrong"]]
            text = str(data["text"]).strip() if kind == "passage" else None
            options = [correct] + wrong

            if len(wrong) != 2 or not _format_ok(q, options, language, banco, text):
                continue

            random.shuffle(options)  # el código decide la posición de la respuesta
            answer = options.index(correct)
            if not _solves_correctly(q, options, answer, language, text):
                continue
            result = {"q": q, "options": options, "answer": answer, "topic": topic}
            if text:
                result["text"] = text
            return result
        except Exception:
            continue
    return None


def generate_reading(banco, language: str) -> list[dict]:
    """Devuelve hasta banco.N_READING preguntas: [{"q", "options", "answer", "topic"[, "text"]}, ...].
    Si faltan 1 o 2, sigue con las que hay; solo falla si logra menos."""
    n = banco.N_READING
    need = {
        "grammar": banco.N_GRAMMAR,
        "vocab": banco.N_VOCAB,
        "passage": getattr(banco, "N_PASSAGE", 0),
    }
    pools = {
        "grammar": banco.GRAMMAR_TARGETS,
        "vocab": banco.VOCAB_TARGETS,
        "passage": getattr(banco, "PASSAGE_TARGETS", []),
    }
    have = {k: 0 for k in need}

    questions: list[dict] = []
    seen: set[str] = set()
    for _ in range(MAX_ROUNDS):
        jobs = []
        for kind, pool in pools.items():
            missing = need[kind] - have[kind]
            if missing > 0 and pool:
                jobs += [(kind, t) for t in random.sample(pool, min(missing, len(pool)))]
        if not jobs:
            break
        with ThreadPoolExecutor(max_workers=max(1, WORKERS)) as pool:
            results = list(pool.map(lambda j: _make_question(j[0], j[1], banco, language), jobs))
        for (kind, _), r in zip(jobs, results):
            if not r or have[kind] >= need[kind]:
                continue
            key = (r.get("text", "") + " " + r["q"]).lower()
            if key in seen:
                continue
            seen.add(key)
            questions.append(r)
            have[kind] += 1
        if len(questions) >= n:
            break

    if len(questions) < max(1, n - MISSING_ALLOWED):
        raise RuntimeError(f"Solo se pudieron generar {len(questions)}/{n} preguntas")
    random.shuffle(questions)
    return questions[:n]
