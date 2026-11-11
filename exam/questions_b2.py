"""Configuración del examen B2 (último nivel del semestre). Mismo formato que questions_b1.py.
Las preguntas de lectura las genera Ollama (question_generator.py) a partir de estos temas.
Escritura y habla las califica el agente (grader.py). La escucha B2 está en listening.py (CONFIG["B2"]).

Alcance:
  - Inglés: tomado del banco B2 de la rama `laura` (exam/Questions/questions_b2.py y RESUMEN_B2.txt),
    adaptado a los nombres de atributos que usa hoy el generador (GEN_STYLE, OPTION_LEN, PASSAGE_SHAPE...).
  - Español: el alcance B2 de exam/RESUMEN_ES.txt (imperfecto de subjuntivo y correlación de tiempos,
    concesivas, relativas con subjuntivo, estilo indirecto con cambio de tiempos, ser/estar con
    cambio de significado; temas abstractos, modismos frecuentes, matizar opiniones, registro formal).
Lo prohibido es de C1 (inversión, subjuntivo inglés, oraciones hendidas, vocabulario literario...).

Diferencias con B1:
  - FORBIDDEN_RE solo bloquea la inversión con adverbios negativos (C1): se permite todo lo de B1 y
    lo nuevo de B2 (condicionales mixtos, wish / if only, futuro perfecto, modales de deducción...).
  - En español no hay filtro de formas por código (FORBIDDEN_RE_ES = None): en B2 se evalúan todas las
    formas verbales comunes; lo de C1 lo controla el prompt (FORBIDDEN_ES) y la verificación del modelo.
  - Mini-textos más largos (70-130 palabras) con registro formal y argumentos.
"""
import re

LEVEL = "B2"

# ---------- Lectura: cuántas preguntas y de qué temas ----------
N_READING = 10
N_GRAMMAR = 4    # gramática (frase con un espacio en blanco)
N_VOCAB = 3      # vocabulario y colocaciones
N_PASSAGE = 3    # comprensión con TEXTO (los más lentos de generar: bájalo a 2 si tu PC sufre)

# Límites de largo (frases de gramática/vocabulario): B2 necesita frases de contexto más largas
MAX_QUESTION_WORDS = 30
MAX_OPTION_WORDS = 10
MAX_QUESTION_CHARS = 210
MAX_OPTION_CHARS = 60

# Temas cuya pregunta DEBE traer una frase de contexto (sin ella varias opciones son válidas):
#   "If I ___ that job, I would be living abroad now."  -> had taken / took / have taken
#   "She ___ forgotten: she never forgets."             -> can't have / must have / might have
CONTEXT_TOPICS = (
    "Third conditional and mixed",
    "Past perfect simple vs past simple",
    "Present perfect continuous",
    "Wish and if only",
    "Modal verbs of deduction",
    "Linking and contrast",
    "Future continuous and future perfect",
)

# Mini-textos: el filtro acepta 70-130 palabras; al modelo se le piden 75-115 (el margen es porque se pasa)
PASSAGE_MIN_WORDS = 70
PASSAGE_MAX_WORDS = 130
PASSAGE_PROMPT_MIN_WORDS = 75
PASSAGE_PROMPT_MAX_WORDS = 115
PASSAGE_MAX_OPTION_WORDS = 14
PASSAGE_MAX_OPTION_CHARS = 90
PASSAGE_Q_WORDS = 20

