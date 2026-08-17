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
PANEL = Path("panel.html")

COLECCIONES = ["Heroes Ascendentes", "First Partner", "30 Aniversario"]
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
    vs = sorted({p for p in POKEMON if re.search(r"\b" + p, n)})
    # Solo distinguimos por variante cuando el titulo nombra UN unico Pokemon.
    # Con varios (packs combinados) o ninguno -> ficha generica del tipo.
    return f" ({vs[0]})" if len(vs) == 1 else ""

def clasifica(nombre):
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
    ofs = sorted([e for e in group if e["idioma"] == lang and e["disponible"]
                  and e["precio_num"] is not None], key=lambda e: e["precio_num"])
    hay = [e for e in group if e["idioma"] == lang]
    if ofs:
        b = ofs[0]
        return (f'<div class="lang ok"><span class="lg">{lang}</span>'
                f'<a href="{b["url"]}" target="_blank" rel="noopener">{b["precio"]}</a>'
                f'<small>{b["tienda"]}</small></div>')
    if hay:
        return f'<div class="lang no"><span class="lg">{lang}</span><span>agotado</span></div>'
    return f'<div class="lang na"><span class="lg">{lang}</span><span>&mdash;</span></div>'


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
    thumb = (f'<div class="thumb"><img loading="lazy" src="{img}" alt=""></div>'
             if img else '<div class="thumb ph"></div>')
    badge = '<div class="badges"><span class="badge">&#11015; minimo</span></div>' if es_min else ""
    grafica = sparkline(serie) if serie else ""
    return (f'<div class="{cls}" data-name="{dname}" data-avail="{1 if disp else 0}" '
            f'data-price="{dprice}" data-min="{1 if es_min else 0}">'
            f'{thumb}<div class="body"><h3>{display}</h3>{badge}'
            f'<div class="langs">{_media(group, "ES")}{_media(group, "EN")}</div>{grafica}</div></div>')


def _seccion(titulo, grupos, min_keys, series):
    def hay_disp(g): return any(e["disponible"] for e in g)
    orden = sorted(grupos.items(), key=lambda kv: (not hay_disp(kv[1]), kv[0]))
    tarjetas = "".join(
        _tarjeta(g[0]["display"], g, k in min_keys, series.get(k)) for k, g in orden)
    return (f'<section><h2>{titulo} <small>({len(orden)})</small></h2>'
            f'<div class="wrap">{tarjetas}</div></section>')


BASE_CSS = """
:root{--bg:#0f1115;--panel:#171a21;--border:#262b36;--text:#e8e8ea;--muted:#9aa0ad;--ok:#7ee787;--okbg:#12351d;--okbd:#1c5a2e;--warn:#c9a227;--accent:#8ab4ff;--shadow:rgba(0,0,0,.30)}
@media (prefers-color-scheme: light){:root{--bg:#f4f6fa;--panel:#ffffff;--border:#e3e7ef;--text:#1a1d23;--muted:#6b7280;--ok:#15803d;--okbg:#e7f7ec;--okbd:#bbe3c6;--warn:#a56a00;--accent:#2563eb;--shadow:rgba(20,30,60,.12)}}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--text)}
header{padding:18px 20px;background:var(--panel);border-bottom:1px solid var(--border)}
header h1{margin:0;font-size:20px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
.stat{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:8px 14px;min-width:88px}
.stat b{display:block;font-size:20px;line-height:1.1}
.stat span{color:var(--muted);font-size:12px}
.controls{position:sticky;top:0;z-index:5;display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:12px 20px;background:var(--bg);border-bottom:1px solid var(--border)}
.controls input[type=text]{flex:1;min-width:160px;padding:9px 11px;border-radius:9px;border:1px solid var(--border);background:var(--panel);color:var(--text)}
.controls select{padding:9px;border-radius:9px;border:1px solid var(--border);background:var(--panel);color:var(--text)}
.controls label{color:var(--muted);font-size:13px;display:flex;gap:6px;align-items:center}
section{padding:6px 20px 12px}
section>h2{font-size:16px;margin:18px 4px 12px;color:var(--text)}
section>h2 small{color:var(--muted);font-weight:normal}
.wrap{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:14px;overflow:hidden;display:flex;flex-direction:column;transition:transform .12s ease,box-shadow .12s ease}
.card:hover{transform:translateY(-2px);box-shadow:0 8px 22px var(--shadow)}
.card.off{opacity:.5}
.card.min{border-color:var(--okbd);box-shadow:0 0 0 1px var(--okbd) inset}
.thumb{aspect-ratio:1/1;background:var(--bg);display:flex;align-items:center;justify-content:center;border-bottom:1px solid var(--border)}
.thumb img{width:100%;height:100%;object-fit:contain}
.thumb.ph::after{content:'sin imagen';color:var(--muted);font-size:11px}
.body{padding:11px 13px;display:flex;flex-direction:column;gap:8px;flex:1}
.body h3{font-size:13.5px;margin:0;line-height:1.3}
.badges{display:flex;gap:6px;flex-wrap:wrap}
.badge{font-size:10px;font-weight:700;color:#0b2f16;background:var(--ok);border-radius:6px;padding:2px 7px}
.langs{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:auto}
.lang{border:1px solid var(--border);border-radius:9px;padding:7px 6px;text-align:center;font-size:13px}
.lang .lg{display:block;font-size:10px;color:var(--muted);margin-bottom:2px;letter-spacing:.05em}
.lang.ok{background:var(--okbg);border-color:var(--okbd)}
.lang.ok a{color:var(--ok);text-decoration:none;font-weight:700;font-variant-numeric:tabular-nums}
.lang.no span:last-child{color:var(--warn)}
.lang.na span:last-child{color:var(--muted)}
.spark small{display:block;color:var(--muted);font-size:10px;margin-top:2px;text-align:right}
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
        _seccion(c, secciones[c], min_keys, series) for c in COLECCIONES if secciones[c])
    if otros:
        html_secciones += _seccion("Otros (sin identificar)", otros, min_keys, series)

    disp = sum(1 for e in visibles if e["disponible"])
    fecha = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Panel Pokémon TCG</title>
<style>{BASE_CSS}</style></head><body>
<header><h1>Panel Pokémon TCG</h1>
<div class="stats">
  <div class="stat"><b>{disp}</b><span>disponibles</span></div>
  <div class="stat"><b>{len(min_keys)}</b><span>en mínimo</span></div>
  <div class="stat"><b>{total}</b><span>productos</span></div>
  <div class="stat"><b>{ignorados}</b><span>ignorados</span></div>
</div>
<p style="margin:10px 0 0;color:var(--muted);font-size:12px">Actualizado: {fecha}</p></header>
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
