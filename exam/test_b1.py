"""Prueba rápida desde terminal (con Ollama corriendo):  python -m exam.test_b1"""
from exam import questions_b1
from exam.grader import grade
from exam.placement import level_passed, next_step
from exam.question_generator import generate_reading
from exam.questions_b1 import TASK_CHECKLIST, score_reading

SAMPLES = {
    "bueno": (
        "Last week I had a problem at the airport. My flight to Bogota was cancelled because of the bad "
        "weather, and I did not know what to do. I felt very nervous and tired. I went to the information "
        "desk and asked for another flight, and the staff helped me quickly. I learned that I should always "
        "arrive early, and next time I would check the weather before travelling."
    ),
    "con errores": (
        "Last week I have a problem in the airport. My flight cancel because the weather is bad and I not "
        "know what to do. I feel very nervous. I go to the desk and I ask another flight. I learn that I "
        "should arrive early next time and check the weather before I travel."
    ),
    "no cumple la tarea": (
        "The city is very big and has many restaurants, museums and parks. Every weekend people walk in the "
        "streets and buy food in the markets. The weather in this region is usually warm and sunny, so it is "
        "a good place for tourists who like nature and culture."
    ),
    "muy corto (hola)": "hola",
    "otro idioma": (
        "La semana pasada tuve un problema en el aeropuerto. Mi vuelo fue cancelado por el mal tiempo y no "
        "sabía qué hacer. Me sentí muy nervioso y cansado. Fui al mostrador de información y pedí otro vuelo, "
        "y me ayudaron rápido. Aprendí que siempre debo llegar temprano y revisar el clima antes de viajar."
    ),
    "falta un requisito": (
        "Last month I had a problem at university. I lost my laptop on the bus with all my homework inside "
        "it. I felt really sad and worried about my grades. I went to the bus company the next day and "
        "asked about it, but they did not have it, so I had to do all my homework again from the beginning."
    ),
}

if __name__ == "__main__":
    print("Generando preguntas de lectura…")
    questions = generate_reading(questions_b1, "en")
    for i, q in enumerate(questions, start=1):
        print(f"\n{i}. [{q['topic'][:40]}] {q['q']}")
        if q.get("text"):
            print(f"   texto: {q['text']}")
        for j, op in enumerate(q["options"]):
            print(f"   {'✓' if j == q['answer'] else ' '} {op}")

    for name, text in SAMPLES.items():
        result = grade(text, "B1", "en", TASK_CHECKLIST["writing"])
        print(f"\n[{name}] score={result['score']} completada={result['task_completed']}")
        print("  errores:", result["errors"])
        print("  feedback:", result["feedback"])

    reading = score_reading(questions, [q["answer"] for q in questions])  # todas correctas
    print("\nLectura:", reading)
    passed = level_passed(reading, 80, 70)
    print("¿Pasa B1?", passed, "->", next_step("B1", passed))
