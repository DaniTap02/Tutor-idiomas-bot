"""Configuración del examen B1. Mismo formato que questions_a1.py y questions_a2.py.
Las preguntas de lectura las genera Ollama (question_generator.py) a partir de estos temas.
Escritura y habla las califica el agente (grader.py)."""
import re

LEVEL = "B1"

# ---------- Lectura: cuántas preguntas y de qué temas ----------
N_READING = 10
N_GRAMMAR = 4    # gramática (frase con un espacio en blanco)
N_VOCAB = 3      # vocabulario (frase)
N_PASSAGE = 3    # comprensión con MINI-TEXTO (email, noticia, anuncio, blog, reseña)

# Límites de largo (el generador usa los de A1 si el banco no los define)
MAX_QUESTION_WORDS = 20
MAX_OPTION_WORDS = 10
MAX_QUESTION_CHARS = 170
MAX_OPTION_CHARS = 60
PASSAGE_MIN_WORDS = 45
PASSAGE_MAX_WORDS = 95

# Instrucciones de estilo que ve el modelo (en inglés). Sin estas, el generador usa las de A1/A2.
STYLE_HINT = (
    "Use clear, common everyday vocabulary and natural sentences of moderate length "
    "(a little longer than in A2, but never academic or abstract)."
)
OPTION_WORDS_HINT = 6
PASSAGE_STYLE = (
    "4 to 6 sentences with clear, common vocabulary. The text can tell a short story, give an "
    "opinion or explain a situation."
)
PASSAGE_OPTION_WORDS_HINT = 8
PASSAGE_QUESTION_WORDS_HINT = 16

# Cada tema lleva entre paréntesis el ALCANCE permitido: así el modelo no se pasa a B2.
GRAMMAR_TARGETS = [
    "Present perfect simple (have/has + past participle) with for/since, just/already/yet and ever/never for life experiences",
    "Present perfect vs past simple (I have lived here for three years vs I lived in Cali in 2019), with time expressions",
    "Zero and first conditional (If it rains, we will stay at home; If you heat ice, it melts), with if/unless/when",
    "Second conditional for imaginary situations (If I had more time, I would learn another language)",
    "Past continuous vs past simple with while/when (I was walking home when it started to rain)",
    "Passive voice in present simple and past simple, without naming the agent (The room is cleaned every day; The bridge was built in 1990)",
    "Modal verbs for advice, obligation and possibility: should/shouldn't, must/mustn't, have to, might, may, could",
    "Defining relative clauses with who, which, that and where (The man who lives next door is a doctor)",
    "Verb patterns: -ing after enjoy/avoid/finish/suggest, to + infinitive after want/decide/hope/plan, and preposition + -ing (interested in learning)",
    "Used to + infinitive for past habits, and be/get used to + -ing for things that are familiar",
    "Basic reported speech for statements, questions and requests (She said that she was tired; He asked me to wait)",
    "Linking words: because, so, although, however, but, while, unless, in order to",
    "Comparisons: as ... as, not as ... as, too + adjective, adjective + enough, and the more ... the more",
]

VOCAB_TARGETS = [
    "Work and careers: jobs, job interviews, CV, salary, colleagues, skills, experience",
    "Education and studies: courses, exams, degrees, learning a language, study habits",
    "Travel and transport: delays, booking, tickets, lost luggage, accommodation, problems on a trip",
    "Health and lifestyle: fitness, diet, common illnesses, symptoms, stress, healthy habits",
    "Technology and media: the internet, apps, social networks, news, online safety",
    "Environment and nature: recycling, pollution, climate, energy, animals and protecting nature",
    "Feelings, personality and relationships: friends, family, couples, conflicts and solutions",
    "Shopping and services: complaints, refunds, customer service, banks, post office",
    "Housing and city life: renting, neighbours, public services, noise, traffic",
    "Free time, culture and events: films, music, festivals, books, hobbies, sports",
]

