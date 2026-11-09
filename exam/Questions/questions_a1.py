"""Configuración del examen A1. Las preguntas de lectura YA NO están escritas aquí:
las genera Ollama (ver question_generator.py) a partir de los temas permitidos en A1.
Escritura y habla las califica el agente (grader.py)."""
from exam import espanol as es

# ---------- Lectura: cuántas preguntas y de qué temas ----------
N_READING = 10
N_GRAMMAR = 6   # de las 10 preguntas, 6 de gramática...
N_VOCAB = 4     # ...y 4 de vocabulario/conversación

# Límites de largo. Más que el valor por defecto (14) porque los temas de CONTEXT_TOPICS llevan una
# frase de contexto antes de la frase con el espacio en blanco, y 14 palabras no alcanzan:
# "My brother is 10 and my sister is 15. My brother is ___ than my sister." son 16.
MAX_QUESTION_WORDS = 20
MAX_QUESTION_CHARS = 150

# Temas cuya pregunta DEBE traer una frase de contexto antes de la frase con el espacio en blanco.
# Sin contexto varias opciones son igual de válidas y la pregunta no tiene respuesta única:
#   "My brother is ___ than my sister."  -> taller / younger / shorter
#   "The book is ___ the table."         -> on / under / next to
#   "___ book is mine."                  -> this / that
# Se comparan con el INICIO del texto del tema.
CONTEXT_TOPICS = (
    "Pronouns:",
    "Very common adjectives",
    "Demonstratives",
    "Prepositions of place",
)
# Temas con pronombres de género: el contexto debe mostrar el género (brother, sister, he, she...).
GENDER_CUE_TOPICS = ("Pronouns:",)

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

# ---------- Temas para el examen en ESPAÑOL ----------
# Tomados del temario A1 de español (no son traducción de los de inglés): ser/estar, hay, tener,
# gustar, género y número... El abecedario y la pronunciación no se evalúan aquí con opción múltiple
# escrita: quedan para la escucha y el habla.
GRAMMAR_TARGETS_ES = [
    "Ser y estar en presente (soy, eres, es; estoy, estás, está) para origen, profesión, ubicación y estado; afirmativo, negativo y preguntas",
    "Hay frente a estar: hay + un/una/número (Hay un banco cerca) y el/la + está (El banco está en la plaza)",
    "Tener en presente (tengo, tienes, tiene, tenemos, tienen) para edad, familia y cosas que se poseen",
    "Gustar en presente: me gusta / me gustan, te gusta, le gusta, nos gusta, con sustantivos en singular o plural y con infinitivos",
    "Presente de indicativo de verbos regulares -ar, -er, -ir (hablo, comes, vive, trabajamos) en rutinas y hechos",
    "Género y número de sustantivos y adjetivos con concordancia (el libro rojo, las casas blancas, una chica alta)",
    "Artículos definidos e indefinidos (el, la, los, las, un, una, unos, unas) con concordancia de género y número",
    "Pronombres personales sujeto (yo, tú, él, ella, usted, nosotros, ustedes, ellos, ellas) y concordancia con el verbo",
    "Verbos reflexivos de rutina en presente (me levanto, te duchas, se llama, nos acostamos)",
    "Demostrativos este/esta/estos/estas y ese/esa/esos/esas con objetos cotidianos",
    "Posesivos mi/mis, tu/tus, su/sus, nuestro/nuestra/nuestros/nuestras",
    "Preguntas con qué, dónde, cómo, cuándo, quién, cuántos/cuántas y de dónde sobre datos cotidianos",
]

VOCAB_TARGETS_ES = [
    "Saludos, despedidas y presentaciones (hola, buenos días, me llamo, mucho gusto, hasta luego)",
    "Números del 0 al 100 y la hora (son las tres y media, es la una)",
    "Días de la semana y meses del año",
    "Países, nacionalidades e idiomas con concordancia de género (Colombia, colombiano/colombiana, hablo inglés)",
    "Profesiones y lugares de trabajo (médico, profesora, estudiante, hospital, escuela)",
    "La familia y la descripción de personas (alto, joven, simpático, pelo largo)",
    "La casa: habitaciones y objetos cotidianos (cocina, dormitorio, mesa, cama, lámpara)",
    "La ciudad: lugares y transporte (supermercado, banco, parque, hospital, autobús)",
    "La ropa y los colores",
    "La comida y las bebidas: alimentos comunes, pedir en una cafetería y gustos",
    "El tiempo atmosférico (hace calor, hace frío, llueve, está nublado)",
]

# Sin contexto varias opciones son válidas:
#   "La sopa ___ fría."      -> es / está      "___ libro es mío."   -> este / ese
#   "___ casa es grande."    -> mi / tu / su   "___ vive en Cali."   -> él / ella
CONTEXT_TOPICS_ES = (
    "Ser y estar",
    "Hay frente a estar",
    "Pronombres personales",
    "Demostrativos",
    "Posesivos",
)
GENDER_CUE_TOPICS_ES = ("Pronombres personales", "Posesivos")

FORBIDDEN_ES = (
    "any past tense (fui, comí, comía, he comido), any future (iré, voy a ir), subjunctive, "
    "conditional (gustaría, podría), commands and imperative forms, combined object pronouns (se lo, me la), "
    "impersonal or passive se, idioms, regional slang, rare or abstract vocabulary"
)

# Filtro por código (español). Solo presente: se anulan pasados, futuros, subjuntivo, condicional e imperativo.
FORBIDDEN_RE_ES = es.compilar(
    es.PERFECTO, es.PLUSCUAMPERFECTO, es.PASADOS_COMUNES, es.FUTURO_SIMPLE, es.IR_A,
    es.CONDICIONAL_SIMPLE, es.CORTESIA, es.SUBJ_PRESENTE, es.SUBJ_IMPERFECTO, es.IMPERATIVO,
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
