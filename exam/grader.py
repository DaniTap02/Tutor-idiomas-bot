"""Agente calificador.

El LLM NO decide el nivel ni si "pasa": solo responde preguntas simples (¿está en el idioma?,
¿cumple cada requisito?, ¿cómo queda cada oración corregida?). El código aplica las reglas y calcula
el puntaje:
  - idioma: el código cuenta palabras frecuentes de cada idioma antes de preguntarle al modelo;
  - requisitos: el modelo cita las palabras del estudiante que lo cumplen, el código comprueba que la
    cita esté en el texto y una segunda revisión confirma que esa cita de verdad cumple el requisito;
  - errores: el modelo corrige cada oración y el código compara; lo que cambió es un error.
Así un modelo pequeño (7B) es suficiente, y los casos raros ("hola", otro idioma) los
atrapa el código antes de depender del modelo.

Variables de entorno (todas opcionales):
  OLLAMA_MODEL    modelo a usar (por defecto qwen2.5:7b)
  OLLAMA_NUM_CTX  tamaño de contexto (por defecto 2048; súbelo si usas textos largos y tu RAM lo aguanta)
  OLLAMA_TIMEOUT  segundos de espera por llamada (por defecto 120)
  OLLAMA_URL      dirección de Ollama
"""
import difflib
import json
import os
import re
import unicodedata

import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")  # ajusta al tag que tengas: `ollama list`
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX") or 2048)
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT") or 120)

LANGUAGE_NAME = {"en": "English", "es": "Spanish"}
LANGUAGE_NAME_ES = {"en": "inglés", "es": "español"}

# Mensajes fijos que ve el estudiante, en el idioma de la interfaz (ui_language). El examen usa
# español; las lecciones del tutor usan el idioma que se estudia.
MENSAJES = {
    "es": {
        "corto_habla": "Tu audio es muy corto. Habla al menos {n} palabras en {idioma}.",
        "corto_texto": "Tu texto es muy corto. Escribe al menos {n} palabras en {idioma}.",
        "idioma_habla": "Debes hablar en {idioma}.",
        "idioma_texto": "Tu texto debe estar escrito en {idioma}.",
        "falto": "Te faltó incluir:",
        "nombres": LANGUAGE_NAME_ES,
    },
    "en": {
        "corto_habla": "Your audio is too short. Say at least {n} words in {idioma}.",
        "corto_texto": "Your text is too short. Write at least {n} words in {idioma}.",
        "idioma_habla": "You must speak in {idioma}.",
        "idioma_texto": "Your text must be written in {idioma}.",
        "falto": "You still need to include:",
        "nombres": LANGUAGE_NAME,
    },
}

# Valores iniciales: calibrar probando con textos reales.
PENALTY_PER_ERROR = {"A1": 10, "A2": 8, "B1": 6, "B2": 6}
MIN_WORDS = {"A1": 5, "A2": 20, "B1": 50, "B2": 60}
# Hablando se dicen menos palabras que escribiendo, y la transcripción puede perder alguna:
# el mínimo de la parte de HABLA es más bajo que el de escritura.
MIN_WORDS_SPEAKING = {"A1": 8, "A2": 20, "B1": 40, "B2": 40}
MISSING_PENALTY = 25  # puntos que se restan por cada requisito de la tarea que falte
# Tope de errores que descuentan puntos (textos largos: un modelo pequeño puede inventar errores).
# Los niveles que no aparecen aquí no tienen tope (A1, A2 y B2 siguen como antes).
MAX_ERRORS_COUNTED = {"B1": 5}

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
2. requirements: for each one, "ok" true only if the text clearly satisfies it; "quote" COPIES the
   exact words of the student that satisfy it (copy them, do not explain or invent them; "" if
   nothing in the text satisfies it, and then ok must be false); and "why" a very short sentence in
   {feedback_language} saying what is missing (or "" when ok is true). Something close but different
   does not count: staying at home is not going somewhere, describing a problem is not asking for a
   solution.
{requirements}
3. feedback: one short encouraging sentence in {feedback_language}.
(The errors are checked separately: do not list them.)

