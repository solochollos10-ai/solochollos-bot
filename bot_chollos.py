import os
import asyncio
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from PIL import Image, ImageOps
from io import BytesIO
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

# ==============================
# VARIABLES DE ENTORNO (RAILWAY)
# ==============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
affiliate_tag = os.getenv("AFFILIATE_TAG")
PROXY_URL = os.getenv("PROXY_URL", None)  # Opcional: http://user:pass@proxy:port

source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"

client = TelegramClient("session_bot_chollos_v2", api_id, api_hash)
ua = UserAgent()

# Sesión HTTP robusta
session = requests.Session()
session.headers.update({
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
})

if PROXY_URL:
    session.proxies = {"http": PROXY_URL, "https": PROXY_URL}

def markdown_escape(text):
    """Escapa caracteres especiales para Markdown"""
    if not text:
        return ""
    chars = r'*_[]()~`>#+=|{}.!-'
    for char in chars:
        text = text.replace(char, f'\\{char}')
    return text

# ==============================
# FUNCIONES AMAZON ROBUSTAS
# ==============================
def extract_asin(url):
    patterns = [r"/dp/([A-Z0-9]{10})", r"/gp/product/([A-Z0-9]{10})"]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def resolve_amazon_link(url):
    try:
        # Headers frescos
        session.headers["User-Agent"] = ua.random
        r = session.get(url, allow_redirects=True, timeout=15)
        final_url = r.url.split("?")[0]
        return extract_asin(final_url)
    except Exception as e:
        print(f"Error resolviendo enlace {url}: {e}")
        return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def scrape_amazon_product(asin):
    url = f"https://www.amazon.es/dp/{asin}"
    try:
        # Headers nuevos para cada intento
        session.headers["User-Agent"] = ua.random
        r = session.get(url, timeout=20)
        
        if r.status_code == 403 or r.status_code == 503:
            raise Exception(f"Bloqueado {r.status_code}")
        
        if r.status_code != 200:
            print(f"Status inesperado {r.status_code} para {asin}")
            return None
            
        soup = BeautifulSoup(r.text, "lxml")

        # TÍTULO (múltiples selectores)
        title_selectors = [
            "#productTitle",
            "span.a-size-large.a-color-base.a-text-normal",
            "h1.a-size-large.a-spacing-none"
        ]
        title = None
        for sel in title_selectors:
            title = soup.select_one(sel)
            if title:
                break
        title = title.get_text(strip=True)[:200] if title else "Producto Amazon"

        # PRECIO (múltiples formatos)
        price = None
        price_selectors = [
            ".a-price .a-price-whole",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            ".a-price-symbol + .a-price-whole"
        ]
        price_whole = soup.select_one(price_selectors[0])
        if price_whole:
            price_fraction = soup.select_one(".a-price .a-price-fraction")
            fraction = price_fraction.text.strip() if price_fraction else "00"
            price = f"{price_whole.text.strip()},{fraction}€"
        else:
            for sel in price_selectors[1:]:
                price_elem = soup.select_one(sel)
                if price_elem:
                    price = price_elem.text.strip()
                    break

        # PRECIO ANTIGUO
        old_price_selectors = [
            ".a-text-price .a-offscreen",
            ".priceBlockStrikePriceString",
            "span.a-price.a-text-price span.a-offscreen"
        ]
        old_price = None
        for sel in old_price_selectors:
            old_price_elem = soup.select_one(sel)
            if old_price_elem:
                old_price = old_price_elem.text.strip()
                break

        # RATING Y REVIEWS
        rating_elem = soup.select_one("#acrPopover")
        rating = rating_elem.get("title") if rating_elem else None
        
        reviews_elem = soup.select_one("#acrCustomerReviewText")
        reviews_text = ""
        if reviews_elem:
            reviews_clean = re.sub(r"[^\d.]", "", reviews_elem.text.strip())
            reviews_text = f"{reviews_clean} opiniones"

        # IMAGEN
        img_url = None
        landing = soup.select_one("#landingImage")
        if landing:
            img_url = landing.get("data-old-hires") or landing.get("src")
        if not img_url:
            og_img = soup.select_one('meta[property="og:image"]')
            img_url = og_img.get("content") if og_img else None

        return {
            "title": title,
            "price": price,
            "old_price": old_price,
            "rating": rating,
            "reviews": reviews_text,
            "image": img_url
        }
    except Exception as e:
        print(f"Error scraping {asin}: {e}")
        raise  # Para que tenacity reintente

