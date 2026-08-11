#!/usr/bin/env python3
"""
Monitor de stock: SOLO ETB (Elite Trainer Box) del 30 Aniversario de Pokemon TCG.

Como funciona (sin IA, todo gratis):
  1. En cada tienda descarga una pagina de listado (busqueda o categoria).
  2. Descubre los productos cuyo NOMBRE encaja con el filtro
     (ETB / Caja de Entrenador Elite) + (30 Aniversario / Celebration).
  3. Para cada candidato entra en su pagina y mira si esta disponible.
  4. Si un producto pasa a DISPONIBLE, te avisa por Telegram con el enlace.
  5. Guarda el estado en state.json para no repetir avisos.

Pensado para ejecutarse en GitHub Actions. Solo usa peticiones HTTP simples.
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

# Paginas donde buscar. Puedes anadir mas URLs a "discovery" por tienda.
TIENDAS = [
    {
        "nombre": "OZ Juegos",
        "discovery": ["https://ozjuegos.com/?s=aniversario&post_type=product"],
    },
    {
        "nombre": "Reino de Cartas",
        "discovery": ["https://reinodecartas.com/?s=aniversario"],
    },
    {
        "nombre": "ShinyHit",
        "discovery": ["https://shinyhit.com/categoria-producto/30-aniversario/"],
    },
]

# Filtro por nombre de producto. Debe cumplir UN termino de cada lista.
# (Todo se compara en minusculas y sin acentos.)
TERMINOS_ETB = ["etb", "elite trainer", "entrenador elite"]
TERMINOS_ANIVERSARIO = ["30 aniversario", "30o aniversario", "aniversario",
                        "30 celebration", "30th", "celebration"]

# Senales de stock en la pagina de producto (minusculas, sin acentos).
SENALES_DISPONIBLE = ["anadir al carrito", "add-to-cart", "comprar ahora",
                      "single_add_to_cart_button", "reservar", "preventa"]
SENALES_AGOTADO = ["agotado", "sin existencias", "sin stock",
                   "no disponible", "out of stock", "avisadme"]

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
FICHERO_ESTADO = Path("state.json")
MAX_PRODUCTOS = 40          # tope de seguridad por ejecucion
PAUSA_ENTRE_PETICIONES = 1  # segundos, para ser educado con las tiendas

# --------------------------------------------------------------------------- #
# UTILIDADES
# --------------------------------------------------------------------------- #

def normaliza(texto: str) -> str:
    """Minusculas y sin acentos, para comparar de forma robusta."""
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower()


def descargar(url: str) -> str:
    resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=25,
                     follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def encaja_filtro(nombre: str) -> bool:
    n = normaliza(nombre)
    tiene_etb = any(t in n for t in TERMINOS_ETB)
    tiene_aniv = any(t in n for t in TERMINOS_ANIVERSARIO)
    return tiene_etb and tiene_aniv


# --------------------------------------------------------------------------- #
# 1. DESCUBRIR PRODUCTOS QUE ENCAJAN
# --------------------------------------------------------------------------- #

def descubrir(tienda: dict) -> dict:
    """Devuelve {url_producto: nombre} de los productos que pasan el filtro."""
    encontrados = {}
    for url in tienda["discovery"]:
        try:
            html = descargar(url)
        except Exception as e:  # noqa: BLE001
            print(f"[!] {tienda['nombre']}: fallo al abrir {url}: {e}")
            continue
        sopa = BeautifulSoup(html, "html.parser")
        for a in sopa.find_all("a", href=True):
            nombre = a.get_text(strip=True)
            if not nombre or len(nombre) < 6:
                continue
            if not encaja_filtro(nombre):
                continue
            href = urljoin(url, a["href"])
            # Nos quedamos con enlaces a fichas de producto de WooCommerce.
            if "/producto/" in href or "/tienda-tcg/" in href:
                encontrados.setdefault(href, nombre)
    if not encontrados:
        print(f"[i] {tienda['nombre']}: 0 productos que encajen "
              f"(puede ser normal, o revisar la URL de busqueda).")
    return encontrados


# --------------------------------------------------------------------------- #
# 2. COMPROBAR STOCK EN LA FICHA DE PRODUCTO
# --------------------------------------------------------------------------- #

def hay_stock(url_producto: str) -> tuple[bool | None, str | None]:
    """Devuelve (disponible, precio). disponible None si no se puede decidir."""
    try:
        html = descargar(url_producto)
    except Exception as e:  # noqa: BLE001
        print(f"[!] No se pudo abrir {url_producto}: {e}")
        return None, None

    texto = normaliza(html)
    precio = None
    m = re.search(r"(\d{1,4}[.,]\d{2})\s*(?:€|eur)", html)
    if m:
        precio = m.group(1).replace(".", ",") + " €"

    tiene_carrito = any(s in texto for s in SENALES_DISPONIBLE)
    tiene_agotado = any(s in texto for s in SENALES_AGOTADO)

    if tiene_carrito:
        return True, precio
    if tiene_agotado:
        return False, precio
    return None, precio


# --------------------------------------------------------------------------- #
# 3. ESTADO Y AVISOS
# --------------------------------------------------------------------------- #

def cargar_estado() -> dict:
    if FICHERO_ESTADO.exists():
        return json.loads(FICHERO_ESTADO.read_text(encoding="utf-8"))
    return {}


def guardar_estado(estado: dict) -> None:
    FICHERO_ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2),
                              encoding="utf-8")


def avisar(nombre: str, tienda: str, url: str, precio: str | None) -> None:
    p = precio or "precio no detectado"
    texto = (f"🟢 STOCK: {nombre}\n"
             f"Tienda: {tienda}\n"
             f"Precio: {p}\n"
             f"Comprar: {url}")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": texto},
                timeout=15,
            ).raise_for_status()
            print(f"[✓] Aviso enviado: {nombre}")
            return
        except Exception as e:  # noqa: BLE001
            print(f"[!] Fallo enviando a Telegram: {e}")
    print("\n" + "=" * 50 + f"\n{texto}\n" + "=" * 50 + "\n")


# --------------------------------------------------------------------------- #
# PRINCIPAL
# --------------------------------------------------------------------------- #

def main() -> None:
    estado = cargar_estado()
    revisados = 0

    for tienda in TIENDAS:
        candidatos = descubrir(tienda)
        for url, nombre in candidatos.items():
            if revisados >= MAX_PRODUCTOS:
                break
            revisados += 1
            time.sleep(PAUSA_ENTRE_PETICIONES)

            disponible, precio = hay_stock(url)
            antes = estado.get(url, {}).get("disponible", False)
            etiqueta = {True: "DISPONIBLE", False: "agotado",
                        None: "sin determinar"}[disponible]
            print(f"[{tienda['nombre']}] {nombre}: {etiqueta}")

            if disponible and not antes:
                avisar(nombre, tienda["nombre"], url, precio)

            if disponible is not None:
                estado[url] = {"disponible": disponible,
                               "nombre": nombre,
                               "tienda": tienda["nombre"]}

    guardar_estado(estado)
    print(f"Hecho. {revisados} producto(s) revisado(s).")


if __name__ == "__main__":
    main()
