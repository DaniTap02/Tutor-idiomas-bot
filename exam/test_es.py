"""Prueba del examen en ESPAÑOL desde terminal (con Ollama corriendo).

    python -m exam.test_es A1          (o A2, B1, B2)
    python -m exam.test_es A2 escucha  (además genera los textos de escucha; sin audio)

Muestra las preguntas de lectura generadas y califica escritos de ejemplo del nivel."""
import sys

from exam import questions_a1, questions_a2, questions_b1, questions_b2
from exam.grader import grade
from exam.listening import generate_listening
from exam.question_generator import generate_reading
from exam.telegram_flow import _checklist

BANCOS = {"A1": questions_a1, "A2": questions_a2, "B1": questions_b1, "B2": questions_b2}

# Por nivel: (tarea de escritura que se califica, ejemplos)
MUESTRAS = {
    "A1": {
        "bueno": "Hola, me llamo Tapi. Soy de Ibagué, en Colombia. Me gusta mucho el fútbol y la música.",
        "con errores": "Hola, yo llamo Tapi. Yo es de Colombia. Me gusta los perros y la musica.",
        "sin tildes (no debe restar en A1)": "Hola, me llamo Tapi. Soy de Ibague. Me gusta el cafe y la musica.",
        "otro idioma": "Hi, my name is Tapi. I am from Colombia and I like football.",
        "falta un requisito": "Hola, me llamo Tapi. Tengo veinte años y estudio en la universidad.",
    },
    "A2": {
        "bueno": (
            "¡Hola, Ana! El fin de semana pasado fui a Cartagena con mi familia. Hacía sol y nadamos en "
            "la playa. Comí un pescado delicioso y me encantó la ciudad vieja. ¡Hasta pronto!"
        ),
        "con errores": (
            "El fin de semana pasado yo voy a Cartagena con mi familia. Nosotros comimos pescado y yo "
            "nadé en el mar. La ciudad fue muy bonito y me gustó mucho, me gustó mucho."
        ),
        "muy corto": "Fui a la playa el domingo.",
        "falta un requisito": (
            "¡Hola, Ana! El fin de semana pasado me quedé en casa con mi familia. Vimos televisión todo "
            "el día y hablamos mucho. Fue un fin de semana tranquilo y todos estábamos felices."
        ),
    },
    "B1": {
        "bueno": (
            "En mi opinión, las redes sociales tienen cosas buenas y malas para los jóvenes. Por un lado, "
            "sirven para estar en contacto con amigos y para aprender cosas nuevas, porque hay mucha "
            "información útil. Sin embargo, muchos jóvenes pasan demasiadas horas mirando el celular y "
            "duermen poco. Además, a veces comparan su vida con la de otros y se sienten mal. Por lo "
            "tanto, creo que es importante que los jóvenes usen las redes con límites."
        ),
        "sin razones": (
            "Las redes sociales son muy populares hoy en día. Mucha gente las usa todos los días en su "
            "celular o en el computador. Hay muchas aplicaciones diferentes, como Instagram, TikTok y "
            "WhatsApp. Los jóvenes y los adultos las usan para muchas cosas diferentes en su vida."
        ),
    },
    "B2": {
        "bueno": (
            "Estimado señor Pérez: le escribo para presentar una reclamación sobre el servicio de limpieza "
            "que contraté el viernes pasado. El equipo llegó dos horas tarde y dejó la cocina y el baño sucios. "
            "Por este motivo, tuve que cancelar una cena familiar y limpiar todo yo misma. Ya he llamado dos "
            "veces a su oficina y he enviado un correo, pero nadie me ha respondido. Le agradecería que "
            "enviaran de nuevo al equipo esta semana sin costo o que me devolvieran el dinero. Quedo a la "
            "espera de su respuesta. Atentamente, Ana Torres"
        ),
        "sin solución": (
            "Estimado señor Pérez: le escribo porque el servicio de limpieza que contraté el viernes fue muy "
            "malo. El equipo llegó tarde, no trajo los productos necesarios y dejó la cocina y el baño sucios. "
            "Me sentí muy molesta porque había invitado a mi familia a cenar esa noche y la casa no estaba "
            "lista. Es la primera vez que contrato su empresa y la experiencia fue muy desagradable para mí "
            "y para mi familia. Atentamente, Ana Torres"
        ),
    },
}


def main():
    nivel = (sys.argv[1] if len(sys.argv) > 1 else "A1").upper()
    banco = BANCOS[nivel]
    print(f"Generando preguntas de lectura {nivel} en español… (puede tardar)")
    preguntas = generate_reading(banco, "es")
    for i, q in enumerate(preguntas, start=1):
        print(f"\n{i}. [{q['topic'][:50]}]")
        if q.get("text"):
            print(f"   TEXTO: {q['text']}")
        print(f"   {q['q']}")
        for j, op in enumerate(q["options"]):
            print(f"   {'✓' if j == q['answer'] else ' '} {op}")

    if "escucha" in sys.argv[2:]:
        print(f"\nGenerando escucha {nivel} en español…")
        for i, q in enumerate(generate_listening(banco, "es"), start=1):
            print(f"\n🎧 {i}. AUDIO: {q['text']}\n   {q['q']}")
            for j, op in enumerate(q["options"]):
                print(f"   {'✓' if j == q['answer'] else ' '} {op}")

    # B1 tiene varias tareas: se califica con la de opinión (la de los ejemplos)
    if nivel == "B1":
        checklist = next(t for t in banco.WRITING_TASKS if t["id"] == "opinion")["checklist"]
    elif nivel == "B2":   # B2: la tarea del correo formal (la de los ejemplos)
        checklist = next(t for t in banco.WRITING_TASKS if t["id"] == "formal_email")["checklist"]
    else:
        checklist = _checklist(banco, "writing", "es")
    for nombre, texto in MUESTRAS[nivel].items():
        r = grade(texto, nivel, "es", checklist)
        print(f"\n[{nombre}] puntaje={r['score']} completada={r['task_completed']} reescribir={r['needs_rewrite']}")
        print("  errores:", r["errors"])
        print("  feedback:", r["feedback"])


if __name__ == "__main__":
    main()
