"""Configuración del examen A1. Las preguntas de lectura YA NO están escritas aquí:
las genera Ollama (ver question_generator.py) a partir de los temas permitidos en A1.
Escritura y habla las califica el agente (grader.py)."""

# ---------- Lectura: cuántas preguntas y de qué temas ----------
N_READING = 10
N_GRAMMAR = 6   # de las 10 preguntas, 6 de gramática...
N_VOCAB = 4     # ...y 4 de vocabulario/conversación

# Cada tema lleva entre paréntesis el ALCANCE permitido: así el modelo no se pasa a nivel A2/B1.
GRAMMAR_TARGETS = [
    "Verb To Be (I am, you are, he/she/it is, we/they are): affirmative, negative, questions, short answers",
    "Simple present (habits, routines, facts) with very common verbs only (eat, like, live, work, play, go); negative with don't/doesn't",
    "Present continuous (am/is/are + verb-ing) for actions happening now, with very common verbs (read, eat, watch, run)",
    "Simple past, ONLY was/were and a few very common verbs (went, had, played, watched, worked) with yesterday or last night",
    "Pronouns: I/you/he/she/it/we/they, possessives (my, your, his, her) and me/him/her/us/them",
    "Articles a/an/the (a book, an apple, the sun)",
    "Plurals of common nouns (book/books, box/boxes, child/children, man/men)",
    "Demonstratives this/that/these/those with everyday objects",
    "Very common adjectives (big/small, tall/short, hot/cold) and simple comparatives (bigger than, taller than)",
    "Modal CAN for ability (I can swim, she can't drive)",
    "Prepositions of place (in, on, under, next to) and time (at 7 o'clock, on Monday, in June)",
    "There is / There are with everyday places and objects",
    "Wh- questions (What, Where, Who, When, How) about simple everyday facts",
]

VOCAB_TARGETS = [
    "Introductions: greeting, saying goodbye, name, age, country, nationality",
    "Numbers 1-100 and ordinals up to 10th (first, second, third...)",
    "Personal information: address, phone number, simple jobs (teacher, doctor, student)",
    "Family members and simple descriptions of people (tall, young, friendly)",
    "Days of the week, months, telling the time, daily routines (wake up, have breakfast, go to bed)",
    "The home: rooms (kitchen, bedroom) and everyday objects (table, bed, lamp)",
    "Food and drink: common foods, ordering at a café, likes and dislikes",
    "Clothes and colors",
    "Shopping and prices (how much is it?)",
    "Places in the city (supermarket, school, hospital, park) and simple directions (turn left, go straight)",
    "The weather (sunny, rainy, cold, hot)",
]

# Prohibido en preguntas A1 (lo ve el modelo en el prompt)
FORBIDDEN = (
    "present perfect, future tenses (will, going to), conditionals, passive voice, "
    "reported speech, relative clauses, phrasal verbs, idioms, modal verbs other than 'can', "
    "gerunds/infinitives after verbs except like/love/want, rare or abstract vocabulary"
)

# ---------- Escritura / habla ----------
WRITING_PROMPT = {
    "en": "Write 3 or 4 short sentences introducing yourself: your name, where you are from, and something you like.",
    "es": "Escribe 3 o 4 frases cortas presentándote: tu nombre, de dónde eres y algo que te gusta.",
}

SPEAKING_PROMPT = {
    "en": "Send a voice note (15 to 30 seconds): say your name, where you live, and one thing you like.",
    "es": "Envía una nota de voz (15 a 30 segundos): di tu nombre, dónde vives y algo que te gusta.",
}

# check: lo que ve el modelo (en inglés) · label_es: lo que ve el usuario si le falta.
TASK_CHECKLIST = {
    "writing": [
        {"id": "req1", "check": "the student says their name", "label_es": "tu nombre"},
        {"id": "req2", "check": "the student says where they are from", "label_es": "de dónde eres"},
        {"id": "req3", "check": "the student says something they like", "label_es": "algo que te gusta"},
    ],
    "speaking": [
        {"id": "req1", "check": "the student says their name", "label_es": "tu nombre"},
        {"id": "req2", "check": "the student says where they live", "label_es": "dónde vives"},
        {"id": "req3", "check": "the student says something they like", "label_es": "algo que te gusta"},
    ],
}


def score_reading(questions: list[dict], answers: list[int]) -> float:
    """questions: las preguntas generadas para este examen. answers: índice elegido por pregunta. 0-100."""
    correct = sum(1 for q, a in zip(questions, answers) if q["answer"] == a)
    return 100 * correct / len(questions)
