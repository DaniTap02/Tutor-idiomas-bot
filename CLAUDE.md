# Contexto para Claude Code — Tutor-idiomas-bot

Este archivo es la memoria del proyecto entre computadores. Léelo completo antes de trabajar.
Última actualización: 11 de noviembre de 2026, al pasar el proyecto a otro PC.

## Qué es
Bot de Telegram tutor de inglés y español (tipo Duolingo), para la materia Sistemas Inteligentes.
Examen de nivel (lectura, escucha, escritura y habla; niveles A1–B2) → lecciones y práctica adaptativas
→ historial en SQLite → recordatorios. El README.md explica la arquitectura y los comandos.

## Reglas del proyecto (no negociables)
- Windows, PowerShell, Python 3.13, entorno `.venv`. El PC del dueño tiene 8 GB de RAM y una GPU de 2 GB: todo debe ser liviano.
- Modelo local: `qwen2.5:7b` por Ollama, llamado con httpx. No se agregan APIs pagas ni servicios en la nube; la única excepción es el MCP de Lara Translate.
- **Sin banco pregenerado:** todo se genera en vivo con Ollama y pasa por el validador (filtros de código + verificación con el modelo + evidencia citada). Lo anulado va a `voided_questions.jsonl` y no penaliza.
- **Dos agentes separados:** el validador (`question_generator.py`, `listening.py`) y el calificador (`grader.py`). El calificador juzga el significado y nunca compara con una respuesta esperada.
- **Estructura plana en `exam/`**, sin subcarpetas. Inglés y español son un currículo espejo.
- **Nunca se penaliza al estudiante por una falla del sistema** (Ollama, audio, red o Lara): esa parte no cuenta y el motivo real se registra en `exam/registro.py`.
- Texto al usuario, comentarios y mensajes de commit **en español**, con el estilo del código existente.
- **Nunca subir** `.env`, bases de datos (`*.db`), `datos_bot.pkl` ni datos de usuarios.
- Forma de trabajar: por fases. Al terminar cada una: correr pruebas, hacer commit, decir qué comandos ejecutar y qué probar en Telegram, y esperar el "sigue" del dueño. Si algo del código contradice lo pedido, preguntar antes. Antes de usar una librería nueva, verificar su versión y su API real, y fijarla en `requirements.txt`. Mostrar un mensaje de espera en todo lo que dependa de Ollama.

## Lo que ya está hecho (en main)
| Commit | Qué |
|---|---|
| `362ed85` | Fase 1: `mcp_cliente/lara.py`. Una sesión MCP por stdio con `@translated/lara-mcp@2.2.0` (SDK `mcp==2.3.0`). Usa `detect_language` antes de calificar y `translate` para `/traducir` y el botón "Ver traducción" en A1/A2 (`exam/traduccion.py`). |
| `16aa427` | Fase 2: `exam/tutor.py` + `exam/lecciones.py`. `/leccion`, `/practicar`, `/nivel`, `/idioma`; si falla un tema se repite, con 3 aciertos seguidos avanza, y al terminar las 5 lecciones ofrece el examen. |
| `1e60093` | Fase 3: `exam/historial.py` (SQLite), `/puntos` con el progreso acumulado y `exam/metricas.py` (métricas del PEAS). |
| `133338b` | Fase 4: `exam/questions_b2.py` en inglés y español. Aprobar B2 termina el currículo. Con esto hay 40 lecciones. |
| `5bda319` | Fase 5: `exam/recordatorios.py` (JobQueue, America/Bogota, guardados en SQLite), pytest (`python -m pytest`), README, `docs/` (wiki y guion de la demo) y `.vscode/` fuera del repo. |

## Decisiones tomadas con el dueño
- Rama `laura` (reorganiza `exam/` en subcarpetas): **NO se fusionó**. Su B2 en inglés se adaptó a main (atributos `GEN_STYLE`, `OPTION_LEN`, `PASSAGE_SHAPE`...). El B2 en español sale de `exam/RESUMEN_ES.txt`.
- Rama `jp-dev`: solo tiene archivos B2 vacíos; no se usó.
- Se conserva `comandos_terminal.txt` (actualizado). `.vscode/` salió del repo.
- Commits: uno por fase.
- El idioma nativo del estudiante es "el otro idioma" del bot: si estudia inglés, su nativo es el español.
- La retroalimentación de las lecciones va en el idioma que se estudia; la del examen sigue en español (`grader.grade(..., ui_language=...)`).
- `bot.py` carga el `.env` ANTES de importar los módulos, para que las variables `OLLAMA_*` y `LARA_*` del `.env` se apliquen.

## Lo que FALTA (siguiente paso)
Nada se ha probado todavía con servicios reales. En el PC original Ollama era demasiado lento: `test_a1` y `test_a2` agotaron los 15 minutos por ReadTimeout. Pendiente en el PC nuevo:
1. `python -m pytest`: debe dar 13 passed (corre sin Ollama, Telegram ni Lara).
2. `python -m exam.diagnostico`, para revisar Ollama, la voz y Whisper.
3. Con Ollama real: `python -m exam.test_a1`, `test_a2`, `test_b1 lectura`, `test_b2 lectura` (en y es) y `test_es B2`. Revisar la calidad de las preguntas, sobre todo B2 y las explicaciones de las lecciones, y los tiempos.
4. Lara real: credenciales en `.env` (`LARA_ACCESS_KEY_ID`/`SECRET`), Node 22.23.4+, y luego `python -m mcp_cliente.probar_lara`.
5. Telegram real (`python bot.py`):
   - examen completo (escribir una vez en otro idioma para ver el aviso de Lara);
   - `/leccion`, fallando un ejercicio para ver que se repite el tema;
   - `/practicar`, `/traducir`, `/idioma` y `/puntos`;
   - `/recordatorio` dos minutos adelante para ver que se envía solo, y después `/recordatorio off`.
6. Ajustar según lo que salga y anotarlo aquí.
7. Después: pegar los textos de `docs/wiki/` en la wiki de GitHub, preparar la demo con `docs/guion_demo.md` y, si da el tiempo, la comparación fonética y la evaluación con usuarios.

## Comandos útiles
- Todas las pruebas sin servicios: `python -m pytest`
- Una sola prueba: `python -m exam.test_tutor`
- Métricas: `python -m exam.metricas`
- Preguntas anuladas: `python -m exam.void_report`
- Ajustes para un PC lento (PowerShell): `$env:EXAM_LISTENING_N="2"; $env:WHISPER_MODEL="tiny"; $env:OLLAMA_TIMEOUT="180"`

## Nota técnica para Claude
En la herramienta Bash de este entorno, los heredocs de Python convertían `\\n` en saltos de línea reales y rompían los reemplazos de texto que contenían `\n`. Para esos casos conviene usar la herramienta Edit.
