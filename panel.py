#!/usr/bin/env python3
"""
Genera un panel HTML (panel.html) y un historico de precios (history.csv)
a partir de state.json (el que deja check_stock.py).

- Agrupa el mismo producto entre tiendas por una CLAVE simple derivada del
  titulo (tipo + set + idioma) y muestra el mejor precio de cada grupo.
- Anade al historico una fila SOLO cuando cambia el precio o la disponibilidad
  (para que no crezca sin control en cada ejecucion).

Requiere que state.json guarde tambien 'precio' por producto (ver README).
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

# --------------------------------------------------------------------------- #
# EMPAREJAMIENTO SIMPLE POR PALABRAS CLAVE
# --------------------------------------------------------------------------- #

def normaliza(t: str) -> str:
    t = unicodedata.normalize("NFD", t or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower()

# (etiqueta, [sinonimos en minusculas y sin acentos])
SETS = [
    ("Caos Creciente",     ["caos creciente", "chaos rising"]),
    ("Heroes Ascendentes", ["heroes ascendentes", "ascended heroes"]),
    ("Fuegos Fantasmales", ["fuegos fantasmales", "phantasmal flames"]),
    ("Equilibrio Perfecto",["equilibrio perfecto", "perfect order"]),
    ("Oscuridad Absoluta", ["oscuridad absoluta", "pitch black"]),
    ("First Partner",      ["first partner", "primer companero", "primeros companeros"]),
    ("30 Aniversario",     ["30 aniversario", "30th", "30 celebration", "30 celebracion",
                            "pokemon day", "celebrations"]),
    ("Corona Astral",      ["corona astral", "stellar crown"]),
    ("Mascarada Crepuscular", ["mascarada crepuscular", "twilight masquerade"]),
    ("Rivales Predestinados", ["rivales predestinados", "destined rivals"]),
    ("Mega Evolucion",     ["mega evolucion", "megaevolucion", "mega evolution"]),
]
TIPOS = [
    ("ETB",            ["etb", "elite trainer", "entrenador elite"]),
    ("UPC",            ["upc", "ultra premium", "ultra-premium"]),
    ("EX Box",         ["ex box", "mega ex box", "mega-ex", "ex-box"]),
    ("Booster Bundle", ["booster bundle", "bundle"]),
    ("Caja 36",        ["36 sobres", "caja 36", "caja de 36", "booster box", "display"]),
    ("Mini Lata",      ["mini lata", "mini tin", "minilata","lata", "tin"]),
    ("Blister",        ["blister"]),
    ("Sobre",          ["sobre", "booster pack", "sleeved booster"]),
    ("Pin Collection", ["pin deluxe", "deluxe pin", "pin collection"]),
    ("Poster",         ["poster collection", "premium poster"]),
    ("Tech Sticker",   ["tech sticker"]),
    ("Coleccion Ilustracion", ["coleccion ilustracion", "illustration collection"]),
]
IDIOMAS = [
    ("EN",    ["ingles", "(en", "[en]", "english", "eng)"]),
    ("JP",    ["japones", "(jp", "japan"]),
    ("CHINO", ["chino", "(chs", "s-chino", "(cn"]),
    ("ES",    ["espanol", "castellano", "(es", "[es]", "esp)", "esp "]),
]

def _primero(nombre_norm, tabla):
    for etiqueta, claves in tabla:
        if any(k in nombre_norm for k in claves):
            return etiqueta
    return None

def clave_producto(nombre: str) -> str:
    n = normaliza(nombre)
    tset = _primero(n, SETS)
    tipo = _primero(n, TIPOS)
    idioma = _primero(n, IDIOMAS) or "ES"  # por defecto ES en tiendas espanolas
    # serie de First Partner, si aparece
    serie = ""
    m = re.search(r"seri[ea]s?\s*([123])", n)
    if tset == "First Partner" and m:
        serie = f" Serie {m.group(1)}"
    if tipo and tset:
        return f"{tipo} · {tset}{serie} · {idioma}"
    # sin clasificar claro: usar el titulo normalizado recortado (agrupa exactos)
    return re.sub(r"\s+", " ", n)[:60]


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


# --------------------------------------------------------------------------- #
# HISTORICO (solo cambios)
# --------------------------------------------------------------------------- #

def actualizar_historico(entradas: list) -> None:
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
        nuevo_fichero = not HIST.exists()
        with HIST.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nuevo_fichero:
                w.writerow(["fecha", "clave", "tienda", "nombre", "precio",
                            "disponible", "url"])
            w.writerows(nuevas)
    VISTO.write_text(json.dumps(visto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[panel] historico: {len(nuevas)} cambio(s) registrado(s).")


# --------------------------------------------------------------------------- #
# PANEL HTML
# --------------------------------------------------------------------------- #

def genera_panel(entradas: list) -> None:
    grupos = {}
    for e in entradas:
        grupos.setdefault(e["clave"], []).append(e)

    # Orden: primero los grupos con alguna oferta disponible, luego por nombre.
    def ofertas_disp(lst):
        return sorted([x for x in lst if x["disponible"] and x["precio_num"] is not None],
                      key=lambda x: x["precio_num"])

    filas_html = []
    grupos_ord = sorted(grupos.items(),
                        key=lambda kv: (len(ofertas_disp(kv[1])) == 0, kv[0]))
    for clave, lst in grupos_ord:
        disp = ofertas_disp(lst)
        agotados = [x for x in lst if not x["disponible"]]
        if disp:
            mejor = disp[0]
            ofertas = "".join(
                f'<li class="{"best" if x is mejor else ""}">'
                f'<a href="{x["url"]}" target="_blank">{x["tienda"]}</a>'
                f'<span>{x["precio"] or "-"}</span></li>'
                for x in disp)
            extra = f'<p class="ago">Agotado en: {", ".join(sorted(set(x["tienda"] for x in agotados)))}</p>' if agotados else ""
            filas_html.append(
                f'<div class="card"><h2>{clave}</h2>'
                f'<p class="mejor">Mejor precio: <b>{mejor["precio"]}</b> en {mejor["tienda"]}</p>'
                f'<ul>{ofertas}</ul>{extra}</div>')
        else:
            filas_html.append(
                f'<div class="card off"><h2>{clave}</h2>'
                f'<p class="ago">Sin stock ahora ({len(lst)} tienda(s))</p></div>')

    disponibles = sum(1 for e in entradas if e["disponible"])
    fecha = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel Pokémon TCG</title>
<style>
:root{{color-scheme:light dark}}
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;
background:#0f1115;color:#e8e8ea}}
header{{padding:20px 24px;background:#171a21;border-bottom:1px solid #262b36}}
header h1{{margin:0;font-size:20px}}
header p{{margin:4px 0 0;color:#9aa0ad;font-size:13px}}
.wrap{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
gap:14px;padding:20px}}
.card{{background:#171a21;border:1px solid #262b36;border-radius:12px;padding:14px 16px}}
.card.off{{opacity:.55}}
.card h2{{font-size:15px;margin:0 0 8px}}
.mejor{{margin:0 0 8px;color:#7ee787;font-size:14px}}
.card ul{{list-style:none;margin:0;padding:0}}
.card li{{display:flex;justify-content:space-between;padding:5px 8px;border-radius:8px;
font-size:13px}}
.card li.best{{background:#12351d}}
.card li a{{color:#8ab4ff;text-decoration:none}}
.card li span{{color:#e8e8ea;font-variant-numeric:tabular-nums}}
.ago{{color:#9aa0ad;font-size:12px;margin:8px 0 0}}
</style></head><body>
<header><h1>Panel Pokémon TCG</h1>
<p>Actualizado: {fecha} · {disponibles} producto(s) disponible(s) · {len(grupos)} grupo(s)</p></header>
<div class="wrap">{"".join(filas_html)}</div>
</body></html>"""
    PANEL.write_text(html, encoding="utf-8")
    print(f"[panel] panel.html generado ({disponibles} disponibles, {len(grupos)} grupos).")


# --------------------------------------------------------------------------- #
# PRINCIPAL
# --------------------------------------------------------------------------- #

def main() -> None:
    if not STATE.exists():
        print("[panel] no hay state.json todavia.")
        return
    estado = json.loads(STATE.read_text(encoding="utf-8"))
    entradas = []
    for url, info in estado.items():
        nombre = info.get("nombre", "")
        precio = info.get("precio")
        entradas.append({
            "url": url,
            "nombre": nombre,
            "tienda": info.get("tienda", ""),
            "disponible": bool(info.get("disponible")),
            "precio": precio,
            "precio_num": parse_precio(precio),
            "clave": clave_producto(nombre),
        })
    actualizar_historico(entradas)
    genera_panel(entradas)


if __name__ == "__main__":
    main()
