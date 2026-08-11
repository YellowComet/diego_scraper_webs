#!/usr/bin/env python3
"""
Monitor de stock: SOLO ETB (Elite Trainer Box) del 30 Aniversario de Pokemon TCG.

Filtro (equilibrado):
  - Se buscan enlaces de producto en paginas YA acotadas al 30 aniversario.
  - Un producto vale si su titulo real contiene un termino ETB y NO esta en la
    lista negra de otros juegos. La condicion de "aniversario" la garantiza la
    pagina de origen (scope), o el propio titulo/URL.
  - NO se exige la palabra "Pokemon" (muchas fichas no la ponen en el titulo).
"""

import json
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# CONFIGURACION
# --------------------------------------------------------------------------- #

# aniversario=True -> la pagina ya esta acotada al 30 aniversario, asi que
# cualquier ETB que aparezca ahi cuenta como del aniversario.
TIENDAS = [
    {"nombre": "OZ Juegos", "aniversario": True,
     "discovery": ["https://ozjuegos.com/?s=aniversario&post_type=product"]},
    {"nombre": "Reino de Cartas", "aniversario": True,
     "discovery": ["https://reinodecartas.com/?s=aniversario"]},
    {"nombre": "ShinyHit", "aniversario": True,
     "discovery": ["https://shinyhit.com/categoria-producto/30-aniversario/"]},
]

TERMINOS_ETB = [""]
TERMINOS_ANIVERSARIO = ["30 aniversario", "aniversario 30", "30o aniversario",
                        "30 celebration", "30 celebracion", "30th", "primer compañero", "primer", "caos creciente", "fuegos fantasmales", "ascended heroes", "heroes ascendentes"]

LISTA_NEGRA = ["one piece", "dragon ball", "magic", "lorcana", "naruto",
               "digimon", "star wars", "flesh and blood", "altered",
               "riftbound", "yu-gi-oh", "yugioh", "gundam", "heroquest",
               "mitos y leyendas"]

SENALES_DISPONIBLE = ["anadir al carrito", "add-to-cart", "comprar ahora",
                      "single_add_to_cart_button", "reservar", "preventa"]
SENALES_AGOTADO = ["agotado", "sin existencias", "sin stock",
                   "no disponible", "out of stock", "avisadme"]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}
FICHERO_ESTADO = Path("state.json")
MAX_PRODUCTOS = 40
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


def es_etb(nombre: str) -> bool:
    n = normaliza(nombre)
    if any(t in n for t in LISTA_NEGRA):
        return False
    return any(t in n for t in TERMINOS_ETB)


def es_del_aniversario(nombre: str, url: str, scope: bool) -> bool:
    if scope:
        return True
    txt = normaliza(nombre + " " + url)
    return any(t in txt for t in TERMINOS_ANIVERSARIO)


def nombre_real(sopa: BeautifulSoup, fallback: str) -> str:
    h1 = sopa.select_one("h1.product_title, h1.entry-title, h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if sopa.title and sopa.title.get_text(strip=True):
        return sopa.title.get_text(strip=True)
    return fallback


def extrae_precio(sopa: BeautifulSoup):
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


# --------------------------------------------------------------------------- #
# DESCUBRIR Y EVALUAR
# --------------------------------------------------------------------------- #

def descubrir(tienda: dict) -> dict:
    encontrados = {}
    total_links = 0
    for url in tienda["discovery"]:
        try:
            html = descargar(url)
        except Exception as e:
            print(f"[!] {tienda['nombre']}: fallo al abrir {url}: {e}")
            continue
        sopa = BeautifulSoup(html, "html.parser")
        for a in sopa.find_all("a", href=True):
            href = urljoin(url, a["href"])
            if "/producto/" not in href and "/tienda-tcg/" not in href:
                continue
            total_links += 1
            nombre = a.get_text(strip=True)
            if nombre and len(nombre) >= 6 and es_etb(nombre):
                encontrados.setdefault(href, nombre)
    print(f"[i] {tienda['nombre']}: {total_links} enlaces de producto, "
          f"{len(encontrados)} candidatos ETB.")
    for n in list(encontrados.values())[:15]:
        print(f"      candidato: {n}")
    return encontrados


def evaluar(url: str, fallback: str, scope: bool):
    try:
        html = descargar(url)
    except Exception as e:
        print(f"[!] No se pudo abrir {url}: {e}")
        return None
    sopa = BeautifulSoup(html, "html.parser")
    nombre = nombre_real(sopa, fallback)

    if not es_etb(nombre):
        print(f"[x] Descartado (no es ETB / lista negra): {nombre}")
        return None
    if not es_del_aniversario(nombre, url, scope):
        print(f"[x] Descartado (sin marca de aniversario): {nombre}")
        return None

    precio = extrae_precio(sopa)
    texto = normaliza(html)
    if any(s in texto for s in SENALES_DISPONIBLE):
        disponible = True
    elif any(s in texto for s in SENALES_AGOTADO):
        disponible = False
    else:
        disponible = None
    return nombre, disponible, precio


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
    revisados = 0
    for tienda in TIENDAS:
        scope = tienda.get("aniversario", False)
        for url, fallback in descubrir(tienda).items():
            if revisados >= MAX_PRODUCTOS:
                break
            revisados += 1
            time.sleep(PAUSA_ENTRE_PETICIONES)
            resultado = evaluar(url, fallback, scope)
            if resultado is None:
                continue
            nombre, disponible, precio = resultado
            antes = estado.get(url, {}).get("disponible", False)
            etiqueta = {rue: "DISPONIBLE", False: "agotado",
                        None: "sin determinar"}[disponible]
            print(f"[{tienda['nombre']}] {nombre}: {etiqueta}")
            if disponible and not antes:
                avisar(nombre, tienda["nombre"], url, precio)
            if disponible is not None:
                estado[url] = {"disponible": disponible, "nombre": nombre,
                               "tienda": tienda["nombre"]}
    guardar_estado(estado)
    print(f"Hecho. {revisados} candidato(s) evaluado(s).")


if __name__ == "__main__":
    main()
