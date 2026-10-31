"""Configuración del examen B1. Mismo formato que questions_a2.py (más algunos atributos opcionales).
Las preguntas de lectura las genera Ollama (question_generator.py) a partir de estos temas.
Escritura y habla las califica el agente (grader.py).

Diferencias con A2:
  - FORBIDDEN_RE mucho más permisivo: en B1 SÍ se evalúan would, should, might, could, must, been,
    going to, etc. Solo se prohíben estructuras de B2 o superiores.
  - Mini-textos más largos (55-120 palabras) y el CÓDIGO elige el tipo de pregunta de comprensión
    (idea principal / detalle / actitud o intención del autor).
  - Escritura: el código elige al azar UNA tarea entre varias (WRITING_TASKS), cada una con su checklist.
  - Temas propios para el examen en español (GRAMMAR_TARGETS_ES, VOCAB_TARGETS_ES, FORBIDDEN_ES),
    porque varios temas de B1 no tienen equivalente en español (-ed/-ing, do/make, for/since).
"""
import re

LEVEL = "B1"

# ---------- Lectura: cuántas preguntas y de qué temas ----------
N_READING = 10
N_GRAMMAR = 5    # gramática (frase corta con un espacio en blanco)
N_VOCAB = 2      # vocabulario (frase corta)
N_PASSAGE = 3    # comprensión con MINI-TEXTO (los más lentos de generar: bájalo a 2 si tu PC sufre)

# Límites de largo (frases cortas de gramática/vocabulario)
MAX_QUESTION_WORDS = 20
MAX_OPTION_WORDS = 8
MAX_QUESTION_CHARS = 150
MAX_OPTION_CHARS = 40

# Mini-textos: el filtro acepta 55-120 palabras; al modelo se le piden 60-110 (el margen es porque se pasa)
PASSAGE_MIN_WORDS = 45
PASSAGE_MAX_WORDS = 130
PASSAGE_PROMPT_MIN_WORDS = 65
PASSAGE_PROMPT_MAX_WORDS = 100
# Las opciones de las preguntas de actitud/intención son más largas que las de frases cortas
PASSAGE_MAX_OPTION_WORDS = 12
PASSAGE_MAX_OPTION_CHARS = 80
PASSAGE_Q_WORDS = 15

# Textos de los prompts (por nivel)
GEN_STYLE = "Use common everyday words and clear sentences of intermediate level (not too long)."
OPTION_LEN = "short (1 to 5 words)"
GEN_EXAMPLES = (
    '{"q": "If I ___ more money, I would travel around the world.", "correct": "had", "wrong": ["have", "will have"]}\n'
    '{"q": "She asked me ___ I liked the film.", "correct": "if", "wrong": ["that", "what"]}\n'
    '{"q": "You need a ticket to travel by train. You can buy it at the ___.", '
    '"correct": "ticket office", "wrong": ["pharmacy", "library"]}'
)
PASSAGE_SHAPE = "5 to 8 sentences with common everyday words (intermediate level)"
# Ejemplo largo (~75 palabras): con un ejemplo corto el modelo copia ese largo y el filtro lo anula.
PASSAGE_EXAMPLE = (
    '{"text": "Dear Mr Evans, I am writing about the English course that I started last month. '
    'Unfortunately, the classes are too big, and the teacher does not have time to help every student. '
    'In addition, the room is very hot and noisy because the windows do not close properly. '
    'I enjoy the lessons, but I think the school should offer smaller groups. '
    'I would be grateful if you could tell me about other options. Yours sincerely, Maria Lopez", '
    '"q": "Why is Maria writing the letter?", "correct": "To ask for a better solution", '
    '"wrong": ["To stop the course", "To thank the teacher"]}'
)
PASSAGE_OPTION_LEN = "short phrases (1 to 10 words)"

# Tipos de pregunta de comprensión: los elige el CÓDIGO y se los indica al modelo en el prompt.
PASSAGE_QUESTION_TYPES = {
    "main_idea": (
        "The question asks about the MAIN IDEA or the purpose of the text "
        "(for example: What is the text about? Why is it written?)."
    ),
    "detail": (
        "The question asks about ONE specific detail that is clearly written in the text "
        "(who, what, when, where, how much, how long)."
    ),
    "attitude": (
        "The question asks about the writer's ATTITUDE, opinion or INTENTION "
        "(for example: What does the writer think about ...? Why does the writer write this email?). "
        "The answer must be clear from the text."
    ),
}
# "attitude" solo se usa en textos cuyo tipo (PASSAGE_TARGETS) coincide con esta expresión:
# opinión, correo/carta o artículo (NO en anuncios o carteles).
PASSAGE_ATTITUDE_RE = re.compile(r"article|e-?mail|letter|opinion|blog", re.I)

