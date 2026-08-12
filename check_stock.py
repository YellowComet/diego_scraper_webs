#!/usr/bin/env python3
"""
Monitor de stock Pokemon TCG (ETB y sets concretos) en varias tiendas.

- Respeta robots.txt: antes de tocar una tienda comprueba su robots.txt y, si
  prohibe el acceso automatizado, la SALTA (no se scrapea).
- Detecta la plataforma sola: URL con "/collections/" -> Shopify (JSON);
  el resto -> WooCommerce/HTML.
- Filtro por TERMINOS_INTERES + lista negra.

Anadir tienda = pegar su URL de categoria/coleccion Pokemon en TIENDAS.
"""

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
    "30 celebration", "30 celebracion", "30th", "celebrations", "celebraciones",
    "primer companero", "first partner",
    "heroes ascendentes", "ascended heroes",
]

LISTA_NEGRA = ["one piece", "dragon ball", "magic", "lorcana", "naruto",
               "digimon", "star wars", "flesh and blood", "altered",
               "riftbound", "yu-gi-oh", "yugioh", "gundam", "heroquest",
               "mitos y leyendas", "union arena", "25th"]

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
MAX_PRODUCTOS = 600
PAUSA_ENTRE_PETICIONES = 1

# --------------------------------------------------------------------------- #
# UTILIDADES
# --------------------------------------------------------------------------- #

def normaliza(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower()


def descargar(url: str) -> str:
    resp = httpx.get(url, headers=HEADERS, timeout=25, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


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


def es_shopify(url: str) -> bool:
    return "/collections/" in url


# --------------------------------------------------------------------------- #
# SHOPIFY (JSON)
# --------------------------------------------------------------------------- #

def revisar_shopify(nombre_tienda: str, coll_url: str) -> list:
    parts = urlsplit(coll_url)
    base = f"{parts.scheme}://{parts.netloc}"
    json_url = f"{base}{parts.path.rstrip('/')}/products.json?limit=250"
    try:
        data = json.loads(descargar(json_url))
    except Exception as e:
        print(f"[!] {nombre_tienda}: no se pudo leer JSON ({e})")
        return []
    resultados = []
    for p in data.get("products", []):
        titulo = p.get("title", "")
        if not es_interesante(titulo):
            continue
        variants = p.get("variants", [])
        disponible = any(v.get("available") for v in variants)
        precios = [v.get("price") for v in variants if v.get("price")]
        precio = fmt_precio(min(map(float, precios))) if precios else None
        purl = f"{base}/products/{p.get('handle')}"
        resultados.append((titulo, purl, disponible, precio))
    print(f"[i] {nombre_tienda} (shopify): {len(resultados)} de interes.")
    for t, _, _, _ in resultados[:15]:
        print(f"      candidato: {t}")
    return resultados


# --------------------------------------------------------------------------- #
# WOOCOMMERCE (HTML)
# --------------------------------------------------------------------------- #

def es_link_producto(href: str) -> bool:
    return any(m in href for m in WOO_MARKERS)


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


def revisar_woocommerce(nombre_tienda: str, cat_url: str) -> list:
    try:
        html = descargar(cat_url)
    except Exception as e:
        print(f"[!] {nombre_tienda}: fallo al abrir {cat_url}: {e}")
        return []
    sopa = BeautifulSoup(html, "html.parser")
    candidatos = {}
    total = 0
    for a in sopa.find_all("a", href=True):
        href = urljoin(cat_url, a["href"])
        if not es_link_producto(href):
            continue
        total += 1
        nombre = a.get_text(strip=True)
        if nombre and len(nombre) >= 6 and es_interesante(nombre):
            candidatos.setdefault(href.split("?")[0], nombre)
    print(f"[i] {nombre_tienda} (woo): {total} enlaces, {len(candidatos)} de interes.")
    for n in list(candidatos.values())[:15]:
        print(f"      candidato: {n}")

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
        texto = normaliza(phtml)
        if any(s in texto for s in SENALES_DISPONIBLE):
            disp = True
        elif any(s in texto for s in SENALES_AGOTADO):
            disp = False
        else:
            disp = None
        resultados.append((nombre, url, disp, extrae_precio_html(psopa)))
    return resultados


# --------------------------------------------------------------------------- #
# ESTADO Y AVISOS
# --------------------------------------------------------------------------- #

def cargar_estado() -> dict:
    if FICHERO_ESTADO.exists():
        return json.loads(FICHERO_ESTADO.read_text(encoding="utf-8"))
    return {}


def guardar_estado(estado: dict) -> None:
    FICHERO_ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2),
                              encoding="utf-8")


def avisar(nombre: str, tienda: str, url: str, precio) -> None:
    p = precio or "comprueba en la web"
    texto = (f"\U0001F7E2 STOCK: {nombre}\n"
             f"Tienda: {tienda}\n"
             f"Precio: {p}\n"
             f"Comprar: {url}")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": chat_id, "text": texto},
                       timeout=15).raise_for_status()
            print(f"[OK] Aviso enviado: {nombre}")
            return
        except Exception as e:
            print(f"[!] Fallo enviando a Telegram: {e}")
    print("\n" + "=" * 50 + f"\n{texto}\n" + "=" * 50 + "\n")


# --------------------------------------------------------------------------- #
# PRINCIPAL
# --------------------------------------------------------------------------- #

def main() -> None:
    estado = cargar_estado()
    vistos = set()
    for tienda in TIENDAS:
        for url in tienda["discovery"]:
            if not permitido_por_robots(url):
                print(f"[robots] {tienda['nombre']}: bloqueado por robots.txt, se salta.")
                continue
            if es_shopify(url):
                items = revisar_shopify(tienda["nombre"], url)
            else:
                items = revisar_woocommerce(tienda["nombre"], url)
            for nombre, purl, disponible, precio in items:
                if purl in vistos or len(vistos) >= MAX_PRODUCTOS:
                    continue
                vistos.add(purl)
                antes = estado.get(purl, {}).get("disponible", False)
                etiqueta = {True: "DISPONIBLE", False: "agotado",
                            None: "sin determinar"}[disponible]
                print(f"[{tienda['nombre']}] {nombre}: {etiqueta}")
                if disponible and not antes:
                    avisar(nombre, tienda["nombre"], purl, precio)
                if disponible is not None:
                    estado[purl] = {"disponible": disponible, "nombre": nombre,
                                    "tienda": tienda["nombre"], "precio": precio}
    guardar_estado(estado)
    print(f"Hecho. {len(vistos)} producto(s) evaluado(s).")


if __name__ == "__main__":
    main()

