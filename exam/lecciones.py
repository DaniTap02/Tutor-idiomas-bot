"""Temario de las LECCIONES del tutor: 5 lecciones por nivel e idioma (inglés y español espejo).

Son DATOS, no preguntas escritas: cada lección dice qué temas de gramática y vocabulario practica
(la gramática PERMITIDA en la lección), su objetivo y la tarea corta de escritura. Las preguntas y
la mini explicación las genera Ollama en vivo (exam/tutor.py) y pasan por el MISMO validador del
examen (question_generator.py). Lo prohibido del nivel es el FORBIDDEN del banco questions_xx.py.

Los temas se nombran con el INICIO del texto del tema en el banco (GRAMMAR_TARGETS / VOCAB_TARGETS
y sus versiones _ES), así se reutilizan tal cual, con su alcance, y valen CONTEXT_TOPICS y
GENDER_CUE_TOPICS. exam/test_tutor.py comprueba que todos existan en el banco.

Espejo: inglés y español tienen la misma estructura (mismo tema de la lección, mismo número de
temas, misma tarea); solo cambia el idioma y los puntos gramaticales propios de cada lengua.

Cada lección:
  id            "A1-1" ...
  titulo        {"en", "es"}
  objetivo      {"en", "es"}
  gramatica     {"en": [inicio de tema...], "es": [...]}
  vocabulario   {"en": [...], "es": [...]}
  escritura     {"en", "es"}: tarea corta que califica grader.py
  checklist     [{"id", "check" (lo lee el modelo, en inglés), "label": {"en", "es"}}]
"""

# Mínimo de palabras de la escritura corta de una lección (más bajo que el del examen)
MIN_PALABRAS_LECCION = {"A1": 5, "A2": 15, "B1": 30, "B2": 40}

