"""Generador de preguntas de lectura con Ollama.

El CÓDIGO elige los temas (solo los permitidos en A1), baraja las opciones y decide cuál es la
correcta; el LLM solo redacta UNA pregunta por tema. Cada pregunta pasa por filtros:
  1) formato válido (3 opciones distintas, cortas, sin letras A/B/C, un solo espacio en blanco),
  2) filtro de palabras prohibidas (inglés),
  3) verificación: el modelo marca qué opciones son válidas y debe haber EXACTAMENTE una,
     la marcada como correcta (descarta preguntas ambiguas).
Lo que no pasa se descarta y se genera de nuevo con otro intento/tema.

Es SÍNCRONO (httpx): llámalo con asyncio.to_thread desde el bot.
"""
import random
import re
from concurrent.futures import ThreadPoolExecutor

from exam.grader import LANGUAGE_NAME, _call_ollama

ATTEMPTS_PER_TOPIC = 3
MAX_ROUNDS = 3

# Palabras que delatan temas de niveles superiores (solo inglés). "may" no se incluye: es el mes.
FORBIDDEN_EN = re.compile(r"\b(will|would|could|should|must|might|been|being|going to)\b", re.I)

BLANK = re.compile(r"_{2,}")
INLINE_OPTIONS = re.compile(r"(?:^|\s)[A-Da-d][\).]\s")   # "A) ...", "B. ..." dentro de la pregunta
LETTER_OPTION = re.compile(r"^[A-Da-d][\).]?$")           # opción que es solo "A", "B)", ...
PICTURE = re.compile(r"\b(picture|image|photo|imagen|foto|dibujo)\b", re.I)
# Cualquier carácter fuera del alfabeto latino (chino, japonés, cirílico, árabe, emojis...) invalida la pregunta.
NON_LATIN = re.compile(r"[^\u0000-\u024F\u2000-\u206F]")
RIDDLE = re.compile(r"\b(what|who) am i\b|\bif i am not\b", re.I)   # adivinanzas / preguntas trampa
MAX_QUESTION_WORDS = 14
MAX_OPTION_WORDS = 8

GEN_PROMPT = """You write multiple-choice questions for a CEFR A1 {language} placement exam (absolute beginners).
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

SOLVE_PROMPT = """You are a strict {language} teacher. For the multiple-choice question below,
decide for EACH option whether it is a correct answer (true) or not (false).
Several options may be true if the question is ambiguous: be honest.

Reply ONLY with JSON: {{"valid": [true or false, ...]}} with one value per option, in the same order."""


def _is_true(v) -> bool:
    return v is True or str(v).lower() == "true"


def _solves_correctly(q: str, options: list[str], answer: int, language: str) -> bool:
    """Pasa solo si EXACTAMENTE una opción es válida y es la marcada como correcta."""
    listing = q + "\n" + "\n".join(f"{i}. {o}" for i, o in enumerate(options))
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


def _format_ok(q: str, options: list[str], language: str) -> bool:
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
    if len(q.split()) > MAX_QUESTION_WORDS or any(len(o.split()) > MAX_OPTION_WORDS for o in options):
        return False
    if language == "en" and FORBIDDEN_EN.search(" ".join([q] + options)):
        return False
    return True


def _make_question(topic: str, banco, language: str) -> dict | None:
    system = GEN_PROMPT.format(
        language=LANGUAGE_NAME[language], topic=topic, forbidden=banco.FORBIDDEN
    )
    for _ in range(ATTEMPTS_PER_TOPIC):
        try:
            data = _call_ollama(system, "Write the question now.", temperature=0.6)
            q = str(data["q"]).strip()
            correct = str(data["correct"]).strip()
            wrong = [str(w).strip() for w in data["wrong"]]
            options = [correct] + wrong

            if len(wrong) != 2 or not _format_ok(q, options, language):
                continue

            random.shuffle(options)  # el código decide la posición de la respuesta
            answer = options.index(correct)
            if not _solves_correctly(q, options, answer, language):
                continue
            return {"q": q, "options": options, "answer": answer, "topic": topic}
        except Exception:
            continue
    return None


def generate_reading(banco, language: str) -> list[dict]:
    """Devuelve banco.N_READING preguntas: [{"q", "options", "answer", "topic"}, ...]."""
    n = banco.N_READING
    topics = random.sample(banco.GRAMMAR_TARGETS, banco.N_GRAMMAR) + random.sample(
        banco.VOCAB_TARGETS, banco.N_VOCAB
    )
    all_topics = banco.GRAMMAR_TARGETS + banco.VOCAB_TARGETS

    questions: list[dict] = []
    seen: set[str] = set()
    for _ in range(MAX_ROUNDS):
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda t: _make_question(t, banco, language), topics))
        for r in results:
            if r and r["q"].lower() not in seen:
                seen.add(r["q"].lower())
                questions.append(r)
        if len(questions) >= n:
            break
        # Reemplaza los que fallaron con temas nuevos
        topics = random.sample(all_topics, n - len(questions))

    if len(questions) < n:
        raise RuntimeError(f"Solo se pudieron generar {len(questions)}/{n} preguntas")
    random.shuffle(questions)
    return questions[:n]
