#!/usr/bin/env python3
"""
Monitor de stock Pokemon TCG (ETB y sets concretos) en varias tiendas.

- Respeta robots.txt: antes de tocar una tienda comprueba su robots.txt y, si
  prohibe el acceso automatizado, la SALTA.
- Detecta la plataforma sola: URL con "/collections/" -> Shopify (JSON);
  el resto -> WooCommerce/HTML (con paginacion).
- Filtro por TERMINOS_INTERES + lista negra.
- Avisa por Telegram: reposicion (agotado->disponible) y BAJADA de precio.
- Reintenta las descargas ante fallos transitorios.
"""

import csv
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# CONFIGURACION
# --------------------------------------------------------------------------- #

TIENDAS = [
    # === ACTIVAS (verificadas: devuelven productos) ===
    # --- WooCommerce / HTML ---
    {"nombre": "OZ Juegos",
     "discovery": ["https://ozjuegos.com/categoria-producto/juegos-de-cartas/pokemon/"]},
    {"nombre": "Reino de Cartas",
     "discovery": ["https://reinodecartas.com/categorias/pokemon-tcg/"]},
    {"nombre": "Flash Store",
     "discovery": ["https://flashstore.es/categoria/pokemon/"]},
    {"nombre": "The Card Station",
     "discovery": ["https://thecardstation.es/home/pokemon-tcg/"]},
    # --- Shopify (JSON automatico) ---
    {"nombre": "CardZone",
     "discovery": ["https://cardzone.es/collections/cartas-pokemon-tcg"]},
    {"nombre": "TCG Level",
     "discovery": ["https://tcglevel.com/collections/pokemon"]},
    {"nombre": "Sunny Store",
     "discovery": ["https://sunnystore.es/collections/pokemon"]},
    {"nombre": "Factory Cards TCG",
     "discovery": ["https://factorycardstcg.com/collections/comprarcartaspokemon"]},
    {"nombre": "Alfriki",
     "discovery": ["https://alfriki.com/collections/pokemon"]},
    {"nombre": "Toy Planet",
     "discovery": ["https://www.toyplanet.com/collections/pokemon"]},
    {"nombre": "Darizard9",
     "discovery": ["https://www.darizard9.com/collections/pokemon"]},
    {"nombre": "Grillecards",
     "discovery": ["https://grillecards.com/collections/pokemon"]},
    {"nombre": "La Boveda Friki",
     "discovery": ["https://labovedafriki.es/collections/pokemon"]},
    {"nombre": "Pokemillon",
     "discovery": ["https://www.pokemillon.com/collections/pokemon"]},
    {"nombre": "TodoHits",
     "discovery": ["https://todohits.com/collections/pokemon"]},
    {"nombre": "AllinTCG",
     "discovery": ["https://allintcg.com/collections/pokemon"]},
    {"nombre": "JJCOLLECTION",
     "discovery": ["https://www.jjcollection.es/collections/pokemon-tcg-atrapalos-todos"]},
    {"nombre": "Metamorph Center",
     "discovery": ["https://metamorphcenter.com/collections/pokemon-tcg"]},
    {"nombre": "Pokedex Card",
     "discovery": ["https://www.pokedexcards.com/collections/espanol",
                   "https://www.pokedexcards.com/collections/ingles"]},
    {"nombre": "RyuCards",
     "discovery": ["https://www.ryucardstcg.com/collections/espanol",
                   "https://www.ryucardstcg.com/collections/ingles"]},
    {"nombre": "Saruman Games",
     "discovery": ["https://sarumangames.es/collections/pokemon-juego-de-cartas-coleccionables"]},
    {"nombre": "UNSOBREMAS",
     "discovery": ["https://unsobremas.com/collections/pokemon-tcg"]},

    # --- Tiendas nuevas ---
    {"nombre": "Iberian Collect",
     "discovery": ["https://iberiancollect.com/collections/ascended-heroes",
                   "https://iberiancollect.com/collections/30-aniversary-celebration"]},
    {"nombre": "Pokezilla",
     "discovery": ["https://pokezilla.com/collections/ascended-heroes",
                   "https://pokezilla.com/collections/30-aniversario"]},
    {"nombre": "StarGeek",
     "discovery": ["https://www.stargeek.es/cartas-pokemon/"]},
    {"nombre": "Pokewoke",
     "discovery": ["https://pokewoke.store/poke-tienda/"]},
    {"nombre": "TCG Fusion",
     "discovery": ["https://tcgfusion.com/tienda/pokemon-tcg/"]},

    # === CASOS ESPECIALES / PENDIENTES ===
    #   BattleDeck (battledeck.es) -> plataforma propia "Namura": sin /products.json
    #       ni fichas de producto navegables; necesitaria un parser a medida.
    #   PokeDealTCG (pokedealtcg.es) -> sin pagina de categoria Pokemon concreta.

    # === FUERA (no scrapeables por via directa) ===
    #   only-cards.com / frikidenacimiento.es -> robots.txt prohibe scraping
    #   geekkaos.com / shinyhit.com           -> 403 (Cloudflare / anti-bot)
    #   Para estas, usar su canal / newsletter oficial.
]

