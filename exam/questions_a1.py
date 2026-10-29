"""Banco del examen A1. Lectura se califica por código; escritura y habla las califica el agente."""

READING = {
    "en": [
        {"q": "She ___ a student.", "options": ["is", "are", "am"], "answer": 0},
        {"q": "I ___ from Colombia.", "options": ["is", "am", "are"], "answer": 1},
        {"q": "What is the opposite of 'big'?", "options": ["small", "tall", "fast"], "answer": 0},
        {"q": "They ___ two brothers.", "options": ["has", "have", "is"], "answer": 1},
        {"q": "Choose the correct sentence.", "options": ["He like pizza.", "He likes pizza.", "He liking pizza."], "answer": 1},
    ],
    "es": [
        {"q": "Yo ___ estudiante.", "options": ["soy", "eres", "es"], "answer": 0},
        {"q": "Ella ___ en Bogotá.", "options": ["vive", "vivo", "viven"], "answer": 0},
        {"q": "¿Cuál es el opuesto de 'grande'?", "options": ["pequeño", "alto", "rápido"], "answer": 0},
        {"q": "Nosotros ___ dos hermanos.", "options": ["tengo", "tenemos", "tienen"], "answer": 1},
        {"q": "Elige la frase correcta.", "options": ["Me gusta el café.", "Me gustan el café.", "Yo gusto café."], "answer": 0},
    ],
}

WRITING_PROMPT = {
    "en": "Write 3 or 4 short sentences introducing yourself: your name, where you are from, and something you like.",
    "es": "Escribe 3 o 4 frases cortas presentándote: tu nombre, de dónde eres y algo que te gusta.",
}

SPEAKING_PROMPT = {
    "en": "Send a voice note (15 to 30 seconds): say your name, where you live, and one thing you like.",
    "es": "Envía una nota de voz (15 a 30 segundos): di tu nombre, dónde vives y algo que te gusta.",
}

# Requisitos de la tarea. El calificador verifica cada uno por separado (más fiable en modelos chicos).
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


def score_reading(language: str, answers: list[int]) -> float:
    """answers: índice elegido por el usuario por pregunta. Devuelve 0-100."""
    questions = READING[language]
    correct = sum(1 for q, a in zip(questions, answers) if q["answer"] == a)
    return 100 * correct / len(questions)
