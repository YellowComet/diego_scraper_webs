# Monitor ETB 30 Aniversario (Pokémon TCG)

Bot gratuito que vigila las **ETB del 30 Aniversario** en OZ Juegos, Reino de
Cartas y ShinyHit, y te avisa por **Telegram** cuando alguna está disponible.
Corre en **GitHub Actions** (sin servidor propio) y **no usa ninguna API de
pago**.

## Qué hace

Cada 10 minutos entra en una página de búsqueda/categoría de cada tienda, se
queda solo con los productos cuyo nombre encaja con el filtro (Elite Trainer
Box / Caja de Entrenador Élite **y** 30 Aniversario), comprueba en la ficha si
están a la venta y, si uno pasa a disponible, te manda el enlace por Telegram.
Guarda el estado en `state.json` para no repetir avisos.

## Puesta en marcha (10 minutos)

1. **Crea el bot de Telegram**
   - Habla con [@BotFather](https://t.me/BotFather) → `/newbot` → te da un
     **token**.
   - Escribe algo a tu bot y saca tu **chat_id** (por ejemplo, hablando con
     [@userinfobot](https://t.me/userinfobot)).

2. **Sube estos archivos a un repositorio de GitHub** (público = minutos de
   Actions gratis e ilimitados; privado también vale, con 2.000 min/mes).

3. **Añade los secretos** en el repo → *Settings → Secrets and variables →
   Actions → New repository secret*:
   - `TELEGRAM_BOT_TOKEN` = el token de BotFather
   - `TELEGRAM_CHAT_ID` = tu chat_id

4. **Activa Actions** (pestaña *Actions* del repo). Puedes lanzarlo a mano con
   *Run workflow* para probar; después irá solo cada 10 min.

## Ajustes rápidos (en `check_stock.py`)

- **Qué vigilar:** cambia `TERMINOS_ETB` / `TERMINOS_ANIVERSARIO`. Por ejemplo,
  para vigilar cualquier ETB, deja `TERMINOS_ANIVERSARIO` con solo `[""]`.
- **Dónde buscar:** añade URLs a `discovery` de cada tienda (páginas de
  categoría o búsquedas). Si una tienda deja de encontrar productos, prueba a
  cambiar su URL de búsqueda.
- **Frecuencia:** el `cron` del workflow. Recuerda: el mínimo real de GitHub
  son 5 minutos.

## Cosas a tener en cuenta (las que muerden)

- **El cron de GitHub es "best-effort":** mínimo 5 min y puede retrasarse en
  horas punta. Perfecto para reposiciones; **no** para pillar un drop al
  segundo (para eso, una Raspberry Pi o VPS con cron propio).
- **IP de GitHub (Azure):** alguna tienda con anti-bot podría bloquear estas
  IPs más que tu conexión de casa. Si pasa, ese es el motivo.
- **Auto-desactivación a los 60 días** sin commits en la rama principal. Como
  el bot solo commitea `state.json` cuando cambia algo, si hay mucha calma
  puede desactivarse: reactívalo desde *Actions* o añade una acción
  *keepalive*.
- **Filtro por texto:** si una tienda escribe "ETB" de forma rara en el título,
  ajústalo en `TERMINOS_ETB`. "Reserva/preventa" cuenta como disponible (es
  comprable); quítalo de `SENALES_DISPONIBLE` si solo quieres stock inmediato.

## Only-Cards

`only-cards.com` bloquea el acceso automatizado en su `robots.txt`, así que se
ha dejado fuera a propósito. Para esa tienda, mejor su newsletter o avisos
oficiales.
