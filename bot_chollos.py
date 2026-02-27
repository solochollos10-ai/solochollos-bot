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
# CONFIGURACIÓN
# ==============================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
AFFILIATE_TAG = os.getenv("AFFILIATE_TAG", "solochollos08-21")

source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"

client = TelegramClient("session_bot_chollos", API_ID, API_HASH)

# ==============================
# SESIÓN HTTP (anti-bloqueo básico)
# ==============================
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
})

# ==============================
# AMAZON UTILIDADES
# ==============================
def extract_asin(url):
    patterns = [
        r"/dp/([A-Z0-9]{10})",
        r"/gp/product/([A-Z0-9]{10})"
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def resolve_amazon_link(url):
    try:
        r = session.get(url, allow_redirects=True, timeout=15)
        final = r.url.split("?")[0]
        return extract_asin(final)
    except:
        return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={AFFILIATE_TAG}"

# ==============================
# SCRAPING AMAZON (selectores actuales)
# ==============================
def scrape_amazon_product(asin):
    url = f"https://www.amazon.es/dp/{asin}"
    try:
        r = session.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        # Título (usando el selector dado por el usuario)
        title = soup.select_one("#productTitle")
        title = title.get_text(strip=True) if title else "Producto Amazon"

        # Precio actual (buscando el precio nuevo en la página)
        price = None
        price_elem = soup.select_one(".a-price .a-offscreen")
        if price_elem:
            price = price_elem.get_text(strip=True)

        # Precio antiguo (buscando el precio recomendado)
        old_price = None
        old_price_elem = soup.select_one(".a-size-small .a-color-secondary .a-offscreen")
        if old_price_elem:
            old_price = old_price_elem.get_text(strip=True)

        # Rating
        rating_elem = soup.select_one("#acrPopover")
        rating = rating_elem["title"] if rating_elem and rating_elem.has_attr("title") else ""

        # Reviews
        reviews_elem = soup.select_one("#acrCustomerReviewText")
        reviews = reviews_elem.get_text(strip=True) if reviews_elem else ""

        # Imagen
        img_url = None
        img_elem = soup.select_one("#main-image-container img")
        if img_elem:
            img_url = img_elem.get("data-old-hires") or img_elem.get("src")

        return {
            "title": title,
            "price": price or "",
            "old_price": old_price or "",
            "rating": rating or "",
            "reviews": reviews or "",
            "image": img_url or ""
        }

    except Exception as e:
        print("Scraping error:", e)
        return None

# ==============================
# IMAGEN CON MARCO
# ==============================
def fetch_and_frame_image(url):
    try:
        r = session.get(url, timeout=15)
        img = Image.open(BytesIO(r.content)).convert("RGB")
        img.thumbnail((1100, 1100))
        framed = ImageOps.expand(img, border=10, fill="#ff7a00")

        buffer = BytesIO()
        buffer.name = "producto.jpg"
        framed.save(buffer, format="JPEG", quality=90)
        buffer.seek(0)
        return buffer
    except:
        return None

# ==============================
# PROCESAR MENSAJES DEL CANAL ORIGEN
# ==============================
async def process_source_message(event):
    text = event.raw_text or ""

    # Copiar SIEMPRE el mensaje original (si no es Amazon)
    links = re.findall(r'(https?://\S+)', text)

    if not links:
        # copiar mensaje normal
        await client.send_message(target_channel, text)
        return

    amazon_link = None
    for link in links:
        if "amazon" in link or "amzn.to" in link:
            amazon_link = link
            break

    # Si no es Amazon → copiar tal cual
    if not amazon_link:
        await client.send_message(target_channel, text)
        return

    # Resolver ASIN
    asin = resolve_amazon_link(amazon_link)
    if not asin:
        await client.send_message(target_channel, text)
        return

    product = scrape_amazon_product(asin)
    if not product:
        await client.send_message(target_channel, text)
        return

    affiliate_url = build_affiliate_url(asin)

    message = "🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥\n"
    message += f"**{product['title']}**\n"

    if product["rating"]:
        message += f"⭐ {product['rating']} {product['reviews']}\n"

    if product["price"]:
        message += f"🟢 **AHORA {product['price']}**\n"
    else:
        message += "🟢 **AHORA: No disponible**\n"

    if product["old_price"]:
        message += f"🔴 ~~ANTES: {product['old_price']}~~\n"

    message += f"🔰 {affiliate_url}"

    img = fetch_and_frame_image(product["image"])

    try:
        if img:
            await client.send_file(target_channel, img, caption=message, parse_mode="md")
        else:
            await client.send_message(target_channel, message, parse_mode="md")
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)

# ==============================
# MAIN
# ==============================
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("BOT ACTIVO")

    @client.on(events.NewMessage(chats=source_channel))
    async def handler(event):
        await process_source_message(event)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
