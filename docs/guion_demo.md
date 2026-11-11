# Guion de la demo (unos 10 minutos)

**Antes de empezar (no cuenta en el tiempo):**
- Ollama encendido (`ollama list`) y `python bot.py` corriendo. Debe decir «Lara Translate (MCP) conectado».
- Un usuario de prueba **ya ubicado en A1 de inglés**, para no esperar la generación del examen completo en vivo. Ten también un chat nuevo listo para mostrar el `/start`.
- Terminal aparte con `python -m pytest` y `python -m exam.metricas` listos.
- Sube el volumen para la escucha.

| Min | Qué mostrar | Qué decir |
|---|---|---|
| 0:00–1:00 | README: diagrama de arquitectura | Qué es el tutor, tipo de agente (utilidad + aprendizaje) y PEAS en una frase. Todo corre local salvo Telegram, edge-tts y Lara. |
| 1:00–3:00 | Chat nuevo: `/start` → Inglés → primeras preguntas de lectura → un audio de escucha | «Ninguna pregunta está escrita a mano»: las genera Ollama y el validador las revisa antes. Mostrar el botón 🔁 de la escucha. |
| 3:00–4:00 | `voided_questions.jsonl` / `python -m exam.void_report` | La pregunta ambigua *My brother is ___ than my sister* se anula por falta de evidencia; el estudiante nunca la ve. |
| 4:00–5:30 | Usuario A1: escritura en español a propósito → aviso de Lara → escritura en inglés → retroalimentación con **🌐 Ver traducción** | **MCP**: `detect_language` evita calificar un texto en otro idioma (sin penalizar); `translate` explica la retroalimentación en A1/A2. |
| 5:30–7:00 | `/leccion`: explicación generada → fallar un ejercicio → el siguiente es del mismo tema → acertar 3 seguidas → escritura corta | La adaptación: repite el tema fallado con otra pregunta y avanza con una racha. Al completar 5 lecciones ofrece el examen. |
| 7:00–7:45 | `/traducir I would like a coffee` y `/idioma` | La segunda herramienta del MCP, y el cambio de idioma (inglés y español espejo). |
| 7:45–8:30 | `/puntos` y `/recordatorio 19:30` | Progreso acumulado en SQLite (no se borra con `/reiniciar`). Recordatorio diario con la JobQueue, hora de Colombia, que invita a la lección pendiente. |
| 8:30–9:15 | Terminal: `python -m exam.metricas` | Las métricas del PEAS: errores que no se repiten, aciertos por tema, avance por nivel, retorno tras recordatorio, anuladas por tipo. |
| 9:15–10:00 | Terminal: `python -m pytest` | Todas las pruebas corren sin Telegram, internet, Ollama ni Lara, en segundos. Cierre: limitaciones (pronunciación, velocidad en 8 GB de RAM) y lo que sigue. |

**Plan B si algo falla en vivo:**
- **Ollama lento:** baja la espera con `EXAM_LISTENING_N=2` y `EXAM_EXIGIR_EVIDENCIA=0`, o muestra el usuario ya ubicado.
- **Lara no responde:** muestra que el bot sigue igual («La traducción no está disponible en este momento») y explica el motivo en el registro. Es justo el principio de no penalizar por fallas del sistema.
- **No hay internet para los audios:** el examen muestra el texto y esa pregunta no cuenta.
