# PEAS y tipo de agente

## Tipo de agente

El tutor es un **agente basado en utilidad con aprendizaje**:

- **Basado en utilidad:** en cada paso elige la acción que más acerca al estudiante a su meta, que es dominar los temas de su nivel y subir de nivel. Repite un tema fallado en vez de seguir, avanza cuando hay una racha de aciertos y ofrece el examen cuando termina las lecciones.
- **Con aprendizaje:** guarda el historial del estudiante en SQLite (ejercicios por tema, errores del calificador, lecciones, exámenes) y lo usa para cambiar lo que hace después. Por ejemplo, `/practicar` elige más seguido los temas que el estudiante ha fallado, y `/puntos` le muestra qué repasar.
- Por dentro hay **dos agentes con responsabilidades separadas**:
  - el **validador de preguntas** decide si una pregunta generada es apta *antes* de que el estudiante la vea;
  - el **calificador** juzga el *significado* de las respuestas abiertas, sin compararlas con una respuesta esperada.

## PEAS

| Elemento | Descripción |
|---|---|
| **P – Desempeño** | Nivel inicial correcto; contenido acorde al nivel e idioma; preguntas sin ambigüedad (respuesta única con evidencia citada); retroalimentación útil (qué falta y por qué); dificultad adaptativa; constancia del estudiante (recordatorios); nunca penalizar por fallas del sistema. |
| **E – Entorno** | Chat de Telegram con un estudiante. El bot depende de servicios externos que pueden fallar: Ollama local, edge-tts (internet), Whisper local, servidor MCP de Lara (internet). |
| **A – Actuadores** | Aplicar el examen de nivel (4 partes); asignar y actualizar el nivel por idioma; generar lecciones, explicaciones y ejercicios; calificar escritura y habla; traducir (`translate`); repetir temas o avanzar; registrar el progreso; enviar recordatorios diarios. |
| **S – Sensores** | Mensajes de texto; botones de respuesta; notas de voz transcritas en local (faster-whisper); idioma detectado del texto (`detect_language` de Lara); comandos; hora del recordatorio; historial en SQLite. |

## Propiedades del entorno

| Propiedad | Valor | Por qué |
|---|---|---|
| Observable | **Parcialmente** | El agente solo ve lo que el estudiante responde; su conocimiento real se infiere. |
| Determinista | **Estocástico** | El modelo genera preguntas distintas cada vez; el estudiante puede acertar por azar. |
| Episódico | **Secuencial** | Cada respuesta cambia lo que viene después (repetir, avanzar, subir de nivel). |
| Estático | **Dinámico** | El estudiante puede tardar, abandonar o volver por un recordatorio. |
| Discreto | **Discreto** | Turnos de mensajes, opciones de botón, niveles A1–B2. |
| Agentes | **Único** | Un estudiante por conversación. |

## Métricas de éxito (`python -m exam.metricas`)

1. **Errores que no se repiten tras la retroalimentación:**
   - en ejercicios, % de temas fallados que se aciertan la siguiente vez;
   - en textos, % de errores del calificador que no vuelven a aparecer.
2. **Aciertos por tema** (idioma + tema), para ver qué temas cuestan más.
3. **Avance por nivel:** cuántos aprueban cada examen y cuántas lecciones se completan por nivel.
4. **Tasa de retorno tras un recordatorio:** % de recordatorios después de los cuales el estudiante vuelve en 24 horas.
5. **Preguntas anuladas por tipo** (motivo y parte), para mejorar el generador.
6. **Precisión del examen inicial:** nivel asignado frente a una autoevaluación o a un docente (se mide con usuarios).
