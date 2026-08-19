#!/usr/bin/env python3
"""
Panel comparador Pokemon TCG a partir de state.json.

- Ficha por producto (idioma fuera de la clave): dentro, chips ES/EN con mejor
  precio y tienda, foto del producto, mini-grafica de evolucion y distintivo de
  minimo historico (resaltado).
- Secciones por coleccion + "Otros". Ignora chino / idiomas != ES,EN.
- Buscador + filtros (disponibles / minimos) + orden. Tema claro/oscuro segun el
  sistema y diseno responsive (movil/PC).
- Mantiene history.csv (solo cambios).
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
MAX_FILAS_HIST = 8000   # tope de history.csv (se conserva el minimo por producto)
PANEL = Path("panel.html")

COLECCIONES = ["Heroes Ascendentes", "First Partner", "30 Aniversario"]
# Combinaciones (coleccion, tipo) que NO se muestran en el panel:
COLORES = {"Heroes Ascendentes": "#ef5b3b", "First Partner": "#3b9cff",
           "30 Aniversario": "#f0b429", "Otros (sin identificar)": "#8a8f9a"}
OCULTAR = {("First Partner", "Sobre"),
           ("First Partner", "Booster Bundle"),
           ("First Partner", "Album")}
SETS_INTERES = set(COLECCIONES)

# --------------------------------------------------------------------------- #

def normaliza(t: str) -> str:
    t = unicodedata.normalize("NFD", t or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower()

SETS = [
    ("Caos Creciente",         ["caos creciente", "chaos rising"]),
    ("Heroes Ascendentes",     ["heroes ascendentes", "ascended heroes", "mega ascended", "mega heroes"]),
    ("Fuegos Fantasmales",     ["fuegos fantasmales", "phantasmal flames"]),
    ("Equilibrio Perfecto",    ["equilibrio perfecto", "perfect order"]),
    ("Oscuridad Absoluta",     ["oscuridad absoluta", "pitch black"]),
    ("First Partner",          ["first partner", "primer companero", "primeros companeros"]),
    ("30 Aniversario",         ["30 aniversario", "30 anniv", "30th", "pokemon day", "dia de pokemon",
                                "special collection 30", "day 2026", "special day"]),
    ("Corona Astral",          ["corona astral", "stellar crown"]),
    ("Mascarada Crepuscular",  ["mascarada crepuscular", "twilight masquerade"]),
    ("Rivales Predestinados",  ["rivales predestinados", "destined rivals"]),
    ("Juntos de Aventuras",    ["juntos de aventuras", "journey together"]),
    ("Evoluciones Prismaticas",["prismatic", "prismaticas"]),
    ("Chispas Fulgurantes",    ["chispas fulgurantes", "surging sparks"]),
    ("Fulgor Negro",           ["fulgor negro", "black bolt"]),
    ("Llama Blanca",           ["llama blanca", "white flare"]),
    ("Mega Evolucion",         ["mega evolucion gardevoir", "mega evolucion lucario",
                                "mega evoluciones gardevoir", "mega evoluciones lucario"]),
    ("Escarlata y Purpura",    ["escarlata y purpura", "miraidon", "koraidon"]),
    ("Llamas Obsidianas",      ["llamas obsidianas", "obsidian flames"]),
]
TIPOS = [
    ("UPC",                 ["ultra premium", "upc"]),
    ("Case x10",            ["case x10", "x10 elite", "case x", "case caos", "case pokemon"]),
    ("EX Box",              ["ex box", "mega ex box", "mega-ex", "ex-box"]),
    ("Gift Box",            ["gift box"]),
    ("ETB",                 ["etb", "elite trainer", "entrenador elite", "caja de entrenador",
                             "caja entrenador"]),
    ("Booster Bundle",      ["booster bundle", "bundle"]),
    ("Caja 36",             ["36 sobres", "caja de 36", "booster box", "display"]),
    ("Pin Collection",      ["pin deluxe", "deluxe pin", "pin collection", "caja con pin"]),
    ("Poster",              ["poster collection", "premium poster", "poster"]),
    ("Album",               ["album", "binder", "archivador", "carpeta"]),
    ("Coleccion Ilustracion",["coleccion ilustracion", "illustration collection", "collection box",
                              "caja first partner", "card set"]),
    ("Special Collection",  ["special collection", "pokemon day", "dia de pokemon", "day 2026",
                             "special day"]),
    # Blister de pegatinas = Tech Sticker Collection = Coleccion con Pegatinas
    # Especiales: MISMO producto, distintos nombres segun tienda -> un solo tipo.
    ("Coleccion Pegatinas", ["tech sticker", "pegatinas especiales", "special sticker",
                             "pegatinas", "blister"]),
    ("Mini Lata",           ["mini lata", "mini tin", "minilata", "mini tins"]),
    ("Lata",                ["lata", "tin"]),
    ("Sobre",               ["sobre", "booster pack", "sleeved booster"]),
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
# Distintas tiendas nombran la misma coleccion por promos distintos.
# Se unifican a un nombre canonico (edita para cambiar cual se conserva):
VARIANTE_ALIAS = {"charizard": "charmander", "gengar": "gastly", "larry": "komala"}

TIPOS_CON_VARIANTE = {"EX Box", "Poster", "Pin Collection", "UPC",
                      "Coleccion Pegatinas", "Gift Box"}


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
    vs = {p for p in POKEMON if re.search(r"\b" + p, n)}
    vs = sorted({VARIANTE_ALIAS.get(x, x) for x in vs})   # unificar alias
    # Solo distinguimos por variante cuando queda UN unico promo.
    # Con varios (packs combinados) o ninguno -> ficha generica del tipo.
    return f" ({vs[0]})" if len(vs) == 1 else ""

def clasifica(nombre):
    n = normaliza(nombre)
    tset = _primero(n, SETS)
    tipo = _primero(n, TIPOS)
    idioma = _primero(n, IDIOMAS) or "ES"
    # First Partner sin tipo explicito -> es la Coleccion Ilustracion.
    if tset == "First Partner" and tipo is None:
        tipo = "Coleccion Ilustracion"
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


def historial_por_url():
    h = {}
    if not HIST.exists():
        return h
    try:
        with HIST.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if str(row.get("disponible", "")).lower() not in ("true", "1"):
                    continue
                n = parse_precio(row.get("precio"))
                if n is not None:
                    h.setdefault(row.get("url"), []).append(n)
    except Exception as e:
        print(f"[panel] no se pudo leer historial: {e}")
    return h


def historial_detallado():
    h = {}
    if not HIST.exists():
        return h
    try:
        with HIST.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                disp = str(row.get("disponible", "")).lower() in ("true", "1")
                h.setdefault(row.get("url"), []).append(
                    (row.get("fecha", ""), parse_precio(row.get("precio")), disp))
    except Exception as e:
        print(f"[panel] no se pudo leer historial detallado: {e}")
    return h


def serie_mejor_precio(group, det):
    eventos = []
    for e in group:
        for fecha, precio, disp in det.get(e["url"], []):
            eventos.append((fecha, e["url"], precio, disp))
    eventos.sort(key=lambda x: x[0])
    estado_url = {}
    serie = []
    for fecha, url, precio, disp in eventos:
        estado_url[url] = precio if (disp and precio is not None) else None
        activos = [p for p in estado_url.values() if p is not None]
        if activos:
            mejor = min(activos)
            if not serie or abs(serie[-1] - mejor) > 0.001:
                serie.append(mejor)
    return serie


def sparkline(vals, w=150, h=30):
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pts = " ".join(
        f"{i/(n-1)*w:.1f},{h-3 - (v-lo)/rng*(h-6):.1f}" for i, v in enumerate(vals))
    color = "#22a03a" if vals[-1] <= vals[0] else "#e05a4f"
    fp = lambda x: f"{x:.2f}".replace(".", ",")
    return (f'<div class="spark"><svg viewBox="0 0 {w} {h}" width="100%" height="{h}" '
            f'preserveAspectRatio="none"><polyline fill="none" stroke="{color}" '
            f'stroke-width="1.6" points="{pts}"/></svg>'
            f'<small>hist. {fp(lo)}\u2013{fp(hi)} \u20ac</small></div>')


def _rotar_historico(max_filas=MAX_FILAS_HIST):
    """Mantiene history.csv acotado: conserva las ultimas filas y, ademas, la
    fila de precio minimo por producto (para no perder el minimo historico)."""
    if not HIST.exists():
        return
    with HIST.open(encoding="utf-8") as f:
        filas = list(csv.reader(f))
    if len(filas) <= max_filas + 1:
        return
    cab, datos = filas[0], filas[1:]
    I_PRECIO, I_DISP, I_URL = 4, 5, 6
    recientes = datos[-max_filas:]
    en_recientes = set(map(tuple, recientes))
    # fila de menor precio disponible por url
    min_por_url = {}
    for fila in datos:
        if len(fila) <= I_URL:
            continue
        if str(fila[I_DISP]).lower() not in ("true", "1"):
            continue
        n = parse_precio(fila[I_PRECIO])
        if n is None:
            continue
        u = fila[I_URL]
        if u not in min_por_url or n < min_por_url[u][0]:
            min_por_url[u] = (n, tuple(fila))
    extra = [list(t) for (_, t) in min_por_url.values() if t not in en_recientes]
    final = sorted(extra + recientes, key=lambda x: x[0])   # por fecha
    with HIST.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cab)
        w.writerows(final)
    print(f"[panel] historico rotado: {len(datos) + 1} -> {len(final) + 1} filas.")


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
    _rotar_historico()


def _media(group, lang):
    ofs = sorted([e for e in group if e["idioma"] == lang and e["disponible"]
                  and e["precio_num"] is not None], key=lambda e: e["precio_num"])
    hay = [e for e in group if e["idioma"] == lang]
    if ofs:
        b = ofs[0]
        return (f'<div class="lang ok"><span class="lg">{lang}</span>'
                f'<a href="{b["url"]}" target="_blank" rel="noopener">{b["precio"]}</a>'
                f'<small>{b["tienda"]}</small></div>')
    if hay:
        return (f'<div class="lang no"><span class="lg">{lang}</span>'
                f'<span>agotado</span><small>{hay[0]["tienda"]}</small></div>')
    return f'<div class="lang na"><span class="lg">{lang}</span><span>&mdash;</span></div>'


def _todas_tiendas(group):
    """Desplegable con todas las tiendas del producto (solo si hay ocultas)."""
    # Se muestra cuando hay mas ofertas que idiomas (los chips ya ensenan 1 por idioma).
    if len(group) <= len({e["idioma"] for e in group}):
        return ""
    disp = sorted([e for e in group if e["disponible"] and e["precio_num"] is not None],
                  key=lambda e: e["precio_num"])
    resto = [e for e in group if e not in disp]
    filas = []
    for e in disp:
        filas.append(f'<li><a href="{e["url"]}" target="_blank" rel="noopener">{e["tienda"]}</a>'
                     f'<span class="p">{e["precio"]}</span>'
                     f'<span class="lgm">{e["idioma"]}</span></li>')
    for e in resto:
        est = "agotado" if not e["disponible"] else (e["precio"] or "\u2014")
        filas.append(f'<li class="ag"><span>{e["tienda"]}</span>'
                     f'<span class="p">{est}</span>'
                     f'<span class="lgm">{e["idioma"]}</span></li>')
    return (f'<details class="all"><summary>Ver todas las tiendas ({len(group)})</summary>'
            f'<ul>{"".join(filas)}</ul></details>')


def _imagen(group):
    disp_ord = sorted([e for e in group if e["disponible"] and e["precio_num"] is not None],
                      key=lambda e: e["precio_num"])
    for e in disp_ord + group:
        if e.get("img"):
            return e["img"]
    return ""


def _tarjeta(display, group, es_min=False, serie=None):
    disp = any(e["disponible"] for e in group)
    cls = "card" + ("" if disp else " off") + (" min" if es_min else "")
    precios = [e["precio_num"] for e in group if e["disponible"] and e["precio_num"] is not None]
    dprice = f"{min(precios):.2f}" if precios else ""
    dname = normaliza(display + " " + (group[0].get("set") or ""))
    img = _imagen(group)
    ribbon = '<span class="ribbon">&#11015; minimo</span>' if es_min else ""
    thumb = (f'<div class="thumb"><img loading="lazy" src="{img}" alt="">{ribbon}</div>'
             if img else f'<div class="thumb ph">{ribbon}</div>')
    grafica = sparkline(serie) if serie else ""
    return (f'<div class="{cls}" data-name="{dname}" data-avail="{1 if disp else 0}" '
            f'data-price="{dprice}" data-min="{1 if es_min else 0}">'
            f'{thumb}<div class="body"><h3>{display}</h3>'
            f'<div class="langs">{_media(group, "ES")}{_media(group, "EN")}</div>'
            f'{_todas_tiendas(group)}{grafica}</div></div>')


def _seccion(titulo, grupos, min_keys, series, accent):
    def hay_disp(g): return any(e["disponible"] for e in g)
    orden = sorted(grupos.items(), key=lambda kv: (not hay_disp(kv[1]), kv[0]))
    tarjetas = "".join(
        _tarjeta(g[0]["display"], g, k in min_keys, series.get(k)) for k, g in orden)
    return (f'<section style="--acc:{accent}"><h2>{titulo} <small>({len(orden)})</small></h2>'
            f'<div class="wrap">{tarjetas}</div></section>')


BASE_CSS = """
:root{--bg:#0e1117;--panel:#161b24;--panel2:#1c2230;--border:#28303e;--text:#eef1f6;--muted:#9aa3b2;--ok:#4ade80;--okbg:#123122;--okbd:#1f6b3f;--warn:#f0b429;--accent:#5b8cff;--shadow:rgba(0,0,0,.35)}
@media (prefers-color-scheme: light){:root{--bg:#eef1f7;--panel:#ffffff;--panel2:#f6f8fc;--border:#e2e7f0;--text:#161a22;--muted:#5b6474;--ok:#15803d;--okbg:#e8f7ee;--okbd:#bfe6cb;--warn:#a8720a;--accent:#2f6bff;--shadow:rgba(20,30,60,.12)}}
*{box-sizing:border-box}
body{font-family:'Inter',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:var(--text);-webkit-font-smoothing:antialiased;background:radial-gradient(1100px 380px at 100% -60%, color-mix(in srgb,var(--accent) 12%, transparent), transparent),var(--bg)}
h1,h2,.stat b,.lang.ok a,.ribbon{font-family:'Space Grotesk','Inter',system-ui,sans-serif}
header{padding:22px 22px 16px;background:linear-gradient(180deg,var(--panel),color-mix(in srgb,var(--panel) 82%,var(--bg)));border-bottom:1px solid var(--border)}
.brand{display:flex;align-items:center;gap:10px}
.brand .dot{width:13px;height:13px;border-radius:50%;background:conic-gradient(from 0deg,#ff5350,#3b9cff,#f0b429,#4ade80,#ff5350)}
header h1{margin:0;font-size:22px;font-weight:700;letter-spacing:-.01em}
.stats{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.stat{display:flex;align-items:baseline;gap:7px;background:var(--panel2);border:1px solid var(--border);border-radius:999px;padding:7px 14px}
.stat b{font-size:16px;line-height:1}.stat span{color:var(--muted);font-size:12px}
.sub{margin:12px 0 0;color:var(--muted);font-size:12px}
.controls{position:sticky;top:0;z-index:5;display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:12px 22px;background:color-mix(in srgb,var(--bg) 80%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--border)}
.controls input[type=text]{flex:1;min-width:170px;padding:10px 12px;border-radius:10px;border:1px solid var(--border);background:var(--panel);color:var(--text);font-size:14px}
.controls select{padding:10px;border-radius:10px;border:1px solid var(--border);background:var(--panel);color:var(--text)}
.controls label{color:var(--muted);font-size:13px;display:flex;gap:6px;align-items:center;user-select:none}
section{padding:8px 22px 14px}
section>h2{font-size:14px;margin:20px 2px 12px;color:var(--text);display:flex;align-items:center;gap:10px;text-transform:uppercase;letter-spacing:.07em}
section>h2::before{content:"";width:10px;height:10px;border-radius:3px;background:var(--acc,var(--accent));box-shadow:0 0 12px var(--acc,var(--accent))}
section>h2 small{color:var(--muted);font-weight:400;text-transform:none;letter-spacing:0}
.wrap{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:15px}
.card{position:relative;background:var(--panel);border:1px solid var(--border);border-radius:16px;overflow:hidden;display:flex;flex-direction:column;transition:transform .14s ease,box-shadow .14s ease,border-color .14s ease}
.card::before{content:"";position:absolute;inset:0 0 auto 0;height:3px;background:var(--acc,var(--accent));opacity:0;transition:opacity .14s}
.card:hover{transform:translateY(-3px);box-shadow:0 12px 28px var(--shadow);border-color:color-mix(in srgb,var(--acc,var(--accent)) 45%,var(--border))}
.card:hover::before{opacity:1}
.card.off{opacity:.5}
.card.min{border-color:var(--okbd)}
.thumb{position:relative;aspect-ratio:1/1;background:#fff;display:flex;align-items:center;justify-content:center;border-bottom:1px solid var(--border)}
.thumb img{width:100%;height:100%;object-fit:contain;padding:6px}
.thumb.ph{background:var(--panel2)}.thumb.ph::after{content:'sin imagen';color:var(--muted);font-size:11px}
.ribbon{position:absolute;top:8px;left:8px;background:var(--warn);color:#241a00;font-size:10px;font-weight:700;padding:3px 9px;border-radius:999px;letter-spacing:.02em;box-shadow:0 2px 8px rgba(0,0,0,.28)}
.body{padding:12px 13px 13px;display:flex;flex-direction:column;gap:9px;flex:1}
.body h3{font-size:13.5px;margin:0;line-height:1.3;font-weight:600}
.langs{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:auto}
.lang{border:1px solid var(--border);border-radius:11px;padding:8px 6px;text-align:center;font-size:13px;background:var(--panel2)}
.lang .lg{display:block;font-size:10px;color:var(--muted);margin-bottom:3px;letter-spacing:.08em}
.lang small{display:block;color:var(--muted);font-size:11px;margin-top:2px}
.lang.ok{background:var(--okbg);border-color:var(--okbd)}
.lang.ok a{color:var(--ok);text-decoration:none;font-weight:700;font-size:15px;font-variant-numeric:tabular-nums}
.lang.no span:nth-child(2){color:var(--warn);font-weight:600}.lang.na span:last-child{color:var(--muted)}
.spark svg{display:block}.spark small{display:block;color:var(--muted);font-size:10px;margin-top:3px;text-align:right}
details.all>summary{cursor:pointer;color:var(--muted);font-size:11px;list-style:none;user-select:none;padding:2px 0}
details.all>summary::-webkit-details-marker{display:none}
details.all>summary::before{content:"\\25b8 ";color:var(--acc,var(--accent))}
details.all[open]>summary::before{content:"\\25be "}
details.all ul{list-style:none;margin:7px 0 0;padding:0;display:flex;flex-direction:column;gap:4px}
details.all li{display:flex;align-items:center;gap:8px;font-size:12px;padding:5px 7px;border-radius:8px;background:var(--panel2)}
details.all li a,details.all li>span:first-child{flex:1;text-decoration:none;color:var(--text)}
details.all li a{color:var(--accent)}
details.all li .p{font-variant-numeric:tabular-nums;font-weight:600;color:var(--ok)}
details.all li.ag .p,details.all li.ag span:first-child{color:var(--muted);font-weight:400}
details.all li .lgm{font-size:10px;color:var(--muted);width:26px;text-align:right}
a:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{transition:none!important}.card:hover{transform:none}}
@media (max-width:520px){.wrap{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:11px}header h1{font-size:19px}}
"""

CONTROLS_HTML = """
<div class="controls">
  <input type="text" id="q" placeholder="Buscar producto...">
  <label><input type="checkbox" id="soloDisp"> Solo disponibles</label>
  <label><input type="checkbox" id="soloMin"> Solo minimos</label>
  <select id="orden"><option value="rel">Orden: relevancia</option><option value="precio">Precio menor primero</option><option value="nombre">Nombre A-Z</option></select>
</div>
"""

SCRIPT_JS = """
<script>
(function(){
 var q=document.getElementById('q'),sd=document.getElementById('soloDisp'),sm=document.getElementById('soloMin'),od=document.getElementById('orden');
 function apply(){
  var t=(q.value||'').toLowerCase();
  document.querySelectorAll('section').forEach(function(sec){
   var wrap=sec.querySelector('.wrap'); if(!wrap)return;
   var cards=Array.prototype.slice.call(wrap.children),vis=0;
   cards.forEach(function(c){
    var okT=(c.dataset.name||'').indexOf(t)>=0;
    var okD=!sd.checked||c.dataset.avail==='1';
    var okM=!sm.checked||c.dataset.min==='1';
    var show=okT&&okD&&okM; c.style.display=show?'':'none'; if(show)vis++;
   });
   if(od.value!=='rel'){
    cards.sort(function(a,b){
     if(od.value==='precio'){return parseFloat(a.dataset.price||'999999')-parseFloat(b.dataset.price||'999999');}
     return (a.dataset.name||'').localeCompare(b.dataset.name||'');
    });
    cards.forEach(function(c){wrap.appendChild(c);});
   }
   sec.style.display=vis?'':'none';
  });
 }
 q.addEventListener('input',apply);sd.addEventListener('change',apply);sm.addEventListener('change',apply);od.addEventListener('change',apply);
})();
</script>
"""


def genera_panel(entradas):
    visibles = [e for e in entradas if e["idioma"] in ("ES", "EN")]
    ignorados = len(entradas) - len(visibles)

    secciones = {c: {} for c in COLECCIONES}
    otros = {}
    for e in visibles:
        tipo_e = e["key"].split("|")[1] if "|" in e["key"] else ""
        if (e["set"], tipo_e) in OCULTAR:
            continue
        destino = secciones[e["set"]] if e["set"] in SETS_INTERES else otros
        destino.setdefault(e["key"], []).append(e)

    hist = historial_por_url()
    det = historial_detallado()
    min_keys = set()
    series = {}
    total = 0
    for grupos in list(secciones.values()) + [otros]:
        total += len(grupos)
        for key, g in grupos.items():
            actual = [e["precio_num"] for e in g if e["disponible"] and e["precio_num"] is not None]
            previos = [p for e in g for p in hist.get(e["url"], [])]
            if actual and previos:
                cur = min(actual)
                if cur <= min(previos) + 0.001 and max(previos) > cur + 0.001:
                    min_keys.add(key)
            serie = serie_mejor_precio(g, det)
            if len(serie) >= 2:
                series[key] = serie

    html_secciones = "".join(
        _seccion(c, secciones[c], min_keys, series, COLORES.get(c, "#8a8f9a"))
        for c in COLECCIONES if secciones[c])
    if otros:
        html_secciones += _seccion("Otros (sin identificar)", otros, min_keys, series,
                                   COLORES.get("Otros (sin identificar)", "#8a8f9a"))

    disp = sum(1 for e in visibles if e["disponible"])
    fecha = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<title>Panel Pokémon TCG</title>
<style>{BASE_CSS}</style></head><body>
<header>
  <div class="brand"><span class="dot"></span><h1>Panel Pokémon TCG</h1></div>
  <div class="stats">
    <div class="stat"><b>{disp}</b><span>disponibles</span></div>
    <div class="stat"><b>{len(min_keys)}</b><span>en mínimo</span></div>
    <div class="stat"><b>{total}</b><span>productos</span></div>
    <div class="stat"><b>{ignorados}</b><span>ignorados</span></div>
  </div>
  <p class="sub">Actualizado: {fecha}</p>
</header>
{CONTROLS_HTML}
{html_secciones}{SCRIPT_JS}</body></html>"""
    PANEL.write_text(html, encoding="utf-8")
    print(f"[panel] {disp} disponibles · {len(min_keys)} minimos · {total} productos · {ignorados} ignorados.")


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
            "precio_num": parse_precio(precio), "img": info.get("img", ""),
            "set": tset, "idioma": idioma, "display": display, "key": key,
        })
    genera_panel(entradas)
    actualizar_historico(entradas)


if __name__ == "__main__":
    main()
