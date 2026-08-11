#!/usr/bin/env python3
"""
Monitor de stock: SOLO ETB (Elite Trainer Box) del 30 Aniversario de Pokemon TCG.
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
     "discovery": ["https://ozjuegos.com/?s=aniversario&post_type=product"]},
    {"nombre": "Reino de Cartas",
     "discovery": ["https://reinodecartas.com/?s=aniversario"]},
    {"nombre": "ShinyHit",
     "discovery": ["https://shinyhit.com/categoria-producto/30-aniversario/"]},
]

# Debe cumplir: contener "pokemon" + un termino ETB + un termino de 30 aniversario,
# y NO contener ninguna palabra de la lista negra. (Minusculas y sin acentos.)
OBLIGATORIO = ["pokemon"]
TERMINOS_ETB = []
TERMINOS_ANIVERSARIO = ["30 aniversario", "aniversario 30", "30o aniversario",
                        "30 celebration", "30 celebracion", "30th", "ascended heroes", "heroes ascendentes", "primer compañero", "fuegos fantasmales"]
LISTA_NEGRA = ["one piece", "dragon ball", "magic", "lorcana", "naruto",
               "digimon", "star wars", "flesh and blood", "altered",
               "riftbound", "yu-gi-oh", "yugioh", "gundam", "heroquest",
               "mitos y leyendas"]

SENALES_DISPONIBLE = ["anadir al carrito", "add-to-cart", "comprar ahora",
                      "single_add_to_cart_button", "reservar", "preventa"]
SENALES_AGOTADO = ["agotado", "sin existencias", "sin stock",
                   "no disponible", "out of stock", "avisadme"]

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
FICHERO_ESTADO = Path("state.json")
MAX_PRODUCTOS = 40
PAUSA_ENTRE_PETICIONES = 1

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

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


def encaja_filtro(nombre: str) -> bool:
    n = normaliza(nombre)
    if any(t in n for t in LISTA_NEGRA):
        return False
    if not all(t in n for t in OBLIGATORIO):
        return False
    if not any(t in n for t in TERMINOS_ETB):
        return False
    if not any(t in n for t in TERMINOS_ANIVERSARIO):
        return False
    return True


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
    for url in tienda["discovery"]:
        try:
            html = descargar(url)
        except Exception as e:
            print(f"[!] {tienda['nombre']}: fallo al abrir {url}: {e}")
            continue
        sopa = BeautifulSoup(html, "html.parser")
        for a in sopa.find_all("a", href=True):
            nombre = a.get_text(strip=True)
            if not nombre or len(nombre) < 6 or not encaja_filtro(nombre):
                continue
            href = urljoin(url, a["href"])
            if "/producto/" in href or "/tienda-tcg/" in href:
                encontrados.setdefault(href, nombre)
    if not encontrados:
        print(f"[i] {tienda['nombre']}: 0 candidatos en el listado.")
    return encontrados


def evaluar(url: str, fallback: str):
    try:
        html = descargar(url)
    except Exception as e:
        print(f"[!] No se pudo abrir {url}: {e}")
        return None
    sopa = BeautifulSoup(html, "html.parser")
    nombre = nombre_real(sopa, fallback)
    if not encaja_filtro(nombre):
        print(f"[x] Descartado (no encaja): {nombre}")
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