TERMINOS_INTERES = [
    "30 aniversario", "aniversario 30", "30o aniversario",
    "30 celebration", "30 celebracion", "30th",
    "primer companero", "first partner",
    "heroes ascendentes", "ascended heroes",
]

LISTA_NEGRA = ["one piece", "dragon ball", "magic", "lorcana", "naruto",
               "digimon", "star wars", "flesh and blood", "altered",
               "riftbound", "yu-gi-oh", "yugioh", "gundam", "heroquest",
               "mitos y leyendas", "union arena", "25th", "chino"]

# Lista de deseos: avisa AL INSTANTE si un producto concreto baja de tu precio
# objetivo. Casa por PALABRAS: todas las de "terminos" deben aparecer en el
# titulo (minusculas, sin acentos); "excluir" es opcional. Pon la lista vacia
# para desactivarla. Ejemplos (edita a tu gusto):
LISTA_DESEOS = [
    # First Partner (cualquier serie 1/2/3), en espanol, <= 30 EUR
    {"nombre": "First Partner (ES)",
     "terminos": ["first partner|primer companero"],
     "excluir": ["ingles"], "max": 30.0},
    # ETB Heroes Ascendentes, en espanol, <= 55 EUR
    {"nombre": "ETB Heroes Ascendentes (ES)",
     "terminos": ["etb|elite trainer|entrenador elite", "heroes ascendentes|ascended heroes"],
     "excluir": ["ingles"], "max": 55.0},
    # Cajas EX de Heroes Ascendentes (Meganium/Emboar/Feraligatr), en espanol, <= 45 EUR
    {"nombre": "EX Box Heroes Ascendentes (ES)",
     "terminos": ["ex box", "heroes ascendentes|ascended heroes"],
     "excluir": ["ingles"], "max": 45.0},
]


WOO_MARKERS = ["/producto/", "/product/", "/tienda-tcg/"]

SENALES_DISPONIBLE = ["anadir al carrito", "anadir a la cesta", "agregar al carrito",
                      "add-to-cart", "comprar ahora", "single_add_to_cart_button",
                      "reservar", "reserva", "preventa"]
SENALES_AGOTADO = ["agotado", "sin existencias", "sin stock",
                   "no disponible", "out of stock", "avisadme"]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}
FICHERO_ESTADO = Path("state.json")
HIST = Path("history.csv")
MAX_PRODUCTOS = 600
MAX_PAGINAS = 5          # paginas por categoria WooCommerce a recorrer
MAX_PAGINAS_SHOPIFY = 10  # paginas de products.json (250 c/u) a recorrer
PAUSA_ENTRE_PETICIONES = 1
REINTENTOS = 3           # intentos por descarga ante fallos transitorios

# --------------------------------------------------------------------------- #
# UTILIDADES
# --------------------------------------------------------------------------- #

