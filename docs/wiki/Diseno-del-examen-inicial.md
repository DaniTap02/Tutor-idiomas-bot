# Diseño del examen inicial

## Objetivo

Ubicar al estudiante en su nivel de partida (A1, A2, B1 o B2) en inglés o en español, con las cuatro habilidades: **lectura, escucha, escritura y habla**. El examen se detiene en el **primer nivel que no aprueba**: si pasa A2 pero no B1, aprende desde B1. **Aprobar B2 termina el currículo del semestre.**

## Partes por nivel

| Parte | Formato | Cómo se califica |
|---|---|---|
| 📖 Lectura | 10 preguntas de opción múltiple: gramática, vocabulario y (desde A2) comprensión de textos cortos | % de aciertos |
| 🎧 Escucha | 3 audios cortos generados con edge-tts; se puede repetir cada uno una vez | % de aciertos (solo los audios que sí se oyeron) |
| ✍️ Escritura | Una consigna del nivel (B1 y B2 eligen una al azar entre varias) | Calificador: requisitos del checklist y errores |
| 🎤 Habla | Nota de voz según la consigna del nivel | Whisper transcribe en local; el calificador revisa el contenido |

| Nivel | Lectura (gramática / vocabulario / textos) | Escritura | Habla |
|---|---|---|---|
| A1 | 6 / 4 / 0 | Presentarse en 3–4 frases | 15–30 s: nombre, dónde vive, algo que le gusta |
| A2 | con textos cortos | Mensaje sobre el fin de semana | 30–45 s: rutina y planes |
| B1 | 5 / 2 / 3 | Correo informal, relato u opinión | 45–60 s: una experiencia memorable |
| B2 | 4 / 3 / 3 | Correo formal de reclamo o texto argumentativo | 60–90 s: opinión sobre la tecnología |

## Regla de aprobación (`exam/placement.py`)

- Cada parte evaluada debe sacar **al menos 60**, y el **promedio al menos 70**.
- Una parte que no se pudo evaluar por una falla del sistema **no se promedia**.

## Las preguntas se generan en vivo y se validan

No hay banco pregenerado. Para cada pregunta:
1. El **código** elige el tema entre los permitidos del nivel (cada tema trae su alcance entre paréntesis).
2. **Ollama** redacta la pregunta. El código baraja las opciones y decide cuál es la correcta.
3. **Filtros de código:** formato, alfabeto latino, largo, palabras prohibidas del nivel, contexto obligatorio en los temas que lo necesitan, pista de género en pronombres, nada que solo funcione escrito en la escucha.
4. **Verificación con el modelo** (temperatura 0): exactamente una opción válida, contexto suficiente y nivel correcto.
5. **Evidencia citada:** el modelo copia las palabras que hacen única la respuesta y el código comprueba que estén de verdad en la pregunta. Sin evidencia, la pregunta se anula.

Lo anulado no se muestra, se registra en `voided_questions.jsonl` y se genera otra. Los mismos controles valen para los ejercicios de las lecciones.

## El calificador

- Juzga el **significado**, nunca compara con una respuesta esperada.
- Acepta contracciones, sinónimos, variantes regionales (ustedes/vosotros, carro/coche) y erratas que no cambian el sentido.
- Si falta un requisito, dice **qué falta y por qué**.
- Antes de calificar, **Lara (`detect_language`)** comprueba el idioma: si el texto está claramente en otro, se pide de nuevo **sin contar el intento**.
- En español, las tildes que faltan no cuentan en A1 y A2. En la parte de habla nunca cuentan, porque las pone Whisper.

## Español espejo

El examen en español tiene la misma estructura que el de inglés. Sus temas no se tradujeron: salen del temario de español:
- **A1:** ser/estar, hay, gustar;
- **A2:** indefinido/imperfecto, imperativo;
- **B1:** subjuntivo presente, contraste de pasados;
- **B2:** imperfecto de subjuntivo, concesivas, estilo indirecto, ser/estar con cambio de significado.

Cada nivel tiene sus propios filtros de formas verbales prohibidas (`exam/espanol.py`).

## Después del examen

El estudiante queda en las **5 lecciones de su nivel**. Al completarlas, el tutor le ofrece **volver a presentar el examen de ese nivel** para subir.
