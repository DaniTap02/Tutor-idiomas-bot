"""Historial del estudiante en SQLite (sqlite3 de la librería estándar).

Guarda lo que el agente necesita para aprender del estudiante y lo que mide exam/metricas.py:
  usuarios        id de Telegram, primera y última vez que usó el bot
  actividad       cada vez que el usuario hace algo (para la tasa de retorno tras un recordatorio)
  examen_partes   puntaje de cada parte (lectura, escucha, escritura, habla) por nivel rendido
  examen_niveles  si aprobó o no cada nivel del examen y el promedio
  ejercicios      cada ejercicio respondido: origen (práctica/lección), tema, correcto o no, fecha
  lecciones       lecciones completadas con el puntaje de su escritura
  errores         errores que encontró el calificador, por tipo (grammar, vocabulary, spelling)
  lara_usos       uso de las herramientas de Lara (detect_language, translate): ok o motivo de falla

El historial NO se borra con /reiniciar (que solo reinicia el nivel): /puntos muestra el progreso
acumulado de verdad. El archivo .db está en el .gitignore: nunca se sube.

Nada de lo que hay aquí puede tumbar el bot: si la base falla, se registra en el log y se sigue.
El usuario se identifica con user_data["uid"], que bot.py pone en cada mensaje.

Variable de entorno: HISTORIAL_DB (por defecto historial.db, en la carpeta del proyecto).
"""
import logging
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone

log = logging.getLogger(__name__)

