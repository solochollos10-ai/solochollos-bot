import asyncio
import re
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from PIL import Image, ImageOps
import io

# ==============================
# CONFIGURACIÓN
# ==============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

affiliate_tag = "solochollos08-21"
source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"

client = TelegramClient("session_bot_chollos", api_id, api_hash)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9"
})

# ==============================
# FUNCIONES AMAZON
# ==============================
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
        asin = extract_asin(final_url)
        if asin:
            return asin
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

        title = soup.select_one("#productTitle")
        title = title.get_text(strip=True) if title else "Producto Amazon"

        price_whole = soup.select_one(".a-price-whole")
        price_fraction = soup.select_one(".a-price-fraction")
        price = f"{price_whole.text.strip()},{price_fraction.text.strip()}€" if price_whole and price_fraction else None

        old_price = soup.select_one(".a-price.a-text-price .a-offscreen")
        old_price = old_price.text.strip() if old_price else None

        rating = soup.select_one("#acrPopover")
        rating = rating.get("title") if rating else None

        reviews = soup.select_one("#acrCustomerReviewText")
        reviews = reviews.text.strip() if reviews else None

        img_url = None
        landing = soup.select_one("#landingImage")
        if landing:
            img_url = landing.get("data-old-hires") or landing.get("src")
        if not img_url:
            og_img = soup.select_one('meta[property="og:image"]')
            if og_img:
                img_url = og_img.get("content")

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

# ==============================
# AÑADIR MARCO Y REDIMENSIONAR IMAGEN
# ==============================
def add_frame_and_resize_image(url, border_color="#ffa500", border_width=20, max_size=1024):
    try:
        resp = session.get(url, timeout=15)
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")

        # Redimensionar si es demasiado grande
        img.thumbnail((max_size - 2*border_width, max_size - 2*border_width), Image.ANTIALIAS)

        # Añadir marco
        framed_img = ImageOps.expand(img, border=border_width, fill=border_color)

        buf = io.BytesIO()
        framed_img.save(buf, format="JPEG")
        buf.seek(0)
        return buf
    except Exception as e:
        print("Error añadiendo marco/redimensionando:", e)
        return None

# ==============================
# PROCESAR MENSAJES DEL CANAL ORIGEN
# ==============================
async def process_source_message(event):
    text = event.raw_text or ""
    links = re.findall(r'(https?://\S+)', text)
    amazon_link = None
    for link in links:
        if "amzn.to" in link or "amazon.es" in link:
            amazon_link = link
            break
    if not amazon_link:
        return

    # Mantener el enlace original
    new_text = text

    asin = resolve_amazon_link(amazon_link)
    product = scrape_amazon_product(asin) if asin else None

    try:
        if product and product["image"]:
            framed_img = add_frame_and_resize_image(product["image"])
            if framed_img:
                await client.send_file(target_channel, framed_img, caption=new_text, parse_mode="md")
            else:
                await client.send_file(target_channel, product["image"], caption=new_text, parse_mode="md")
        else:
            await client.send_message(target_channel, new_text, parse_mode="md")
        print("✅ Oferta copiada desde @chollosdeluxe")
    except Exception as e:
        print("Error enviando mensaje:", e)

# ==============================
# PROCESAR ENLACES PEGADOS EN TU CANAL
# ==============================
async def process_target_message(event):
    text = event.raw_text.strip()
    if not re.match(r'^https?://\S+$', text):
        return

    asin = resolve_amazon_link(text)
    if not asin:
        return

    await event.delete()
    affiliate_url = build_affiliate_url(asin)
    product = scrape_amazon_product(asin)
    if not product:
        return

    rating_text = product["rating"] if product["rating"] else ""
    reviews_text = ""
    if product["reviews"]:
        reviews_clean = re.sub(r"[^\d\.]", "", product["reviews"])
        reviews_text = f"{reviews_clean} opiniones"

    price_text = product["price"].replace(",,", ",") if product["price"] else ""
    old_price_text = product["old_price"] if product["old_price"] else ""

    message = f"""🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥

**{product['title']}**

⭐ {rating_text} y {reviews_text}

🟢 **AHORA {price_text}**
🔴 ~~ANTES: {old_price_text}~~

🔰 **{affiliate_url}**
"""

    try:
        if product["image"]:
            framed_img = add_frame_and_resize_image(product["image"])
            if framed_img:
                await client.send_file(target_channel, framed_img, caption=message, parse_mode="md")
            else:
                await client.send_file(target_channel, product["image"], caption=message, parse_mode="md")
        else:
            await client.send_message(target_channel, message, parse_mode="md")
        print("✅ Oferta generada desde enlace en tu canal")
    except Exception as e:
        print("Error publicando oferta:", e)

# ==============================
# MAIN
# ==============================
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 BOT ACTIVADO")
    print("✅ Copia @chollosdeluxe → @solochollos10")
    print("✅ Generación automática de ofertas con enlaces afiliados, fotos y marco naranja")

    @client.on(events.NewMessage(chats=source_channel))
    async def handler_source(event):
        await process_source_message(event)

    @client.on(events.NewMessage(chats=target_channel))
    async def handler_target(event):
        await process_target_message(event)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
