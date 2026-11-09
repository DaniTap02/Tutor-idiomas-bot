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
PENALTY_PER_ERROR = {"A1": 10, "A2": 8, "B1": 6, "B2": 6}
MIN_WORDS = {"A1": 5, "A2": 20, "B1": 50, "B2": 40}
# Hablando se dicen menos palabras que escribiendo, y la transcripción puede perder alguna:
# el mínimo de la parte de HABLA es más bajo que el de escritura.
MIN_WORDS_SPEAKING = {"A1": 8, "A2": 20, "B1": 40, "B2": 40}
MISSING_PENALTY = 25  # puntos que se restan por cada requisito de la tarea que falte

# Reglas del calificador propias de cada idioma (se insertan en SYSTEM_PROMPT).
# Español: el bot es para Colombia, pero se acepta cualquier variante (ustedes/vosotros, carro/coche).
# Las tildes que faltan: en A1 y A2 no cuentan como error (casi nadie las escribe en el celular);
# desde B1 sí se listan como error de ortografía. Nunca hacen falso un requisito.
TILDES_CUENTAN = {"A1": False, "A2": False, "B1": True, "B2": True}
LANG_NOTE = {
    "es": (
        "- Spanish from ANY country is correct: Latin American or Spain forms (ustedes or vosotros,\n"
        "  carro or coche, celular or móvil, voseo) are never errors.\n"
        "- A missing written accent (tilde: esta/está, cafe/café, como/cómo) or a missing opening mark\n"
        "  (¿ ¡) never makes a requirement false. {tildes}\n"
    ),
}
_TILDES = {
    True: "You may list it in errors as spelling.",
    False: "Do NOT list it in errors at this level.",
}


def _lang_note(language: str, level: str, is_transcript: bool) -> str:
    nota = LANG_NOTE.get(language, "")
    if not nota:
        return ""
    # En una transcripción las tildes las pone Whisper: nunca son del estudiante.
    return nota.format(tildes=_TILDES[TILDES_CUENTAN.get(level, True) and not is_transcript])

SYSTEM_PROMPT = """You are a fair {language} examiner for CEFR level {level}.
You receive a text written by a student{transcript_note}.
Your job is ONLY to check the text and detect errors. Do not give a level.

How to judge, before anything else:
- Judge the MEANING, never the exact words. There is no expected answer to compare with.
- A requirement is satisfied if the student says it in ANY correct way: a synonym, an equivalent
  expression, a contraction ("I'm" = "I am", "don't" = "do not"), a different but valid structure,
  or a regional variant. "I'm happy" and "I am happy" are equally correct.
- A small spelling slip that does NOT change the meaning (recieve, tomorow, Ibage) still satisfies
  the requirement. You may list it in errors, but the requirement is true.
- When something is only PARTLY there, mark the requirement false and say in `why` exactly what is
  missing, so the student knows what to add. Do not mark it false without saying why.
- Never penalise the student for something the exam did not ask for.
{lang_note}
1. is_in_language: true only if the text is written in {language}.
   Text in any other language (for example Spanish when the exam is in English) must be false.
   A few words borrowed from another language (a city, a name, a dish) do NOT make it false.
2. requirements: for each one, "ok" true only if the text clearly satisfies it, and "why" a very
   short sentence in {feedback_language} saying what is missing (or "" when ok is true).
{requirements}
3. errors: list each real error once (grammar, vocabulary or spelling) that a {level} student
   should be able to avoid. Only list something if the original is actually incorrect: never
   "correct" a sentence that is already right, and never list a contraction, a synonym, a regional
   variant or a mere stylistic alternative. Use an empty list if there are none.
4. feedback: one short encouraging sentence in {feedback_language}.

Reply ONLY with JSON in this exact shape:
{{"is_in_language": true or false,
  "requirements": {{{shape}}},
  "errors": [{{"fragment": "...", "type": "grammar|vocabulary|spelling", "correction": "..."}}],
  "feedback": "..."}}"""


def _call_ollama(system: str, user: str, temperature: float = 0.1) -> dict:
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature, "num_ctx": 2048},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    return json.loads(response.json()["message"]["content"])


VERIFY_PROMPT = """You are a strict {language} grammar checker.
For each numbered item, decide if the fragment contains a REAL mistake (grammar, spelling or a wrong word).
If the fragment is already correct, or the correction is only another way of saying the same thing, answer false.

Reply ONLY with JSON: {{"items": [true or false, ...]}} with one value per item, in the same order."""


def _requisito_ok(respuesta) -> bool:
    """El modelo puede responder un requisito como true/false o como {"ok": ..., "why": ...}.
    Se aceptan las dos formas: un modelo pequeño no siempre respeta la estructura pedida."""
    if isinstance(respuesta, dict):
        respuesta = respuesta.get("ok")
    if isinstance(respuesta, str):
        return respuesta.strip().lower() in ("true", "si", "sí", "yes", "ok")
    return bool(respuesta)