Reply ONLY with JSON in this exact shape:
{{"is_in_language": true or false,
  "requirements": {{{shape}}},
  "feedback": "..."}}"""


def _call_ollama(system: str, user: str, temperature: float = 0.1) -> dict:
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature, "num_ctx": OLLAMA_NUM_CTX},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    return json.loads(response.json()["message"]["content"])


# LOS ERRORES: el modelo CORRIGE el texto oración por oración y el CÓDIGO compara cada oración con su
# corrección; lo que cambió es un error. Antes el modelo listaba los errores y una segunda pasada los
# confirmaba, y con qwen2.5:7b fallaban las dos cosas: no listaba "yo es de Colombia" y la segunda pasada
# borraba "I go" -> "I went". En la prueba real, textos llenos de errores sacaban 100.
CORRECT_PROMPT = """You are a careful {language} proofreader for a CEFR {level} student{transcript_note}.
Each numbered item is one sentence written by the student. For each one, write the SAME sentence with
ONLY its real mistakes corrected: wrong verb forms or tenses, wrong agreement, missing words that make
it ungrammatical, misspelled words, or a word that is wrong in that sentence.
- Change as FEW words as possible. Keep everything else exactly as the student wrote it.
- If the sentence is already correct, copy it EXACTLY, unchanged.
- Never change a correct sentence to make it more elegant: no synonyms, no style changes, no
  contractions or expansions ("I'm" and "I am" are both correct), no regional variants.
{lang_note}
Reply ONLY with JSON: {{"items": ["corrected sentence 1", "corrected sentence 2", ...]}} with one
sentence per item, in the same order."""

# LOS REQUISITOS: el modelo ve cada requisito con las palabras del estudiante que lo cumplen (la cita) y
# dice si de verdad lo cumplen. En la prueba real, "I stayed at home" contaba como "a dónde fuiste".
REQ_CHECK_PROMPT = """You check if a student's text satisfies the requirements of a {language} writing task.
You get the full text and, for each numbered item, a requirement and the words of the student that are
supposed to satisfy it. Answer true only if the text really does what the requirement asks.
- Judge ONLY the CONTENT. Do NOT judge grammar, spelling or style: they are graded separately.
  A sentence with mistakes still satisfies the requirement if its meaning does ("My name Laura" says
  the name; "We eated fish" says what they ate; "I goed to the beach" is a past tense).
- Judge the WHOLE text: if the quoted words do not satisfy it but another part of the text does,
  answer true.
- A synonym or another way of saying it counts. Every past tense counts as past (in Spanish the
  pretérito "fui, comí" and the imperfecto "hacía, nadábamos" are both past).
- Something close but different does NOT count: staying at home is not going somewhere, describing a
  problem is not asking for a solution.
"why": a very short sentence ALWAYS in {feedback_language} (even if the text is in another language)
saying what is missing ("" when ok is true).

