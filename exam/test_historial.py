"""Prueba SIN Telegram del historial en SQLite y de las métricas (base temporal, no toca historial.db):

    python -m exam.test_historial

Comprueba que se guarda cada cosa (examen por parte, ejercicios, lecciones, errores por tipo, uso de
Lara), que /puntos muestra el progreso acumulado y no se pierde con /reiniciar, que la base rota no
tumba al bot, y que las métricas del PEAS dan lo esperado con datos conocidos.
"""
import asyncio
import json
import logging
import os
import sqlite3
import tempfile
from contextlib import closing

from exam import historial, metricas

logging.disable(logging.CRITICAL)

CARPETA = tempfile.mkdtemp()
historial.DB = os.path.join(CARPETA, "historial_prueba.db")

ok_total = 0
fail_total = 0


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK    " if condicion else "  FALLA ") + nombre)
    ok_total += bool(condicion)
    fail_total += not condicion


def contar(tabla):
    with closing(historial.conectar()) as con:
        return con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]


ud = {"uid": 111}
otro = {"uid": 222}

print("\n== Escrituras")
historial.registrar_actividad(111)
historial.registrar_examen(ud, "en", "A1", {"lectura": 80, "escucha": None, "escritura": 70, "habla": 90}, True)
historial.registrar_examen(ud, "en", "A2", {"lectura": 40, "escritura": 50}, False)
check("examen: una fila por parte evaluada (sin la que no se evaluó)", contar("examen_partes") == 5)
check("examen: una fila por nivel rendido", contar("examen_niveles") == 2)

for tema, correcta in [("T1", False), ("T1", True), ("T2", False), ("T2", False), ("T2", True), ("T3", True)]:
    historial.registrar_ejercicio(ud, "leccion", "en", "A2", tema, correcta)
historial.registrar_ejercicio(otro, "practica", "es", "A1", "T9", True)
historial.registrar_ejercicio({}, "practica", "es", "A1", "T9", True)   # sin uid: no se guarda
check("ejercicios guardados (y sin uid no se guarda nada)", contar("ejercicios") == 7)

historial.registrar_errores(ud, "en", "A2", "leccion", "writing", [
    {"fragment": "I goed", "type": "grammar", "correction": "I went"},
    {"fragment": "tomorow", "type": "spelling", "correction": "tomorrow"},
    {"fragment": "x", "type": "raro", "correction": "y"},
])
historial.registrar_leccion(ud, "en", "A2", "A2-1", 85)
historial.registrar_errores(ud, "en", "A2", "leccion", "writing", [
    {"fragment": "I GOED", "type": "grammar", "correction": "I went"},
])
historial.registrar_leccion(ud, "en", "A2", "A2-2", 90)
with closing(historial.conectar()) as con:
    tipos = sorted(f[0] for f in con.execute("SELECT DISTINCT tipo FROM errores"))
check("errores por tipo; un tipo desconocido queda como 'otro'", tipos == ["grammar", "otro", "spelling"])

historial.registrar_uso_lara("translate", True, None)
historial.registrar_uso_lara("detect_language", False, "lara_cuota")
check("uso de Lara guardado (sin textos)", contar("lara_usos") == 2)

print("\n== /puntos")
import bot  # noqa: E402  (importa el bot sin arrancarlo)

datos = historial.resumen_usuario(111)
texto = bot.texto_puntos(datos)
check("resumen por idioma con ejercicios y aciertos", datos["en"]["ejercicios"] == (3, 6))
check("/puntos muestra aciertos, lecciones y exámenes", "50% de aciertos en 6 ejercicios" in texto
      and "Lecciones completadas: 2" in texto and "Examen A1: aprobado" in texto and "Examen A2: no aprobado" in texto)
check("/puntos muestra los errores por tipo", "gramática 2" in texto and "ortografía 1" in texto)
check("/puntos de otro usuario no mezcla datos", historial.resumen_usuario(222)["es"]["ejercicios"] == (1, 1)
      and "en" not in historial.resumen_usuario(222))
check("usuario sin datos: mensaje para empezar", "Todavía no tienes" in bot.texto_puntos({}))


class Msg:
    def __init__(self):
        self.enviados = []

    async def reply_text(self, texto, reply_markup=None):
        self.enviados.append(texto)
        return self


class Ctx:
    def __init__(self):
        self.user_data = {"uid": 111, "nivel": {"language": "en", "level": "A2", "provisional": False},
                          "niveles": {"en": {"language": "en", "level": "A2", "provisional": False}}}


class U:
    def __init__(self):
        self.message = Msg()
        self.effective_message = self.message
        self.effective_user = type("Usuario", (), {"id": 111})()
        self.callback_query = None


