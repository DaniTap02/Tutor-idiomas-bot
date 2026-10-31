"""Prueba rápida del examen B1 desde terminal.

  python -m exam.test_b1              -> todo (filtros + lectura + escritura; necesita Ollama)
  python -m exam.test_b1 filtros      -> solo el filtro de palabras prohibidas (SIN Ollama, instantáneo)
  python -m exam.test_b1 lectura      -> solo genera y muestra las preguntas de lectura
  python -m exam.test_b1 lectura es   -> lo mismo pero para el examen de español
  python -m exam.test_b1 escritura    -> solo califica las muestras de escritura

Los tiempos con tu PC pueden ser largos: usa 'filtros', 'lectura' y 'escritura' por separado si quieres.
"""
import sys
import time

from exam import questions_b1
from exam.grader import MIN_WORDS, grade
from exam.placement import level_passed, next_step
from exam.question_generator import generate_reading
from exam.questions_b1 import FORBIDDEN_RE, WRITING_TASKS, score_reading

# Muestras de escritura por tarea (cada una de 65 a 90 palabras; el mínimo de B1 es 50)
SAMPLES = {
    "email": {
        "bueno": (
            "Hi Mark! I'm so happy that you are coming to visit me next month. Welcome to Bogotá! I think "
            "you will love the city. We can go hiking in the mountains and, if you like food, we can try "
            "the street markets. Remember to bring a light jacket because the evenings can be cold, and "
            "you should also bring comfortable shoes. Are you going to arrive by bus or by plane? Tell me "
            "the time and I will pick you up. I can't wait to see you! Best wishes, Laura"
        ),
        "con errores": (
            "Hi Mark! I am very happy because you comes to visit me the next month. Welcome to my city! "
            "We can to go to the museum and eat typical food in the mountains. You must bring a jacket "
            "because it's cold in the night and you needs comfortable shoes too. Which day you arrive? "
            "I wait for you at the airport and we goed to my house together. See you soon and take care "
            "of you! Laura"
        ),
        "falta requisitos (sin consejo ni pregunta)": (
            "Hi Mark! I am very happy that you are visiting my city next month and you are welcome to stay "
            "at my house. We can go to the museum on Saturday and then we can have lunch in a typical "
            "restaurant. On Sunday we can walk in the big park near my house and visit the old market. I "
            "think you will like it because the city has a lot of history. See you soon! Laura"
        ),
    },
    "story": {
        "bueno": (
            "It was a rainy Saturday and I was at home when the phone rang. It was my best friend Carlos, "
            "who was crying because he had lost his dog in the park. First, I put on my coat and ran to "
            "his house. Then we looked for the dog in every street near the park for two hours. Finally, "
            "a little girl found the dog under a bench and we were very happy. After that, we went to a "
            "cafe and had hot chocolate."
        ),
        "con errores": (
            "It was a rainy Saturday and I was at home when the phone rang. It was my friend Carlos and he "
            "cry because he losed his dog in the park. First I go to his house and then we looking for "
            "the dog in all the streets. Finally we finded him under a bench and we was very happy. After "
            "that we goed to a cafe to drink a hot chocolate and we talked about the dog."
        ),
        "falta requisitos (presente y sin orden)": (
            "It is a rainy Saturday and I am at home when the phone rings. It is my friend Carlos and he "
            "is very sad because his dog is not at home. He is crying and he asks me for help. I like dogs "
            "very much and I think that pets are part of the family. My own dog is big and brown and he "
            "sleeps all day on the sofa near the window."
        ),
    },
    "opinion": {
        "bueno": (
            "In my opinion, social media is good for young people, but only if they use it carefully. "
            "First, it helps them to keep in touch with friends and family who live far away. In addition, "
            "they can learn many new things, for example from videos about science or languages. However, "
            "some teenagers spend too many hours online, so they sleep less and have worse marks. Although "
            "there are some risks, I think the benefits are bigger."
        ),
        "con errores": (
            "In my opinion social media is good for young peoples. They can talk with friends who lives in "
            "other countrys and they can learn many things from the internet every day. But some teenagers "
            "use it to much and they doesn't sleep enough because they are always in the phone. I think is "
            "more good than bad for they, and parents should not be worried."
        ),
        "falta requisitos (sin opinión ni razones)": (
            "Social media is a very popular topic today. Many applications exist, like Instagram, TikTok "
            "and WhatsApp. Millions of people in the world use them every day. Some apps are free and "
            "other apps cost money every month. Companies earn a lot of money with advertising. The most "
            "popular social network is Facebook, and it was created in two thousand and four by a "
            "university student."
        ),
    },
}