def _requisito_motivo(respuesta) -> str:
    """La explicación corta de por qué falta un requisito, si el modelo la dio."""
    if isinstance(respuesta, dict):
        motivo = respuesta.get("why") or respuesta.get("motivo") or ""
        return str(motivo).strip()[:150]
    return ""


def _verify_errors(errors: list, language: str) -> list:
    """Segunda pasada: descarta falsos errores (frases correctas que el modelo 'corrigió' sin necesidad).
    Si algo sale mal, se conservan los errores originales."""
    if not errors:
        return errors
    try:
        listing = "\n".join(
            f"{i}. fragment: {e.get('fragment', '')} | correction: {e.get('correction', '')}"
            for i, e in enumerate(errors, start=1)
        )
        verdict = _call_ollama(VERIFY_PROMPT.format(language=LANGUAGE_NAME[language]), listing)
        items = verdict.get("items", [])
        if len(items) != len(errors):
            return errors
        return [e for e, real in zip(errors, items) if real is True or str(real).lower() == "true"]
    except Exception:
        return errors


def grade(
    text: str,
    level: str,
    language: str,
    checklist: list[dict],
    is_transcript: bool = False,
    feedback_language: str = "Spanish",
    skill: str = "writing",
) -> dict:
    """Devuelve:
    {"score": 0-100, "task_completed": bool, "errors": [...], "feedback": str, "needs_rewrite": bool}

    needs_rewrite=True significa que el texto no se pudo evaluar (muy corto o en otro idioma):
    el bot debe pedirle al usuario que lo escriba (o lo grabe) de nuevo, sin contar el intento.

    skill: "writing" o "speaking". Solo cambia los mensajes en español que ve el estudiante
    (en la parte de habla se le dice "audio"/"habla", no "texto"/"escribe") y el mínimo de palabras.
    is_transcript: el texto viene de una transcripción (se ignoran puntuación y mayúsculas).
    """
    hablando = skill == "speaking"
    minimo = (MIN_WORDS_SPEAKING if hablando else MIN_WORDS)[level]

    # 1) Largo mínimo: lo decide el código, no el modelo
    if len(text.split()) < minimo:
        if hablando:
            aviso = (
                f"Tu audio es muy corto. Habla al menos {minimo} palabras "
                f"en {LANGUAGE_NAME_ES[language]}."
            )
        else:
            aviso = (
                f"Tu texto es muy corto. Escribe al menos {minimo} palabras "
                f"en {LANGUAGE_NAME_ES[language]}."
            )
        return {
            "score": 0,
            "task_completed": False,
            "errors": [],
            "needs_rewrite": True,
            "feedback": aviso,
            "missing": [c["id"] for c in checklist],
        }

    # 2) El modelo responde preguntas simples en JSON
    system = SYSTEM_PROMPT.format(
        language=LANGUAGE_NAME[language],
        level=level,
        requirements="\n".join(f"   {c['id']}: {c['check']}" for c in checklist),
        shape=", ".join(f'"{c["id"]}": {{"ok": true or false, "why": "..."}}' for c in checklist),
        feedback_language=feedback_language,
        lang_note=_lang_note(language, level, is_transcript),
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
            "feedback": (
                f"Debes hablar en {LANGUAGE_NAME_ES[language]}."
                if hablando
                else f"Tu texto debe estar escrito en {LANGUAGE_NAME_ES[language]}."
            ),
            "missing": [c["id"] for c in checklist],
        }

    answers = result.get("requirements", {}) or {}
    missing = [c for c in checklist if not _requisito_ok(answers.get(c["id"]))]
    errors = _verify_errors(result.get("errors", []) or [], language)

    score = max(0, 100 - PENALTY_PER_ERROR[level] * len(errors) - MISSING_PENALTY * len(missing))

    if missing:
        # Además de QUÉ falta, se dice POR QUÉ cuando el modelo lo explicó: una respuesta a medias
        # no se marca mal sin más, se le indica qué le falta para completarla.
        lineas = []
        for c in missing:
            motivo = _requisito_motivo(answers.get(c["id"]))
            lineas.append(f"• {c['label_es']}" + (f" — {motivo}" if motivo else ""))
        feedback = "Te faltó incluir:\n" + "\n".join(lineas)
    else:
        feedback = result.get("feedback", "")

    return {
        "score": score,
        "task_completed": not missing,
        "errors": errors,
        "needs_rewrite": False,
        "feedback": feedback,
        "missing": [c["id"] for c in missing],
    }
