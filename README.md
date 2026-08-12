# Monitor de stock Pokémon TCG

Bot gratuito que vigila el stock de producto sellado de **Pokémon TCG** en
decenas de tiendas online españolas y te avisa por **Telegram** cuando algo que
te interesa vuelve a estar disponible. Además genera un **panel comparador de
precios** propio. Corre en **GitHub Actions** (sin servidor) y **sin ninguna API
de pago**.

**Panel en vivo:** https://yellowcomet.github.io/diego_scraper_webs/panel.html

## Qué hace

Cada pocos minutos recorre las tiendas configuradas, se queda solo con los
productos cuyo título encaja con tu lista de interés (`TERMINOS_INTERES`),
comprueba disponibilidad y precio, y:

- Te manda un aviso de **Telegram** cuando algo pasa a disponible.
- Actualiza un **panel HTML** (`panel.html`) que agrupa el mismo producto entre
  tiendas y te enseña el **mejor precio** de cada uno.
- Registra los cambios de precio/stock en un **histórico** (`history.csv`).

Guarda el estado en `state.json` para no repetir avisos.

## Cómo detecta cada tienda

No hay que configurar la plataforma a mano: el bot la detecta por la URL.

- **Shopify** (URL con `/collections/…`): usa el JSON público de la tienda, con
  disponibilidad y precio exactos.
- **WooCommerce / HTML** (categoría normal): rastrea las fichas de producto y
  lee el stock del HTML.

**Respeta el `robots.txt`**: antes de tocar una tienda comprueba si permite el
acceso automatizado y, si lo prohíbe, la salta.

## Puesta en marcha

1. **Crea el bot de Telegram**
   - Habla con [@BotFather](https://t.me/BotFather) → `/newbot` → te da un **token**.
   - Saca tu **chat_id** (por ejemplo con [@userinfobot](https://t.me/userinfobot)).

2. **Sube estos archivos a un repositorio de GitHub**
   (público = Actions gratis e ilimitado y Pages gratis; privado también vale,
   con 2.000 min/mes de Actions y sin Pages).

3. **Añade los secretos** en *Settings → Secrets and variables → Actions*:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

4. **Da permiso de escritura a Actions** en *Settings → Actions → General →
   Workflow permissions → Read and write permissions* (para que pueda guardar
   `state.json`, `history.csv` y `panel.html`).

5. **Activa Actions** y lánzalo a mano con *Run workflow* para probar.

6. **(Opcional) Publica el panel** con *Settings → Pages → deploy desde `main`,
   carpeta raíz*. Copia la URL resultante arriba en este README.

## Añadir tiendas

Pega en `TIENDAS` (en `check_stock.py`) la URL de la sección Pokémon:

```python
{"nombre": "Nombre Tienda",
 "discovery": ["https://tienda.es/collections/pokemon"]},   # Shopify
{"nombre": "Otra Tienda",
 "discovery": ["https://otra.es/categoria-producto/pokemon/"]},  # WooCommerce
```

El bot detecta la plataforma solo. Si una tienda sale con `0 de interés` o
`fallo`, suele ser un handle/URL equivocado; prueba con la URL real de su
listado Pokémon.

## Ajustes rápidos

- **Qué vigilar:** edita `TERMINOS_INTERES` (tipos de producto y nombres de set)
  y `LISTA_NEGRA` (otros juegos a descartar) en `check_stock.py`.
- **Cómo agrupa el panel:** edita `SETS`, `TIPOS` e `IDIOMAS` en `panel.py`.
- **Frecuencia:** el `cron` del workflow (mínimo real de GitHub: 5 min).
- **Reservas/preventas:** cuentan como disponible; quita `"reservar"` y
  `"preventa"` de `SENALES_DISPONIBLE` si solo quieres stock inmediato.

## Cosas a tener en cuenta

- **El cron de GitHub es "best-effort":** mínimo 5 min y puede retrasarse en
  horas punta. Vale para reposiciones; no para pillar un *drop* al segundo (para
  eso, una Raspberry Pi o VPS con cron propio).
- **IP de GitHub (Azure):** alguna tienda con anti-bot/Cloudflare puede
  bloquear estas IPs (verás un 403). No hay atajo limpio por Actions.
- **Auto-desactivación a los 60 días** sin commits en la rama principal;
  reactívalo desde *Actions* o añade una acción *keepalive*.

## Tiendas fuera de cobertura

- `only-cards.com`, `frikidenacimiento.es` → su `robots.txt` prohíbe el scraping.
- `geekkaos.com`, `shinyhit.com` → responden 403 (Cloudflare / anti-bot).
- `battledeck.es` → plataforma propia sin JSON ni fichas navegables.

Para esas, lo correcto es su canal/newsletter oficial.
