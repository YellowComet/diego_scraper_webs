#!/usr/bin/env python3
"""
Genera panel.html (comparador) + history.csv a partir de state.json.

Emparejamiento por palabras clave con:
  - SET (coleccion), TIPO (formato) e IDIOMA.
  - VARIANTE (Pokemon/promo) para distinguir EX Box, blisters, posters, etc.
  - Serie / volumen para First Partner.
Solo muestra los SETS de SETS_INTERES; el resto (otras colecciones o sin
clasificar) se ocultan y se cuentan.
"""

import csv
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

STATE = Path("state.json")
HIST = Path("history.csv")
VISTO = Path("precio_visto.json")
PANEL = Path("panel.html")

# --- Colecciones que quieres ver en el panel (edita a tu gusto) -------------- #
SETS_INTERES = {"30 Aniversario", "First Partner", "Heroes Ascendentes"}
# (para volver a ver Caos Creciente / Fuegos Fantasmales, anadelos aqui Y en
#  TERMINOS_INTERES de check_stock.py)

# --------------------------------------------------------------------------- #

def normaliza(t: str) -> str:
    t = unicodedata.normalize("NFD", t or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower()

# Etiqueta -> sinonimos (minusculas, sin acentos). Orden = prioridad.
SETS = [
    ("Caos Creciente",       ["caos creciente", "chaos rising"]),
    ("Heroes Ascendentes",   ["heroes ascendentes", "ascended heroes", "mega ascended", "mega heroes"]),
    ("Fuegos Fantasmales",   ["fuegos fantasmales", "phantasmal flames"]),
    ("Equilibrio Perfecto",  ["equilibrio perfecto", "perfect order"]),
    ("Oscuridad Absoluta",   ["oscuridad absoluta", "pitch black"]),
    ("First Partner",        ["first partner", "primer companero", "primeros companeros"]),
    ("30 Aniversario",       ["30 aniversario", "30 anniv", "30th", "pokemon day", "dia de pokemon",
                              "celebrations first partner", "special collection 30", "day 2026"]),
    ("Corona Astral",        ["corona astral", "stellar crown"]),
    ("Mascarada Crepuscular",["mascarada crepuscular", "twilight masquerade"]),
    ("Rivales Predestinados",["rivales predestinados", "destined rivals"]),
    ("Juntos de Aventuras",  ["juntos de aventuras", "journey together"]),
    ("Evoluciones Prismaticas",["prismatic", "prismaticas", "evoluciones prismaticas"]),
    ("Chispas Fulgurantes",  ["chispas fulgurantes", "surging sparks"]),
    ("Fulgor Negro",         ["fulgor negro", "black bolt"]),
    ("Llama Blanca",         ["llama blanca", "white flare"]),
    ("Mega Evolucion",       ["mega evolucion gardevoir", "mega evolucion lucario",
                              "mega evoluciones gardevoir", "mega evoluciones lucario"]),
    ("Escarlata y Purpura",  ["escarlata y purpura", "miraidon", "koraidon", "scarlet"]),
    ("Llamas Obsidianas",    ["llamas obsidianas", "obsidian flames"]),
]
TIPOS = [
    ("UPC",              ["ultra premium", "upc"]),
    ("Case x10",         ["case x10", "x10 elite", "case x", "case caos", "case pokemon"]),
    ("EX Box",           ["ex box", "mega ex box", "mega-ex", "ex-box"]),
    ("Gift Box",         ["gift box"]),
    ("ETB",              ["etb", "elite trainer", "entrenador elite", "caja de entrenador",
                          "caja entrenador"]),
    ("Booster Bundle",   ["booster bundle", "bundle"]),
    ("Caja 36",          ["36 sobres", "caja de 36", "booster box", "display"]),
    ("Tech Sticker",     ["tech sticker"]),
    ("Pin Collection",   ["pin deluxe", "deluxe pin", "pin collection", "caja con pin", "pin "]),
    ("Poster",           ["poster collection", "premium poster", "poster"]),
    ("Coleccion Pegatinas",["pegatinas especiales", "special sticker", "pegatinas"]),
    ("Coleccion Ilustracion",["coleccion ilustracion", "illustration collection", "collection box",
                              "caja first partner", "card set"]),
    ("Special Collection",["special collection", "pokemon day", "dia de pokemon", "day 2026",
                           "special day"]),
    ("Mini Lata",        ["mini lata", "mini tin", "minilata", "mini tins"]),
    ("Lata",             ["lata", "tin"]),
    ("Blister",          ["blister", "sleeved booster"]),
    ("Sobre",            ["sobre", "booster pack"]),
]
IDIOMAS = [
    ("EN",    ["ingles", "(en", "[en]", "english", "eng)", "- ingles", "inglet"]),
    ("JP",    ["japones", "(jp", "japan"]),
    ("CHINO", ["chino", "(chs", "s-chino", "(cn", "vol.1 chino", "vol.2 chino"]),
    ("ES",    ["espanol", "castellano", "(es", "[es]", "esp)", "- espanol", "espan"]),
]
POKEMON = ["charizard", "charmander", "gastly", "gengar", "komala", "tangela",
           "sneasel", "weavile", "meganium", "emboar", "feraligatr", "gardevoir",
           "lucario", "erika", "larry", "umbreon", "espeon", "pikachu",
           "bulbasaur", "squirtle", "dragapult", "mewtwo", "koraidon", "miraidon"]
# Tipos donde la variante (Pokemon/promo) distingue producto.
TIPOS_CON_VARIANTE = {"EX Box", "Blister", "Poster", "Tech Sticker",
                      "Pin Collection", "UPC", "Coleccion Pegatinas", "Gift Box"}


def _primero(n, tabla):
    for etiqueta, claves in tabla:
        if any(k in n for k in claves):
            return etiqueta
    return None

def set_de(nombre: str):
    return _primero(normaliza(nombre), SETS)

def _serie(n: str) -> str:
    m = re.search(r"seri[ea]s?\s*([123])", n)
    if m:
        return f" S{m.group(1)}"
    m = re.search(r"vol\.?\s*([12])", n)
    if m:
        return f" Vol{m.group(1)}"
    m = re.search(r"\b(iii|ii|i)\b", n)
    if m:
        return " S" + {"i": "1", "ii": "2", "iii": "3"}[m.group(1)]
    return ""

def _variante(n: str) -> str:
    vs = sorted({p for p in POKEMON if re.search(r"\b" + p, n)})
    return " (" + "+".join(vs) + ")" if vs else ""

def clave_producto(nombre: str) -> str:
    n = normaliza(nombre)
    tset = _primero(n, SETS)
    tipo = _primero(n, TIPOS)
    idioma = _primero(n, IDIOMAS) or "ES"
    if not (tipo and tset):
        return re.sub(r"\s+", " ", n)[:60]          # sin clasificar
    extra = ""
    if tset == "First Partner":
        extra += _serie(n)
    if tipo in TIPOS_CON_VARIANTE:
        extra += _variante(n)
    return f"{tipo} · {tset}{extra} · {idioma}"


def parse_precio(p):
    if not p:
        return None
    m = re.search(r"(\d{1,4}(?:\.\d{3})*,\d{2}|\d{1,4}[.,]\d{2})", p)
    if not m:
        return None
    v = m.group(1)
    v = v.replace(".", "").replace(",", ".") if "," in v else v
    try:
        return float(v)
    except ValueError:
        return None


def actualizar_historico(entradas):
    visto = json.loads(VISTO.read_text()) if VISTO.exists() else {}
    fecha = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    nuevas = []
    for e in entradas:
        clave_v = f"{e['precio']}|{e['disponible']}"
        if visto.get(e["url"]) != clave_v:
            nuevas.append([fecha, e["clave"], e["tienda"], e["nombre"],
                           e["precio"] or "", e["disponible"], e["url"]])
            visto[e["url"]] = clave_v
    if nuevas:
        nuevo = not HIST.exists()
        with HIST.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(["fecha", "clave", "tienda", "nombre", "precio",
                            "disponible", "url"])
            w.writerows(nuevas)
    VISTO.write_text(json.dumps(visto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[panel] historico: {len(nuevas)} cambio(s).")


def genera_panel(entradas):
    visibles = [e for e in entradas if e["set"] in SETS_INTERES]
    ocultos = len(entradas) - len(visibles)
    grupos = {}
    for e in visibles:
        grupos.setdefault(e["clave"], []).append(e)

    def disp_ord(lst):
        return sorted([x for x in lst if x["disponible"] and x["precio_num"] is not None],
                      key=lambda x: x["precio_num"])

    tarjetas = []
    for clave, lst in sorted(grupos.items(),
                             key=lambda kv: (len(disp_ord(kv[1])) == 0, kv[0])):
        disp = disp_ord(lst)
        agotados = sorted(set(x["tienda"] for x in lst if not x["disponible"]))
        if disp:
            mejor = disp[0]
            items = "".join(
                f'<li class="{"best" if x is mejor else ""}">'
                f'<a href="{x["url"]}" target="_blank">{x["tienda"]}</a>'
                f'<span>{x["precio"] or "-"}</span></li>' for x in disp)
            extra = (f'<p class="ago">Agotado en: {", ".join(agotados)}</p>'
                     if agotados else "")
            tarjetas.append(
                f'<div class="card"><h2>{clave}</h2>'
                f'<p class="mejor">Mejor precio: <b>{mejor["precio"]}</b> · {mejor["tienda"]}</p>'
                f'<ul>{items}</ul>{extra}</div>')
        else:
            tarjetas.append(
                f'<div class="card off"><h2>{clave}</h2>'
                f'<p class="ago">Sin stock ahora ({len(lst)} tienda(s))</p></div>')

    disponibles = sum(1 for e in visibles if e["disponible"])
    fecha = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel Pokémon TCG</title>
<style>
:root{{color-scheme:dark}}
body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e8e8ea}}
header{{padding:20px 24px;background:#171a21;border-bottom:1px solid #262b36}}
header h1{{margin:0;font-size:20px}} header p{{margin:4px 0 0;color:#9aa0ad;font-size:13px}}
.wrap{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;padding:20px}}
.card{{background:#171a21;border:1px solid #262b36;border-radius:12px;padding:14px 16px}}
.card.off{{opacity:.5}} .card h2{{font-size:15px;margin:0 0 8px}}
.mejor{{margin:0 0 8px;color:#7ee787;font-size:14px}}
.card ul{{list-style:none;margin:0;padding:0}}
.card li{{display:flex;justify-content:space-between;padding:5px 8px;border-radius:8px;font-size:13px}}
.card li.best{{background:#12351d}} .card li a{{color:#8ab4ff;text-decoration:none}}
.card li span{{font-variant-numeric:tabular-nums}} .ago{{color:#9aa0ad;font-size:12px;margin:8px 0 0}}
</style></head><body>
<header><h1>Panel Pokémon TCG</h1>
<p>Actualizado: {fecha} · {disponibles} disponible(s) · {len(grupos)} producto(s) · {ocultos} oculto(s) (otras colecciones)</p></header>
<div class="wrap">{"".join(tarjetas)}</div></body></html>"""
    PANEL.write_text(html, encoding="utf-8")
    print(f"[panel] {len(grupos)} grupos visibles, {ocultos} ocultos.")


def main():
    if not STATE.exists():
        print("[panel] no hay state.json.")
        return
    estado = json.loads(STATE.read_text(encoding="utf-8"))
    entradas = []
    for url, info in estado.items():
        nombre = info.get("nombre", "")
        precio = info.get("precio")
        entradas.append({
            "url": url, "nombre": nombre, "tienda": info.get("tienda", ""),
            "disponible": bool(info.get("disponible")), "precio": precio,
            "precio_num": parse_precio(precio),
            "set": set_de(nombre), "clave": clave_producto(nombre),
        })
    actualizar_historico(entradas)
    genera_panel(entradas)


if __name__ == "__main__":
    main()
