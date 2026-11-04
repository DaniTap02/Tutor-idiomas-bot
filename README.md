Readme · MD
Tutor Inteligente de Idiomas (Telegram Bot)
Proyecto de la materia Sistemas Inteligentes. Es un chatbot de Telegram que funciona como tutor de idiomas personalizado (similar a Duolingo), enfocado inicialmente en inglés y español, con la posibilidad de un tercer idioma según el tiempo disponible.

Al primer contacto con el bot, el usuario realiza un examen inicial (gramática, escucha y pronunciación) que determina su nivel de partida. A partir de ahí, el sistema entrega lecciones, ejercicios y retroalimentación adaptados a su desempeño, y envía recordatorios de estudio por Telegram.

El tutor es una herramienta de apoyo al aprendizaje: no reemplaza a un docente ni equivale a una certificación oficial.

Documentación (wiki)
PEAS y tipo de agente
Niveles y currículo
Diseño del examen inicial
Arquitectura técnica
Roles del equipo
Estado del proyecto
 Fase 0: diseño y fundamentos
 Fase 1: esqueleto del bot
 Fase 2: examen de nivel funcional (en curso: el examen A1 ya evalúa lectura, escritura y habla por nota de voz; faltan A2 y B1)
 Fase 3: tutor y contenido adaptativo
 Fase 4: recordatorios, pulido y evaluación final
Diseño del agente (resumen PEAS)
Tipo de agente: basado en utilidad, con aprendizaje. No reacciona con reglas fijas: evalúa el desempeño del usuario y modifica su comportamiento futuro (dificultad, contenido y ritmo de recordatorios) según el historial acumulado.

Elemento	Descripción
Entorno	Chat de Telegram. El usuario interactúa por texto, voz y archivos multimedia.
Desempeño	Nivel inicial correcto, contenido acorde al nivel, conversación coherente, retroalimentación de errores, dificultad adaptativa, recordatorios y registro del progreso.
Sensores	Mensajes de texto, notas de voz, documentos e imágenes, respuestas de examen y ejercicios, horarios de recordatorio e historial en base de datos.
Actuadores	Aplicar el examen, asignar y actualizar el nivel, enviar lecciones y material, evaluar respuestas, ajustar la dificultad, registrar el progreso y enviar recordatorios.
Métricas de éxito: precisión del examen inicial (nivel asignado frente a una referencia o autoevaluación), porcentaje de errores que no se repiten tras la retroalimentación, tasa de retorno tras un recordatorio y coherencia entre el desempeño y el ajuste de dificultad.

Propiedades del entorno: parcialmente observable, estocástico, secuencial, dinámico, discreto y de agente único.

Desafíos principales: precisión del examen en pronunciación (reconocimiento de voz y comparación fonética), comprensión de distintas formas de expresar una misma respuesta, evaluación de respuestas abiertas, coherencia conversacional, selección de contenido por nivel e idioma, y motivación del usuario a lo largo del tiempo.

Estado actual del código
El bot ya tiene un examen de ubicación y un modo de práctica con ejercicios de opción múltiple.

Examen de ubicación (nivel A1)
Al escribir /start por primera vez, el usuario elige idioma (inglés o español) y rinde el examen, que tiene tres partes:

Lectura: 10 preguntas de opción múltiple (6 de gramática y 4 de vocabulario) que genera Ollama en cada examen. El código elige los temas, baraja las opciones y filtra las preguntas dudosas (formato, palabras prohibidas y una verificación del modelo con una sola respuesta válida).
Escritura: el usuario se presenta en 3 o 4 frases. El calificador revisa idioma, requisitos de la tarea y errores; el código calcula el puntaje.
Habla: el usuario envía una nota de voz de 15 a 30 segundos. Se transcribe en local con faster-whisper, se verifica que haya hablado en el idioma del examen y el texto se califica con el mismo calificador que la escritura. El bot muestra lo que entendió.
El examen se detiene en el primer nivel que no se pasa (cada parte debe sacar al menos 60 y el promedio al menos 70). Cuando exista el examen de A2, B1 y B2, basta con agregarlos a BANCOS en exam/telegram_flow.py.

Nota sobre la pronunciación: la transcripción comprueba que el usuario se hizo entender, pero no mide la pronunciación fonética. La comparación fonética sigue en la hoja de ruta.

Práctica (español)
5 ejercicios de gramática y vocabulario con tres opciones.
Se responde escribiendo la palabra o el número de la opción (1, 2 o 3).
La comparación ignora mayúsculas y tildes.
Explicación después de cada respuesta, sea correcta o no.
Puntuación por usuario.
Respuesta a saludos simples.
Comandos
Comando	Descripción
/start	Inicia el examen si es la primera vez; si ya tiene nivel, muestra el menú
/help	Ayuda de uso
/practicar	Presenta un ejercicio aleatorio
/siguiente	Cambia a otro ejercicio
/puntos	Muestra respuestas correctas e incorrectas
/reiniciar	Solo para pruebas: borra el nivel y repite el examen
Limitaciones actuales
Solo existe el examen de A1; A2, B1 y B2 están pendientes (el nivel queda como provisional si se pasa A1).
La práctica tiene solo 5 ejercicios y únicamente en español.
El examen necesita Ollama encendido para generar preguntas y calificar.
Los datos se guardan en un archivo local (datos_bot.pkl); todavía no hay base de datos ni historial de progreso.
La parte de habla no evalúa la pronunciación fonética.
Aún no hay recordatorios.
Requisitos
Python 3.10 o superior (el entorno del repositorio fue creado con Python 3.14).
Una cuenta de Telegram y un token de bot creado con @BotFather.
Ollama con el modelo qwen2.5:7b (o el que configures con OLLAMA_MODEL).
Dependencias de Python en requirements.txt, entre ellas python-telegram-bot 22.x, python-dotenv, httpx y faster-whisper.
Instalación
bash
# 1. Clonar el repositorio
git clone https://github.com/DaniTap02/Tutor-idiomas-bot.git
cd Tutor-idiomas-bot

