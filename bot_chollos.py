import os
import asyncio
import re
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from PIL import Image, ImageOps
from io import BytesIO

# ==============================
# CONFIG / VARIABLES DE ENTORNO
# ==============================
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
AFFILIATE_TAG = os.getenv("AFFILIATE_TAG", "solochollos08-21")

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise SystemExit("Faltan variables de entorno: API_ID, API_HASH o BOT_TOKEN")

api_id = int(API_ID)
api_hash = API_HASH
bot_token = BOT_TOKEN
affiliate_tag = AFFILIATE_TAG

source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"

client = TelegramClient("session_bot_chollos", api_id, api_hash)

# ==============================
# SESIÓN HTTP (headers realistas)
# ==============================
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
})

# ==============================
# UTILIDADES AMAZON
# ==============================
def extract_asin(url):
    patterns = [
        r"/dp/([A-Z0-9]{10})",
        r"/gp/product/([A-Z0-9]{10})",
        r"/product/([A-Z0-9]{10})"
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None

def resolve_amazon_link(url):
    """
    Resuelve shortlinks (amzn.to) y devuelve ASIN (o None).
    Usa la sesión con headers para reducir bloqueos.
    """
    try:
        r = session.get(url, allow_redirects=True, timeout=15)
        final = r.url.split("?")[0]
        return extract_asin(final)
    except Exception as e:
        print("resolve_amazon_link error:", e)
        return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

# ==============================
# SCRAPING ROBUSTO (selectores indicados)
# ==============================
def scrape_amazon_product(asin):
    """
    Obtiene: title, price, old_price, rating, reviews, image (data-old-hires preferred).
    Usa los selectores que has proporcionado como prioritarios.
    """
    url = f"https://www.amazon.es/dp/{asin}"
    headers = session.headers.copy()
    headers["Referer"] = url
    try:
        r = session.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        # Título
        title_elem = soup.select_one("#productTitle")
        if not title_elem:
            title_elem = soup.select_one("span.a-size-large.a-color-base.a-text-normal")
        title = title_elem.get_text(strip=True) if title_elem else "Producto Amazon"

        # PRECIO AHORA: principal (apex core)
        price = None
        price_elem = soup.select_one(".apex-pricetopay-value .a-offscreen")
        if price_elem and price_elem.get_text(strip=True):
            price = price_elem.get_text(strip=True)
        else:
            # fallback a bloques clásicos
            alt = soup.select_one("#priceblock_ourprice, #priceblock_dealprice, .a-price .a-offscreen")
            if alt:
                price = alt.get_text(strip=True)

        # PRECIO ANTES: basisprice
        old_price = None
        old_price_elem = soup.select_one(".apex-basisprice-value .a-offscreen")
        if old_price_elem and old_price_elem.get_text(strip=True):
            old_price = old_price_elem.get_text(strip=True)
        else:
            alt_old = soup.select_one(".a-text-price .a-offscreen, #priceblock_listprice")
            if alt_old:
                old_price = alt_old.get_text(strip=True)

        # VALORACIÓN
        rating_elem = soup.select_one("#acrPopover")
        rating = ""
        if rating_elem and rating_elem.has_attr("title"):
            rating = rating_elem["title"].strip()
        else:
            # fallback textual
            rating_alt = soup.select_one("span[data-hook='rating-out-of-text']")
            if rating_alt:
                rating = rating_alt.get_text(strip=True)

        # RESEÑAS (número)
        reviews_elem = soup.select_one("#acrCustomerReviewText")
        reviews = ""
        if reviews_elem:
            reviews = reviews_elem.get_text(strip=True)
        else:
            rev_alt = soup.select_one("span[data-hook='total-review-count']")
            if rev_alt:
                reviews = rev_alt.get_text(strip=True)

        # IMAGEN: landingImage -> data-old-hires preferred -> src -> og:image fallback
        img_url = None
        landing = soup.select_one("#landingImage")
        if landing:
            img_url = landing.get("data-old-hires") or landing.get("data-old-hires") or landing.get("src")
        if not img_url:
            og = soup.select_one('meta[property="og:image"]')
            if og and og.get("content"):
                img_url = og["content"]

        # Normalizar precios (si vienen con espacios/otros)
        if price:
            price = price.replace("\xa0", " ").strip()
        if old_price:
            old_price = old_price.replace("\xa0", " ").strip()

        return {
            "title": title,
            "price": price or "",
            "old_price": old_price or "",
            "rating": rating or "",
            "reviews": reviews or "",
            "image": img_url or ""
        }
    except Exception as e:
        print("scrape_amazon_product error:", e)
        return None

# ==============================
# IMAGEN: REDIMENSIONAR + MARCO NARANJA
# ==============================
def fetch_and_frame_image(url, max_dim=1280, border_px=12, border_color="#ffa500"):
    """
    Descarga, redimensiona manteniendo proporción y añade marco naranja.
    Devuelve BytesIO listo para send_file.
    """
    if not url:
        return None
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")

        # calcular tamaño de target (restar borde)
        inner_max = max_dim - 2 * border_px
        img.thumbnail((inner_max, inner_max), Image.LANCZOS)

        # aplicar marco
        framed = ImageOps.expand(img, border=border_px, fill=border_color)

        out = BytesIO()
        out.name = "product.jpg"
        framed.save(out, format="JPEG", quality=90)
        out.seek(0)
        return out
    except Exception as e:
        print("fetch_and_frame_image error:", e)
        return None

# ==============================
# HANDLERS: copiar desde origen + generar oferta
# ==============================
async def process_source_message(event):
    """
    - Copia el enlace amzn.to directamente al canal objetivo.
    - Intenta generar una oferta enriquecida y publicarla (imagen + datos).
    """
    text = event.raw_text or ""
    links = re.findall(r'(https?://\S+)', text)
    if not links:
        return

    amazon_link = None
    for link in links:
        if "amzn.to" in link or "amazon.es" in link:
            amazon_link = link
            break
    if not amazon_link:
        return

    # 1) Copiar enlace directo tal cual
    try:
        await client.send_message(target_channel, amazon_link)
        print("🔗 Copiado enlace directo:", amazon_link)
    except Exception as e:
        print("Error copiando enlace directo:", e)

    # 2) Generar oferta enriquecida (si se puede)
    asin = resolve_amazon_link(amazon_link)
    if not asin:
        return

    product = scrape_amazon_product(asin)
    if not product:
        return

    affiliate_url = build_affiliate_url(asin)

    # Preparar campos con fallback legible
    rating_block = ""
    if product["rating"] and product["reviews"]:
        # limpiar reviews: "1.234" o "(1.234)"
        reviews_clean = re.sub(r"[^\d\.]", "", product["reviews"])
        if reviews_clean:
            rating_block = f"{product['rating']} y {reviews_clean} opiniones"
        else:
            rating_block = f"{product['rating']}"
    elif product["rating"]:
        rating_block = product["rating"]
    elif product["reviews"]:
        rating_block = product["reviews"]

    price_new = product["price"] or ""
    price_old = product["old_price"] or ""

    # Construir mensaje final (Markdown)
    message_lines = [
        "🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥",
        f"**{product['title']}**",
    ]
    if rating_block:
        message_lines.append(f"⭐ {rating_block}")
    # precio
    if price_new:
        message_lines.append(f"🟢 **AHORA {price_new}**")
    else:
        message_lines.append("🟢 **AHORA: Precio no disponible**")
    if price_old:
        message_lines.append(f"🔴 ~~ANTES: {price_old}~~")
    # link afiliado
    message_lines.append(f"🔰 {affiliate_url}")
    message = "\n".join(message_lines)

    # Procesar imagen (descarga, resize, marco)
    img_buf = None
    if product["image"]:
        img_buf = fetch_and_frame_image(product["image"])

    try:
        if img_buf:
            await client.send_file(target_channel, img_buf, caption=message, parse_mode="md")
            print("✅ Oferta publicada con imagen")
        else:
            await client.send_message(target_channel, message, parse_mode="md")
            print("✅ Oferta publicada sin imagen")
    except FloodWaitError as e:
        print("FloodWait:", e.seconds)
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print("Error publicando oferta enriquecida:", e)

# ==============================
# HANDLER: cuando pegues solo un enlace en TU canal
# ==============================
async def process_target_message(event):
    text = (event.raw_text or "").strip()
    if not re.match(r'^https?://\S+$', text):
        return

    asin = resolve_amazon_link(text)
    if not asin:
        return

    # borrar mensaje original (para ocultar enlace feo)
    try:
        await event.delete()
    except Exception:
        pass

    product = scrape_amazon_product(asin)
    affiliate_url = build_affiliate_url(asin)
    if not product:
        # si no hay datos, publicar solo afiliado
        await client.send_message(target_channel, affiliate_url)
        return

    # formatear rating/reviews
    rating_block = ""
    if product["rating"] and product["reviews"]:
        reviews_clean = re.sub(r"[^\d\.]", "", product["reviews"])
        rating_block = f"{product['rating']} y {reviews_clean} opiniones"
    elif product["rating"]:
        rating_block = product["rating"]
    elif product["reviews"]:
        rating_block = product["reviews"]

    price_new = product["price"] or ""
    price_old = product["old_price"] or ""

    message_lines = [
        "🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥",
        f"**{product['title']}**",
    ]
    if rating_block:
        message_lines.append(f"⭐ {rating_block}")
    if price_new:
        message_lines.append(f"🟢 **AHORA {price_new}**")
    else:
        message_lines.append("🟢 **AHORA: Precio no disponible**")
    if price_old:
        message_lines.append(f"🔴 ~~ANTES: {price_old}~~")
    message_lines.append(f"🔰 {affiliate_url}")
    message = "\n".join(message_lines)

    img_buf = None
    if product["image"]:
        img_buf = fetch_and_frame_image(product["image"])

    try:
        if img_buf:
            await client.send_file(target_channel, img_buf, caption=message, parse_mode="md")
        else:
            await client.send_message(target_channel, message, parse_mode="md")
    except FloodWaitError as e:
        print("FloodWait:", e.seconds)
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print("Error publicando oferta desde tu canal:", e)

# ==============================
# MAIN
# ==============================
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 BOT ARRANCADO")
    print(f"Copiando {source_channel} → {target_channel}")

    @client.on(events.NewMessage(chats=source_channel))
    async def _on_source(event):
        await process_source_message(event)

    @client.on(events.NewMessage(chats=target_channel))
    async def _on_target(event):
        await process_target_message(event)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
