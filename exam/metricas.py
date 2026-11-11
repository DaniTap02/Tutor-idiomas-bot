"""Métricas del PEAS del README, calculadas con el historial (exam/historial.py):

    python -m exam.metricas            (todas, para todos los usuarios)

  1. % de errores que NO se repiten tras la retroalimentación:
       - ejercicios: después de fallar un tema (y ver la respuesta correcta), ¿acertó la SIGUIENTE vez
         que le salió ese tema?
       - textos: de los errores que marcó el calificador, ¿cuántos NO volvieron a aparecer (el mismo
         fragmento) en un texto posterior del mismo estudiante?
  2. Aciertos por tema (idioma + tema).
  3. Avance por nivel: niveles aprobados en el examen y lecciones completadas por nivel.
  4. Tasa de retorno después de un recordatorio: de los recordatorios enviados, en cuántos el
     estudiante volvió a usar el bot en las 24 horas siguientes.
  5. Preguntas anuladas por tipo (motivo y parte), leídas de voided_questions.jsonl.

Todas las funciones reciben una conexión (las pruebas usan una base temporal) y devuelven datos;
main() los imprime.
"""
import json
import os
import sys
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta

from exam import historial

HORAS_RETORNO = 24


def _tabla_existe(con, nombre: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (nombre,)).fetchone() is not None


def errores_no_repetidos_ejercicios(con) -> dict:
    """{"fallos_con_reintento", "corregidos", "porcentaje"}: tras fallar un tema, ¿acertó el siguiente intento?"""
    filas = con.execute("SELECT usuario, idioma, tema, correcta FROM ejercicios ORDER BY usuario, idioma, tema, fecha, rowid")
    con_reintento = corregidos = 0
    anterior = None
    for f in filas:
        clave = (f["usuario"], f["idioma"], f["tema"])
        if anterior and anterior[0] == clave and not anterior[1]:
            con_reintento += 1
            corregidos += f["correcta"]
        anterior = (clave, f["correcta"])
    return {"fallos_con_reintento": con_reintento, "corregidos": corregidos,
            "porcentaje": 100 * corregidos / con_reintento if con_reintento else None}


def errores_no_repetidos_textos(con) -> dict:
    """De los errores del calificador seguidos de otro texto del mismo estudiante e idioma,
    ¿cuántos NO se volvieron a cometer (mismo fragmento, sin importar mayúsculas)?"""
    filas = con.execute("SELECT usuario, idioma, fecha, lower(trim(fragmento)) AS frag FROM errores "
                        "WHERE fragmento <> '' ORDER BY usuario, idioma, fecha").fetchall()
    # Fechas de los textos calificados (cualquier error o lección completada cuenta como texto)
    textos: dict = {}
    for f in con.execute("SELECT usuario, idioma, fecha FROM errores "
                         "UNION SELECT usuario, idioma, fecha FROM lecciones "
                         "UNION SELECT usuario, idioma, fecha FROM examen_partes WHERE parte IN ('escritura', 'habla')"):
        textos.setdefault((f["usuario"], f["idioma"]), set()).add(f["fecha"])
    evaluables = no_repetidos = 0
    for f in filas:
        clave = (f["usuario"], f["idioma"])
        if not any(fecha > f["fecha"] for fecha in textos.get(clave, ())):
            continue   # no escribió nada después: no se puede saber
        evaluables += 1
        repetido = any(g["usuario"] == f["usuario"] and g["idioma"] == f["idioma"] and g["fecha"] > f["fecha"]
                       and g["frag"] == f["frag"] for g in filas)
        no_repetidos += not repetido
    return {"evaluables": evaluables, "no_repetidos": no_repetidos,
            "porcentaje": 100 * no_repetidos / evaluables if evaluables else None}


def aciertos_por_tema(con) -> list[dict]:
    return [dict(f) | {"porcentaje": 100 * f["ok"] / f["total"]} for f in con.execute(
        "SELECT idioma, tema, SUM(correcta) AS ok, COUNT(*) AS total FROM ejercicios "
        "GROUP BY idioma, tema ORDER BY idioma, 1.0 * SUM(correcta) / COUNT(*)")]


def avance_por_nivel(con) -> dict:
    examenes = [dict(f) for f in con.execute(
        "SELECT idioma, nivel, COUNT(DISTINCT usuario) AS presentaron, "
        "COUNT(DISTINCT CASE WHEN aprobado = 1 THEN usuario END) AS aprobaron "
        "FROM examen_niveles GROUP BY idioma, nivel ORDER BY idioma, nivel")]
    lecciones = [dict(f) for f in con.execute(
        "SELECT idioma, nivel, COUNT(*) AS completadas, COUNT(DISTINCT usuario) AS estudiantes "
        "FROM lecciones GROUP BY idioma, nivel ORDER BY idioma, nivel")]
    return {"examenes": examenes, "lecciones": lecciones}