def normaliza(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower()


def descargar(url: str) -> str:
    """Descarga con reintentos. No reintenta errores 4xx (403/404) salvo 429."""
    ultimo = None
    for i in range(REINTENTOS):
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=25, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code < 500 and code != 429:
                raise
            ultimo = e
        except Exception as e:
            ultimo = e
        if i < REINTENTOS - 1:
            time.sleep(2 * (i + 1))
    raise ultimo


_robots_cache: dict = {}

def permitido_por_robots(url: str) -> bool:
    """True si el robots.txt del sitio permite acceder a esta URL. Si no hay
    robots.txt o falla, se asume permitido."""
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    rp = _robots_cache.get(base)
    if rp is None:
        rp = RobotFileParser()
        try:
            r = httpx.get(f"{base}/robots.txt", headers=HEADERS, timeout=15,
                          follow_redirects=True)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots_cache[base] = rp
    try:
        return rp.can_fetch("*", url)
    except Exception:
        return True


def es_interesante(nombre: str) -> bool:
    n = normaliza(nombre)
    if any(t in n for t in LISTA_NEGRA):
        return False
    return any(t in n for t in TERMINOS_INTERES)


def fmt_precio(valor) -> str:
    try:
        return f"{float(valor):.2f}".replace(".", ",") + " \u20ac"
    except (TypeError, ValueError):
        return "comprueba en la web"


def num_precio(p):
    """Convierte "54,95 \u20ac" -> 54.95 (o None si no se puede)."""
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


def objetivo_para(nombre: str, deseos: list):
    """Precio objetivo (el mas bajo) entre los deseos que casan con el titulo, o None.
    Cada termino admite alternativas separadas por "|" (vale cualquiera de ellas)."""
    n = normaliza(nombre)
    def casa(term):
        return any(alt in n for alt in term.split("|"))
    maxes = [w["max"] for w in deseos
             if all(casa(t) for t in w["terminos"]) and not any(x in n for x in w["excluir"])]
    return min(maxes) if maxes else None


def es_shopify(url: str) -> bool:
    return "/collections/" in url


# --------------------------------------------------------------------------- #
# SHOPIFY (JSON)
# --------------------------------------------------------------------------- #

def revisar_shopify(nombre_tienda: str, coll_url: str) -> list:
    parts = urlsplit(coll_url)
    base = f"{parts.scheme}://{parts.netloc}"
    base_json = f"{base}{parts.path.rstrip('/')}/products.json"
    resultados = []
    total = 0
    for page in range(1, MAX_PAGINAS_SHOPIFY + 1):
        url = f"{base_json}?limit=250&page={page}"
        try:
            data = json.loads(descargar(url))
        except Exception as e:
            if page == 1:
                print(f"[!] {nombre_tienda}: no se pudo leer JSON ({e})")
            break
        prods = data.get("products", [])
        if not prods:
            break
        total += len(prods)
        for p in prods:
            titulo = p.get("title", "")
            if not es_interesante(titulo):
                continue
            variants = p.get("variants", [])
            disponible = any(v.get("available") for v in variants)
            precios = [v.get("price") for v in variants if v.get("price")]
            precio = fmt_precio(min(map(float, precios))) if precios else None
            purl = f"{base}/products/{p.get('handle')}"
            imgs = p.get("images") or []
            img = ""
            if imgs:
                primera = imgs[0]
                img = primera.get("src", "") if isinstance(primera, dict) else str(primera)
            resultados.append((titulo, purl, disponible, precio, img))
        if len(prods) < 250:
            break                       # ultima pagina
        time.sleep(PAUSA_ENTRE_PETICIONES)
    print(f"[i] {nombre_tienda} (shopify): {len(resultados)} de interes (de {total} en la coleccion).")
    for t, *_ in resultados[:15]:
        print(f"      candidato: {t}")
    return resultados


# --------------------------------------------------------------------------- #
# WOOCOMMERCE (HTML, con paginacion)
# --------------------------------------------------------------------------- #

def es_link_producto(href: str) -> bool:
    return any(m in href for m in WOO_MARKERS)


def _url_pagina(cat_url: str, n: int) -> str:
    """Construye la URL de la pagina n de una categoria WooCommerce (page/N/)."""
    if n <= 1:
        return cat_url
    p = urlsplit(cat_url)
    path = p.path if p.path.endswith("/") else p.path + "/"
    nueva = f"{p.scheme}://{p.netloc}{path}page/{n}/"
    return nueva + (f"?{p.query}" if p.query else "")


def nombre_real(sopa: BeautifulSoup, fallback: str) -> str:
    h1 = sopa.select_one("h1.product_title, h1.entry-title, h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if sopa.title and sopa.title.get_text(strip=True):
        return sopa.title.get_text(strip=True)
    return fallback


def extrae_precio_html(sopa: BeautifulSoup):
    cont = None
    for sel in [".summary p.price", ".summary .price", "p.price", ".price"]:
        cont = sopa.select_one(sel)
        if cont:
            break
    if not cont:
        return None
    ins = cont.find("ins")
    objetivo = ins if ins else cont
    texto = objetivo.get_text(" ", strip=True)
    m = re.search(r"(\d{1,4}(?:\.\d{3})*,\d{2})", texto)
    if not m:
        m = re.search(r"(\d{1,4}[.,]\d{2})", texto)
    return (m.group(1) + " \u20ac") if m else None


def _stock_woo(sopa):
    """Disponibilidad del PRODUCTO PRINCIPAL en una ficha WooCommerce.
    Maneja productos con variantes (p. ej. idioma ES/EN) leyendo el stock real de
    cada variante, y evita falsos positivos del boton de compra o los relacionados."""
    resumen = sopa.select_one("div.summary, .entry-summary, .product-summary")
    rt = normaliza(resumen.get_text(" ")) if resumen is not None else normaliza(sopa.get_text(" "))

    # 1) Producto con variantes: stock real de cada variante (JSON embebido en el form).
    vf = sopa.select_one("form.variations_form")
    if vf is not None:
        raw = vf.get("data-product_variations")
        if raw and raw.strip().lower() not in ("false", ""):
            try:
                variaciones = json.loads(raw)
                estados = [bool(v.get("is_in_stock")) for v in variaciones]
                if estados:
                    return any(estados)   # disponible solo si ALGUNA variante tiene stock
            except Exception:
                pass

    # 2) Negativo fuerte: frases inequivocas de agotado (aunque haya boton de compra).
    if any(x in rt for x in ["sin existencias", "este producto esta agotado",
                             "agotado actualmente", "lista de espera", "te avisaremos",
                             "volvamos a tener stock", "cuando haya existencias",
                             "avisame cuando", "notificarme cuando"]):
        return False
    if sopa.select_one("p.stock.out-of-stock, .stock.out-of-stock"):
        return False

    # 3) Positivo: boton de compra real (no deshabilitado) o stock in-stock.
    boton = sopa.select_one("form.cart button.single_add_to_cart_button, "
                            "form.cart button[name='add-to-cart']")
    if boton is not None and not boton.has_attr("disabled"):
        return True
    if sopa.select_one("p.stock.in-stock, .stock.in-stock"):
        return True

    # 4) Positivo acotado por el texto del resumen.
    if any(x in rt for x in ["anadir al carrito", "anadir a la cesta", "agregar al carrito",
                             "comprar ahora", "reservar", "preventa"]):
        return True

    # 5) Negativo generico (solo en el resumen, no en toda la pagina).
    if any(x in rt for x in ["agotado", "sin stock", "no disponible", "fuera de stock",
                             "avisame", "avisadme", "notificarme"]):
        return False
    return None


def revisar_woocommerce(nombre_tienda: str, cat_url: str) -> list:
    # 1) Descubrir candidatos recorriendo varias paginas de la categoria.
    candidatos = {}
    total_links = 0
    for n in range(1, MAX_PAGINAS + 1):
        page_url = _url_pagina(cat_url, n)
        try:
            html = descargar(page_url)
        except Exception as e:
            if n == 1:
                print(f"[!] {nombre_tienda}: fallo al abrir {page_url}: {e}")
            break  # pagina inexistente (404) -> fin de la categoria
        sopa = BeautifulSoup(html, "html.parser")
        enlaces_pagina = 0
        for a in sopa.find_all("a", href=True):
            href = urljoin(page_url, a["href"])
            if not es_link_producto(href):
                continue
            enlaces_pagina += 1
            total_links += 1
            nombre = a.get_text(strip=True)
            if nombre and len(nombre) >= 6 and es_interesante(nombre):
                candidatos.setdefault(href.split("?")[0], nombre)
        if enlaces_pagina == 0:
            break  # no hay mas productos
        if n < MAX_PAGINAS:
            time.sleep(PAUSA_ENTRE_PETICIONES)

    print(f"[i] {nombre_tienda} (woo): {total_links} enlaces, {len(candidatos)} de interes.")
    for nm in list(candidatos.values())[:15]:
        print(f"      candidato: {nm}")

    # 2) Evaluar cada candidato (stock + precio en su ficha).
    resultados = []
    for url, fallback in candidatos.items():
        if not permitido_por_robots(url):
            continue
        time.sleep(PAUSA_ENTRE_PETICIONES)
        try:
            phtml = descargar(url)
        except Exception as e:
            print(f"[!] No se pudo abrir {url}: {e}")
            continue
        psopa = BeautifulSoup(phtml, "html.parser")
        nombre = nombre_real(psopa, fallback)
        if not es_interesante(nombre):
            continue
        disp = _stock_woo(psopa)
        og = psopa.select_one('meta[property="og:image"]')
        img = og.get("content", "") if og else ""
        resultados.append((nombre, url, disp, extrae_precio_html(psopa), img))
    return resultados


# --------------------------------------------------------------------------- #
# ESTADO Y AVISOS
# --------------------------------------------------------------------------- #

def leer_min_historico() -> dict:
    """url -> menor precio disponible registrado hasta ahora (de history.csv)."""
    minimos = {}
    if not HIST.exists():
        return minimos
    try:
        with HIST.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if str(row.get("disponible", "")).lower() not in ("true", "1"):
                    continue
                n = num_precio(row.get("precio"))
                if n is None:
                    continue
                u = row.get("url")
                if u and (u not in minimos or n < minimos[u]):
                    minimos[u] = n
    except Exception as e:
        print(f"[!] No se pudo leer historial de minimos: {e}")
    return minimos


def cargar_estado() -> dict:
    if FICHERO_ESTADO.exists():
        return json.loads(FICHERO_ESTADO.read_text(encoding="utf-8"))
    return {}


def guardar_estado(estado: dict) -> None:
    FICHERO_ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2),
                              encoding="utf-8")


