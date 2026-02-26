import os
import asyncio
import re
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from PIL import Image, ImageOps
from io import BytesIO

# ==================================================
# VARIABLES DE ENTORNO (RAILWAY)
# ==================================================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
affiliate_tag = os.getenv("AFFILIATE_TAG")

source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"

client = TelegramClient("session_bot_chollos", api_id, api_hash)

# ==================================================
# SESIÓN HTTP OPTIMIZADA
# ==================================================
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
})

# ==================================================
# FUNCIONES AMAZON
# ==================================================
def extract_asin(url):
    patterns = [
        r"/dp/([A-Z0-9]{10})",
        r"/gp/product/([A-Z0-9]{10})"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def resolve_amazon_link(url):
    try:
        r = session.get(url, allow_redirects=True, timeout=15)
        final_url = r.url.split("?")[0]
        return extract_asin(final_url)
    except Exception as e:
        print("Error resolviendo enlace:", e)
        return None


def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"


def scrape_amazon_product(asin):
    url = f"https://www.amazon.es/dp/{asin}"

    try:
        r = session.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        # ==============================
        # TÍTULO
        # ==============================
        title_elem = soup.select_one("#productTitle")
        title = title_elem.get_text(strip=True) if title_elem else "Producto Amazon"

        # ==============================
        # PRECIO ACTUAL (APEX)
        # ==============================
        price = None
        price_elem = soup.select_one(".apex-pricetopay-value .a-offscreen")

        if price_elem:
            price = price_elem.get_text(strip=True)

        if not price:
            fallback_price = soup.select_one("#priceblock_ourprice, #priceblock_dealprice")
            if fallback_price:
                price = fallback_price.get_text(strip=True)

        # ==============================
        # PRECIO ANTERIOR
        # ==============================
        old_price = None
        old_price_elem = soup.select_one(".apex-basisprice-value .a-offscreen")

        if old_price_elem:
            old_price = old_price_elem.get_text(strip=True)

        if not old_price:
            fallback_old = soup.select_one(".a-text-price .a-offscreen")
            if fallback_old:
                old_price = fallback_old.get_text(strip=True)

        # ==============================
        # VALORACIÓN
        # ==============================
        rating_elem = soup.select_one("#acrPopover")
        rating = rating_elem["title"] if rating_elem and rating_elem.has_attr("title") else ""

        # ==============================
        # REVIEWS
        # ==============================
        reviews_elem = soup.select_one("#acrCustomerReviewText")
        reviews = reviews_elem.get_text(strip=True) if reviews_elem else ""

        # ==============================
        # IMAGEN PRINCIPAL
        # ==============================
        img_url = None
        landing = soup.select_one("#landingImage")

        if landing:
            img_url = landing.get("data-old-hires") or landing.get("src")

        if not img_url:
            og = soup.select_one('meta[property="og:image"]')
            if og:
                img_url = og.get("content")

        return {
            "title": title,
            "price": price,
            "old_price": old_price,
            "rating": rating,
            "reviews": reviews,
            "image": img_url
        }

    except Exception as e:
        print("Error scraping:", e)
        return None


# ==================================================
# PROCESAR IMAGEN (REDIMENSION + MARCO NARANJA)
# ==================================================
def process_image(image_url):
    try:
        response = session.get(image_url, timeout=15)
        img = Image.open(BytesIO(response.content)).convert("RGB")

        # Redimensionar si es grande
        max_size = (1280, 1280)
        img.thumbnail(max_size, Image.LANCZOS)

        # Añadir marco naranja #ffa500
        img = ImageOps.expand(img, border=12, fill=(255, 165, 0))

        bio = BytesIO()
        bio.name = "producto.jpg"
        img.save(bio, "JPEG", quality=95)
        bio.seek(0)

        return bio

    except Exception as e:
        print("Error procesando imagen:", e)
        return None


# ==================================================
# FORMATEAR MENSAJE
# ==================================================
def build_message(product, affiliate_url):
    message = (
        "🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥\n"
        f"**{product['title']}**\n"
    )

    if product["rating"] or product["reviews"]:
        message += f"⭐ {product['rating']} {product['reviews']}\n"

    if product["price"]:
        message += f"🟢 **AHORA {product['price']}** "

    if product["old_price"]:
        message += f"🔴 ~~ANTES: {product['old_price']}~~"

    message += f"\n🔰 {affiliate_url}"

    return message


# ==================================================
# PROCESAR MENSAJES
# ==================================================
async def process_message(event):
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

    asin = resolve_amazon_link(amazon_link)
    if not asin:
        return

    affiliate_url = build_affiliate_url(asin)
    product = scrape_amazon_product(asin)

    if not product:
        return

    message = build_message(product, affiliate_url)

    img_file = process_image(product["image"]) if product["image"] else None

    try:
        if img_file:
            await client.send_file(
                target_channel,
                img_file,
                caption=message,
                parse_mode="md"
            )
        else:
            await client.send_message(
                target_channel,
                message,
                parse_mode="md"
            )

        print("✅ Oferta publicada correctamente")

    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)


# ==================================================
# MAIN
# ==================================================
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 BOT ACTIVADO")
    print("🔥 Scraping optimizado con selectores reales Amazon")

    @client.on(events.NewMessage(chats=source_channel))
    async def handler_source(event):
        await process_message(event)

    @client.on(events.NewMessage(chats=target_channel))
    async def handler_target(event):
        await process_message(event)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