DB = os.getenv("HISTORIAL_DB", "historial.db")
_LOCK = threading.Lock()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    creado TEXT NOT NULL,
    ultimo_uso TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actividad (
    usuario INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    tipo TEXT
);
CREATE TABLE IF NOT EXISTS examen_partes (
    usuario INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    idioma TEXT NOT NULL,
    nivel TEXT NOT NULL,
    parte TEXT NOT NULL,
    puntaje REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS examen_niveles (
    usuario INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    idioma TEXT NOT NULL,
    nivel TEXT NOT NULL,
    aprobado INTEGER NOT NULL,
    promedio REAL
);
CREATE TABLE IF NOT EXISTS ejercicios (
    usuario INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    origen TEXT NOT NULL,
    idioma TEXT NOT NULL,
    nivel TEXT NOT NULL,
    tema TEXT NOT NULL,
    correcta INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS lecciones (
    usuario INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    idioma TEXT NOT NULL,
    nivel TEXT NOT NULL,
    leccion TEXT NOT NULL,
    puntaje REAL
);
CREATE TABLE IF NOT EXISTS errores (
    usuario INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    idioma TEXT NOT NULL,
    nivel TEXT NOT NULL,
    origen TEXT NOT NULL,
    habilidad TEXT NOT NULL,
    tipo TEXT NOT NULL,
    fragmento TEXT,
    correccion TEXT
);
CREATE TABLE IF NOT EXISTS lara_usos (
    fecha TEXT NOT NULL,
    herramienta TEXT NOT NULL,
    ok INTEGER NOT NULL,
    motivo TEXT
);
CREATE INDEX IF NOT EXISTS ix_ejercicios_usuario ON ejercicios (usuario, idioma, tema, fecha);
CREATE INDEX IF NOT EXISTS ix_actividad_usuario ON actividad (usuario, fecha);
"""

TIPOS_ERROR = ("grammar", "vocabulary", "spelling")


def ahora() -> str:
    """Fecha UTC con microsegundos: las métricas ordenan por fecha y dos registros del mismo
    segundo (un texto y el siguiente) deben quedar en orden."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def conectar(ruta: str | None = None) -> sqlite3.Connection:
    """Conexión con el esquema creado. Cada operación abre y cierra la suya (es rápido y seguro con hilos)."""
    con = sqlite3.connect(ruta or DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def _escribir(sql: str, filas: list[tuple]) -> bool:
    """Ejecuta una escritura. Nunca lanza: la base es un registro, no puede frenar al estudiante."""
    if not filas:
        return True
    try:
        with _LOCK, closing(conectar()) as con, con:
            con.executemany(sql, filas)
        return True
    except Exception:
        log.warning("No pude guardar en el historial (%s)", DB, exc_info=True)
        return False


def uid(user_data: dict) -> int | None:
    return user_data.get("uid") if isinstance(user_data, dict) else None


# ---------------------------------------------------------------- Escrituras

def registrar_actividad(usuario: int | None, tipo: str = "mensaje") -> None:
    if usuario is None:
        return
    fecha = ahora()
    try:
        with _LOCK, closing(conectar()) as con, con:
            con.execute("INSERT INTO usuarios (id, creado, ultimo_uso) VALUES (?, ?, ?) "
                        "ON CONFLICT(id) DO UPDATE SET ultimo_uso = excluded.ultimo_uso",
                        (usuario, fecha, fecha))
            con.execute("INSERT INTO actividad (usuario, fecha, tipo) VALUES (?, ?, ?)", (usuario, fecha, tipo))
    except Exception:
        log.warning("No pude guardar la actividad en el historial", exc_info=True)


def registrar_examen(user_data: dict, idioma: str, nivel: str, puntajes: dict, aprobado: bool) -> None:
    """Puntaje de cada parte evaluada y el resultado del nivel. Las partes no evaluadas no se guardan."""
    usuario = uid(user_data)
    if usuario is None:
        return
    fecha = ahora()
    _escribir("INSERT INTO examen_partes VALUES (?, ?, ?, ?, ?, ?)",
              [(usuario, fecha, idioma, nivel, parte, float(p)) for parte, p in puntajes.items() if p is not None])
    valores = [float(p) for p in puntajes.values() if p is not None]
    promedio = sum(valores) / len(valores) if valores else None
    _escribir("INSERT INTO examen_niveles VALUES (?, ?, ?, ?, ?, ?)",
              [(usuario, fecha, idioma, nivel, int(bool(aprobado)), promedio)])


def registrar_ejercicio(user_data: dict, origen: str, idioma: str, nivel: str, tema: str, correcta: bool) -> None:
    usuario = uid(user_data)
    if usuario is None:
        return
    _escribir("INSERT INTO ejercicios VALUES (?, ?, ?, ?, ?, ?, ?)",
              [(usuario, ahora(), origen, idioma, nivel, tema, int(bool(correcta)))])


def registrar_leccion(user_data: dict, idioma: str, nivel: str, leccion: str, puntaje: float | None) -> None:
    usuario = uid(user_data)
    if usuario is None:
        return
    _escribir("INSERT INTO lecciones VALUES (?, ?, ?, ?, ?, ?)",
              [(usuario, ahora(), idioma, nivel, leccion, puntaje)])


def registrar_errores(user_data: dict, idioma: str, nivel: str, origen: str, habilidad: str, errores: list) -> None:
    """Errores del calificador. origen: "examen" o "leccion"; habilidad: "writing" o "speaking"."""
    usuario = uid(user_data)
    if usuario is None or not errores:
        return
    fecha = ahora()
    filas = []
    for e in errores:
        if not isinstance(e, dict):
            continue
        tipo = str(e.get("type", "")).lower()
        filas.append((usuario, fecha, idioma, nivel, origen, habilidad,
                      tipo if tipo in TIPOS_ERROR else "otro",
                      str(e.get("fragment", ""))[:200], str(e.get("correction", ""))[:200]))
    _escribir("INSERT INTO errores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", filas)


def registrar_uso_lara(herramienta: str, ok: bool, motivo: str | None) -> None:
    """Gancho de mcp_cliente.lara (cliente.al_usar). No guarda textos: solo la herramienta y el resultado."""
    _escribir("INSERT INTO lara_usos VALUES (?, ?, ?, ?)", [(ahora(), herramienta, int(bool(ok)), motivo)])


# ---------------------------------------------------------------- Lecturas

def resumen_usuario(usuario: int) -> dict:
    """Progreso acumulado por idioma para /puntos. Devuelve {} si no hay datos o la base falla."""
    try:
        with closing(conectar()) as con:
            out: dict = {}
            for f in con.execute("SELECT idioma, SUM(correcta) AS ok, COUNT(*) AS total FROM ejercicios "
                                 "WHERE usuario = ? GROUP BY idioma", (usuario,)):
                out.setdefault(f["idioma"], {})["ejercicios"] = (f["ok"] or 0, f["total"])
            for f in con.execute("SELECT idioma, COUNT(DISTINCT nivel || leccion) AS n FROM lecciones "
                                 "WHERE usuario = ? GROUP BY idioma", (usuario,)):
                out.setdefault(f["idioma"], {})["lecciones"] = f["n"]
            for f in con.execute("SELECT idioma, nivel, MAX(aprobado) AS aprobado, COUNT(*) AS veces "
                                 "FROM examen_niveles WHERE usuario = ? GROUP BY idioma, nivel ORDER BY nivel",
                                 (usuario,)):
                out.setdefault(f["idioma"], {}).setdefault("examenes", []).append(
                    (f["nivel"], bool(f["aprobado"]), f["veces"]))
            for f in con.execute("SELECT idioma, tema, SUM(correcta) AS ok, COUNT(*) AS total FROM ejercicios "
                                 "WHERE usuario = ? GROUP BY idioma, tema HAVING total >= 2 "
                                 "ORDER BY 1.0 * SUM(correcta) / COUNT(*) ASC LIMIT 20", (usuario,)):
                out.setdefault(f["idioma"], {}).setdefault("temas_flojos", []).append(
                    (f["tema"], f["ok"] or 0, f["total"]))
            for f in con.execute("SELECT idioma, tipo, COUNT(*) AS n FROM errores WHERE usuario = ? "
                                 "GROUP BY idioma, tipo ORDER BY n DESC", (usuario,)):
                out.setdefault(f["idioma"], {}).setdefault("errores", []).append((f["tipo"], f["n"]))
            return out
    except Exception:
        log.warning("No pude leer el historial", exc_info=True)
        return {}