Reply ONLY with JSON: {{"items": [{{"ok": true or false, "why": "..."}}, ...]}} one per item, in order."""

_NO_PALABRA = re.compile(r"[^0-9a-zñß]+", re.I)   # se aplica después de quitar las tildes
_TOKEN = re.compile(r"[^\W_]+(?:'[^\W_]+)?")         # palabras del texto, con su apóstrofo (I'm, don't)
_ORACIONES = re.compile(r"(?<=[.!?])\s+")
MAX_ORACIONES = 15   # textos largos: se corrigen las primeras (un 7B se pierde con listas largas)

# Palabras muy frecuentes de cada idioma, para saber POR CÓDIGO si el texto está en otro idioma (cuando
# Lara no está disponible y el modelo no lo nota: en la prueba real calificó con 100 un texto en español
# del examen de inglés). Solo palabras que no existen en el otro idioma.
FRECUENTES = {
    "en": {"the", "and", "is", "are", "was", "were", "to", "of", "my", "with", "for", "it", "we",
           "you", "at", "on", "but", "very", "this", "have", "i", "went", "like"},
    "es": {"el", "la", "los", "las", "de", "del", "que", "y", "en", "un", "una", "es", "con", "por",
           "para", "mi", "fue", "muy", "pero", "se", "al", "lo", "como", "yo", "soy", "estoy"},
}


# Requisitos de FORMA que el código sabe revisar. Un requisito del banco los usa con "patron": "<clave>".
# Si el patrón aparece en el texto, el requisito no pasa por la segunda revisión del modelo (en la prueba
# real, esa revisión decía que «Sin embargo… porque… Además» no tenía conectores). Con "basta": True el
# requisito es SOLO de forma y el patrón decide (los conectores); sin él, el patrón confirma la forma y el
# contenido lo juzga la primera respuesta del modelo (el pasado: "algo que hiciste, en pasado").
PATRONES = {
    "conectores": {
        "en": r"\b(because|however|although|even though|so|in addition|moreover|furthermore|therefore|"
              r"whereas|but|also|while|despite|in spite of|on the other hand|nevertheless|first|finally)\b",
        "es": r"\b(porque|sin embargo|aunque|así que|además|por lo tanto|pero|también|mientras|en cambio|"
              r"por eso|no obstante|a pesar de|por un lado|por otro lado|en primer lugar|finalmente|ya que)\b",
    },
    "conectores_b2": {
        "en": r"\b(however|although|even though|whereas|while|despite|in spite of|nevertheless|"
              r"on the other hand|as long as|provided that|unless|in case|therefore|moreover)\b",
        "es": r"\b(sin embargo|aunque|no obstante|a pesar de|en cambio|mientras que|por un lado|"
              r"por otro lado|por lo tanto|ya que|puesto que|siempre que|a menos que)\b",
    },
    "pasado": {
        "en": r"\b(was|were|went|did|had|saw|ate|made|took|came|got|bought|swam|met|left|felt|"
              r"found|gave|told|wrote|\w{2,}ed)\b",
        "es": r"\b(fui|fue|fuimos|fueron|estuve|estuvo|estuvimos|tuve|tuvo|hice|hizo|hicimos|vi|vio|"
              r"vimos|di|dio|\w+(?:é|ó|aste|iste|aron|ieron|aba|aban|ábamos|ía|ían|íamos))\b",
    },
}


def _patron_ok(c: dict, text: str, language: str) -> bool:
    """True si el requisito tiene un patrón de forma y aparece en el texto."""
    patron = PATRONES.get(c.get("patron", ""), {}).get(language)
    return bool(patron) and re.search(patron, text, re.I) is not None


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _palabras(texto: str) -> list[str]:
    """Palabras en minúscula, sin signos ni tildes (para comparar citas con el texto del estudiante)."""
    return [p for p in _NO_PALABRA.split(_sin_tildes((texto or "").lower())) if p]


def _otro_idioma(texto: str, language: str) -> bool:
    """True si el texto está claramente en el OTRO idioma del bot (cuenta palabras frecuentes)."""
    otro = "es" if language == "en" else "en"
    palabras = _palabras(texto)
    propias = sum(1 for p in palabras if p in FRECUENTES.get(language, ()))
    ajenas = sum(1 for p in palabras if p in FRECUENTES.get(otro, ()))
    return ajenas >= 3 and ajenas > 2 * propias


def _esta_en_texto(cita: str, texto: str) -> bool:
    """La cita está COPIADA del texto del estudiante. Se comparan PARES de palabras seguidas: palabras
    sueltas no bastan ("Me llamo Ana Torres" comparte "me", "ana" y "torres" con una carta firmada por
    Ana Torres sin estar en ella). Se acepta una cita aproximada (la mitad de los pares), no una inventada."""
    citadas = _palabras(cita)
    fuente = _palabras(texto)
    if not citadas:
        return False
    if len(citadas) == 1:
        return citadas[0] in fuente
    pares_fuente = set(zip(fuente, fuente[1:]))
    pares = list(zip(citadas, citadas[1:]))
    return sum(1 for p in pares if p in pares_fuente) / len(pares) >= 0.5


def _comparables(tokens: list[str], tildes: bool) -> list[str]:
    """Las palabras como se comparan: sin mayúsculas, y sin tildes si en este nivel no cuentan."""
    return [t.lower() if tildes else _sin_tildes(t.lower()) for t in tokens]


def _diferencias(original: str, corregida: str, tildes: bool) -> list[dict]:
    """Los errores de UNA oración: los trozos que la corrección cambió (con una palabra de contexto a
    cada lado, para que el estudiante vea dónde está). La puntuación y las mayúsculas no cuentan."""
    a, b = _TOKEN.findall(original), _TOKEN.findall(corregida)
    ca, cb = _comparables(a, tildes), _comparables(b, tildes)
    if ca == cb:
        return []
    matcher = difflib.SequenceMatcher(None, ca, cb, autojunk=False)
    if matcher.ratio() < 0.5:   # la reescribió entera: se cuenta como UN error de la oración
        return [{"fragment": original.strip(), "type": "grammar", "correction": corregida.strip()}]
    errores = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        antes, despues = a[i1:i2], b[j1:j2]
        tipo = "grammar"
        if len(antes) == 1 and len(despues) == 1 and difflib.SequenceMatcher(
                None, ca[i1], cb[j1]).ratio() >= 0.75:
            tipo = "spelling"
        izq = a[max(0, i1 - 1):i1]
        der = a[i2:i2 + 1]
        errores.append({
            "fragment": " ".join(izq + antes + der),
            "type": tipo,
            "correction": " ".join(izq + despues + der),
        })
    return errores


def _corregir(text: str, language: str, level: str, is_transcript: bool) -> list[dict]:
    """Los errores del texto (ver CORRECT_PROMPT). Si el modelo falla o responde mal, no se cuenta
    ningún error: es una falla del sistema y nunca se castiga al estudiante por ella."""
    oraciones = [o for o in _ORACIONES.split(text.strip()) if _TOKEN.search(o)][:MAX_ORACIONES]
    if not oraciones:
        return []
    system = CORRECT_PROMPT.format(
        language=LANGUAGE_NAME[language], level=level,
        lang_note=_lang_note(language, level, is_transcript),
        transcript_note=(" (an automatic transcription of speech: ignore punctuation and capitalization)"
                         if is_transcript else ""),
    )
    try:
        items = _call_ollama(system, "\n".join(f"{i}. {o}" for i, o in enumerate(oraciones, start=1)),
                             temperature=0.0).get("items", [])
    except Exception:
        return []
    if not isinstance(items, list) or len(items) != len(oraciones):
        return []
    tildes = language == "es" and TILDES_CUENTAN.get(level, True) and not is_transcript
    errores = []
    for original, corregida in zip(oraciones, items):
        corregida = re.sub(r"^\s*\d+[.)]\s*", "", str(corregida or ""))   # "1. ..." si el modelo numeró
        if corregida.strip():
            errores.extend(_diferencias(original, corregida, tildes))
    return errores


def _revisar_requisitos(checklist: list[dict], answers: dict, text: str, language: str,
                        feedback_language: str) -> dict:
    """Segunda revisión de los requisitos que el modelo dio por cumplidos con una cita: ¿esas palabras
    de verdad cumplen el requisito? Devuelve {id: {"ok": False, "why": ...}} con los que NO lo cumplen.
    Si la revisión falla, se respeta la primera respuesta (no se castiga por una falla del sistema)."""
    revisar = [c for c in checklist
               if isinstance(answers.get(c["id"]), dict) and _requisito_ok(answers[c["id"]], text)
               and str(answers[c["id"]].get("quote") or "").strip()
               and not _patron_ok(c, text, language)]   # lo que el código ve en el texto no se revisa
    if not revisar:
        return {}
    listing = f"Full text: {text}\n\n" + "\n".join(
        f'{i}. requirement: {c["check"]}\n   student\'s words: "{answers[c["id"]]["quote"]}"'
        for i, c in enumerate(revisar, start=1))
    try:
        items = _call_ollama(REQ_CHECK_PROMPT.format(language=LANGUAGE_NAME[language],
                                                     feedback_language=feedback_language),
                             listing, temperature=0.0).get("items", [])
    except Exception:
        return {}
    if not isinstance(items, list) or len(items) != len(revisar):
        return {}
    return {c["id"]: {"ok": False, "why": _requisito_motivo(r)}
            for c, r in zip(revisar, items) if not _requisito_ok(r)}


def _requisito_ok(respuesta, texto: str = "") -> bool:
    """El modelo puede responder un requisito como true/false o como {"ok": ..., "quote": ..., "why": ...}.
    Se aceptan las dos formas: un modelo pequeño no siempre respeta la estructura pedida.

    Si trae "quote", la cita debe estar de verdad en el texto: así el código comprueba lo que el modelo
    afirma (en la prueba real daba por cumplido "pide una solución" en una carta que no pedía ninguna).
    Si el modelo no devolvió el campo, es una falla de formato del sistema: no se castiga al estudiante."""
    if isinstance(respuesta, dict):
        if "quote" in respuesta and texto and not _esta_en_texto(str(respuesta.get("quote") or ""), texto):
            return False
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


def grade(
    text: str,
    level: str,
    language: str,
    checklist: list[dict],
    is_transcript: bool = False,
    feedback_language: str = "Spanish",
    skill: str = "writing",
    min_words: int | None = None,
    ui_language: str = "es",
) -> dict:
    """Devuelve:
    {"score": 0-100, "task_completed": bool, "errors": [...], "feedback": str, "needs_rewrite": bool}

    needs_rewrite=True significa que el texto no se pudo evaluar (muy corto o en otro idioma):
    el bot debe pedirle al usuario que lo escriba (o lo grabe) de nuevo, sin contar el intento.

    skill: "writing" o "speaking". Solo cambia los mensajes en español que ve el estudiante
    (en la parte de habla se le dice "audio"/"habla", no "texto"/"escribe") y el mínimo de palabras.
    is_transcript: el texto viene de una transcripción (se ignoran puntuación y mayúsculas).
    min_words: mínimo de palabras propio (las escrituras cortas de las lecciones); por defecto el del examen.
    ui_language: idioma de los mensajes fijos ("es" en el examen; el que se estudia en las lecciones).
    """
    hablando = skill == "speaking"
    minimo = min_words if min_words is not None else (MIN_WORDS_SPEAKING if hablando else MIN_WORDS)[level]
    textos = MENSAJES.get(ui_language, MENSAJES["es"])
    idioma = textos["nombres"][language]

    # 1) Largo mínimo: lo decide el código, no el modelo
    if len(text.split()) < minimo:
        aviso = textos["corto_habla" if hablando else "corto_texto"].format(n=minimo, idioma=idioma)
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
        shape=", ".join(f'"{c["id"]}": {{"ok": true or false, "quote": "...", "why": "..."}}' for c in checklist),
        feedback_language=feedback_language,
        lang_note=_lang_note(language, level, is_transcript),
        transcript_note=(
            " (it is an automatic transcription of speech: ignore punctuation and capitalization)"
            if is_transcript
            else ""
        ),
    )
    # El idioma lo revisa también el CÓDIGO: así no hace falta llamar al modelo si está en el otro idioma
    result = {"is_in_language": False} if _otro_idioma(text, language) else _call_ollama(system, text)

    # 3) El código aplica las reglas
    if not bool(result.get("is_in_language", False)):
        return {
            "score": 0,
            "task_completed": False,
            "errors": [],
            "needs_rewrite": True,
            "feedback": textos["idioma_habla" if hablando else "idioma_texto"].format(idioma=idioma),
            "missing": [c["id"] for c in checklist],
        }

    answers = dict(result.get("requirements", {}) or {})
    answers.update(_revisar_requisitos(checklist, answers, text, language, feedback_language))
    # Requisitos solo de forma (los conectores): si el código los ve en el texto, se cumplen
    answers.update({c["id"]: True for c in checklist if c.get("basta") and _patron_ok(c, text, language)})
    missing = [c for c in checklist if not _requisito_ok(answers.get(c["id"]), text)]
    errors = _corregir(text, language, level, is_transcript)

    cap = MAX_ERRORS_COUNTED.get(level)
    counted = len(errors) if cap is None else min(len(errors), cap)
    score = max(0, 100 - PENALTY_PER_ERROR[level] * counted - MISSING_PENALTY * len(missing))

    if missing:
        # Además de QUÉ falta, se dice POR QUÉ cuando el modelo lo explicó: una respuesta a medias
        # no se marca mal sin más, se le indica qué le falta para completarla.
        lineas = []
        for c in missing:
            motivo = _requisito_motivo(answers.get(c["id"]))
            lineas.append(f"• {c['label_es']}" + (f" — {motivo}" if motivo else ""))
        feedback = textos["falto"] + "\n" + "\n".join(lineas)
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
