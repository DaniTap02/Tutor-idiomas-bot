"""Prueba rápida desde terminal (con Ollama corriendo):  python -m exam.test_b2"""
from exam import questions_b2
from exam.grader import grade
from exam.placement import level_passed, next_step
from exam.question_generator import generate_reading
from exam.questions_b2 import TASK_CHECKLIST, score_reading

SAMPLES = {
    "bueno": (
        "Dear Sir or Madam, I am writing to complain about the service I received at your hotel last week. "
        "The air conditioning in my room did not work, and nobody repaired it during the whole stay. As a "
        "result, I could not sleep properly and I had to cancel an important meeting. I have already spoken "
        "to the reception twice and sent an email, but I have not received any answer. I would be grateful "
        "if you could refund part of the price. I look forward to hearing from you. Yours faithfully, Laura"
    ),
    "con errores": (
        "Dear Sir, I write to complain about the service what I receive in your hotel last week. The air "
        "conditioning not work and nobody repair it in all the stay. Because of this I can not sleep good and "
        "I must cancel a meeting important. I already speak with the reception two times and I send an email "
        "but nobody answer me. Please you give me a refund of part of the price. Thank you for your time."
    ),
    "no cumple la tarea": (
        "Technology has changed the way people communicate in the last twenty years. Many people now use "
        "their phones to talk with friends, read the news and work from home. Some experts say that this is "
        "positive because it saves time, while others think it makes us feel more alone than before, "
        "especially young people who spend many hours online every day."
    ),
    "muy corto (hola)": "hola",
    "otro idioma": (
        "Estimado señor, le escribo para quejarme del servicio que recibí en su hotel la semana pasada. "
        "El aire acondicionado de mi habitación no funcionaba y nadie lo reparó durante toda mi estancia. "
        "Por eso no pude dormir bien y tuve que cancelar una reunión importante. Ya hablé dos veces con la "
        "recepción y envié un correo, pero no he recibido respuesta. Le agradecería que me devolviera una "
        "parte del precio. Quedo atenta a su respuesta."
    ),
    "falta un requisito": (
        "Dear Sir or Madam, I am writing to complain about the service I received at your hotel last week. "
        "The air conditioning in my room did not work, and nobody repaired it during the whole stay. As a "
        "result, I could not sleep properly and I had to cancel an important meeting the next morning, which "
        "was very stressful for me. I think the hotel should take better care of its rooms. Yours faithfully, Laura"
    ),
}

if __name__ == "__main__":
    print("Generando preguntas de lectura…")
    questions = generate_reading(questions_b2, "en")
    for i, q in enumerate(questions, start=1):
        print(f"\n{i}. [{q['topic'][:40]}] {q['q']}")
        if q.get("text"):
            print(f"   texto: {q['text']}")
        for j, op in enumerate(q["options"]):
            print(f"   {'✓' if j == q['answer'] else ' '} {op}")

    for name, text in SAMPLES.items():
        result = grade(text, "B2", "en", TASK_CHECKLIST["writing"])
        print(f"\n[{name}] score={result['score']} completada={result['task_completed']}")
        print("  errores:", result["errors"])
        print("  feedback:", result["feedback"])

    reading = score_reading(questions, [q["answer"] for q in questions])  # todas correctas
    print("\nLectura:", reading)
    passed = level_passed(reading, 80, 70)
    print("¿Pasa B2?", passed, "->", next_step("B2", passed))
