"""Prueba rápida de la parte de ESCUCHA (con Ollama corriendo e internet para el audio):
    python -m exam.test_escucha            -> A1 en inglés
    python -m exam.test_escucha B1 es      -> nivel B1 en español

Genera los audios con sus preguntas y guarda los .mp3 en la carpeta audio_prueba/ para que los escuches.
"""
import asyncio
import os
import sys

from exam import questions_a1, questions_a2, questions_b1
from exam.listening import CONFIG, generate_listening
from exam.tts import synthesize

BANCOS = {"A1": questions_a1, "A2": questions_a2, "B1": questions_b1}


async def guardar_audios(preguntas: list[dict], nivel: str, idioma: str) -> None:
    os.makedirs("audio_prueba", exist_ok=True)
    for i, q in enumerate(preguntas):
        ruta = os.path.join("audio_prueba", f"{nivel}_{idioma}_{i + 1}.mp3")
        await synthesize(q["text"], idioma, ruta, rate=CONFIG[nivel]["rate"], voice_index=i)
        print(f"   audio guardado: {ruta}")


if __name__ == "__main__":
    nivel = sys.argv[1].upper() if len(sys.argv) > 1 else "A1"
    idioma = sys.argv[2].lower() if len(sys.argv) > 2 else "en"

    print(f"Generando escucha {nivel} ({idioma})…")
    preguntas = generate_listening(BANCOS[nivel], idioma)
    for i, q in enumerate(preguntas, start=1):
        print(f"\n{i}. [{q['topic'][:40]}]")
        print(f"   texto: {q['text']}  ({len(q['text'].split())} palabras)")
        print(f"   pregunta: {q['q']}")
        for j, op in enumerate(q["options"]):
            print(f"   {'✓' if j == q['answer'] else ' '} {op}")

    print("\nGenerando audios…")
    asyncio.run(guardar_audios(preguntas, nivel, idioma))
