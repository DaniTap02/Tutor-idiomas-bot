# Tutor Inteligente de Idiomas (Telegram Bot)

Proyecto de la materia **Sistemas Inteligentes**. Es un chatbot de Telegram que funciona como tutor de idiomas personalizado (similar a Duolingo), enfocado inicialmente en **inglés y español**, con la posibilidad de un tercer idioma según el tiempo disponible.

Al primer contacto con el bot, el usuario realiza un **examen inicial** (gramática, escucha y pronunciación) que determina su nivel de partida. A partir de ahí, el sistema entrega lecciones, ejercicios y retroalimentación adaptados a su desempeño, y envía recordatorios de estudio por Telegram.

> El tutor es una herramienta de apoyo al aprendizaje: no reemplaza a un docente ni equivale a una certificación oficial.

## Documentación (wiki)

- [PEAS y tipo de agente](https://github.com/DaniTap02/Tutor-idiomas-bot/wiki/PEAS-y-tipo-de-agente)
- [Niveles y currículo](https://github.com/DaniTap02/Tutor-idiomas-bot/wiki/Niveles-y-curr%C3%ADculo)
- [Diseño del examen inicial](https://github.com/DaniTap02/Tutor-idiomas-bot/wiki/Dise%C3%B1o-del-examen-inicial)
- [Arquitectura técnica](https://github.com/DaniTap02/Tutor-idiomas-bot/wiki/Arquitectura-t%C3%A9cnica)
- [Roles del equipo](https://github.com/DaniTap02/Tutor-idiomas-bot/wiki/Roles-del-equipo)

## Estado del proyecto

- [X] **Fase 0:** diseño y fundamentos
- [X] **Fase 1:** esqueleto del bot
- [ ] **Fase 2:** examen de nivel funcional
- [ ] **Fase 3:** tutor y contenido adaptativo
- [ ] **Fase 4:** recordatorios, pulido y evaluación final

## Diseño del agente (resumen PEAS)

**Tipo de agente:** basado en utilidad, con aprendizaje. No reacciona con reglas fijas: evalúa el desempeño del usuario y modifica su comportamiento futuro (dificultad, contenido y ritmo de recordatorios) según el historial acumulado.

| Elemento | Descripción |
|---|---|
| **Entorno** | Chat de Telegram. El usuario interactúa por texto, voz y archivos multimedia. |
| **Desempeño** | Nivel inicial correcto, contenido acorde al nivel, conversación coherente, retroalimentación de errores, dificultad adaptativa, recordatorios y registro del progreso. |
| **Sensores** | Mensajes de texto, notas de voz, documentos e imágenes, respuestas de examen y ejercicios, horarios de recordatorio e historial en base de datos. |
| **Actuadores** | Aplicar el examen, asignar y actualizar el nivel, enviar lecciones y material, evaluar respuestas, ajustar la dificultad, registrar el progreso y enviar recordatorios. |

**Métricas de éxito:** precisión del examen inicial (nivel asignado frente a una referencia o autoevaluación), porcentaje de errores que no se repiten tras la retroalimentación, tasa de retorno tras un recordatorio y coherencia entre el desempeño y el ajuste de dificultad.

**Propiedades del entorno:** parcialmente observable, estocástico, secuencial, dinámico, discreto y de agente único.

**Desafíos principales:** precisión del examen en pronunciación (reconocimiento de voz y comparación fonética), comprensión de distintas formas de expresar una misma respuesta, evaluación de respuestas abiertas, coherencia conversacional, selección de contenido por nivel e idioma, y motivación del usuario a lo largo del tiempo.

## Estado actual del código

La versión actual es un prototipo que enseña **español** con ejercicios de opción múltiple:

- 5 ejercicios de gramática y vocabulario con tres opciones.
- Se responde escribiendo la palabra o el número de la opción (1, 2 o 3).
- La comparación ignora mayúsculas y tildes.
- Explicación después de cada respuesta, sea correcta o no.
- Puntuación por usuario durante la sesión.
- Respuesta a saludos simples.

### Comandos

| Comando | Descripción |
|---|---|
| `/start` | Mensaje de bienvenida y lista de comandos |
| `/help` | Ayuda de uso |
| `/practicar` | Presenta un ejercicio aleatorio |
| `/siguiente` | Cambia a otro ejercicio |
| `/puntos` | Muestra respuestas correctas e incorrectas de la sesión |

### Limitaciones actuales

- La puntuación se guarda en memoria y se pierde al reiniciar el bot.
- Solo hay 5 ejercicios y un único idioma.
- Aún no hay examen inicial, niveles, voz, base de datos ni recordatorios.
- No existe `requirements.txt`.

## Requisitos

- Python 3.10 o superior (el entorno del repositorio fue creado con Python 3.14).
- Una cuenta de Telegram y un token de bot creado con [@BotFather](https://t.me/BotFather).
- Dependencias: [`python-telegram-bot`](https://python-telegram-bot.org/) 22.x y [`python-dotenv`](https://pypi.org/project/python-dotenv/).

## Instalación

```bash
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
pip install python-telegram-bot python-dotenv
```

## Configuración

1. Abre [@BotFather](https://t.me/BotFather) en Telegram, envía `/newbot` y sigue los pasos para obtener el token.
2. Crea un archivo `.env` en la raíz del proyecto:

```env
TELEGRAM_BOT_TOKEN=tu_token_aqui
```

> **Seguridad:** `.env` ya está en `.gitignore`. No lo subas al repositorio ni lo compartas (por ejemplo, dentro de un `.zip`). Si el token se expone, revócalo con `/revoke` en @BotFather y genera uno nuevo.

## Ejecución

```bash
python bot.py
```

Luego abre tu bot en Telegram y escribe `/start`. El bot usa *long polling*, por lo que no necesita servidor público ni webhook.

## Estructura del proyecto

```
Tutor-idiomas-bot/
├── bot.py        # Comandos, ejercicios y puntuación
├── .env          # Token de Telegram (no se versiona)
├── .gitignore    # Excluye .env, .venv/, __pycache__/ y *.pyc
└── README.md
```

Cómo funciona `bot.py`:

- `EJERCICIOS`: lista de diccionarios con `pregunta`, `opciones`, `respuesta` y `explicacion`.
- `normalizar()`: pasa el texto a minúsculas y elimina tildes para comparar respuestas.
- `/practicar` elige un ejercicio al azar y lo guarda en `context.user_data`.
- `responder()` compara el texto del usuario con la respuesta correcta y actualiza el puntaje.
- `main()` registra los manejadores y arranca el bot con `run_polling()`.

### Agregar ejercicios

```python
{
    "pregunta": "¿Cuál es el plural de «lápiz»?",
    "opciones": ["lápizes", "lápices", "lápizs"],
    "respuesta": "lápices",
    "explicacion": "Las palabras terminadas en -z cambian la z por c: lápiz → lápices.",
},
```

Cada ejercicio debe tener exactamente tres opciones, porque el bot acepta las respuestas numéricas 1, 2 y 3.

## Hoja de ruta

- [ ] Examen inicial de nivel: gramática, escucha y pronunciación.
- [ ] Niveles y currículo por idioma (inglés y español).
- [ ] Contenido en inglés; tercer idioma opcional según el tiempo.
- [ ] Notas de voz con reconocimiento de voz (STT) y comparación fonética.
- [ ] Tutor adaptativo que ajuste la dificultad según el desempeño.
- [ ] Evaluación de respuestas abiertas y retroalimentación de errores.
- [ ] Base de datos para el historial de progreso.
- [ ] Recordatorios de estudio por Telegram con horario configurable.
- [ ] `requirements.txt` y pruebas automatizadas.

## Ramas

- `main`: rama principal.
- `laura`: rama de trabajo.

## Contribuir

1. Crea una rama a partir de `main`.
2. Haz tus cambios y confirma con mensajes claros.
3. Abre un Pull Request describiendo qué cambió y por qué.
