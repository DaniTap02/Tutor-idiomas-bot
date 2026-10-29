"""Prueba rápida desde terminal (con Ollama corriendo):  python -m exam.test_a1"""
from exam.grader import grade
from exam.placement import level_passed, next_step
from exam.questions_a1 import TASK_CHECKLIST, score_reading

SAMPLES = {
    "bueno": "My name is Laura. I am from Colombia. I like music and dogs.",
    "con errores": "My name Laura. I from Colombia. I likes music.",
    "no cumple la tarea": "The weather is nice today.",
}

if __name__ == "__main__":
    for name, text in SAMPLES.items():
        result = grade(text, "A1", "en", TASK_CHECKLIST["writing"])
        print(f"\n[{name}] score={result['score']} completada={result['task_completed']}")
        print("  errores:", result["errors"])
        print("  feedback:", result["feedback"])

    reading = score_reading("en", [0, 1, 0, 1, 1])  # 5/5 correctas
    print("\nLectura:", reading)
    passed = level_passed(reading, 80, 70)
    print("¿Pasa A1?", passed, "->", next_step("A1", passed))
