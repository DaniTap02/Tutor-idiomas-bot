"""Prueba rápida del examen A2 desde terminal (con Ollama corriendo):  python -m exam.test_a2"""
from exam import questions_a2
from exam.grader import grade
from exam.placement import level_passed, next_step
from exam.question_generator import generate_reading
from exam.questions_a2 import TASK_CHECKLIST, score_reading

SAMPLES = {
    "bueno": (
        "Hi Ana! Last weekend I went to Cartagena with my family. The weather was sunny and "
        "we swam at the beach. I ate delicious fish and I loved the old city. See you soon!"
    ),
    "con errores": (
        "Last weekend I go to Cartagena with my family. We eated fish and I swimmed in the sea. "
        "The city was beautifull and I likes it a lot."
    ),
    "muy corto": "I went to the beach last Sunday.",
    "otro idioma": (
        "Hola Ana! El fin de semana pasado fui a Cartagena con mi familia. Hizo sol y nadamos "
        "en la playa. Comí pescado muy rico y me encantó la ciudad."
    ),
    "falta un requisito": (
        "Hi Ana! Last weekend I stayed at home with my family. We watched television all day "
        "and we talked a lot. It was a quiet weekend and everybody was happy."
    ),
}

if __name__ == "__main__":
    print("Generando preguntas de lectura A2… (puede tardar)")
    questions = generate_reading(questions_a2, "en")
    for i, q in enumerate(questions, start=1):
        print(f"\n{i}. [{q['topic'][:45]}]")
        if q.get("text"):
            print(f"   TEXTO: {q['text']}")
        print(f"   {q['q']}")
        for j, op in enumerate(q["options"]):
            print(f"   {'✓' if j == q['answer'] else ' '} {op}")

    for name, text in SAMPLES.items():
        result = grade(text, "A2", "en", TASK_CHECKLIST["writing"])
        print(f"\n[{name}] score={result['score']} completada={result['task_completed']} "
              f"reescribir={result['needs_rewrite']}")
        print("  errores:", result["errors"])
        print("  feedback:", result["feedback"])

    reading = score_reading(questions, [q["answer"] for q in questions])  # todas correctas
    print("\nLectura:", reading)
    passed = level_passed(reading, 80, 70)
    print("¿Pasa A2?", passed, "->", next_step("A2", passed))
