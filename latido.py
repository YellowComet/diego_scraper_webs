#!/usr/bin/env python3
"""
Latido diario: manda una vez al dia un mensaje corto de Telegram confirmando que
el monitor sigue vivo (y de paso, al commitear su marca, evita que GitHub
desactive el workflow por inactividad a los 60 dias).

Se ejecuta en cada ronda pero solo actua una vez al dia, por la manana.
RESUMEN/latido comparten patron; usa LATIDO_TEST=1 para forzarlo en pruebas.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import httpx

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Madrid")
except Exception:
    TZ = None

STATE = Path("state.json")
MARCA = Path("latido_enviado.txt")
HORA_INICIO, HORA_FIN = 8, 12       # ventana de manana


def ahora():
    return datetime.now(TZ) if TZ else datetime.utcnow() + timedelta(hours=1)


def main():
    forzar = os.environ.get("LATIDO_TEST") == "1"
    t = ahora()
    hoy = t.strftime("%Y-%m-%d")
    if not forzar:
        if not (HORA_INICIO <= t.hour < HORA_FIN):
            print(f"[latido] fuera de ventana ({t.hour}h).")
            return
        if MARCA.exists() and MARCA.read_text().strip() == hoy:
            print("[latido] ya enviado hoy.")
            return

    total = disponibles = 0
    if STATE.exists():
        estado = json.loads(STATE.read_text(encoding="utf-8"))
        total = len(estado)
        disponibles = sum(1 for v in estado.values() if v.get("disponible"))

    texto = (f"\u2705 Monitor Pok\u00e9mon activo\n"
             f"Vigilando {total} productos \u00b7 {disponibles} disponibles ahora\n"
             f"{t.strftime('%d/%m/%Y %H:%M')}")

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": chat, "text": texto},
                       timeout=15).raise_for_status()
            print("[latido] enviado.")
        except Exception as e:
            print(f"[latido] fallo Telegram: {e}")
    else:
        print("[latido] sin credenciales; mensaje:\n" + texto)

    if not forzar:
        MARCA.write_text(hoy, encoding="utf-8")


if __name__ == "__main__":
    main()
