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
# UTILIDADES AMAZON
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

        # Título
        title_elem = soup.select_one("#productTitle")
        title = title_elem.get_text(strip=True) if title_elem else "Producto Amazon"

        # PRECIO ACTUAL
        price = None
        price_elem = soup.select_one(".apex-pricetopay-value .a-offscreen")
        if price_elem:
            price = price_elem.get_text(strip=True)
        else:
            alt = soup.select_one(".a-price .a-offscreen")
            if alt:
                price = alt.get_text(strip=True)

        # PRECIO ANTERIOR
        old_price = None
        old_price_elem = soup.select_one(".apex-basisprice-value .a-offscreen")
        if old_price_elem:
            old_price = old_price_elem.get_text(strip=True)
        else:
            alt_old = soup.select_one(".a-text-price .a-offscreen")
            if alt_old:
                old_price = alt_old.get_text(strip=True)

        # VALORACIÓN
        rating_elem = soup.select_one("#acrPopover")
        rating = rating_elem["title"] if rating_elem and rating_elem.has_attr("title") else ""

        # REVIEWS
        reviews_elem = soup.select_one("#acrCustomerReviewText")
        reviews = reviews_elem.get_text(strip=True) if reviews_elem else ""

        # FOTO
        img_url = None
        img_elem = soup.select_one('#imageBlock #main-image-container img')
        if img_elem:
            img_url = img_elem.get('src')

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
# HANDLERS: copiar desde origen + generar oferta
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
    await client.start(bot_token=BOT_TOKEN)
    print("🤖 BOT ARRANCADO")
    print(f"Copiando {source_channel} → {target_channel}")

    @client.on(events.NewMessage(chats=source_channel))
    async def handler(event):
        await process_source_message(event)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