# Cada tema lleva entre paréntesis el ALCANCE permitido: así el modelo no se pasa a B2.
GRAMMAR_TARGETS = [
    "Past tenses: simple past vs past continuous (I was reading when he called) and past perfect (She had already left when we arrived)",
    "Used to / would for past habits (I used to play football; we would visit our grandparents every summer)",
    "Present perfect simple (for/since, ever/never, already/yet, just) and present perfect continuous (I've been waiting for an hour)",
    "Present simple vs present continuous, and future forms: will, be going to and present continuous for arrangements",
    "Modals of ability, possibility and permission: can, could, may, might, be able to",
    "Modals of obligation and advice: must, have to, don't have to, mustn't, should, shall (Shall we...?)",
    "First and second conditionals (If it rains, I'll stay at home; If I had more money, I would buy a car)",
    "Third conditional (If I had studied, I would have passed the exam)",
    "Passive voice, present simple and past simple only (English is spoken here; The bridge was built in 1990)",
    "Comparatives and superlatives with short and long adjectives, and as...as / less...than",
    "Basic reported speech: statements and simple questions (He said he was tired; She asked if I liked it)",
    "Defining and non-defining relative clauses with who, which, that, where, whose",
    "Verb patterns: verb + -ing or to + infinitive (enjoy doing, decide to, stop doing)",
    "Adjectives ending in -ed and -ing (interested/interesting, bored/boring)",
    "Linking words: however, although, even though, because, so, in addition",
]

VOCAB_TARGETS = [
    "Travel and holidays: booking hotels, buying tickets, directions, transport, problems while travelling",
    "Work and studies: jobs, simple interviews, work routines, study plans",
    "Everyday life and free time: sports, hobbies, entertainment, cooking and restaurants",
    "Health and wellbeing: healthy lifestyle, parts of the body, basic symptoms at the doctor",
    "Environment and technology: nature, pollution, recycling, social media, everyday electronic devices",
    "Common word pairs: do/make, say/tell, for/since, both/either/neither",
]

# Tipos de mini-texto para las preguntas de comprensión
PASSAGE_TARGETS = [
    "a short newspaper-style article about a local event, a trip or a simple discovery",
    "a public announcement or advertisement for an event, a course, a job or a service",
    "an informal email from a friend who tells some news and asks for something",
    "a formal or semi-formal email or letter (a complaint, a request for information, a booking)",
    "a short blog post or opinion text where the writer gives a personal opinion about a topic (technology, studying, a place)",
]

# ---------- Temas para el examen en ESPAÑOL ----------
# Varios temas de B1 no existen en español (adjetivos -ed/-ing, do/make, for/since), así que se adaptan.
GRAMMAR_TARGETS_ES = [
    "Pretérito indefinido vs pretérito imperfecto (Comía cuando llamaron) y pluscuamperfecto (Ya había salido cuando llegamos)",
    "Imperfecto para hábitos del pasado y soler + infinitivo (Antes jugaba al fútbol; Solíamos visitar a los abuelos cada verano)",
    "Pretérito perfecto (he vivido; ya/todavía no, nunca, alguna vez, hace/desde) y llevar/estar + gerundio (Llevo una hora esperando)",
    "Presente vs estar + gerundio, y formas de futuro: futuro simple, ir a + infinitivo y presente con valor de futuro",
    "Habilidad, posibilidad y permiso: poder, saber + infinitivo, ¿Puedo...?, se puede, estar permitido",
    "Obligación y consejo: tener que, hay que, deber, no hace falta, deberías, ¿Vamos a...? / ¿Por qué no...?",
    "Condicional con si: Si llueve, me quedaré en casa; Si tuviera más dinero, compraría un coche",
    "Condicional perfecto con si (Si hubiera estudiado, habría aprobado el examen)",
    "Voz pasiva con ser + participio en presente y pasado simple, y la pasiva refleja (Aquí se habla español; El puente fue construido en 1990)",
    "Comparativos y superlativos (más/menos... que, tan... como, el más..., mejor/peor)",
    "Estilo indirecto básico: afirmaciones y preguntas sencillas (Dijo que estaba cansado; Preguntó si me gustaba)",
    "Oraciones de relativo especificativas y explicativas con que, quien, donde, cuyo, el cual",
    "Verbos + infinitivo o gerundio y perífrasis comunes (decidir + infinitivo, dejar de, acabar de, seguir + gerundio, empezar a)",
    "Ser y estar con adjetivos que cambian de sentido (es aburrido / está aburrido; es listo / está listo)",
    "Conectores: sin embargo, aunque, porque, así que, además, a pesar de que",
]