# Casos que no dependen de la tarea (se prueban con la tarea del correo)
GENERALES = {
    "muy corto": "I want to write a short email to my friend about his visit.",
    "otro idioma": (
        "Hola Mark! Estoy muy feliz de que vengas a visitarme el próximo mes. Bienvenido a mi ciudad! "
        "Podemos ir a las montañas y probar la comida típica de la región. Lleva una chaqueta porque "
        "hace frío por la noche y también unos zapatos cómodos. A qué hora llegas? Te espero en el "
        "aeropuerto y vamos juntos a mi casa. Un abrazo, Laura"
    ),
}

# Filtro de palabras prohibidas de B1: (frase, ¿debe rechazarse?)
FILTRO_CASOS = [
    ("If I had more money, I would buy a car.", False),
    ("If I had studied, I would have passed the exam.", False),
    ("I've been waiting for an hour.", False),
    ("We should leave now because it might rain.", False),
    ("You must wear a helmet and you mustn't run.", False),
    ("I used to play football and I'm going to start again.", False),
    ("Best wishes, Laura", False),
    ("You will have to book a hotel.", False),
    ("She had been interested in music for years.", False),
    ("She had been working there for ten years.", True),
    ("The house is being built now.", True),
    ("By 2030 we will have finished the project.", True),
    ("I would rather stay at home.", True),
    ("I wish I had more time.", True),
    ("If only I were taller.", True),
    ("You ought to see a doctor.", True),
    ("You should have called me.", True),
    ("He must have forgotten the keys.", True),
    ("Not only did he forget, but he also lied.", True),
    ("I had my hair cut yesterday.", True),
]


def probar_filtros():
    print("== Filtro de palabras prohibidas B1 ==")
    fallos = 0
    for frase, debe_rechazar in FILTRO_CASOS:
        rechazada = bool(FORBIDDEN_RE.search(frase))
        ok = rechazada == debe_rechazar
        fallos += not ok
        print(f"  {'OK ' if ok else 'MAL'} {'rechaza' if rechazada else 'acepta '} | {frase}")
    print("Filtro:", "todo bien ✅" if not fallos else f"{fallos} casos mal ❌")


def probar_lectura(language: str):
    print(f"Generando preguntas de lectura B1 ({language})… (puede tardar bastante)")
    t0 = time.time()
    questions = generate_reading(questions_b1, language)
    print(f"Listo en {time.time() - t0:.0f} s: {len(questions)} preguntas")
    for i, q in enumerate(questions, start=1):
        tipo = f" · {q['qtype']}" if q.get("qtype") else ""
        print(f"\n{i}. [{q['topic'][:45]}{tipo}]")
        if q.get("text"):
            print(f"   TEXTO ({len(q['text'].split())} palabras): {q['text']}")
        print(f"   {q['q']}")
        for j, op in enumerate(q["options"]):
            print(f"   {'✓' if j == q['answer'] else ' '} {op}")
    reading = score_reading(questions, [q["answer"] for q in questions])  # todas correctas
    print("\nLectura:", reading)
    passed = level_passed(reading, 80, 70)
    print("¿Pasa B1?", passed, "->", next_step("B1", passed))


def probar_escritura():
    print(f"\n== Escritura B1 (mínimo {MIN_WORDS['B1']} palabras) ==")
    for tarea in WRITING_TASKS:
        print(f"\n######## Tarea: {tarea['id']} ########\n{tarea['prompt']['en']}")
        for nombre, texto in SAMPLES[tarea["id"]].items():
            r = grade(texto, "B1", "en", tarea["checklist"])
            print(f"\n[{tarea['id']} · {nombre}] ({len(texto.split())} palabras) score={r['score']} "
                  f"completada={r['task_completed']} reescribir={r['needs_rewrite']}")
            print("  errores:", r["errors"])
            print("  feedback:", r["feedback"])
    tarea = WRITING_TASKS[0]
    for nombre, texto in GENERALES.items():
        r = grade(texto, "B1", "en", tarea["checklist"])
        print(f"\n[{nombre}] score={r['score']} completada={r['task_completed']} reescribir={r['needs_rewrite']}")
        print("  feedback:", r["feedback"])


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "todo"
    idioma = sys.argv[2] if len(sys.argv) > 2 else "en"
    if modo in ("todo", "filtros"):
        probar_filtros()
    if modo in ("todo", "lectura"):
        probar_lectura(idioma)
    if modo in ("todo", "escritura"):
        probar_escritura()
