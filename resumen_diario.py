#!/usr/bin/env python3
"""
Resumen diario por Telegram: SOLO productos que han BAJADO de precio respecto
al dia anterior, agrupados por coleccion. Se envia una vez al dia por la manana.

Reutiliza el emparejamiento de panel.py (mismo "producto" y mejor precio).
Se ejecuta en cada run del workflow, pero se autolimita con:
  - una ventana horaria (manana), y
  - un fichero marca (resumen_enviado.txt) para no repetir en el dia.
Ponte RESUMEN_TEST=1 para forzar el envio ignorando ventana/marca (pruebas).
"""

import html
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import panel  # reutiliza clasifica / parse_precio / COLECCIONES / SETS_INTERES

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Madrid")
except Exception:
    TZ = None

STATE = Path("state.json")
REF = Path("resumen_ref.json")          # mejor precio por producto del ultimo resumen
MARCA = Path("resumen_enviado.txt")     # fecha del ultimo envio

HORA_INICIO, HORA_FIN = 9, 12           # ventana de manana (9:00-11:59)
UMBRAL_BAJADA = 0.01                    # euros minimos para contar como bajada


def ahora_local():
    return datetime.now(TZ) if TZ else datetime.utcnow() + timedelta(hours=1)


def fmt(num):
    return f"{num:.2f}".replace(".", ",") + " \u20ac"


def mejores(estado):
    """Mejor precio disponible por producto (key del panel)."""
    g = {}
    for url, info in estado.items():
        if not info.get("disponible"):
            continue
        num = panel.parse_precio(info.get("precio"))
        if num is None:
            continue
        tset, idi, disp, key = panel.clasifica(info.get("nombre", ""))
        if idi not in ("ES", "EN"):
            continue
        c = g.get(key)
        if c is None or num < c["num"]:
            g[key] = {"num": num, "tienda": info.get("tienda", ""),
                      "url": url, "display": disp, "set": tset}
    return g


def detecta_bajadas(actuales, ref):
    b = []
    for key, cur in actuales.items():
        r = ref.get(key)
        if r is not None and cur["num"] < r - UMBRAL_BAJADA:
            x = dict(cur)
            x["ref"] = r
            b.append(x)
    return b


def construye_mensaje(bajadas):
    lineas = ["\U0001F4C9 <b>Bajadas de precio de hoy</b>"]
    for col in panel.COLECCIONES + ["Otros"]:
        if col == "Otros":
            grupo = [x for x in bajadas if x["set"] not in panel.SETS_INTERES]
        else:
            grupo = [x for x in bajadas if x["set"] == col]
        if not grupo:
            continue
        grupo.sort(key=lambda x: x["num"])
        lineas.append(f"\n<b>{html.escape(col)}</b>")
        for x in grupo:
            lineas.append(
                f"\u2022 {html.escape(x['display'])} \u2014 {fmt(x['ref'])} \u2192 "
                f"<b>{fmt(x['num'])}</b> \u00b7 "
                f'<a href="{html.escape(x["url"], quote=True)}">{html.escape(x["tienda"])}</a>')
    return "\n".join(lineas)


def enviar(texto):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("[resumen] sin credenciales; mensaje que se enviaria:\n" + texto)
        return
    httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
               json={"chat_id": chat, "text": texto, "parse_mode": "HTML",
                     "disable_web_page_preview": True}, timeout=15).raise_for_status()
    print("[resumen] enviado.")


def main():
    if not STATE.exists():
        print("[resumen] no hay state.json.")
        return
    forzar = os.environ.get("RESUMEN_TEST") == "1"
    t = ahora_local()
    hoy = t.strftime("%Y-%m-%d")
    if not forzar:
        if not (HORA_INICIO <= t.hour < HORA_FIN):
            print(f"[resumen] fuera de ventana ({t.hour}h).")
            return
        if MARCA.exists() and MARCA.read_text().strip() == hoy:
            print("[resumen] ya enviado hoy.")
            return

    estado = json.loads(STATE.read_text(encoding="utf-8"))
    actuales = mejores(estado)
    ref = json.loads(REF.read_text()) if REF.exists() else {}
    bajadas = detecta_bajadas(actuales, ref)

    # Guardar la referencia de hoy (para comparar manana) y marcar el dia.
    REF.write_text(json.dumps({k: v["num"] for k, v in actuales.items()},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    if not forzar:
        MARCA.write_text(hoy, encoding="utf-8")

    if not bajadas:
        print("[resumen] sin bajadas hoy.")
        return
    enviar(construye_mensaje(bajadas))


if __name__ == "__main__":
    main()