def tasa_retorno(con, horas: int = HORAS_RETORNO) -> dict:
    """Recordatorios enviados (tabla de exam/recordatorios.py) seguidos de actividad en `horas`."""
    if not _tabla_existe(con, "recordatorio_envios"):
        return {"enviados": 0, "con_retorno": 0, "porcentaje": None}
    enviados = con.execute("SELECT usuario, fecha FROM recordatorio_envios").fetchall()
    con_retorno = 0
    for e in enviados:
        limite = (datetime.fromisoformat(e["fecha"]) + timedelta(hours=horas)).isoformat(timespec="seconds")
        volvio = con.execute("SELECT 1 FROM actividad WHERE usuario = ? AND fecha > ? AND fecha <= ? LIMIT 1",
                             (e["usuario"], e["fecha"], limite)).fetchone()
        con_retorno += volvio is not None
    return {"enviados": len(enviados), "con_retorno": con_retorno,
            "porcentaje": 100 * con_retorno / len(enviados) if enviados else None}


def anuladas_por_tipo(ruta: str | None = None) -> dict:
    """Preguntas anuladas por motivo y por parte (kind), del registro voided_questions.jsonl."""
    ruta = ruta or os.getenv("EXAM_VOID_LOG", "voided_questions.jsonl")
    motivos, partes = Counter(), Counter()
    total = 0
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                try:
                    fila = json.loads(linea)
                except ValueError:
                    continue
                total += 1
                motivos[str(fila.get("reason", "?")).split(":")[0]] += 1
                partes[fila.get("kind", "?")] += 1
    return {"total": total, "por_motivo": motivos.most_common(), "por_parte": partes.most_common()}


def uso_lara(con) -> list[dict]:
    return [dict(f) for f in con.execute(
        "SELECT herramienta, SUM(ok) AS ok, COUNT(*) AS total, "
        "GROUP_CONCAT(DISTINCT motivo) AS motivos FROM lara_usos GROUP BY herramienta")]


def calcular(ruta_db: str | None = None, ruta_void: str | None = None) -> dict:
    with closing(historial.conectar(ruta_db)) as con:
        return {
            "errores_ejercicios": errores_no_repetidos_ejercicios(con),
            "errores_textos": errores_no_repetidos_textos(con),
            "aciertos_por_tema": aciertos_por_tema(con),
            "avance": avance_por_nivel(con),
            "retorno": tasa_retorno(con),
            "anuladas": anuladas_por_tipo(ruta_void),
            "lara": uso_lara(con),
        }


def _pct(valor) -> str:
    return "sin datos" if valor is None else f"{valor:.0f}%"


def main() -> int:
    m = calcular()
    print("=== Métricas del tutor (PEAS) ===\n")
    e = m["errores_ejercicios"]
    print(f"1. Errores que no se repiten tras la retroalimentación")
    print(f"   Ejercicios: {_pct(e['porcentaje'])} ({e['corregidos']} de {e['fallos_con_reintento']} temas fallados "
          "se acertaron la vez siguiente)")
    t = m["errores_textos"]
    print(f"   Textos:     {_pct(t['porcentaje'])} ({t['no_repetidos']} de {t['evaluables']} errores no se repitieron)")
    print("\n2. Aciertos por tema (los más flojos primero)")
    for f in m["aciertos_por_tema"][:15] or [None]:
        print("   sin datos" if f is None else
              f"   [{f['idioma']}] {f['porcentaje']:3.0f}%  ({f['ok']}/{f['total']})  {f['tema'][:70]}")
    print("\n3. Avance por nivel")
    for f in m["avance"]["examenes"] or [None]:
        print("   examen: sin datos" if f is None else
              f"   examen [{f['idioma']}] {f['nivel']}: aprobaron {f['aprobaron']} de {f['presentaron']}")
    for f in m["avance"]["lecciones"]:
        print(f"   lecciones [{f['idioma']}] {f['nivel']}: {f['completadas']} completadas por {f['estudiantes']} estudiante(s)")
    r = m["retorno"]
    print(f"\n4. Tasa de retorno tras un recordatorio (24 h): {_pct(r['porcentaje'])} "
          f"({r['con_retorno']} de {r['enviados']} recordatorios)")
    a = m["anuladas"]
    print(f"\n5. Preguntas anuladas: {a['total']}")
    print("   por motivo: " + (", ".join(f"{k} {v}" for k, v in a["por_motivo"]) or "sin datos"))
    print("   por parte:  " + (", ".join(f"{k} {v}" for k, v in a["por_parte"]) or "sin datos"))
    if m["lara"]:
        print("\nUso de Lara (MCP): " + ", ".join(
            f"{f['herramienta']} {f['ok']}/{f['total']} ok" + (f" (fallas: {f['motivos']})" if f["motivos"] else "")
            for f in m["lara"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
