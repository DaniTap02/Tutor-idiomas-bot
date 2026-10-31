"""Configuración del examen A2. Mismo formato que questions_a1.py.
Las preguntas de lectura las genera Ollama (question_generator.py) a partir de estos temas.
Escritura y habla las califica el agente (grader.py)."""
import re

LEVEL = "A2"

# ---------- Lectura: cuántas preguntas y de qué temas ----------
N_READING = 10
N_GRAMMAR = 5    # gramática (frase corta con un espacio en blanco)
N_VOCAB = 3      # vocabulario (frase corta)
N_PASSAGE = 2    # comprensión con MINI-TEXTO (nota, cartel, mensaje, email corto)

# Límites de largo (el generador usa los de A1 si el banco no los define)
MAX_QUESTION_WORDS = 16
MAX_OPTION_WORDS = 8
PASSAGE_MIN_WORDS = 18
PASSAGE_MAX_WORDS = 65

# Cada tema lleva entre paréntesis el ALCANCE permitido: así el modelo no se pasa a B1.
GRAMMAR_TARGETS = [
    "Present simple vs present continuous (routines vs happening now), with frequency adverbs always/usually/sometimes/never",
    "Simple past: regular verbs (-ed) and common irregular verbs (go-went, have-had, see-saw, buy-bought, eat-ate), negatives with didn't and questions with Did...?",
    "Future: going to for plans and intentions; basic will for predictions and quick decisions (I'll help you)",
    "Modals can/could for ability, permission and polite requests (Can I...?, Could you...?)",
    "Must / have to / don't have to for simple everyday rules and necessity",
    "Comparatives and superlatives (taller than, more interesting than, the most expensive, the best)",
    "There is / There are with some and any (There aren't any shops; Is there a bank?)",
    "Quantifiers: some/any, much/many, a lot of, a few/a little (countable vs uncountable)",
    "Pronouns: personal, possessive (mine, yours) and object; possessive 's",
    "Prepositions of time and place (in, on, at, under, between, next to) and movement (to, from, across)",
]

VOCAB_TARGETS = [
    "Personal information, family, jobs, physical and personality descriptions",
    "Daily routines and free time: schedules, sports, hobbies, TV, music",
    "Shopping and food: supermarket, ordering at a restaurant, prices, basic food and drink",
    "Places in town, public transport, asking for and giving directions",
    "Travel and holidays: hotels, booking, weather, describing a past trip",
    "Health: basic symptoms, going to the doctor or the pharmacy",
]

# Tipos de mini-texto para las preguntas de comprensión
PASSAGE_TARGETS = [
    "a short note from a family member or friend (a reminder, a plan or simple instructions)",
    "a public sign or notice (shop opening hours, a rule, a train station announcement)",
    "a short text message between two friends (being late, changing a plan, where to meet)",
    "a short simple email about a holiday, a trip or a visit to the doctor or pharmacy",
    "a short advertisement or notice for a restaurant, a hotel or a shop (prices, hours, offers)",
]

# Prohibido en preguntas A2 (lo ve el modelo en el prompt)
FORBIDDEN = (
    "present perfect, conditionals (if...), passive voice, reported speech, relative clauses, "
    "phrasal verbs (except very common ones like get up, turn on), idioms, "
    "modal verbs other than can/could/must/have to/will, "
    "gerunds/infinitives after verbs except like/love/want/enjoy and going to + verb, "
    "rare or abstract vocabulary"
)

# Filtro por código (solo inglés). En A2 SÍ se permiten will, going to, could, must, have to.
# "would like" se permite (restaurantes y compras). "may" no se incluye: es el mes.
FORBIDDEN_RE = re.compile(
    r"\b(would(?! like)|should|might|been|being|ought to|used to)\b", re.I
)

# ---------- Escritura / habla ----------
WRITING_PROMPT = {
    "en": (
        "Write a message to a friend (25 to 35 words) about your last weekend or holiday. "
        "Say where you went, what you did, what you ate or saw, and something you liked."
    ),
    "es": (
        "Escribe un mensaje a un amigo (25 a 35 palabras) sobre tu último fin de semana o vacaciones. "
        "Cuenta a dónde fuiste, qué hiciste, qué comiste o viste y algo que te gustó."
    ),
}

SPEAKING_PROMPT = {
    "en": (
        "Send a voice note (30 to 45 seconds): describe your daily routine and say what you "
        "are going to do this weekend."
    ),
    "es": (
        "Envía una nota de voz (30 a 45 segundos): describe tu rutina diaria y di qué vas a "
        "hacer este fin de semana."
    ),
}

# check: lo que ve el modelo (en inglés) · label_es: lo que ve el usuario si le falta.
TASK_CHECKLIST = {
    "writing": [
        {"id": "req1", "check": "the student says where they went (a place or a trip)", "label_es": "a dónde fuiste"},
        {"id": "req2", "check": "the student says something they did, using the past tense", "label_es": "qué hiciste (en pasado)"},
        {"id": "req3", "check": "the student says something they ate, saw or bought", "label_es": "qué comiste o viste"},
        {"id": "req4", "check": "the student says something they liked", "label_es": "algo que te gustó"},
    ],
    "speaking": [
        {"id": "req1", "check": "the student describes at least two things they do on a normal day", "label_es": "tu rutina diaria"},
        {"id": "req2", "check": "the student says what they are going to do this weekend, using going to or a clear future plan", "label_es": "tus planes del fin de semana"},
        {"id": "req3", "check": "the student says something they like doing in their free time", "label_es": "algo que te gusta hacer en tu tiempo libre"},
    ],
}


def score_reading(questions: list[dict], answers: list[int]) -> float:
    """questions: las preguntas generadas para este examen. answers: índice elegido por pregunta. 0-100."""
    correct = sum(1 for q, a in zip(questions, answers) if q["answer"] == a)
    return 100 * correct / len(questions)
