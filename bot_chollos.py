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
# VARIABLES DE ENTORNO (RAILWAY)
# ==============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
affiliate_tag = os.getenv("AFFILIATE_TAG")
source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"

client = TelegramClient("session_bot_chollos", api_id, api_hash)

# Sesión HTTP
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9"
})

# ==============================
# FUNCIONES AMAZON
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
        
        # --- TÍTULO ---
        title = soup.select_one("#productTitle")
        if not title:
            title = soup.select_one("span.a-size-large.a-color-base.a-text-normal")
        title = title.get_text(strip=True) if title else "Producto Amazon"
        
        # --- PRECIO ACTUAL ---
        price = None
        price_whole = soup.select_one(".a-price .a-price-whole")
        price_fraction = soup.select_one(".a-price .a-price-fraction")
        if price_whole:
            fraction_text = price_fraction.text.strip() if price_fraction else "00"
            price = f"{price_whole.text.strip()},{fraction_text}€"
        else:
            price_alt = soup.select_one("#priceblock_ourprice") or soup.select_one("#priceblock_dealprice")
            price = price_alt.text.strip() if price_alt else None
        
        # --- PRECIO ANTIGUO ---
        old_price_elem = soup.select_one(".a-text-price .a-offscreen") or soup.select_one(".priceBlockStrikePriceString")
        old_price = old_price_elem.text.strip() if old_price_elem else None
        
        # --- RATING ---
        rating_elem = soup.select_one("#acrPopover")
        rating = rating_elem.get("title") if rating_elem else None
        
        # --- REVIEWS ---
        reviews_elem = soup.select_one("#acrCustomerReviewText")
        reviews_text = ""
        if reviews_elem:
            reviews_clean = re.sub(r"[^\d\.]", "", reviews_elem.text.strip())
            reviews_text = f"{reviews_clean} opiniones"
        
        # --- IMAGEN ---
        img_url = None
        landing = soup.select_one("img#landingImage.a")
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
            "reviews": reviews_text,
            "image": img_url
        }

    except Exception as e:
        print("Error scraping:", e)
        return None

# ==============================
# PROCESAR MENSAJES DEL CANAL ORIGEN
# ==============================
async def process_source_message(event):
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
    
    # Copia directa del enlace al canal
    try:
        await client.send_message(target_channel, amazon_link)
        print(f"🔗 Copiado enlace directo: {amazon_link}")
    except Exception as e:
        print("Error enviando enlace directo:", e)
    
    # Generar oferta completa
    asin = resolve_amazon_link(amazon_link)
    if not asin:
        return
    
    affiliate_url = build_affiliate_url(asin)
    product = scrape_amazon_product(asin)
    if not product:
        return
    
    rating_text = product["rating"] if product["rating"] else ""
    reviews_text = product["reviews"] if product["reviews"] else ""
    price_text = product["price"].replace(",,", ",") if product["price"] else ""
    old_price_text = product["old_price"] if product["old_price"] else ""
    
    message = (
        f"🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥\n"
        f"**{product['title']}**\n"
        f"⭐ {rating_text} y {reviews_text}\n"
        f"🟢 **AHORA {price_text}** 🔴 ~~ANTES: {old_price_text}~~\n"
        f"🔰 {affiliate_url}"
    )
    
    # --- PROCESAR IMAGEN ---
    if product["image"]:
        try:
            resp = session.get(product["image"], timeout=15)
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            # Redimensionar si demasiado grande (Telegram recomienda <= 1280x1280)
            max_size = (1280, 1280)
            img.thumbnail(max_size, Image.ANTIALIAS)
            # Añadir marco naranja (#ffa500)
            border_color = (255, 165, 0)
            img = ImageOps.expand(img, border=10, fill=border_color)
            bio = BytesIO()
            bio.name = "product.jpg"
            img.save(bio, "JPEG")
            bio.seek(0)
            await client.send_file(target_channel, bio, caption=message, parse_mode="md")
            print("✅ Oferta publicada con foto")
        except Exception as e:
            print("Error publicando imagen:", e)
            await client.send_message(target_channel, message, parse_mode="md")
    else:
        await client.send_message(target_channel, message, parse_mode="md")

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
    
    # Borrar mensaje original
    await event.delete()
    
    affiliate_url = build_affiliate_url(asin)
    product = scrape_amazon_product(asin)
    
    if not product:
        return
    
    rating_text = product["rating"] if product["rating"] else ""
    reviews_text = product["reviews"] if product["reviews"] else ""
    price_text = product["price"].replace(",,", ",") if product["price"] else ""
    old_price_text = product["old_price"] if product["old_price"] else ""
    
    message = (
        f"🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥\n"
        f"**{product['title']}**\n"
        f"⭐ {rating_text} y {reviews_text}\n"
        f"🟢 **AHORA {price_text}** 🔴 ~~ANTES: {old_price_text}~~\n"
        f"🔰 {affiliate_url}"
    )
    
    # --- PROCESAR IMAGEN ---
    if product["image"]:
        try:
            resp = session.get(product["image"], timeout=15)
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            max_size = (1280, 1280)
            img.thumbnail(max_size, Image.ANTIALIAS)
            img = ImageOps.expand(img, border=10, fill=(255, 165, 0))
            bio = BytesIO()
            bio.name = "product.jpg"
            img.save(bio, "JPEG")
            bio.seek(0)
            await client.send_file(target_channel, bio, caption=message, parse_mode="md")
        except Exception as e:
            print
