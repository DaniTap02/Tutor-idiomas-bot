"""Prueba la conexión REAL con el servidor MCP de Lara usando tus credenciales del .env:

    python -m mcp_cliente.probar_lara

Necesita Node.js (22.23.4 o superior) e internet. La primera vez npx descarga el servidor y tarda
más. Lista las herramientas reales del servidor (session.list_tools) y prueba las dos que usa el
bot: detect_language y translate. Gasta muy pocos caracteres de la cuota (unas 60 letras).
No imprime las credenciales.
"""
import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from exam.registro import MOTIVOS  # noqa: E402
from mcp_cliente import lara  # noqa: E402


async def main() -> int:
    if not lara.ClienteLara.configurado():
        print("❌ Faltan LARA_ACCESS_KEY_ID y LARA_ACCESS_KEY_SECRET en el .env (mira .env.example).")
        return 1
    print(f"Arrancando el servidor {lara.PAQUETE} por stdio (la primera vez tarda)…")
    if not await lara.iniciar():
        motivo = lara.cliente.ultimo_motivo
        print(f"❌ No arrancó: {motivo} — {MOTIVOS.get(motivo, '')}")
        return 1
    try:
        herramientas = await lara.cliente._sesion.list_tools()
        nombres = [t.name for t in herramientas.tools]
        print(f"✅ Conectado. El servidor expone {len(nombres)} herramientas:")
        print("   " + ", ".join(nombres))
        for t in herramientas.tools:
            if t.name in ("detect_language", "translate"):
                esquema = t.input_schema or {}
                print(f"   · {t.name}: parámetros {list(esquema.get('properties', {}))}, "
                      f"obligatorios {esquema.get('required')}")

        det = await lara.detectar_idioma("I would like to practice my English every day")
        print(f"\ndetect_language → {det}" if det else "\n❌ detect_language no respondió "
              f"({lara.cliente.ultimo_motivo})")
        try:
            t = await lara.traducir("Where is the train station?", "en", "es")
            print(f"translate (en→es) → {t}")
        except Exception as exc:
            print(f"❌ translate falló: {getattr(exc, 'motivo', exc)}")
            return 1
    finally:
        await lara.cerrar()
    print("\n✅ Lara funciona. Ya puedes usar /traducir en el bot.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
