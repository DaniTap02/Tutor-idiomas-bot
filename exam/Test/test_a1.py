"""Prueba rápida desde terminal (con Ollama corriendo):  python -m exam.test_a1"""
from exam import questions_a1
from exam.grader import grade
from exam.placement import level_passed, next_step
from exam.question_generator import generate_reading
from exam.questions_a1 import TASK_CHECKLIST, score_reading

SAMPLES = {
    "bueno": "My name is Laura. I am from Colombia. I like music and dogs.",
    "con errores": "My name Laura. I from Colombia. I likes music.",
    "no cumple la tarea": "The weather is nice today and the sky is blue.",
    "muy corto (hola)": "hola",
    "otro idioma": "Me llamo Laura. Soy de Colombia. Me gusta la música.",
    "falta un requisito": "My name is Laura. I am from Colombia.",
}

if __name__ == "__main__":
    print("Generando preguntas de lectura…")
    questions = generate_reading(questions_a1, "en")
    for i, q in enumerate(questions, start=1):
        print(f"\n{i}. [{q['topic'][:40]}] {q['q']}")
        for j, op in enumerate(q["options"]):
            print(f"   {'✓' if j == q['answer'] else ' '} {op}")

    for name, text in SAMPLES.items():
        result = grade(text, "A1", "en", TASK_CHECKLIST["writing"])
        print(f"\n[{name}] score={result['score']} completada={result['task_completed']}")
        print("  errores:", result["errors"])
        print("  feedback:", result["feedback"])

    reading = score_reading(questions, [q["answer"] for q in questions])  # todas correctas
    print("\nLectura:", reading)
    passed = level_passed(reading, 80, 70)
    print("¿Pasa A1?", passed, "->", next_step("A1", passed))