def _enviar_telegram(texto: str, etiqueta_log: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": chat_id, "text": texto},
                       timeout=15).raise_for_status()
            print(f"[OK] {etiqueta_log}")
            return
        except Exception as e:
            print(f"[!] Fallo enviando a Telegram: {e}")
    print("\n" + "=" * 50 + f"\n{texto}\n" + "=" * 50 + "\n")


def enviar_resumen(nuevos: list, bajadas: list, objetivos: list, minimos: list) -> None:
    """Envia UN solo mensaje por ronda con el nuevo stock y las bajadas.
    Si es muy largo (primer run), lo trocea para no pasar el limite de Telegram."""
    if not nuevos and not bajadas and not objetivos and not minimos:
        print("Sin novedades que avisar en esta ronda.")
        return
    lineas = []
    if minimos:
        lineas.append(f"\U0001F3C6 Nuevo minimo historico ({len(minimos)})")
        for nombre, tienda, url, precio, antes in minimos:
            lineas.append(f"\u2022 {nombre} \u2014 {precio} (antes min. {antes}) \u00b7 {tienda}\n{url}")
    if nuevos:
        lineas.append(f"\U0001F7E2 Nuevo stock ({len(nuevos)})")
        for nombre, tienda, url, precio in nuevos:
            lineas.append(f"\u2022 {nombre} \u2014 {precio or 'ver web'} \u00b7 {tienda}\n{url}")
    if bajadas:
        lineas.append(f"\n\U0001F4C9 Bajadas de precio ({len(bajadas)})")
        for nombre, tienda, url, precio, antes in bajadas:
            lineas.append(f"\u2022 {nombre} \u2014 {antes} \u2192 {precio} \u00b7 {tienda}\n{url}")
    if objetivos:
        lineas.append(f"\n\U0001F3AF Precio objetivo ({len(objetivos)})")
        for nombre, tienda, url, precio, target in objetivos:
            lineas.append(f"\u2022 {nombre} \u2014 {precio} (objetivo \u2264 {fmt_precio(target)}) \u00b7 {tienda}\n{url}")

    buf = ""
    for ln in lineas:
        if buf and len(buf) + len(ln) + 1 > 3500:   # limite ~4096 de Telegram
            _enviar_telegram(buf, "resumen de ronda enviado")
            buf = ""
        buf += ("\n" if buf else "") + ln
    if buf:
        _enviar_telegram(buf, "resumen de ronda enviado")


