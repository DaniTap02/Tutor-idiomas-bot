"""Resumen de las preguntas anuladas:  python -m exam.void_report
Lee voided_questions.jsonl (o la ruta de EXAM_VOID_LOG) y cuenta anuladas por motivo y por tema,
para detectar problemas recurrentes del generador."""
import json
import os
from collections import Counter

VOID_LOG = os.getenv("EXAM_VOID_LOG", "voided_questions.jsonl")

MOTIVOS = {
    "format": "formato inválido",
    "non_latin": "caracteres no latinos",
    "too_long": "pregunta u opciones demasiado largas",
    "passage_length": "mini-texto con largo fuera de rango",
    "forbidden_word": "palabra prohibida del nivel",
    "redundant": "la respuesta correcta repite una palabra (ej. 'short short')",
    "no_context": "falta contexto para decidir la respuesta",
    "no_gender_cue": "pronombre con género sin pista de género en el contexto",
    "key_invalid": "la clave no completa bien la oración",
    "ambiguous": "más de una opción válida",
    "wrong_level": "nivel inadecuado",
    "off_topic": "no mide el tema",
    "verify_error": "falló la verificación del modelo",
}

if __name__ == "__main__":
    if not os.path.exists(VOID_LOG):
        print(f"Aún no hay preguntas anuladas ({VOID_LOG}).")
        raise SystemExit
    rows = [json.loads(l) for l in open(VOID_LOG, encoding="utf-8") if l.strip()]
    print(f"Preguntas anuladas: {len(rows)}\n\nPor motivo:")
    for reason, n in Counter(r["reason"] for r in rows).most_common():
        print(f"  {n:4d}  {reason}: {MOTIVOS.get(reason, '')}")
    print("\nPor tema (los 8 con más anuladas):")
    for topic, n in Counter(f"{r['level']} | {r['topic'][:60]}" for r in rows).most_common(8):
        print(f"  {n:4d}  {topic}")
    print("\nÚltimas 5:")
    for r in rows[-5:]:
        print(f"  [{r['reason']}] {r['q']}  -> {r['options']}")