async def reiniciar_y_puntos():
    ctx = Ctx()
    await bot.reiniciar(U(), ctx)
    u = U()
    await bot.puntos(u, ctx)
    return ctx, u.message.enviados[-1]


ctx, texto = asyncio.run(reiniciar_y_puntos())
check("/reiniciar borra el nivel pero NO el historial", "nivel" not in ctx.user_data
      and "50% de aciertos en 6 ejercicios" in texto)

ctx = {"uid": None}
u = U()
asyncio.run(bot.anotar_usuario(u, type("C", (), {"user_data": ctx})()))
check("anotar_usuario guarda el uid y la actividad", ctx["uid"] == 111 and contar("actividad") == 2)

print("\n== La base nunca tumba al bot")
bueno = historial.DB
historial.DB = os.path.join(CARPETA, "no_existe", "otra", "x.db")
check("escribir en una ruta imposible no lanza", historial.registrar_ejercicio(ud, "pr", "en", "A1", "T", True) is None)
check("leer de una ruta imposible devuelve {}", historial.resumen_usuario(111) == {})
historial.DB = bueno

print("\n== Métricas")
void = os.path.join(CARPETA, "voided.jsonl")
with open(void, "w", encoding="utf-8") as f:
    for razon, kind in [("ambiguous", "grammar"), ("ambiguous", "vocab"), ("no_evidence", "listening"),
                        ("llm_error:ReadTimeout", "grammar")]:
        f.write(json.dumps({"reason": razon, "kind": kind}) + "\n")

with closing(historial.conectar()) as con:
    con.executescript("CREATE TABLE IF NOT EXISTS recordatorio_envios (usuario INTEGER, fecha TEXT);")
    con.execute("INSERT INTO recordatorio_envios VALUES (111, '2000-01-01T10:00:00+00:00')")
    con.execute("INSERT INTO recordatorio_envios VALUES (111, '2000-01-05T10:00:00+00:00')")
    con.execute("INSERT INTO actividad VALUES (111, '2000-01-01T12:00:00+00:00', 'mensaje')")
    con.commit()

m = metricas.calcular(historial.DB, void)
e = m["errores_ejercicios"]
# T1: falla -> acierta (corregido). T2: falla -> falla (no), falla -> acierta (sí). => 2 de 3
check("ejercicios: % de temas fallados que se aciertan la vez siguiente", e["fallos_con_reintento"] == 3
      and e["corregidos"] == 2)
t = m["errores_textos"]
# 1.er texto: I goed, tomorow, x. 2.º texto: I GOED (repetido). Después hay otro texto sin errores.
# Evaluables: los 4 (todos tienen un texto posterior). No repetidos: tomorow, x y el 2.º I GOED.
check("textos: 'I goed' se repitió; 'tomorow' y 'x' no", t["evaluables"] == 4 and t["no_repetidos"] == 3)
temas = {f["tema"]: f["porcentaje"] for f in m["aciertos_por_tema"] if f["idioma"] == "en"}
check("aciertos por tema", temas["T1"] == 50 and round(temas["T2"]) == 33 and temas["T3"] == 100)
ex = {(f["nivel"]): f for f in m["avance"]["examenes"]}
check("avance por nivel: aprobó A1, no A2; 2 lecciones de A2", ex["A1"]["aprobaron"] == 1
      and ex["A2"]["aprobaron"] == 0 and m["avance"]["lecciones"][0]["completadas"] == 2)
check("tasa de retorno: volvió tras 1 de 2 recordatorios", m["retorno"]["enviados"] == 2
      and m["retorno"]["con_retorno"] == 1 and m["retorno"]["porcentaje"] == 50)
a = m["anuladas"]
check("anuladas por motivo y por parte", a["total"] == 4 and dict(a["por_motivo"])["ambiguous"] == 2
      and dict(a["por_motivo"])["llm_error"] == 1 and dict(a["por_parte"])["grammar"] == 2)
check("uso de Lara por herramienta", {f["herramienta"]: f["ok"] for f in m["lara"]} == {"detect_language": 0, "translate": 1})

with closing(sqlite3.connect(os.path.join(CARPETA, "vacia.db"))) as _:
    pass
vacia = metricas.calcular(os.path.join(CARPETA, "vacia.db"), os.path.join(CARPETA, "no_hay.jsonl"))
check("sin datos: las métricas dicen 'sin datos' en vez de fallar", vacia["errores_ejercicios"]["porcentaje"] is None
      and vacia["retorno"]["porcentaje"] is None and vacia["anuladas"]["total"] == 0)

print(f"\nResultado: {ok_total} OK, {fail_total} con falla")
