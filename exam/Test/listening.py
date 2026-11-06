"""Parte de ESCUCHA del examen.

Ollama escribe un texto corto que alguien "diría en voz alta" (mensaje de voz, anuncio, relato...) y UNA
pregunta sobre él. El texto se convierte en audio (exam/tts.py) y el usuario solo lo OYE: nunca lo ve
hasta el final del examen. Usa los mismos filtros y la misma verificación que las preguntas de lectura
(un solo formato válido, palabras prohibidas del nivel y exactamente una respuesta correcta).

La configuración de cada nivel está aquí, en CONFIG, para no tocar los archivos questions_aX / questions_bX.
Es SÍNCRONO (httpx): llámalo con asyncio.to_thread desde el bot.
"""
import random
from types import SimpleNamespace

from exam.grader import LANGUAGE_NAME, _call_ollama
from exam.question_generator import (
    ATTEMPTS_PER_TOPIC,
    LEVEL_DESC,
    MAX_ROUNDS,
    _forbidden_re,
    _format_ok,
    _solves_correctly,
)

MISSING_ALLOWED = 1  # si de 3 audios solo salen 2, el examen sigue con esos 2

# rate: velocidad de la voz (edge-tts). En A1 va más lenta.
CONFIG = {
    "A1": {
        "n": 3,
        "min_words": 15,
        "max_words": 40,
        "q_words": 10,
        "opt_words": 4,
        "rate": "-15%",
        "style": "Use only very simple, common words and short sentences (present simple, basic vocabulary).",
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
        "opt_words": 8,
        "rate": "+0%",
        "style": "Use clear, common everyday vocabulary and natural sentences of moderate length.",
        "targets": [
            "a voice message about a problem (what happened, why and what the speaker will do next)",
            "a short radio news item about a local event or a simple news story",
            "a person telling a friend about an experience or a trip (what happened and how they felt)",
            "a person giving advice to a friend about health, study or money",
            "an announcement about a course or an event, with requirements and conditions",
            "a person giving an opinion about a film, a restaurant or a place and explaining why",
        ],
    },
    "B2": {
        "n": 3,
        "min_words": 70,
        "max_words": 130,
        "q_words": 20,
        "opt_words": 10,
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
  labels, no stage directions, no parentheses, no emojis, no line breaks and no blanks (___).
- The question asks about ONE clear fact that is said in the text (who, what, when, where, why,
  how much). The answer is said clearly, only once. The question has no blank and is short
  (at most {q_words} words).
- Options are short (1 to {opt_words} words), with NO letters or numbers in front of them.
- Exactly ONE correct answer and exactly 2 wrong answers. The wrong answers must be clearly wrong
  according to the text. NEVER use a different but valid answer.
- No pictures, no riddles, no trick questions.
- NEVER use or test: {forbidden}.

Example of the format:
{{"text": "Hi Ana, it is Tom. I am at the bus station, but the bus is late. Please wait for me at the cinema. The film starts at seven thirty.", "q": "Where does Tom want Ana to wait?", "correct": "At the cinema", "wrong": ["At the bus station", "At home"]}}

Reply ONLY with JSON: {{"text": "...", "q": "...", "correct": "...", "wrong": ["...", "..."]}}"""


def _config(banco) -> dict:
    return CONFIG.get(getattr(banco, "LEVEL", "A1"), CONFIG["A1"])


def _make_listening(topic: str, banco, language: str) -> dict | None:
    cfg = _config(banco)
    level = getattr(banco, "LEVEL", "A1")
    system = LISTEN_PROMPT.format(
        level=level,
        level_desc=LEVEL_DESC.get(level, "students"),
        language=LANGUAGE_NAME[language],
        topic=topic,
        min_w=cfg["min_words"],
        max_w=cfg["max_words"] - 6,  # margen: el modelo suele pasarse
        style=cfg["style"],
        q_words=cfg["q_words"],
        opt_words=cfg["opt_words"],
        forbidden=banco.FORBIDDEN,
    )
    # Mismos filtros de formato que la lectura, con los límites de largo de la escucha
    reglas = SimpleNamespace(
        MAX_QUESTION_WORDS=cfg["q_words"],
        MAX_OPTION_WORDS=cfg["opt_words"],
        MAX_QUESTION_CHARS=getattr(banco, "MAX_QUESTION_CHARS", 140),
        MAX_OPTION_CHARS=getattr(banco, "MAX_OPTION_CHARS", 40),
        FORBIDDEN_RE=_forbidden_re(banco),
        PASSAGE_MIN_WORDS=cfg["min_words"],
        PASSAGE_MAX_WORDS=cfg["max_words"],
    )

    for _ in range(ATTEMPTS_PER_TOPIC):
        try:
            data = _call_ollama(system, "Write the text and the question now.", temperature=0.6)
            q = str(data["q"]).strip()
            correct = str(data["correct"]).strip()
            wrong = [str(w).strip() for w in data["wrong"]]
            text = str(data["text"]).strip()
            options = [correct] + wrong

            if len(wrong) != 2 or not _format_ok(q, options, language, reglas, text):
                continue

            random.shuffle(options)  # el código decide la posición de la respuesta
            answer = options.index(correct)
            if not _solves_correctly(q, options, answer, language, text):
                continue
            return {"text": text, "q": q, "options": options, "answer": answer, "topic": topic}
        except Exception:
            continue
    return None


def generate_listening(banco, language: str) -> list[dict]:
    """Devuelve hasta N audios: [{"text", "q", "options", "answer", "topic"}, ...].
    "text" es lo que se convierte en audio. Lanza RuntimeError si salen muy pocos."""
    cfg = _config(banco)
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
        raise RuntimeError(f"Solo se pudieron generar {len(questions)}/{n} audios")
    return questions[:n]