VOCAB_TARGETS_ES = [
    "Viajes y vacaciones: reservar hoteles, comprar pasajes, direcciones, transporte, problemas durante un viaje",
    "Trabajo y estudios: profesiones, entrevistas sencillas, rutinas laborales, planes de estudio",
    "Vida cotidiana y tiempo libre: deportes, aficiones, entretenimiento, cocina y restaurantes",
    "Salud y bienestar: estilo de vida saludable, partes del cuerpo, síntomas básicos en el médico",
    "Medio ambiente y tecnología: naturaleza, contaminación, reciclaje, redes sociales, aparatos electrónicos de uso diario",
    "Pares de palabras comunes: por/para, decir/hablar/contar, desde/hace/durante, tan/tanto",
]

# Prohibido en preguntas B1 (lo ve el modelo en el prompt)
FORBIDDEN = (
    "passive voice in continuous, perfect or future forms, mixed conditionals, wish / if only, "
    "future perfect and future continuous, past perfect continuous, inversion, cleft sentences, "
    "causative have/get something done, modal perfects (should have, must have, might have, could have; "
    "'would have' ONLY in the third conditional), uncommon phrasal verbs, idioms, "
    "rare, technical or very abstract vocabulary"
)

FORBIDDEN_ES = (
    "present subjunctive after verbs of wish, doubt or emotion (espero que..., quiero que...), "
    "commands and imperative forms, future perfect, passive voice in compound tenses, "
    "complex reported speech with several tense changes, idioms and proverbs, "
    "regional slang, rare, technical or very abstract vocabulary"
)

# Filtro por código (solo inglés). Solo se prohíben estructuras de B2 o superiores.
# Se permiten would, should, might, could, must, been, being (gerundio), going to, used to,
# "would have" (tercer condicional), "wishes" (despedidas de correo) y "will have to".
# Los regex NO detectan todo (p. ej. condicionales mixtos, futuro continuo, voz pasiva perfecta):
# eso solo lo controla el texto de FORBIDDEN en el prompt.
_ING_ADJ_OR_NOUN = (
    "interesting|boring|exciting|amazing|surprising|tiring|relaxing|annoying|disappointing|"
    "frightening|confusing|embarrassing|shocking|terrifying|fascinating|nothing|something|"
    "anything|everything|morning|evening|building|king|thing|string|ring|spring"
)
_PARTICIPLES = (
    "been|[a-z]+ed|done|gone|seen|made|taken|eaten|written|left|come|given|known|got|had|"
    "become|begun|found|told|read|met|spoken|heard|bought|paid|run|won"
)
FORBIDDEN_RE = re.compile(
    r"\b(?:"
    rf"had been (?!(?:{_ING_ADJ_OR_NOUN})\b)\w{{3,}}ing"                 # past perfect continuous
    r"|(?:is|are|was|were) being"                                          # passive continuous
    rf"|(?:will|['’]ll) have (?:{_PARTICIPLES})"                           # future perfect (NO "will have to")
    r"|would rather"
    r"|if only"
    r"|ought to"
    r"|wish(?:ed)?\s+(?:I\b|(?:he|she|it|we|they|you)\s+(?:were|was|had|hadn['’]t|could|would|knew|did|didn['’]t))"
    r"|(?:should|shouldn['’]t|must|might|could|couldn['’]t|may|can['’]t)(?:\s+have|['’]ve)"   # modal perfects
    r"|(?:hardly|scarcely|no sooner|not only|only when)\s+(?:have|has|had|did|do|does|was|were|will|would|can|could|is|are)"  # inversion
    r"|(?:had|have|get|got|having|getting)\s+(?:my|your|his|her|our|their)\s+\w+\s+(?:cut|fixed|repaired|painted|cleaned|checked|serviced|delivered|done|\w{3,}ed)"  # causative
    r")\b",
    re.I,
)

