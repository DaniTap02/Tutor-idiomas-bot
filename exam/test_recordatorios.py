"""Prueba SIN Telegram ni internet de los recordatorios (JobQueue real de python-telegram-bot,
base SQLite temporal):

    python -m exam.test_recordatorios      (o con pytest)

Comprueba /recordatorio HH:MM y off, que se guardan en SQLite y se vuelven a programar al
reiniciar el bot, que nunca quedan dos trabajos para el mismo usuario, la hora de Colombia, y que
el mensaje invita a seguir la lección pendiente en el idioma que estudia.
"""
import asyncio
import logging
import os
import tempfile
from contextlib import closing
from types import SimpleNamespace

from telegram.ext import Application

from exam import historial, recordatorios as rec

logging.disable(logging.CRITICAL)

ok_total = 0
fail_total = 0


def check(nombre, condicion):
    global ok_total, fail_total
    print(("  OK    " if condicion else "  FALLA ") + nombre)
    ok_total += bool(condicion)
    fail_total += not condicion


class Msg:
    def __init__(self, chat_id=555):
        self.chat_id = chat_id
        self.enviados = []

    async def reply_text(self, texto, reply_markup=None):
        self.enviados.append(texto)
        return self


def upd(usuario=111):
    m = Msg()
    return SimpleNamespace(effective_message=m, message=m, effective_user=SimpleNamespace(id=usuario))


def app_nueva():
    # Sin conexión: build() no llama a Telegram. La JobQueue no se arranca, solo se programa.
    return Application.builder().token("123456:PRUEBA-sin-red").build()


def trabajos(app, usuario=111):
    return [j for j in app.job_queue.get_jobs_by_name(rec.nombre_trabajo(usuario)) if not j.removed]


async def casos():
    bueno = historial.DB
    historial.DB = os.path.join(tempfile.mkdtemp(), "recordatorios_prueba.db")
    try:
        print("\n== Hora")
        t = rec.leer_hora("19:30")
        check("19:30 se entiende, en hora de Colombia", t.hour == 19 and t.minute == 30
              and str(t.tzinfo) == "America/Bogota")
        check("7:05 también", rec.leer_hora("7:05").hour == 7)
        check("horas inválidas se rechazan", all(rec.leer_hora(x) is None for x in ("25:00", "19:60", "siete", "")))

        print("\n== /recordatorio")
        app = app_nueva()
        ctx = SimpleNamespace(args=["19:30"], job_queue=app.job_queue, user_data={})
        u = upd()
        await rec.comando_recordatorio(u, ctx)
        check("programa el recordatorio y lo confirma", len(trabajos(app)) == 1
              and "19:30" in u.message.enviados[-1])
        check("queda guardado en SQLite", rec.activos() == [(111, 555, "19:30")])
        trigger = trabajos(app)[0].job.trigger
        check("el trabajo diario usa la zona America/Bogota", "America/Bogota" in str(trigger.timezone))

        ctx.args = ["07:00"]
        await rec.comando_recordatorio(upd(), ctx)
        check("cambiar la hora no duplica el trabajo", len(trabajos(app)) == 1 and rec.hora_de(111) == "07:00")

        ctx.args = []
        u = upd()
        await rec.comando_recordatorio(u, ctx)
        check("/recordatorio sin hora dice cómo está", "07:00" in u.message.enviados[-1])

        ctx.args = ["mañana"]
        u = upd()
        await rec.comando_recordatorio(u, ctx)
        check("hora mal escrita: explica el formato", "formato 24 horas" in u.message.enviados[-1])

        print("\n== Sobrevive al reinicio")
        app2 = app_nueva()
        check("al arrancar se vuelve a programar desde SQLite", rec.programar_todos(app2) == 1
              and len(trabajos(app2)) == 1)

        ctx.args = ["off"]
        await rec.comando_recordatorio(upd(), ctx)
        check("/recordatorio off lo apaga", trabajos(app) == [] and rec.activos() == [])
        check("apagado: tras reiniciar no se programa", rec.programar_todos(app_nueva()) == 0)

        print("\n== Mensaje y envío")
        datos = {"nivel": {"language": "en", "level": "A2", "provisional": False},
                 "progreso": {"en": {"level": "A2", "leccion": 2}}}
        texto, idioma = rec.mensaje_para(datos)
        check("invita a la lección pendiente, en el idioma que estudia",
              idioma == "en" and "Travel and plans" in texto and "A2" in texto)
        texto, idioma = rec.mensaje_para({"nivel": {"language": "es", "level": "B1"}})
        check("sin progreso: la lección 1 de su nivel, en español", "Experiencias y relatos" in texto)
        texto, _ = rec.mensaje_para({})
        check("sin nivel todavía: mensaje genérico", "practicar" in texto)

        enviados = []

        async def send_message(chat_id, text, reply_markup=None):
            enviados.append((chat_id, text, reply_markup))

        ctx_job = SimpleNamespace(job=SimpleNamespace(chat_id=555, user_id=111), user_data=datos,
                                  bot=SimpleNamespace(send_message=send_message))
        await rec.enviar_recordatorio(ctx_job)
        check("el recordatorio se envía con botón para seguir la lección", enviados
              and enviados[0][2].inline_keyboard[0][0].callback_data == "recl:seguir")
        with closing(historial.conectar()) as con:
            n = con.execute("SELECT COUNT(*) FROM recordatorio_envios").fetchone()[0]
        check("cada envío queda registrado para la tasa de retorno", n == 1)
    finally:
        historial.DB = bueno


def correr():
    asyncio.run(casos())
    print(f"\nResultado: {ok_total} OK, {fail_total} con falla")
    return fail_total


def test_recordatorios():
    assert correr() == 0, "hay comprobaciones con falla (mira la salida con: pytest -s)"


if __name__ == "__main__":
    raise SystemExit(1 if correr() else 0)