# --------------------------------------------------------------------------- #
# PRINCIPAL
# --------------------------------------------------------------------------- #

def main() -> None:
    estado = cargar_estado()
    vistos = set()
    nuevos, bajadas, objetivos, minimos = [], [], [], []
    hist_min = leer_min_historico()
    deseos = [{"nombre": w["nombre"], "max": w["max"],
               "terminos": [normaliza(t) for t in w["terminos"]],
               "excluir": [normaliza(x) for x in w.get("excluir", [])]}
              for w in LISTA_DESEOS]
    for tienda in TIENDAS:
        for url in tienda["discovery"]:
            if not permitido_por_robots(url):
                print(f"[robots] {tienda['nombre']}: bloqueado por robots.txt, se salta.")
                continue
            if es_shopify(url):
                items = revisar_shopify(tienda["nombre"], url)
            else:
                items = revisar_woocommerce(tienda["nombre"], url)
            for nombre, purl, disponible, precio, img in items:
                if purl in vistos or len(vistos) >= MAX_PRODUCTOS:
                    continue
                vistos.add(purl)
                info_prev = estado.get(purl, {})
                antes = info_prev.get("disponible", False)
                precio_antes = info_prev.get("precio")
                etiqueta = {True: "DISPONIBLE", False: "agotado",
                            None: "sin determinar"}[disponible]
                print(f"[{tienda['nombre']}] {nombre}: {etiqueta}")
                n_new = num_precio(precio)
                hm = hist_min.get(purl)
                es_nuevo_min = (disponible and n_new is not None
                                and hm is not None and n_new < hm - 0.01)
                if es_nuevo_min:
                    minimos.append((nombre, tienda["nombre"], purl, precio, fmt_precio(hm)))
                elif disponible and not antes:
                    nuevos.append((nombre, tienda["nombre"], purl, precio))
                elif disponible and antes:
                    n_old = num_precio(precio_antes)
                    if n_new is not None and n_old is not None and n_new < n_old - 0.01:
                        bajadas.append((nombre, tienda["nombre"], purl, precio, precio_antes))
                # Precio objetivo (lista de deseos): avisar al cruzar (o bajar mas).
                target = objetivo_para(nombre, deseos)
                obj_prev = info_prev.get("obj")
                obj_now = None
                if target is not None and disponible and n_new is not None and n_new <= target + 0.001:
                    if obj_prev is None or n_new < obj_prev - 0.01:
                        objetivos.append((nombre, tienda["nombre"], purl, precio, target))
                    obj_now = n_new
                if disponible is not None:
                    entry = {"disponible": disponible, "nombre": nombre,
                             "tienda": tienda["nombre"], "precio": precio}
                    if obj_now is not None:
                        entry["obj"] = obj_now
                    if img:
                        entry["img"] = img
                    estado[purl] = entry
    guardar_estado(estado)
    enviar_resumen(nuevos, bajadas, objetivos, minimos)
    print(f"Hecho. {len(vistos)} producto(s). Avisos: {len(minimos)} minimos, {len(nuevos)} stock, {len(bajadas)} bajadas, {len(objetivos)} objetivos.")


if __name__ == "__main__":
    main()