# Textos de los prompts (por nivel)
GEN_STYLE = (
    "Use natural, varied vocabulary and sentences of moderate to long length, with some less common "
    "words, but nothing highly technical, literary or specialised."
)
OPTION_LEN = "short (1 to 6 words)"
GEN_EXAMPLES = (
    '{"q": "I didn\'t take the job in London. If I had taken it, I ___ abroad now.", '
    '"correct": "would be living", "wrong": ["will live", "had lived"]}\n'
    '{"q": "Her keys are on the table and her car is outside. She ___ gone out.", '
    '"correct": "can\'t have", "wrong": ["must have", "should have"]}\n'
    '{"q": "The meeting was very long, but we finally ___ a solution that everyone liked.", '
    '"correct": "came up with", "wrong": ["put off", "turned down"]}'
)
PASSAGE_SHAPE = (
    "6 to 9 sentences. The text can explain a situation, defend a point of view or describe a process; "
    "it uses linking words and some less common vocabulary"
)
PASSAGE_EXAMPLE = (
    '{"text": "Dear Ms Carter, I am writing to complain about the internet service at my flat. Since '
    'the company changed the router three weeks ago, the connection has been cutting out several times '
    'a day. As I work from home, this has caused serious problems: I have missed two important online '
    'meetings and had to work from a café. I have already called your helpline twice, but nobody has '
    'come to check the line. I would appreciate it if a technician could visit this week, and I would '
    'also like a discount on this month\'s bill. Yours sincerely, Daniel Ruiz", '
    '"q": "What does Daniel want the company to do?", "correct": "Send a technician and reduce the bill", '
    '"wrong": ["Change his router again", "Cancel his contract immediately"]}'
)
PASSAGE_OPTION_LEN = "short phrases (1 to 12 words)"

PASSAGE_QUESTION_TYPES = {
    "main_idea": (
        "The question asks about the MAIN IDEA or the purpose of the text "
        "(for example: What is the main point of the text? Why was it written?)."
    ),
    "detail": (
        "The question asks about ONE specific detail that is clearly written in the text "
        "(who, what, when, where, how much, how long, which condition)."
    ),
    "attitude": (
        "The question asks about the writer's ATTITUDE, opinion or INTENTION "
        "(for example: How does the writer feel about ...? What is the writer trying to do?). "
        "The answer must be clear from the text."
    ),
}
PASSAGE_ATTITUDE_RE = re.compile(r"article|e-?mail|letter|opinion|blog|review", re.I)

# Cada tema lleva entre paréntesis el ALCANCE permitido: así el modelo no se pasa a C1.
GRAMMAR_TARGETS = [
    "Third conditional and mixed conditionals for past regrets and unreal situations (If I had studied harder, I would have passed; If I had taken that job, I would be living abroad now)",
    "Past perfect simple vs past simple to show which event happened first (By the time we arrived, the film had already started)",
    "Present perfect continuous vs present perfect simple (I have been working here for two years; I have written three reports today)",
    "Passive voice in all common tenses and with modal verbs (The house has been sold; The report must be finished by Friday; The bridge is being repaired)",
    "Reported speech with tense changes and reporting verbs (admitted, denied, suggested, warned, promised, insisted)",
    "Wish and if only for present and past regrets (I wish I had more time; If only I had listened to her)",
    "Modal verbs of deduction in the present and the past (must / might / can't + have + past participle; She can't have forgotten)",
    "Defining and non-defining relative clauses with who, whom, whose, which, where and prepositions (The woman whose car was stolen called the police)",
    "Gerund vs infinitive with a change of meaning (remember / stop / try / regret + -ing or to) and verb + object + infinitive (advise, allow, persuade, warn someone to)",
    "Future continuous and future perfect (This time tomorrow I will be flying; By 2030 she will have finished her degree)",
    "Linking and contrast: despite / in spite of + noun or -ing, whereas, nevertheless, as long as, provided that, unless, in case",
    "Causative have / get something done (I had my car repaired; She got her hair cut)",
    "Determiners and quantifiers: both, either, neither, each, every, whole, most of, several, plenty of",
]

