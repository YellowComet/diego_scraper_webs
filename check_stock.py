#!/usr/bin/env python3
"""
Monitor de stock de productos Pokemon TCG seleccionados (ETB y sets concretos).

Filtro por LISTA POSITIVA:
  - Descubre enlaces de producto en la categoria Pokemon de cada tienda.
  - Un producto vale si su titulo contiene alguno de los TERMINOS_INTERES
    (tipos de producto o nombres de set) y NO esta en la lista negra.
  - Edita TERMINOS_INTERES para anadir/quitar lo que quieras seguir.
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

TIENDAS = [
    {"nombre": "OZ Juegos",
     "discovery": ["https://ozjuegos.com/categoria-producto/juegos-de-cartas/pokemon/"]},
    {"nombre": "Reino de Cartas",
     "discovery": ["https://reinodecartas.com/categorias/pokemon-tcg/"]},
    {"nombre": "ShinyHit",
     "discovery": ["https://shinyhit.com/categoria-producto/pokemon/"]},
]

# LO QUE SI QUIERES SEGUIR. El titulo debe contener al menos uno de estos
# (en minusculas y sin acentos). Anade o quita libremente.
TERMINOS_INTERES = [
    # Tipos de producto
    "etb", "elite trainer", "entrenador elite",
    # 30 Aniversario / Celebration
    "30 aniversario", "aniversario 30", "30o aniversario",
    "30 celebration", "30 celebracion", "30th",
    # Sets concretos
    "primer companero", "first partner",
    "caos creciente",
    "fuegos fantasmales",
    "heroes ascendentes", "ascended heroes",
]

# Si el titulo contiene cualquiera de estas, se descarta (otros juegos).
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
MAX_PRODUCTOS = 60
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


def es_interesante(nombre: str) -> bool:
    n = normaliza(nombre)
    if any(t in n for t in LISTA_NEGRA):
        return False
    return any(t in n for t in TERMINOS_INTERES)


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
            if nombre and len(nombre) >= 6 and es_interesante(nombre):
                encontrados.setdefault(href, nombre)
    print(f"[i] {tienda['nombre']}: {total_links} enlaces de producto, "
          f"{len(encontrados)} de interes.")
    for n in list(encontrados.values())[:15]:
        print(f"      candidato: {n}")
    return encontrados


def evaluar(url: str, fallback: str):
    try:
        html = descargar(url)
    except Exception as e:
        print(f"[!] No se pudo abrir {url}: {e}")
        return None
    sopa = BeautifulSoup(html, "html.parser")
    nombre = nombre_real(sopa, fallback)
    if not es_interesante(nombre):
        print(f"[x] Descartado (no interesa / lista negra): {nombre}")
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
        for url, fallback in descubrir(tienda).items():
            if revisados >= MAX_PRODUCTOS:
                break
            revisados += 1
            time.sleep(PAUSA_ENTRE_PETICIONES)
            resultado = evaluar(url, fallback)
            if resultado is None:
                continue
            nombre, disponible, precio = resultado
            antes = estado.get(url, {}).get("disponible", False)
            etiqueta = {True: "DISPONIBLE", False: "agotado",
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