# ---------- Escritura ----------
# El CÓDIGO elige al azar UNA tarea por examen. Cada tarea tiene su prompt (en/es) y su checklist.
# check: lo que ve el modelo (en inglés) · label_es: lo que ve el usuario si le falta.
WRITING_TASKS = [
    {
        "id": "email",
        "prompt": {
            "en": (
                "A friend from another country will visit your city next month. Write an informal email "
                "to your friend (80 to 100 words): start with a greeting, welcome your friend, suggest two "
                "things to do, give advice about what to bring, ask your friend one question, and finish "
                "with a friendly goodbye."
            ),
            "es": (
                "Un amigo de otro país visitará tu ciudad el próximo mes. Escríbele un correo informal "
                "(80 a 100 palabras): empieza con un saludo, dale la bienvenida, sugiérele dos cosas para "
                "hacer, aconséjale qué llevar, hazle una pregunta y termina con una despedida amable."
            ),
        },
        "checklist": [
            {"id": "req1", "check": "the student welcomes the friend or says they are happy about the visit", "label_es": "darle la bienvenida a tu amigo"},
            {"id": "req2", "check": "the student suggests at least two things to do or places to visit", "label_es": "sugerir dos cosas para hacer"},
            {"id": "req3", "check": "the student gives advice about what to bring or wear", "label_es": "aconsejar qué llevar"},
            {"id": "req4", "check": "the student asks the friend at least one question", "label_es": "hacerle una pregunta a tu amigo"},
        ],
    },
    {
        "id": "story",
        "prompt": {
            "en": (
                "Write a short story (80 to 100 words) that starts with this sentence: \"It was a rainy "
                "Saturday and I was at home when the phone rang.\" Tell what happened first, then, and "
                "finally. Use the past."
            ),
            "es": (
                "Escribe un relato corto (80 a 100 palabras) que empiece con esta frase: \"Era un sábado "
                "lluvioso y yo estaba en casa cuando sonó el teléfono.\" Cuenta qué pasó primero, después "
                "y al final. Usa el pasado."
            ),
        },
        "checklist": [
            {"id": "req1", "check": "the story begins with or clearly continues from the given first sentence (a rainy Saturday, the student at home, the phone ringing)", "label_es": "continuar la frase inicial"},
            {"id": "req2", "check": "the student tells at least three events in a clear order (first, then, finally or similar)", "label_es": "contar qué pasó primero, después y al final"},
            {"id": "req3", "check": "the events are told in the past tense", "label_es": "usar el pasado"},
        ],
    },
    {
        "id": "opinion",
        "prompt": {
            "en": (
                "Is social media good for young people? Write a short text (80 to 100 words) giving your "
                "opinion. Give at least two reasons and use some linking words (because, however, "
                "although, in addition...)."
            ),
            "es": (
                "¿Es bueno el uso de las redes sociales para los jóvenes? Escribe un texto corto (80 a 100 "
                "palabras) dando tu opinión. Da al menos dos razones y usa algunos conectores (porque, "
                "sin embargo, aunque, además...)."
            ),
        },
        "checklist": [
            {"id": "req1", "check": "the student gives a clear personal opinion about whether social media is good or bad for young people", "label_es": "tu opinión"},
            {"id": "req2", "check": "the student gives at least two reasons or examples", "label_es": "al menos dos razones"},
            {"id": "req3", "check": "the student uses at least one linking word such as because, however, although, so, in addition (or its equivalent in the language of the text)", "label_es": "algún conector (because/porque, however/sin embargo, although/aunque...)"},
        ],
    },
]

# Compatibilidad: si algún código lee WRITING_PROMPT / TASK_CHECKLIST["writing"] (como A1 y A2),
# recibe la primera tarea. telegram_flow usa WRITING_TASKS cuando existe.
WRITING_PROMPT = WRITING_TASKS[0]["prompt"]

# ---------- Habla (pendiente de implementar: la transcripción aún no está) ----------
SPEAKING_PROMPT = {
    "en": (
        "Send a voice note (45 to 60 seconds): tell us about a memorable experience in the past, such as "
        "a trip or an event. Say what happened and give your opinion about it."
    ),
    "es": (
        "Envía una nota de voz (45 a 60 segundos): cuéntanos una experiencia memorable del pasado, como "
        "un viaje o un evento. Di qué pasó y da tu opinión sobre ella."
    ),
}

TASK_CHECKLIST = {
    "writing": WRITING_TASKS[0]["checklist"],
    "speaking": [
        {"id": "req1", "check": "the student describes a memorable experience in the past (a trip, an event or similar)", "label_es": "una experiencia pasada memorable"},
        {"id": "req2", "check": "the student says what happened, using past tenses", "label_es": "qué pasó (en pasado)"},
        {"id": "req3", "check": "the student gives an opinion or says how they felt about the experience", "label_es": "tu opinión o cómo te sentiste"},
    ],
}


def score_reading(questions: list[dict], answers: list[int]) -> float:
    """questions: las preguntas generadas para este examen. answers: índice elegido por pregunta. 0-100."""
    correct = sum(1 for q, a in zip(questions, answers) if q["answer"] == a)
    return 100 * correct / len(questions)
