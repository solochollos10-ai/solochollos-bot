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
# CREDENCIALES DESDE VARIABLES DE ENTORNO
# ==============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

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
        
        # --- TÍTULO ---
        title = soup.select_one("#productTitle") or soup.select_one("span.a-size-large.a-color-base.a-text-normal")
        title = title.get_text(strip=True) if title else "Producto Amazon"
        
        # --- PRECIO ACTUAL ---
        price = None
        price_selectors = [
            ".a-price .a-price-whole",  # estándar
            "#corePriceDisplay_desktop_feature_div .a-price .a-price-whole",
            "#priceblock_ourprice",
            "#priceblock_dealprice"
        ]
        fraction_selectors = [".a-price .a-price-fraction"]
        for sel in price_selectors:
            whole = soup.select_one(sel)
            if whole:
                fraction = soup.select_one(fraction_selectors[0])
                fraction_text = fraction.text.strip() if fraction else "00"
                price = f"{whole.text.strip()},{fraction_text}€"
                break
        
        # --- PRECIO ANTIGUO ---
        old_price = None
        old_price_selectors = [
            ".a-price.a-text-price .a-offscreen",
            "#priceblock_listprice",
        ]
        for sel in old_price_selectors:
            old = soup.select_one(sel)
            if old:
                old_price = old.text.strip()
                break
        
        # --- VALORACIÓN ---
        rating = soup.select_one("#acrPopover")
        rating_text = rating["title"].strip() if rating and rating.has_attr("title") else None
        
        # --- NÚMERO DE RESEÑAS ---
        reviews = soup.select_one("#acrCustomerReviewText")
        reviews_text = re.sub(r"[^\d]", "", reviews.text.strip()) if reviews else None
        
        # --- IMAGEN PRINCIPAL ---
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
            "rating": rating_text,
            "reviews": reviews_text,
            "image": img_url
        }

    except Exception as e:
        print("Error scraping:", e)
        return None

# ==============================
# PROCESAMIENTO DE IMAGEN
# ==============================
def process_image(image_url, max_size=(800, 800), border_color="#ffa500"):
    try:
        r = session.get(image_url, timeout=15)
        img = Image.open(BytesIO(r.content)).convert("RGB")
        img.thumbnail(max_size, Image.ANTIALIAS)
        border = ImageOps.expand(img, border=10, fill=border_color)
        output = BytesIO()
        output.name = "product.jpg"
        border.save(output, format="JPEG")
        output.seek(0)
        return output
    except Exception as e:
        print("Error procesando imagen:", e)
        return None

# ==============================
# PROCESAR MENSAJES DEL CANAL ORIGEN
# ==============================
async def process_source_message(event):
    text = event.raw_text or ""
    links = re.findall(r'(https?://\S+)', text)
    if not links:
        return
    
    amazon_link = next((l for l in links if "amzn.to" in l or "amazon.es" in l), None)
    if not amazon_link:
        return

    asin = resolve_amazon_link(amazon_link)
    if not asin:
        print("ASIN no encontrado")
        return

    affiliate_url = build_affiliate_url(asin)
    product = scrape_amazon_product(asin)

    if product:
        rating_text = f"{product['rating']} y {product['reviews']} opiniones" if product['rating'] and product['reviews'] else ""
        price_text = product['price'].replace(",,", ",") if product['price'] else "Precio no disponible"
        old_price_text = product['old_price'] if product['old_price'] else "Precio anterior no disponible"
        
        message = f"🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥\n**{product['title']}**\n⭐ {rating_text}\n🟢 **AHORA {price_text}** 🔴 ~~ANTES: {old_price_text}~~\n🔰 {affiliate_url}"
        
        img_file = process_image(product['image']) if product.get('image') else None
        
        try:
            if img_file:
                await client.send_file(
                    target_channel,
                    img_file,
                    caption=message,
                    parse_mode="md"
                )
            else:
                await client.send_message(target_channel, message, parse_mode="md")
            print("✅ Oferta copiada correctamente")
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print("Error enviando mensaje:", e)

# ==============================
# PROCESAR ENLACES PEGADOS EN EL CANAL DESTINO
# ==============================
async def process_target_message(event):
    text = event.raw_text.strip()
    if not re.match(r'^https?://\S+$', text):
        return

    asin = resolve_amazon_link(text)
    if not asin:
        return
    
    await event.delete()  # Borrar mensaje original
    
    affiliate_url = build_affiliate_url(asin)
    product = scrape_amazon_product(asin)
    
    if not product:
        return
    
    rating_text = f"{product['rating']} y {product['reviews']} opiniones" if product['rating'] and product['reviews'] else ""
    price_text = product['price'].replace(",,", ",") if product['price'] else "Precio no disponible"
    old_price_text = product['old_price'] if product['old_price'] else "Precio anterior no disponible"
    
    message = f"🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥\n**{product['
