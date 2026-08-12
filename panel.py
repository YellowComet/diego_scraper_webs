#!/usr/bin/env python3
"""
Panel comparador Pokemon TCG a partir de state.json.

Estructura:
  - Una FICHA POR PRODUCTO (el idioma NO entra en la clave): dentro de cada
    ficha se muestran Espanol e Ingles (mitad/mitad), con mejor precio y tienda,
    o "agotado" / "—" si no hay.
  - Secciones por coleccion (SETS_INTERES) y un apartado "Otros" para lo no
    identificado dentro de esas colecciones.
  - Se ignora el chino (y cualquier idioma que no sea ES/EN).
Ademas mantiene history.csv (solo cambios de precio/stock).
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

# Colecciones a mostrar (en este orden). Edita a tu gusto.
COLECCIONES = ["Heroes Ascendentes", "First Partner", "30 Aniversario"]
SETS_INTERES = set(COLECCIONES)

# --------------------------------------------------------------------------- #

def normaliza(t: str) -> str:
    t = unicodedata.normalize("NFD", t or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower()

SETS = [
    ("Caos Creciente",       ["caos creciente", "chaos rising"]),
    ("Heroes Ascendentes",   ["heroes ascendentes", "ascended heroes", "mega ascended", "mega heroes"]),
    ("Fuegos Fantasmales",   ["fuegos fantasmales", "phantasmal flames"]),
    ("Equilibrio Perfecto",  ["equilibrio perfecto", "perfect order"]),
    ("Oscuridad Absoluta",   ["oscuridad absoluta", "pitch black"]),
    ("First Partner",        ["first partner", "primer companero", "primeros companeros"]),
    ("30 Aniversario",       ["30 aniversario", "30 anniv", "30th", "pokemon day", "dia de pokemon",
                              "special collection 30", "day 2026", "special day"]),
    ("Corona Astral",        ["corona astral", "stellar crown"]),
    ("Mascarada Crepuscular",["mascarada crepuscular", "twilight masquerade"]),
    ("Rivales Predestinados",["rivales predestinados", "destined rivals"]),
    ("Juntos de Aventuras",  ["juntos de aventuras", "journey together"]),
    ("Evoluciones Prismaticas",["prismatic", "prismaticas"]),
    ("Chispas Fulgurantes",  ["chispas fulgurantes", "surging sparks"]),
    ("Fulgor Negro",         ["fulgor negro", "black bolt"]),
    ("Llama Blanca",         ["llama blanca", "white flare"]),
    ("Mega Evolucion",       ["mega evolucion gardevoir", "mega evolucion lucario",
                              "mega evoluciones gardevoir", "mega evoluciones lucario"]),
    ("Escarlata y Purpura",  ["escarlata y purpura", "miraidon", "koraidon"]),
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
    ("Pin Collection",   ["pin deluxe", "deluxe pin", "pin collection", "caja con pin"]),
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
    ("EN",    ["ingles", "(en", "[en]", "english", "eng)", "- ingles"]),
    ("JP",    ["japones", "(jp", "japan"]),
    ("CHINO", ["chino", "(chs", "s-chino", "(cn"]),
    ("ES",    ["espanol", "castellano", "(es", "[es]", "esp)", "- espanol", "espan"]),
]
POKEMON = ["charizard", "charmander", "gastly", "gengar", "komala", "tangela",
           "sneasel", "weavile", "meganium", "emboar", "feraligatr", "gardevoir",
           "lucario", "erika", "larry", "umbreon", "espeon", "pikachu",
           "bulbasaur", "squirtle", "dragapult", "mewtwo", "koraidon", "miraidon"]
TIPOS_CON_VARIANTE = {"EX Box", "Blister", "Poster", "Tech Sticker",
                      "Pin Collection", "UPC", "Coleccion Pegatinas", "Gift Box"}


def _primero(n, tabla):
    for etiqueta, claves in tabla:
        if any(k in n for k in claves):
            return etiqueta
    return None

def _serie(n):
    m = re.search(r"seri[ea]s?\s*([123])", n)
    if m: return f" S{m.group(1)}"
    m = re.search(r"vol\.?\s*([12])", n)
    if m: return f" Vol{m.group(1)}"
    m = re.search(r"\b(iii|ii|i)\b", n)
    if m: return " S" + {"i": "1", "ii": "2", "iii": "3"}[m.group(1)]
    return ""

def _variante(n):
    vs = sorted({p for p in POKEMON if re.search(r"\b" + p, n)})
    return " (" + "+".join(vs) + ")" if vs else ""

def clasifica(nombre):
    """Devuelve set, idioma, display (titulo de ficha) y key (agrupa sin idioma)."""
    n = normaliza(nombre)
    tset = _primero(n, SETS)
    tipo = _primero(n, TIPOS)
    idioma = _primero(n, IDIOMAS) or "ES"
    if tipo and tset:
        extra = (_serie(n) if tset == "First Partner" else "")
        if tipo in TIPOS_CON_VARIANTE:
            extra += _variante(n)
        display = (tipo + extra).strip()
        key = f"{tset}|{tipo}|{extra}"
    else:
        display = re.sub(r"\s+", " ", nombre).strip()[:70]
        key = f"{tset or '?'}|raw|{normaliza(display)}"
    return tset, idioma, display, key


def parse_precio(p):
    if not p: return None
    m = re.search(r"(\d{1,4}(?:\.\d{3})*,\d{2}|\d{1,4}[.,]\d{2})", p)
    if not m: return None
    v = m.group(1)
    v = v.replace(".", "").replace(",", ".") if "," in v else v
    try: return float(v)
    except ValueError: return None


def actualizar_historico(entradas):
    visto = json.loads(VISTO.read_text()) if VISTO.exists() else {}
    fecha = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    nuevas = []
    for e in entradas:
        cv = f"{e['precio']}|{e['disponible']}"
        if visto.get(e["url"]) != cv:
            nuevas.append([fecha, e["display"], e["tienda"], e["nombre"],
                           e["precio"] or "", e["disponible"], e["url"]])
            visto[e["url"]] = cv
    if nuevas:
        nuevo = not HIST.exists()
        with HIST.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(["fecha", "producto", "tienda", "nombre", "precio",
                            "disponible", "url"])
            w.writerows(nuevas)
    VISTO.write_text(json.dumps(visto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[panel] historico: {len(nuevas)} cambio(s).")


def _media(group, lang):
    """HTML de la mitad de un idioma dentro de una ficha."""
    ofs = sorted([e for e in group if e["idioma"] == lang and e["disponible"]
                  and e["precio_num"] is not None], key=lambda e: e["precio_num"])
    hay = [e for e in group if e["idioma"] == lang]
    if ofs:
        b = ofs[0]
        return (f'<div class="lang ok"><span class="lg">{lang}</span>'
                f'<a href="{b["url"]}" target="_blank">{b["precio"]}</a>'
                f'<small>{b["tienda"]}</small></div>')
    if hay:
        return f'<div class="lang no"><span class="lg">{lang}</span><span>agotado</span></div>'
    return f'<div class="lang na"><span class="lg">{lang}</span><span>—</span></div>'


def _tarjeta(display, group):
    disp = any(e["disponible"] for e in group)
    cls = "card" if disp else "card off"
    return (f'<div class="{cls}"><h3>{display}</h3>'
            f'<div class="langs">{_media(group, "ES")}{_media(group, "EN")}</div></div>')


def _seccion(titulo, grupos):
    def hay_disp(g): return any(e["disponible"] for e in g)
    orden = sorted(grupos.items(), key=lambda kv: (not hay_disp(kv[1]), kv[0]))
    tarjetas = "".join(_tarjeta(g[0]["display"], g) for _, g in orden)
    return f'<section><h2>{titulo} <small>({len(orden)})</small></h2><div class="wrap">{tarjetas}</div></section>'


def genera_panel(entradas):
    # Solo ES/EN; el chino y otros idiomas se ignoran.
    visibles = [e for e in entradas if e["idioma"] in ("ES", "EN")]
    ignorados = len(entradas) - len(visibles)

    secciones = {c: {} for c in COLECCIONES}
    otros = {}
    for e in visibles:
        destino = secciones[e["set"]] if e["set"] in SETS_INTERES else otros
        destino.setdefault(e["key"], []).append(e)

    html_secciones = "".join(
        _seccion(c, secciones[c]) for c in COLECCIONES if secciones[c])
    if otros:
        html_secciones += _seccion("Otros (sin identificar)", otros)

    disp = sum(1 for e in visibles if e["disponible"])
    fecha = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel Pokémon TCG</title>
<style>
:root{{color-scheme:dark}}
body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e8e8ea}}
header{{padding:20px 24px;background:#171a21;border-bottom:1px solid #262b36}}
header h1{{margin:0;font-size:20px}} header p{{margin:4px 0 0;color:#9aa0ad;font-size:13px}}
section{{padding:6px 20px 10px}} section>h2{{font-size:16px;margin:18px 4px 10px;color:#cdd3df}}
section>h2 small{{color:#6b7280;font-weight:normal}}
.wrap{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}}
.card{{background:#171a21;border:1px solid #262b36;border-radius:12px;padding:12px 14px}}
.card.off{{opacity:.5}} .card h3{{font-size:14px;margin:0 0 10px;line-height:1.3}}
.langs{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.lang{{border:1px solid #262b36;border-radius:8px;padding:6px 8px;text-align:center;font-size:13px}}
.lang .lg{{display:block;font-size:11px;color:#9aa0ad;margin-bottom:2px}}
.lang.ok{{background:#12351d;border-color:#1c5a2e}}
.lang.ok a{{color:#7ee787;text-decoration:none;font-weight:600;font-variant-numeric:tabular-nums}}
.lang.ok small{{display:block;color:#9aa0ad;font-size:11px;margin-top:2px}}
.lang.no span:last-child{{color:#c9a227}} .lang.na span:last-child{{color:#6b7280}}
</style></head><body>
<header><h1>Panel Pokémon TCG</h1>
<p>Actualizado: {fecha} · {disp} disponible(s) · {ignorados} ignorado(s) (chino/otros idiomas)</p></header>
{html_secciones}</body></html>"""
    PANEL.write_text(html, encoding="utf-8")
    print(f"[panel] generado · {disp} disponibles · {ignorados} ignorados.")


def main():
    if not STATE.exists():
        print("[panel] no hay state.json.")
        return
    estado = json.loads(STATE.read_text(encoding="utf-8"))
    entradas = []
    for url, info in estado.items():
        nombre = info.get("nombre", "")
        precio = info.get("precio")
        tset, idioma, display, key = clasifica(nombre)
        entradas.append({
            "url": url, "nombre": nombre, "tienda": info.get("tienda", ""),
            "disponible": bool(info.get("disponible")), "precio": precio,
            "precio_num": parse_precio(precio),
            "set": tset, "idioma": idioma, "display": display, "key": key,
        })
    actualizar_historico(entradas)
    genera_panel(entradas)


if __name__ == "__main__":
    main()