LECCIONES = {
    "A1": [
        {
            "id": "A1-1",
            "titulo": {"en": "Hello! Introducing yourself", "es": "¡Hola! Presentarse"},
            "objetivo": {"en": "Say who you are and where you are from.",
                         "es": "Decir quién eres y de dónde eres."},
            "gramatica": {"en": ["Verb To Be", "Pronouns:"],
                          "es": ["Ser y estar", "Pronombres personales"]},
            "vocabulario": {"en": ["Introductions"], "es": ["Saludos"]},
            "escritura": {"en": "Write 2 or 3 sentences: say hello, your name and your country.",
                          "es": "Escribe 2 o 3 frases: saluda, di tu nombre y tu país."},
            "checklist": [
                {"id": "req1", "check": "the student says their name", "label": {"en": "your name", "es": "tu nombre"}},
                {"id": "req2", "check": "the student says their country or where they are from",
                 "label": {"en": "your country", "es": "tu país"}},
            ],
        },
        {
            "id": "A1-2",
            "titulo": {"en": "My family", "es": "Mi familia"},
            "objetivo": {"en": "Talk about your family and describe people.",
                         "es": "Hablar de tu familia y describir personas."},
            "gramatica": {"en": ["Pronouns:", "Very common adjectives"],
                          "es": ["Posesivos", "Tener en presente"]},
            "vocabulario": {"en": ["Family members"], "es": ["La familia"]},
            "escritura": {"en": "Write 2 or 3 sentences about a person in your family: who is it and what is he or she like?",
                          "es": "Escribe 2 o 3 frases sobre una persona de tu familia: ¿quién es y cómo es?"},
            "checklist": [
                {"id": "req1", "check": "the student names a family member", "label": {"en": "a family member", "es": "un familiar"}},
                {"id": "req2", "check": "the student describes that person (age, appearance or personality)",
                 "label": {"en": "a description of that person", "es": "cómo es esa persona"}},
            ],
        },
        {
            "id": "A1-3",
            "titulo": {"en": "My day", "es": "Mi día"},
            "objetivo": {"en": "Talk about your daily routine, days and times.",
                         "es": "Hablar de tu rutina diaria, los días y la hora."},
            "gramatica": {"en": ["Simple present", "Prepositions of place"],
                          "es": ["Presente de indicativo", "Verbos reflexivos"]},
            "vocabulario": {"en": ["Days of the week"], "es": ["Días de la semana", "Números del 0"]},
            "escritura": {"en": "Write 2 or 3 sentences about your day: what do you do and at what time?",
                          "es": "Escribe 2 o 3 frases sobre tu día: ¿qué haces y a qué hora?"},
            "checklist": [
                {"id": "req1", "check": "the student describes at least one daily activity",
                 "label": {"en": "an activity of your day", "es": "una actividad de tu día"}},
                {"id": "req2", "check": "the student says a time or a day", "label": {"en": "a time or a day", "es": "una hora o un día"}},
            ],
        },
        {
            "id": "A1-4",
            "titulo": {"en": "My home and my town", "es": "Mi casa y mi ciudad"},
            "objetivo": {"en": "Describe your home and the places in your town.",
                         "es": "Describir tu casa y los lugares de tu ciudad."},
            "gramatica": {"en": ["There is / There are", "Demonstratives"],
                          "es": ["Hay frente a estar", "Demostrativos"]},
            "vocabulario": {"en": ["The home", "Places in the city"], "es": ["La casa", "La ciudad"]},
            "escritura": {"en": "Write 2 or 3 sentences about your home or your street: what is there?",
                          "es": "Escribe 2 o 3 frases sobre tu casa o tu calle: ¿qué hay?"},
            "checklist": [
                {"id": "req1", "check": "the student mentions rooms, objects or places that exist in their home or town",
                 "label": {"en": "what there is in your home or street", "es": "qué hay en tu casa o tu calle"}},
            ],
        },
        {
            "id": "A1-5",
            "titulo": {"en": "Food, clothes and shopping", "es": "Comida, ropa y compras"},
            "objetivo": {"en": "Say what you like, ask questions and buy things.",
                         "es": "Decir lo que te gusta, hacer preguntas y comprar cosas."},
            "gramatica": {"en": ["Wh- questions", "Modal CAN"],
                          "es": ["Gustar en presente", "Preguntas con"]},
            "vocabulario": {"en": ["Food and drink", "Clothes and colors", "Shopping and prices"],
                            "es": ["La comida", "La ropa y los colores"]},
            "escritura": {"en": "Write 2 or 3 sentences: what food do you like and what clothes do you wear?",
                          "es": "Escribe 2 o 3 frases: ¿qué comida te gusta y qué ropa usas?"},
            "checklist": [
                {"id": "req1", "check": "the student says a food or drink they like or dislike",
                 "label": {"en": "a food you like", "es": "una comida que te gusta"}},
                {"id": "req2", "check": "the student mentions clothes or colors", "label": {"en": "your clothes", "es": "tu ropa"}},
            ],
        },
    ],
    "A2": [
        {
            "id": "A2-1",
            "titulo": {"en": "Routines and home", "es": "Rutinas y casa"},
            "objetivo": {"en": "Compare what you usually do with what you are doing now.",
                         "es": "Contar lo que haces normalmente y lo que estás haciendo ahora."},
            "gramatica": {"en": ["Present simple vs present continuous", "There is / There are with some"],
                          "es": ["Estar + gerundio", "Verbos como gustar"]},
            "vocabulario": {"en": ["Daily routines"], "es": ["Vivienda y vecindario"]},
            "escritura": {"en": "Write 3 or 4 sentences: what do you usually do at home, and what are you doing right now?",
                          "es": "Escribe 3 o 4 frases: ¿qué haces normalmente en casa y qué estás haciendo ahora?"},
            "checklist": [
                {"id": "req1", "check": "the student describes a usual habit or routine", "label": {"en": "a habit", "es": "un hábito"}},
                {"id": "req2", "check": "the student says what they are doing now", "label": {"en": "what you are doing now", "es": "lo que haces ahora"}},
            ],
        },
        {
            "id": "A2-2",
            "titulo": {"en": "My past", "es": "Mi pasado"},
            "objetivo": {"en": "Tell short stories about your life in the past.",
                         "es": "Contar historias cortas de tu vida en el pasado."},
            "gramatica": {"en": ["Simple past: regular", "Pronouns:"],
                          "es": ["Pretérito indefinido", "Pretérito imperfecto"]},
            "vocabulario": {"en": ["Personal information"], "es": ["Biografías"]},
            "escritura": {"en": "Write 3 or 4 sentences about something you did last weekend or when you were a child.",
                          "es": "Escribe 3 o 4 frases sobre algo que hiciste el fin de semana pasado o cuando eras niño o niña."},
            "checklist": [
                {"id": "req1", "check": "the student tells something that happened in the past using past tense",
                 "label": {"en": "something that happened in the past", "es": "algo que pasó en el pasado"}},
                {"id": "req2", "check": "the student says when it happened", "label": {"en": "when it happened", "es": "cuándo pasó"}},
            ],
        },
        {
            "id": "A2-3",
            "titulo": {"en": "Travel and plans", "es": "Viajes y planes"},
            "objetivo": {"en": "Talk about trips and your plans for the future.",
                         "es": "Hablar de viajes y de tus planes para el futuro."},
            "gramatica": {"en": ["Future: going to", "Simple past: regular"],
                          "es": ["Futuro con ir a", "Futuro simple"]},
            "vocabulario": {"en": ["Travel and holidays"], "es": ["Viajes y hostelería"]},
            "escritura": {"en": "Write 3 or 4 sentences about your next holiday: where are you going and what are you going to do?",
                          "es": "Escribe 3 o 4 frases sobre tus próximas vacaciones: ¿adónde vas a ir y qué vas a hacer?"},
            "checklist": [
                {"id": "req1", "check": "the student says a place they plan to visit", "label": {"en": "where you are going", "es": "adónde vas"}},
                {"id": "req2", "check": "the student describes a future plan or intention",
                 "label": {"en": "what you are going to do", "es": "qué vas a hacer"}},
            ],
        },
        {
            "id": "A2-4",
            "titulo": {"en": "Shopping and food", "es": "Compras y comida"},
            "objetivo": {"en": "Compare products and talk about quantities.",
                         "es": "Comparar productos y hablar de cantidades."},
            "gramatica": {"en": ["Quantifiers", "Comparatives and superlatives"],
                          "es": ["Comparativos", "Pronombres de objeto"]},
            "vocabulario": {"en": ["Shopping and food"], "es": ["Compras"]},
            "escritura": {"en": "Write 3 or 4 sentences comparing two shops or two products you know.",
                          "es": "Escribe 3 o 4 frases comparando dos tiendas o dos productos que conoces."},
            "checklist": [
                {"id": "req1", "check": "the student names two shops or products", "label": {"en": "two shops or products", "es": "dos tiendas o productos"}},
                {"id": "req2", "check": "the student compares them", "label": {"en": "a comparison", "es": "una comparación"}},
            ],
        },
        {
            "id": "A2-5",
            "titulo": {"en": "Town and health", "es": "La ciudad y la salud"},
            "objetivo": {"en": "Give directions, follow rules and talk about health.",
                         "es": "Dar indicaciones, seguir reglas y hablar de la salud."},
            "gramatica": {"en": ["Modals can/could", "Must / have to"],
                          "es": ["Imperativo afirmativo", "Contraste entre pretérito"]},
            "vocabulario": {"en": ["Places in town", "Health"], "es": ["Pedir y dar", "Salud y cuerpo"]},
            "escritura": {"en": "Write 3 or 4 sentences: explain to a friend how to go from your home to a place near it.",
                          "es": "Escribe 3 o 4 frases: explícale a un amigo cómo ir de tu casa a un lugar cercano."},
            "checklist": [
                {"id": "req1", "check": "the student names a destination place", "label": {"en": "the place", "es": "el lugar"}},
                {"id": "req2", "check": "the student gives at least one direction (turn, go straight, next to...)",
                 "label": {"en": "the directions", "es": "las indicaciones"}},
            ],
        },
    ],
    "B1": [
        {
            "id": "B1-1",
            "titulo": {"en": "Experiences and stories", "es": "Experiencias y relatos"},
            "objetivo": {"en": "Tell a story and talk about your experiences.",
                         "es": "Contar un relato y hablar de tus experiencias."},
            "gramatica": {"en": ["Past tenses:", "Used to / would", "Present perfect simple"],
                          "es": ["Pretérito perfecto", "Pluscuamperfecto"]},
            "vocabulario": {"en": ["Everyday life and free time"], "es": ["Sentimientos"]},
            "escritura": {"en": "Write 4 to 6 sentences about an experience you remember well and how you felt.",
                          "es": "Escribe de 4 a 6 frases sobre una experiencia que recuerdas bien y cómo te sentiste."},
            "checklist": [
                {"id": "req1", "check": "the student narrates a past experience", "label": {"en": "the experience", "es": "la experiencia"}},
                {"id": "req2", "check": "the student says how they felt", "label": {"en": "how you felt", "es": "cómo te sentiste"}},
            ],
        },
        {
            "id": "B1-2",
            "titulo": {"en": "Work and studies", "es": "Trabajo y estudios"},
            "objetivo": {"en": "Talk about obligations, advice and your work or studies.",
                         "es": "Hablar de obligaciones, consejos y tu trabajo o tus estudios."},
            "gramatica": {"en": ["Modals of obligation", "Modals of ability", "Verb patterns"],
                          "es": ["Condicional simple", "Voz pasiva refleja"]},
            "vocabulario": {"en": ["Work and studies"], "es": ["Mundo laboral"]},
            "escritura": {"en": "Write 4 to 6 sentences giving advice to a friend who is starting a new job or course.",
                          "es": "Escribe de 4 a 6 frases dándole consejos a un amigo que empieza un trabajo o un curso nuevo."},
            "checklist": [
                {"id": "req1", "check": "the student gives at least two pieces of advice", "label": {"en": "two pieces of advice", "es": "dos consejos"}},
                {"id": "req2", "check": "the student explains why", "label": {"en": "the reason", "es": "por qué"}},
            ],
        },
        {
            "id": "B1-3",
            "titulo": {"en": "Plans and conditions", "es": "Planes y condiciones"},
            "objetivo": {"en": "Talk about plans, wishes and imaginary situations.",
                         "es": "Hablar de planes, deseos y situaciones posibles."},
            "gramatica": {"en": ["First and second conditionals", "Third conditional",
                                 "Present simple vs present continuous, and future"],
                          "es": ["Presente de subjuntivo para deseos", "Presente de subjuntivo para duda"]},
            "vocabulario": {"en": ["Travel and holidays"], "es": ["Viajes:"]},
            "escritura": {"en": "Write 4 to 6 sentences: what would you do if you could travel anywhere next year?",
                          "es": "Escribe de 4 a 6 frases: ¿qué esperas de tu próximo viaje y qué dudas tienes?"},
            "checklist": [
                {"id": "req1", "check": "the student describes a wish, plan or possible situation",
                 "label": {"en": "a wish or plan", "es": "un deseo o plan"}},
                {"id": "req2", "check": "the student gives a reason or a consequence", "label": {"en": "a reason", "es": "una razón"}},
            ],
        },
        {
            "id": "B1-4",
            "titulo": {"en": "Opinions and technology", "es": "Opiniones y tecnología"},
            "objetivo": {"en": "Give and support your opinion about technology and the environment.",
                         "es": "Dar y justificar tu opinión sobre la tecnología y los medios."},
            "gramatica": {"en": ["Linking words", "Defining and non-defining", "Passive voice"],
                          "es": ["Conectores discursivos", "Presente de subjuntivo para emociones"]},
            "vocabulario": {"en": ["Environment and technology"], "es": ["Medios de comunicación", "Opiniones y debates"]},
            "escritura": {"en": "Write 4 to 6 sentences: are social networks good or bad? Give your opinion and one reason.",
                          "es": "Escribe de 4 a 6 frases: ¿las redes sociales son buenas o malas? Da tu opinión y una razón."},
            "checklist": [
                {"id": "req1", "check": "the student gives a clear opinion", "label": {"en": "your opinion", "es": "tu opinión"}},
                {"id": "req2", "check": "the student supports it with a reason or example", "label": {"en": "a reason", "es": "una razón"}},
            ],
        },
        {
            "id": "B1-5",
            "titulo": {"en": "Health and communication", "es": "Salud y comunicación"},
            "objetivo": {"en": "Report what people say and compare healthy habits.",
                         "es": "Contar lo que pasó y no confundir palabras parecidas."},
            "gramatica": {"en": ["Basic reported speech", "Comparatives and superlatives with", "Adjectives ending in -ed"],
                          "es": ["Contraste de pasados"]},
            "vocabulario": {"en": ["Health and wellbeing", "Common word pairs"], "es": ["Pares de palabras"]},
            "escritura": {"en": "Write 4 to 6 sentences about a piece of health advice someone gave you and whether you followed it.",
                          "es": "Escribe de 4 a 6 frases sobre un consejo de salud que alguien te dio y si lo seguiste."},
            "checklist": [
                {"id": "req1", "check": "the student reports advice someone gave them", "label": {"en": "the advice", "es": "el consejo"}},
                {"id": "req2", "check": "the student says whether they followed it", "label": {"en": "if you followed it", "es": "si lo seguiste"}},
            ],
        },
    ],
    "B2": [
        {
            "id": "B2-1",
            "titulo": {"en": "Regrets and hypotheses", "es": "Arrepentimientos e hipótesis"},
            "objetivo": {"en": "Talk about past regrets and imaginary situations, and nuance your opinions.",
                         "es": "Hablar de arrepentimientos y situaciones hipotéticas, y matizar tus opiniones."},
            "gramatica": {"en": ["Third conditional and mixed", "Wish and if only", "Past perfect simple vs past simple"],
                          "es": ["Imperfecto de subjuntivo", "Condicional compuesto"]},
            "vocabulario": {"en": ["Opinions, feelings and relationships"], "es": ["Matizar opiniones"]},
            "escritura": {"en": "Write 4 to 6 sentences about a decision you regret or are happy about. What would be different now if you had decided otherwise?",
                          "es": "Escribe de 4 a 6 frases sobre una decisión de la que te arrepientes o te alegras. ¿Qué sería distinto hoy si hubieras decidido otra cosa?"},
            "checklist": [
                {"id": "req1", "check": "the student describes a past decision", "label": {"en": "the decision", "es": "la decisión"}},
                {"id": "req2", "check": "the student imagines what would be different (a hypothetical or conditional idea)",
                 "label": {"en": "what would be different", "es": "qué sería distinto"}},
            ],
        },
        {
            "id": "B2-2",
            "titulo": {"en": "Work and formal language", "es": "Trabajo y lenguaje formal"},
            "objetivo": {"en": "Describe processes at work and write in a formal register.",
                         "es": "Escribir en registro formal y expresar finalidad y condiciones."},
            "gramatica": {"en": ["Passive voice in all common tenses", "Causative have / get"],
                          "es": ["Subjuntivo con expresiones", "Ser y estar con cambio"]},
            "vocabulario": {"en": ["Work and business"], "es": ["Registro formal"]},
            "escritura": {"en": "Write 4 to 6 sentences of a formal email asking your manager for a day off. Explain why and what has already been done.",
                          "es": "Escribe de 4 a 6 frases de un correo formal pidiéndole a tu jefe un día libre. Explica por qué y cómo dejarás el trabajo organizado."},
            "checklist": [
                {"id": "req1", "check": "the student makes a polite, formal request", "label": {"en": "a formal request", "es": "una petición formal"}},
                {"id": "req2", "check": "the student explains the reason", "label": {"en": "the reason", "es": "el motivo"}},
            ],
        },
        {
            "id": "B2-3",
            "titulo": {"en": "Society and the environment", "es": "Sociedad y medio ambiente"},
            "objetivo": {"en": "Build arguments, contrast ideas and talk about social problems.",
                         "es": "Construir argumentos, contrastar ideas y hablar de problemas sociales."},
            "gramatica": {"en": ["Linking and contrast", "Determiners and quantifiers"],
                          "es": ["Oraciones concesivas", "Conectores para argumentar"]},
            "vocabulario": {"en": ["Environment and society"], "es": ["Medio ambiente y sociedad"]},
            "escritura": {"en": "Write 4 to 6 sentences: should cars be banned from city centres? Give an argument for, one against, and your conclusion.",
                          "es": "Escribe de 4 a 6 frases: ¿se deberían prohibir los carros en el centro de las ciudades? Da un argumento a favor, uno en contra y tu conclusión."},
            "checklist": [
                {"id": "req1", "check": "the student gives an argument for and an argument against", "label": {"en": "arguments for and against", "es": "argumentos a favor y en contra"}},
                {"id": "req2", "check": "the student gives a conclusion", "label": {"en": "your conclusion", "es": "tu conclusión"}},
            ],
        },
        {
            "id": "B2-4",
            "titulo": {"en": "Technology and the media", "es": "Tecnología y medios"},
            "objetivo": {"en": "Report what others say and make deductions about news and technology.",
                         "es": "Contar lo que dijeron otros y describir lo que buscas o necesitas."},
            "gramatica": {"en": ["Reported speech with tense changes", "Modal verbs of deduction", "Defining and non-defining"],
                          "es": ["Estilo indirecto", "Oraciones de relativo"]},
            "vocabulario": {"en": ["Media, technology and the internet"], "es": ["Ciencia, tecnología y medios"]},
            "escritura": {"en": "Write 4 to 6 sentences about a piece of news you read recently: what did it say and what do you think really happened?",
                          "es": "Escribe de 4 a 6 frases sobre una noticia que leíste hace poco: ¿qué decía y qué opinas tú?"},
            "checklist": [
                {"id": "req1", "check": "the student reports what the news said", "label": {"en": "what the news said", "es": "qué decía la noticia"}},
                {"id": "req2", "check": "the student gives their own interpretation or opinion", "label": {"en": "your opinion", "es": "tu opinión"}},
            ],
        },
        {
            "id": "B2-5",
            "titulo": {"en": "Culture and life changes", "es": "Cultura y cambios de vida"},
            "objetivo": {"en": "Talk about experiences, future changes and cultural differences.",
                         "es": "Hablar de cultura, usar expresiones frecuentes y repasar el subjuntivo."},
            "gramatica": {"en": ["Present perfect continuous", "Future continuous and future perfect", "Gerund vs infinitive"],
                          "es": ["Ser y estar con cambio", "Imperfecto de subjuntivo"]},
            "vocabulario": {"en": ["Travel, tourism and culture", "Collocations and word choice"],
                            "es": ["Arte y cultura", "Modismos"]},
            "escritura": {"en": "Write 4 to 6 sentences: imagine your life in five years in another country. What will you have done and what will you be doing?",
                          "es": "Escribe de 4 a 6 frases: si vivieras en otro país, ¿qué costumbres te costaría más aceptar y por qué?"},
            "checklist": [
                {"id": "req1", "check": "the student describes life in another country or culture", "label": {"en": "life in another country", "es": "la vida en otro país"}},
                {"id": "req2", "check": "the student gives reasons or details", "label": {"en": "reasons or details", "es": "razones o detalles"}},
            ],
        },
    ],
}