VOCAB_TARGETS = [
    "Work and business: negotiation, deadlines, management, teamwork, promotion, changing careers, working conditions",
    "Education and research: qualifications, scholarships, academic skills, curriculum, study methods",
    "Environment and society: sustainability, climate change, renewable energy, urban problems, inequality",
    "Media, technology and the internet: privacy, influence of social media, artificial intelligence, misinformation, online habits",
    "Health and wellbeing: mental health, lifestyle, treatment, prevention, stress at work",
    "Travel, tourism and culture: cultural differences, customs, heritage, living or working abroad",
    "Money and consumer topics: budgets, debt, investments, consumer rights, advertising",
    "Law, community and citizenship: rules, rights, responsibilities, volunteering, public services",
    "Opinions, feelings and relationships: agreeing and disagreeing, expressing opinions, precise adjectives for emotions and personality",
    "Collocations and word choice: make / do / take / have collocations and common phrasal verbs (carry out, put off, come up with, deal with, turn down)",
]

PASSAGE_TARGETS = [
    "an extract from a newspaper or magazine article about a social, environmental or technology issue",
    "a formal email or letter that makes a complaint or a request, giving reasons and asking for a solution",
    "a personal blog post about a big change in life (moving abroad, a new job, going back to study) with opinions and feelings",
    "a short opinion piece or letter to the editor with arguments for and against an idea",
    "a detailed review of a product, a book or a service with advantages, disadvantages and a recommendation",
    "an announcement or advertisement for a course, an event or a job, with detailed conditions and requirements",
    "a short report that describes a process or the results of a small survey, with simple numbers",
]

# Prohibido en preguntas B2 (lo ve el modelo en el prompt): estructuras de C1
FORBIDDEN = (
    "inversion after negative adverbs (Never have I..., Not only did..., Hardly had...), the English "
    "subjunctive (I suggest that he be...), cleft sentences (What I need is...), advanced idioms and slang, "
    "rare phrasal verbs, literary, technical or highly specialised vocabulary"
)

# Filtro por código (solo inglés). En B2 se permiten todos los tiempos y modales de B1 y B2;
# solo se bloquea la inversión con adverbios negativos (estructura de C1).
FORBIDDEN_RE = re.compile(
    r"\b(?:never|hardly|scarcely|rarely|seldom|little) (?:have|has|had|did|do|does|will|would|can|could|should) "
    r"(?:i|you|we|he|she|they|it)\b"
    r"|\bnot only (?:did|do|does|have|has|had|will|would|can|could)\b"
    r"|\bno sooner (?:had|did)\b",
    re.I,
)

# ---------- Temas para el examen en ESPAÑOL ----------
# Alcance de exam/RESUMEN_ES.txt (sección "PENDIENTE: B2 EN ESPAÑOL").
GRAMMAR_TARGETS_ES = [
    "Imperfecto de subjuntivo y correlación de tiempos en condicionales (Si tuviera dinero, viajaría; Si fuera tú, lo aceptaría)",
    "Condicional compuesto y pluscuamperfecto de subjuntivo para hechos pasados no reales (Si hubiera estudiado, habría aprobado)",
    "Oraciones concesivas con indicativo o subjuntivo (aunque llueve / aunque llueva, por más que estudie, a pesar de que)",
    "Oraciones de relativo con subjuntivo para algo no conocido o que no existe (Busco un trabajo que tenga horario flexible; No hay nadie que lo sepa)",
    "Estilo indirecto con cambio de tiempos (Dijo que vendría; Me preguntó si había terminado; Me pidió que lo llamara)",
    "Ser y estar con cambio de significado (ser listo / estar listo, ser rico / estar rico, ser aburrido / estar aburrido)",
    "Subjuntivo con expresiones de finalidad y tiempo (para que, antes de que, cuando llegues, en cuanto termine)",
    "Conectores para argumentar y matizar: no obstante, en cambio, por consiguiente, siempre que, a no ser que, dado que",
]

