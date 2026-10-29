"""Agente calificador.

El LLM NO decide el nivel: solo detecta errores y si se cumplió la tarea.
El puntaje lo calcula el código, así un modelo pequeño (7B) es suficiente para A1.
Para cambiar de modelo basta con cambiar OLLAMA_MODEL (variable de entorno).
"""
import json
import os

import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")  # ajusta al tag que tengas: `ollama list`

LANGUAGE_NAME = {"en": "English", "es": "Spanish"}

# Puntos que se restan por error. Valores iniciales: calibrar probando con textos reales.
PENALTY_PER_ERROR = {"A1": 10, "A2": 10, "B1": 8, "B2": 6}

SYSTEM_PROMPT = """You are a fair {language} examiner for CEFR level {level}.
You receive a text written by a student{transcript_note}.
Your job is ONLY to detect errors and check the task. Do not give a level.

Task the student had to complete: the text must include {checklist}.

Rules:
- At level {level}, ignore mistakes that belong to higher levels; only count errors that
  a {level} student should be able to avoid.
- List each real error once (grammar, vocabulary or spelling).
- Do not invent errors. If the text is correct, return an empty list.

Reply ONLY with JSON in this exact shape:
{{"task_completed": true or false,
  "errors": [{{"fragment": "...", "type": "grammar|vocabulary|spelling", "correction": "..."}}],
  "feedback": "one or two short encouraging sentences in {feedback_language}"}}"""


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
    checklist: str,
    is_transcript: bool = False,
    feedback_language: str = "Spanish",
) -> dict:
    """Devuelve {"score": 0-100, "task_completed": bool, "errors": [...], "feedback": str}."""
    system = SYSTEM_PROMPT.format(
        language=LANGUAGE_NAME[language],
        level=level,
        checklist=checklist,
        feedback_language=feedback_language,
        transcript_note=(
            " (it is an automatic transcription of speech: ignore punctuation and capitalization)"
            if is_transcript
            else ""
        ),
    )
    result = _call_ollama(system, text)

    errors = result.get("errors", []) or []
    task_completed = bool(result.get("task_completed", False))
    score = 0 if not task_completed else max(0, 100 - PENALTY_PER_ERROR[level] * len(errors))

    return {
        "score": score,
        "task_completed": task_completed,
        "errors": errors,
        "feedback": result.get("feedback", ""),
    }