# 2. Crear y activar un entorno virtual
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Descargar el modelo de Ollama
ollama pull qwen2.5:7b
La primera vez que alguien envíe una nota de voz, faster-whisper descarga el modelo de transcripción (unos 500 MB con small), así que esa primera transcripción tarda más.

Configuración
Abre @BotFather en Telegram, envía /newbot y sigue los pasos para obtener el token.
Crea un archivo .env en la raíz del proyecto:
env
TELEGRAM_BOT_TOKEN=tu_token_aqui
Variables opcionales (con su valor por defecto):

Variable	Descripción	Por defecto
OLLAMA_URL	Dirección del servidor de Ollama	http://localhost:11434
OLLAMA_MODEL	Modelo usado para generar preguntas y calificar	qwen2.5:7b
WHISPER_MODEL	Modelo de transcripción (base es más rápido, small más preciso)	small
Seguridad: .env ya está en .gitignore. No lo subas al repositorio ni lo compartas (por ejemplo, dentro de un .zip). Si el token se expone, revócalo con /revoke en @BotFather y genera uno nuevo.

Ejecución
Con Ollama encendido:

bash
python bot.py
Luego abre tu bot en Telegram y escribe /start. El bot usa long polling, por lo que no necesita servidor público ni webhook.

Prueba del examen sin Telegram
bash
python -m exam.test_a1
Imprime las preguntas generadas con la respuesta correcta señalada y califica textos de ejemplo. Hay más detalles en comandos_terminal.txt.

Estructura del proyecto
Tutor-idiomas-bot/
├── bot.py                  # Comandos, práctica y registro de manejadores
├── exam/
│   ├── __init__.py
│   ├── telegram_flow.py    # Flujo del examen: lectura, escritura y habla
│   ├── stt.py              # Transcripción de notas de voz (faster-whisper)
│   ├── grader.py           # Calificador con Ollama (escritura y habla)
│   ├── question_generator.py  # Generación y verificación de preguntas de lectura
│   ├── questions_a1.py     # Temas, tareas y checklist del examen A1
│   ├── placement.py        # Reglas para pasar de nivel
│   └── test_a1.py          # Prueba por terminal
├── requirements.txt        # Dependencias
├── comandos_terminal.txt   # Guía para probar el examen
├── .env                    # Token de Telegram (no se versiona)
├── .gitignore              # Excluye .env, .venv/, __pycache__/, *.pyc y datos_bot.pkl
└── README.md
Cómo funciona el flujo de voz:

telegram_flow.py pasa del examen de escritura a la parte habla y envía la consigna.
Cuando llega una nota de voz, voz_de_examen() la descarga a una carpeta temporal y llama a transcribe() en un hilo, para no congelar el bot.
transcribe() devuelve el texto y el idioma detectado; si el idioma no coincide con el del examen, se pide repetir el audio.
El texto se califica con grade(..., is_transcript=True) y el checklist speaking de questions_a1.py, y el puntaje se guarda en scores["habla"].
Cómo funciona bot.py:

EJERCICIOS: lista de diccionarios con pregunta, opciones, respuesta y explicacion (modo práctica).
normalizar(): pasa el texto a minúsculas y elimina tildes para comparar respuestas.
/practicar elige un ejercicio al azar y lo guarda en context.user_data.
responder() atiende primero el examen (si está en curso) y, si no, compara la respuesta del usuario con la correcta.
voz() envía las notas de voz al examen; fuera del examen avisa que aún no se usan.
main() registra los manejadores y arranca el bot con run_polling().
Agregar ejercicios
python
{
    "pregunta": "¿Cuál es el plural de «lápiz»?",
    "opciones": ["lápizes", "lápices", "lápizs"],
    "respuesta": "lápices",
    "explicacion": "Las palabras terminadas en -z cambian la z por c: lápiz → lápices.",
},
Cada ejercicio debe tener exactamente tres opciones, porque el bot acepta las respuestas numéricas 1, 2 y 3.

Hoja de ruta
 Examen inicial de nivel: gramática, escucha y pronunciación. (A1 con lectura, escritura y habla listo; faltan A2, B1 y B2, y la parte de escucha)
 Niveles y currículo por idioma (inglés y español).
 Contenido en inglés; tercer idioma opcional según el tiempo.
 Notas de voz con reconocimiento de voz (STT) en el examen.
 Comparación fonética de la pronunciación.
 Parte de escucha: el bot envía audio (TTS) y el usuario responde.
 Tutor adaptativo que ajuste la dificultad según el desempeño.
 Evaluación de respuestas abiertas y retroalimentación de errores.
 Base de datos para el historial de progreso.
 Recordatorios de estudio por Telegram con horario configurable.
 requirements.txt.
 Pruebas automatizadas.
Ramas
main: rama principal.
laura: rama de trabajo.
Contribuir
Crea una rama a partir de main.
Haz tus cambios y confirma con mensajes claros.
Abre un Pull Request describiendo qué cambió y por qué.