VOCAB_TARGETS_ES = [
    "Medio ambiente y sociedad: sostenibilidad, cambio climático, reciclaje, desigualdad, problemas urbanos",
    "Política, economía y ciudadanía: elecciones, impuestos, derechos, servicios públicos, voluntariado",
    "Ciencia, tecnología y medios: inteligencia artificial, privacidad, desinformación, investigación",
    "Arte y cultura: exposiciones, literatura, cine, patrimonio, costumbres de otros países",
    "Modismos y expresiones frecuentes (tomar el pelo, costar un ojo de la cara, estar en las nubes, no tener pelos en la lengua)",
    "Matizar opiniones y expresar acuerdo parcial (hasta cierto punto, no cabe duda de que, me parece que, en parte tienes razón)",
    "Registro formal: cartas de reclamación, solicitudes, fórmulas de cortesía (Le escribo para..., Quedo a la espera de su respuesta)",
]

PASSAGE_TARGETS_ES = [
    "an extract from a newspaper or magazine article about a social, environmental or technology issue",
    "a formal email or letter of complaint or request (reclamación, solicitud) with reasons and a requested solution",
    "a personal blog post about a big change in life (moving abroad, a new job, going back to study) with opinions and feelings",
    "a short opinion piece or letter to the editor with arguments for and against an idea",
    "a detailed review of a book, a film, a restaurant or a service with advantages, disadvantages and a recommendation",
    "an announcement or job advertisement with detailed conditions and requirements",
]

CONTEXT_TOPICS_ES = (
    "Imperfecto de subjuntivo",
    "Condicional compuesto",
    "Oraciones concesivas",
    "Oraciones de relativo",
    "Estilo indirecto",
    "Ser y estar con cambio",
    "Subjuntivo con expresiones",
    "Conectores",
    "Modismos",
)

GEN_STYLE_ES = (
    "Use natural, varied vocabulary and sentences of moderate to long length, with some less common "
    "words, but nothing highly technical, literary or specialised."
)
GEN_EXAMPLES_ES = (
    '{"q": "No tengo dinero ahora. Si lo ___, me compraría un carro nuevo.", '
    '"correct": "tuviera", "wrong": ["tengo", "tendré"]}\n'
    '{"q": "Ya preparé la maleta y tengo el pasaporte en la mano. Por fin ___ listo para el viaje.", '
    '"correct": "estoy", "wrong": ["soy", "fui"]}\n'
    '{"q": "Ese restaurante es carísimo: comer allí cuesta un ojo de la ___.", '
    '"correct": "cara", "wrong": ["mano", "cabeza"]}'
)
PASSAGE_EXAMPLE_ES = (
    '{"text": "Estimada señora Herrera: le escribo para presentar una reclamación sobre el servicio de '
    'internet de mi apartamento. Desde que la empresa cambió el router hace tres semanas, la conexión se '
    'corta varias veces al día. Como trabajo desde casa, esto me ha causado problemas serios: he perdido '
    'dos reuniones importantes y he tenido que trabajar desde una cafetería. Ya he llamado dos veces a la '
    'línea de atención, pero nadie ha venido a revisar la instalación. Le agradecería que un técnico '
    'viniera esta semana y que me hicieran un descuento en la factura. Atentamente, Daniel Ruiz", '
    '"q": "¿Qué le pide Daniel a la empresa?", "correct": "Un técnico y un descuento en la factura", '
    '"wrong": ["Un router nuevo otra vez", "Cancelar el contrato de inmediato"]}'
)

FORBIDDEN_ES = (
    "future subjunctive (fuere, hubiere), literary or archaic forms (vos sois, hubiérades), "
    "very rare idioms and proverbs, regional slang, technical, legal or highly specialised vocabulary, "
    "long sentences with several subordinate clauses"
)

# En B2 se evalúan todas las formas verbales comunes: no hay filtro de formas por código en español.
FORBIDDEN_RE_ES = None

