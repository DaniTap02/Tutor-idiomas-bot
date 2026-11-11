"""Prueba de la parte de ESCUCHA (necesita Ollama corriendo e internet para el audio):

    python -m exam.test_escucha            -> A1 en inglés
    python -m exam.test_escucha B1 es      -> nivel B1 en español

Genera los audios con sus preguntas, guarda los .mp3 en audio_prueba/ para que los escuches, y
muestra qué se anuló por el camino (los motivos están en exam/void_report.py).
"""
import asyncio
import json
import os
import sys
from collections import Counter

from exam import questions_a1, questions_a2, questions_b1, questions_b2
from exam.listening import CONFIG, generate_listening
from exam.registro import MOTIVOS, Fallo
from exam.tts import synthesize
from exam.void_report import VOID_LOG, descripcion

BANCOS = {"A1": questions_a1, "A2": questions_a2, "B1": questions_b1, "B2": questions_b2}


def _anuladas_desde(linea_inicial: int) -> list[dict]:
    """Las preguntas anuladas que se registraron durante esta prueba."""
    if not os.path.exists(VOID_LOG):
        return []
    with open(VOID_LOG, encoding="utf-8") as f:
        filas = [json.loads(l) for l in f if l.strip()]
    return [r for r in filas[linea_inicial:] if r.get("kind") == "listening"]


def _contar_lineas() -> int:
    if not os.path.exists(VOID_LOG):
        return 0
    with open(VOID_LOG, encoding="utf-8") as f:
        return sum(1 for l in f if l.strip())


async def guardar_audios(preguntas: list[dict], nivel: str, idioma: str) -> None:
    os.makedirs("audio_prueba", exist_ok=True)
    for i, q in enumerate(preguntas):
        destino = os.path.join("audio_prueba", f"{nivel}_{idioma}_{i + 1}.mp3")
        try:
            info = await synthesize(q["text"], idioma, destino,
                                    rate=CONFIG[nivel]["rate"], voice_index=i)
            como = "nota de voz" if info["formato"] == "ogg" else "archivo de audio"
            print(f"   audio guardado ({como}, {info['motor']}): {info['ruta']}")
        except Fallo as fallo:
            print(f"   NO se pudo generar el audio {i + 1} — motivo '{fallo.motivo}': "
                  f"{MOTIVOS.get(fallo.motivo, '')}")
            print(f"      error real: {fallo.tecnico}")
            print("      revísalo con:  python -m exam.diagnostico audio")


if __name__ == "__main__":
    nivel = (sys.argv[1].upper() if len(sys.argv) > 1 else "A1")
    idioma = (sys.argv[2].lower() if len(sys.argv) > 2 else "en")
    if nivel not in BANCOS:
        print(f"Nivel desconocido: {nivel}. Disponibles: {', '.join(BANCOS)}")
        raise SystemExit(1)
    if idioma not in ("en", "es"):
        print(f"Idioma desconocido: {idioma}. Usa en o es.")
        raise SystemExit(1)

    antes = _contar_lineas()
    print(f"Generando escucha {nivel} ({idioma})…")
    try:
        preguntas = generate_listening(BANCOS[nivel], idioma)
    except Exception as error:
        print(f"\nFALLÓ: {error}")
        anuladas = _anuladas_desde(antes)
        if anuladas:
            print("\nMotivos de las anuladas:")
            for motivo, n in Counter(r["reason"] for r in anuladas).most_common():
                print(f"  {n:3d}  {motivo}: {descripcion(motivo)}")
        raise SystemExit(1) from None

    for i, q in enumerate(preguntas, start=1):
        print(f"\n{i}. [{q['topic'][:45]}]")
        print(f"   texto: {q['text']}  ({len(q['text'].split())} palabras)")
        print(f"   pregunta: {q['q']}")
        for j, op in enumerate(q["options"]):
            print(f"   {'✓' if j == q['answer'] else ' '} {op}")

    anuladas = _anuladas_desde(antes)
    print(f"\nAudios válidos: {len(preguntas)}/{CONFIG[nivel]['n']} · anuladas por el camino: {len(anuladas)}")
    for motivo, n in Counter(r["reason"] for r in anuladas).most_common():
        print(f"  {n:3d}  {motivo}: {descripcion(motivo)}")

    print("\nGenerando audios…")
    asyncio.run(guardar_audios(preguntas, nivel, idioma))
    print("\nEscúchalos y comprueba que se entienden y que la respuesta se dice claramente.")