# Tipos de mini-texto para las preguntas de comprensión
PASSAGE_TARGETS = [
    "a short email or message about a problem or a change of plans (what happened, why and what to do next)",
    "a short news item about a local event, an accident or a simple news story",
    "an advertisement or notice for a course, a job or an event, with requirements and conditions",
    "a short personal blog post about a trip or an experience (what happened and how the person felt)",
    "a short text giving advice or tips about health, study, money or technology",
    "a short review of a film, a restaurant or a product with positive and negative opinions",
]

# Prohibido en preguntas B1 (lo ve el modelo en el prompt)
FORBIDDEN = (
    "third conditional and mixed conditionals, past perfect continuous, future perfect, "
    "wish / if only structures, modal verbs of past deduction (must have, might have), "
    "inversion, advanced phrasal verbs and idioms, "
    "rare, academic, technical or highly abstract vocabulary"
)

# Filtro por código (solo inglés). En B1 SÍ se permiten would, should, might, could, must, been, being.
# Se bloquean las estructuras de B2: modales de deducción en pasado, past perfect continuous, wish / if only.
FORBIDDEN_RE = re.compile(
    r"\b(?:would|should|might|must|could) have\b|\b(?:had|having) been\b|\bwish(?:es|ed)?\b|\bif only\b|\bought to\b",
    re.I,
)

# ---------- Escritura / habla ----------
WRITING_PROMPT = {
    "en": (
        "Write an email to a friend (50 to 70 words) about a problem you had recently, for example "
        "while travelling, at work or at university. Say what happened, how you felt, what you did "
        "to solve it, and what you learned or would do differently."
    ),
    "es": (
        "Escribe un correo a un amigo (50 a 70 palabras) sobre un problema que tuviste hace poco, "
        "por ejemplo en un viaje, en el trabajo o en la universidad. Cuenta qué pasó, cómo te "
        "sentiste, qué hiciste para resolverlo y qué aprendiste o qué harías diferente."
    ),
}

SPEAKING_PROMPT = {
    "en": (
        "Send a voice note (45 to 60 seconds): talk about a trip or an experience you really enjoyed. "
        "Say what you did, why you liked it, and what you would like to do next time."
    ),
    "es": (
        "Envía una nota de voz (45 a 60 segundos): habla de un viaje o una experiencia que "
        "disfrutaste mucho. Cuenta qué hiciste, por qué te gustó y qué te gustaría hacer la próxima vez."
    ),
}

# check: lo que ve el modelo (en inglés) · label_es: lo que ve el usuario si le falta.
TASK_CHECKLIST = {
    "writing": [
        {"id": "req1", "check": "the student describes a problem that happened (what happened, and when or where)", "label_es": "qué problema tuviste"},
        {"id": "req2", "check": "the student says how they felt about the problem", "label_es": "cómo te sentiste"},
        {"id": "req3", "check": "the student says what they did to solve the problem, using the past tense", "label_es": "qué hiciste para resolverlo"},
        {"id": "req4", "check": "the student says what they learned, or what they would do differently, or gives some advice", "label_es": "qué aprendiste o qué harías diferente"},
    ],
    "speaking": [
        {"id": "req1", "check": "the student says what they did on a past trip or experience, using the past tense", "label_es": "qué hiciste en esa experiencia"},
        {"id": "req2", "check": "the student gives at least one reason or opinion about why they liked it", "label_es": "por qué te gustó"},
        {"id": "req3", "check": "the student says what they would like to do or plan to do next time, or in the future", "label_es": "qué te gustaría hacer la próxima vez"},
    ],
}


def score_reading(questions: list[dict], answers: list[int]) -> float:
    """questions: las preguntas generadas para este examen. answers: índice elegido por pregunta. 0-100."""
    correct = sum(1 for q, a in zip(questions, answers) if q["answer"] == a)
    return 100 * correct / len(questions)
