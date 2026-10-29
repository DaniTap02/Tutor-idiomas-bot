"""Agente calificador.

El LLM NO decide el nivel ni si "pasa": solo responde preguntas simples (¿está en el idioma?,
¿cumple cada requisito?, ¿qué errores hay?). El código aplica las reglas y calcula el puntaje.
Así un modelo pequeño (7B) es suficiente, y los casos raros ("hola", otro idioma) los
atrapa el código antes de depender del modelo.

Para cambiar de modelo basta con cambiar OLLAMA_MODEL (variable de entorno).
"""
import json
import os

import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")  # ajusta al tag que tengas: `ollama list`

LANGUAGE_NAME = {"en": "English", "es": "Spanish"}
LANGUAGE_NAME_ES = {"en": "inglés", "es": "español"}

# Valores iniciales: calibrar probando con textos reales.
PENALTY_PER_ERROR = {"A1": 10, "A2": 10, "B1": 8, "B2": 6}
MIN_WORDS = {"A1": 5, "A2": 10, "B1": 20, "B2": 40}
MISSING_PENALTY = 25  # puntos que se restan por cada requisito de la tarea que falte

SYSTEM_PROMPT = """You are a fair {language} examiner for CEFR level {level}.
You receive a text written by a student{transcript_note}.
Your job is ONLY to check the text and detect errors. Do not give a level.

1. is_in_language: true only if the text is written in {language}.
   Text in any other language (for example Spanish when the exam is in English) must be false.
2. requirements: answer true only if the text clearly satisfies the requirement.
{requirements}
3. errors: list each real error once (grammar, vocabulary or spelling) that a {level} student
   should be able to avoid. Do not invent errors. Use an empty list if there are none.
4. feedback: one short encouraging sentence in {feedback_language}.

Reply ONLY with JSON in this exact shape:
{{"is_in_language": true or false,
  "requirements": {{{shape}}},
  "errors": [{{"fragment": "...", "type": "grammar|vocabulary|spelling", "correction": "..."}}],
  "feedback": "..."}}"""


def _call_ollama(system: str, user: str) -> dict:
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    return json.loads(response.json()["message"]["content"])


def grade(
    text: str,
    level: str,
    language: str,
    checklist: list[dict],
    is_transcript: bool = False,
    feedback_language: str = "Spanish",
) -> dict:
    """Devuelve:
    {"score": 0-100, "task_completed": bool, "errors": [...], "feedback": str, "needs_rewrite": bool}

    needs_rewrite=True significa que el texto no se pudo evaluar (muy corto o en otro idioma):
    el bot debe pedirle al usuario que lo escriba de nuevo, sin contar el intento.
    """
    # 1) Largo mínimo: lo decide el código, no el modelo
    if len(text.split()) < MIN_WORDS[level]:
        return {
            "score": 0,
            "task_completed": False,
            "errors": [],
            "needs_rewrite": True,
            "feedback": (
                f"Tu texto es muy corto. Escribe al menos {MIN_WORDS[level]} palabras "
                f"en {LANGUAGE_NAME_ES[language]}."
            ),
        }

    # 2) El modelo responde preguntas simples en JSON
    system = SYSTEM_PROMPT.format(
        language=LANGUAGE_NAME[language],
        level=level,
        requirements="\n".join(f"   {c['id']}: {c['check']}" for c in checklist),
        shape=", ".join(f'"{c["id"]}": true or false' for c in checklist),
        feedback_language=feedback_language,
        transcript_note=(
            " (it is an automatic transcription of speech: ignore punctuation and capitalization)"
            if is_transcript
            else ""
        ),
    )
    result = _call_ollama(system, text)

    # 3) El código aplica las reglas
    if not bool(result.get("is_in_language", False)):
        return {
            "score": 0,
            "task_completed": False,
            "errors": [],
            "needs_rewrite": True,
            "feedback": f"Tu texto debe estar escrito en {LANGUAGE_NAME_ES[language]}.",
        }

    answers = result.get("requirements", {}) or {}
    missing = [c for c in checklist if not answers.get(c["id"], False)]
    errors = result.get("errors", []) or []

    score = max(0, 100 - PENALTY_PER_ERROR[level] * len(errors) - MISSING_PENALTY * len(missing))

    if missing:
        feedback = "Te faltó incluir: " + ", ".join(c["label_es"] for c in missing) + "."
    else:
        feedback = result.get("feedback", "")

    return {
        "score": score,
        "task_completed": not missing,
        "errors": errors,
        "needs_rewrite": False,
        "feedback": feedback,
    }