# ---------- Escritura ----------
# El CÓDIGO elige al azar UNA tarea por examen. check: lo que ve el modelo (en inglés) ·
# label_es: lo que ve el usuario si le falta.
WRITING_TASKS = [
    {
        "id": "formal_email",
        "prompt": {
            "en": (
                "Write a formal email (80 to 110 words) to the manager of a company, hotel or school about a "
                "problem with a service you received. Explain what went wrong, say how it affected you, "
                "explain what you have already done about it, and ask politely for a specific solution."
            ),
            "es": (
                "Escribe un correo formal (80 a 110 palabras) al gerente de una empresa, un hotel o una "
                "institución educativa sobre un problema con un servicio que recibiste. Explica qué salió mal, "
                "di cómo te afectó, cuenta qué has hecho ya al respecto y pide con cortesía una solución concreta."
            ),
        },
        "checklist": [
            {"id": "req1", "check": "the student explains what went wrong with the service (the problem)", "label_es": "qué salió mal"},
            {"id": "req2", "check": "the student says how the problem affected them (the consequences)", "label_es": "cómo te afectó"},
            {"id": "req3", "check": "the student says what they have already done or tried to solve the problem", "label_es": "qué has hecho ya al respecto"},
            {"id": "req4", "check": "the student asks for a specific solution, using polite and formal language", "label_es": "una solución concreta, con tono formal y cortés"},
        ],
    },
    {
        "id": "essay",
        "prompt": {
            "en": (
                "Write a short essay (90 to 120 words): \"Working from home is better than working in an "
                "office.\" Do you agree? Give arguments for AND against, and finish with your own conclusion."
            ),
            "es": (
                "Escribe un texto argumentativo corto (90 a 120 palabras): «Trabajar desde casa es mejor que "
                "trabajar en una oficina». ¿Estás de acuerdo? Da argumentos a favor Y en contra, y termina con "
                "tu propia conclusión."
            ),
        },
        "checklist": [
            {"id": "req1", "check": "the student gives at least one argument in favour of working from home", "label_es": "un argumento a favor"},
            {"id": "req2", "check": "the student gives at least one argument against it", "label_es": "un argumento en contra"},
            {"id": "req3", "check": "the student finishes with a clear personal conclusion", "label_es": "tu conclusión"},
            {"id": "req4", "check": "the student uses linking words to connect or contrast ideas (however, although, whereas, sin embargo, aunque...)", "label_es": "conectores para unir o contrastar ideas"},
        ],
    },
]

# Compatibilidad con el código que lee WRITING_PROMPT / TASK_CHECKLIST["writing"] (como A1 y A2)
WRITING_PROMPT = WRITING_TASKS[0]["prompt"]

# ---------- Habla ----------
SPEAKING_PROMPT = {
    "en": (
        "Send a voice note (60 to 90 seconds): do you think technology, for example social media or "
        "artificial intelligence, is making our lives better or worse? Give your opinion, support it "
        "with reasons or examples, and mention a disadvantage or another point of view."
    ),
    "es": (
        "Envía una nota de voz (60 a 90 segundos): ¿crees que la tecnología, por ejemplo las redes "
        "sociales o la inteligencia artificial, mejora o empeora nuestra vida? Da tu opinión, apóyala "
        "con razones o ejemplos y menciona una desventaja u otro punto de vista."
    ),
}

TASK_CHECKLIST = {
    "writing": WRITING_TASKS[0]["checklist"],
    "speaking": [
        {"id": "req1", "check": "the student clearly states an opinion about whether technology makes our lives better or worse", "label_es": "tu opinión"},
        {"id": "req2", "check": "the student gives at least two reasons or examples to support the opinion", "label_es": "al menos dos razones o ejemplos"},
        {"id": "req3", "check": "the student mentions a disadvantage, an opposite point of view or a possible solution", "label_es": "una desventaja u otro punto de vista"},
    ],
}


def score_reading(questions: list[dict], answers: list[int]) -> float:
    """questions: las preguntas generadas para este examen. answers: índice elegido por pregunta. 0-100."""
    correct = sum(1 for q, a in zip(questions, answers) if q["answer"] == a)
    return 100 * correct / len(questions)