async def fetch_and_process_image(img_url):
    """Función reutilizable para imagen"""
    if not img_url:
        return None
    try:
        session.headers["User-Agent"] = ua.random
        resp = session.get(img_url, timeout=15)
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        
        # Redimensionar
        max_size = (1280, 1280)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)  # ANTIALIAS deprecated
        
        # Borde naranja
        border_color = (255, 165, 0)
        img = ImageOps.expand(img, border=10, fill=border_color)
        
        bio = BytesIO()
        bio.name = "product.jpg"
        img.save(bio, "JPEG", quality=90)
        bio.seek(0)
        return bio
    except Exception as e:
        print(f"Error procesando imagen {img_url}: {e}")
        return None

def build_offer_message(product, affiliate_url):
    """Mensaje con escape Markdown"""
    title = markdown_escape(product["title"])
    rating_text = markdown_escape(product["rating"] or "")
    reviews_text = markdown_escape(product["reviews"] or "")
    price_text = markdown_escape(product["price"] or "")
    old_price_text = markdown_escape(product["old_price"] or "")
    
    return (
        f"🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥\n"
        f"**{title}**\n"
        f"⭐ {rating_text} y {reviews_text}\n"
        f"🟢 **AHORA {price_text}** 🔴 ~~ANTES: {old_price_text}~~\n"
        f"🔰 {affiliate_url}"
    )

# ==============================
# PROCESAR MENSAJES (ROBUSTO)
# ==============================
async def process_source_message(event):
    text = event.raw_text or ""
    links = re.findall(r'https?://[^\s<>"]+', text)
    if not links:
        return
        
    amazon_link = next((link for link in links if "amazon" in link or "amzn" in link), None)
    if not amazon_link:
        return

    # Enlace directo con delay anti-flood
    try:
        await asyncio.sleep(random.uniform(1, 3))
        await client.send_message(target_channel, amazon_link)
        print(f"🔗 Copiado: {amazon_link}")
    except FloodWaitError as e:
        print(f"Flood wait {e.seconds}s")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print(f"Error enlace directo: {e}")

    # Oferta completa
    await process_offer(amazon_link)

async def process_target_message(event):
    text = event.raw_text.strip()
    if not re.match(r'^https?://[^\s<>"]+$', text):
        return

    await event.delete()
    await process_offer(text)

async def process_offer(amazon_link):
    """Lógica común para ofertas"""
    asin = resolve_amazon_link(amazon_link)
    if not asin:
        return
        
    # Delay anti-bloqueo Amazon
    await asyncio.sleep(random.uniform(3, 7))
    
    affiliate_url = build_affiliate_url(asin)
    product = scrape_amazon_product(asin)
    if not product or not product["price"]:
        print(f"Sin datos válidos para {asin}")
        return

    message = build_offer_message(product, affiliate_url)
    image_bio = await fetch_and_process_image(product["image"])

    try:
        await asyncio.sleep(random.uniform(1, 2))
        if image_bio:
            await client.send_file(target_channel, image_bio, caption=message, parse_mode="md")
            print(f"✅ Oferta con foto {asin}")
        else:
            await client.send_message(target_channel, message, parse_mode="md")
            print(f"✅ Oferta texto {asin}")
    except FloodWaitError as e:
        print(f"Flood en envío {asin}: {e.seconds}s")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print(f"Error enviando oferta {asin}: {e}")

# ==============================
# MAIN
# ==============================
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 BOT CHOLLOS V2 ACTIVADO")
    print(f"✅ {source_channel} → {target_channel}")
    print("✅ Anti-bloqueo: UA rotación, delays, reintentos, proxies opcionales")
    print("✅ Markdown seguro + scraping robusto")

    @client.on(events.NewMessage(chats=source_channel))
    async def handler_source(event):
        try:
            await process_source_message(event)
        except Exception as e:
            print(f"Error handler origen: {e}")

    @client.on(events.NewMessage(chats=target_channel))
    async def handler_target(event):
        try:
            await process_target_message(event)
        except Exception as e:
            print(f"Error handler destino: {e}")

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
