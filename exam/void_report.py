"""Resumen de las preguntas anuladas:  python -m exam.void_report
Lee voided_questions.jsonl (o la ruta de EXAM_VOID_LOG) y cuenta anuladas por motivo, por parte
del examen y por tema, para detectar problemas recurrentes del generador.

Filtrar solo una parte:  python -m exam.void_report listening
"""
import json
import os
import sys
from collections import Counter

VOID_LOG = os.getenv("EXAM_VOID_LOG", "voided_questions.jsonl")

MOTIVOS = {
    "format": "formato inválido",
    "non_latin": "caracteres no latinos",
    "too_long": "pregunta u opciones demasiado largas",
    "passage_length": "texto con largo fuera de rango",
    "forbidden_word": "palabra prohibida del nivel",
    "redundant": "la respuesta correcta repite una palabra (ej. 'short short')",
    "no_context": "falta contexto para decidir la respuesta",
    "no_gender_cue": "pronombre con género sin pista de género en el contexto",
    "key_invalid": "la clave no responde correctamente",
    "ambiguous": "más de una opción válida",
    "no_evidence": "no hay nada escrito que descarte las otras opciones (pregunta ambigua)",
    "wrong_level": "nivel inadecuado",
    "off_topic": "no mide el tema",
    "verify_error": "falló la verificación del modelo",
    # Solo en la parte de ESCUCHA (kind="listening")
    "not_said": "la respuesta no se dice en el audio: habría que adivinarla",
    "hard_to_catch": "no se alcanza a captar oyendo una o dos veces",
    "not_speakable": "no suena a alguien hablando (comillas, etiquetas, fórmulas de carta)",
    "written_ref": "la pregunta habla de «el texto» o pide leer, y el estudiante solo escucha",
}

KINDS = {
    "grammar": "lectura · gramática",
    "vocab": "lectura · vocabulario",
    "passage": "lectura · mini-texto",
    "listening": "escucha",
}


def descripcion(reason: str) -> str:
    if reason.startswith("llm_error:"):
        return f"el modelo no respondió bien ({reason.split(':', 1)[1]})"
    return MOTIVOS.get(reason, "")


if __name__ == "__main__":
    if not os.path.exists(VOID_LOG):
        print(f"Aún no hay preguntas anuladas ({VOID_LOG}).")
        raise SystemExit
    rows = [json.loads(l) for l in open(VOID_LOG, encoding="utf-8") if l.strip()]

    filtro = sys.argv[1] if len(sys.argv) > 1 else None
    if filtro:
        rows = [r for r in rows if r.get("kind") == filtro]
        print(f"Filtrando por parte: {filtro} ({KINDS.get(filtro, '?')})")
        if not rows:
            print("No hay anuladas de esa parte.")
            raise SystemExit

    print(f"Preguntas anuladas: {len(rows)}\n\nPor parte del examen:")
    for kind, n in Counter(r.get("kind") or "?" for r in rows).most_common():
        print(f"  {n:4d}  {kind}: {KINDS.get(kind, '')}")

    print("\nPor motivo:")
    for reason, n in Counter(r["reason"] for r in rows).most_common():
        print(f"  {n:4d}  {reason}: {descripcion(reason)}")

    print("\nPor tema (los 8 con más anuladas):")
    for topic, n in Counter(f"{r['level']} | {r['topic'][:60]}" for r in rows).most_common(8):
        print(f"  {n:4d}  {topic}")

    print("\nÚltimas 5:")
    for r in rows[-5:]:
        print(f"  [{r.get('kind')} · {r['reason']}] {r['q']}  -> {r['options']}")
