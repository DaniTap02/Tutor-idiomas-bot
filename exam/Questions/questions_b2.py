"""Configuración del examen B2. Mismo formato que questions_a1.py, questions_a2.py y questions_b1.py.
Las preguntas de lectura las genera Ollama (question_generator.py) a partir de estos temas.
Escritura y habla las califica el agente (grader.py). La escucha se configura en listening.py."""
import re

LEVEL = "B2"

# ---------- Lectura: cuántas preguntas y de qué temas ----------
N_READING = 10
N_GRAMMAR = 4    # gramática (frase con un espacio en blanco)
N_VOCAB = 2      # vocabulario y colocaciones (frase)
N_PASSAGE = 4    # comprensión con TEXTO (artículo, carta formal, blog, opinión, reseña, anuncio)

# Límites de largo (el generador usa los de A1 si el banco no los define)
MAX_QUESTION_WORDS = 24
MAX_OPTION_WORDS = 12
MAX_QUESTION_CHARS = 200
MAX_OPTION_CHARS = 80
PASSAGE_MIN_WORDS = 70
PASSAGE_MAX_WORDS = 130

# Instrucciones de estilo que ve el modelo (en inglés). Sin estas, el generador usa las de A1/A2.
STYLE_HINT = (
    "Use natural, varied vocabulary and sentences of moderate to long length, with some less "
    "common words, but nothing highly technical, literary or specialised."
)
OPTION_WORDS_HINT = 8
PASSAGE_STYLE = (
    "5 to 8 sentences. The text can explain a situation, defend a point of view or describe a process; "
    "it may use linking words and some less common vocabulary."
)
PASSAGE_OPTION_WORDS_HINT = 10
PASSAGE_QUESTION_WORDS_HINT = 20

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
    "Causative have / get something done (I had my car repaired; She got her hair cut) and used to / would for past habits",
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

# Tipos de texto para las preguntas de comprensión
PASSAGE_TARGETS = [
    "an extract from a newspaper or magazine article about a social, environmental or technology issue",
    "a formal email or letter that makes a complaint or a request, giving reasons and asking for a solution",
    "a personal blog post about a big change in life (moving abroad, a new job, going back to study) with opinions and feelings",
    "a short opinion piece or letter to the editor with arguments for and against an idea",
    "a detailed review of a product, a book or a service with advantages, disadvantages and a recommendation",
    "an announcement or advertisement for a course, an event or a job, with detailed conditions and requirements",
    "a short report that describes a process or the results of a small survey, with simple numbers",
]

# Prohibido en preguntas B2 (lo ve el modelo en el prompt)
FORBIDDEN = (
    "inversion after negative adverbs (Never have I..., Not only did...), the subjunctive, cleft sentences, "
    "advanced idioms and slang, rare phrasal verbs, "
    "literary, technical or highly specialised vocabulary"
)

# Filtro por código (solo inglés). En B2 se permiten todos los tiempos y modales de B1;
# solo se bloquea la inversión con adverbios negativos (estructura de C1).
FORBIDDEN_RE = re.compile(
    r"\b(?:never|hardly|scarcely|rarely|seldom) (?:have|has|had|did|do|does|will|would|can|could|should) (?:i|you|we|he|she|they|it)\b"
    r"|\bnot only (?:did|do|does|have|has|had|will|would|can|could)\b",
    re.I,
)

# ---------- Escritura / habla ----------
WRITING_PROMPT = {
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
}

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

# check: lo que ve el modelo (en inglés) · label_es: lo que ve el usuario si le falta.
TASK_CHECKLIST = {
    "writing": [
        {"id": "req1", "check": "the student explains what went wrong with the service (the problem)", "label_es": "qué salió mal"},
        {"id": "req2", "check": "the student says how the problem affected them (the consequences)", "label_es": "cómo te afectó"},
        {"id": "req3", "check": "the student says what they have already done or tried to solve the problem", "label_es": "qué has hecho ya al respecto"},
        {"id": "req4", "check": "the student asks for a specific solution, using polite and formal language", "label_es": "una solución concreta, con tono formal y cortés"},
    ],
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
