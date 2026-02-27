import os
import asyncio
import re
import requests
from bs4 import BeautifulSoup
import json
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from PIL import Image, ImageOps
from io import BytesIO
import time  # NUEVO: delays anti-ban

# ==============================
# VARIABLES DE ENTORNO
# ==============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
affiliate_tag = os.getenv("AFFILIATE_TAG")

source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"

client = TelegramClient("session_bot_chollos", api_id, api_hash)

# Sesión ANTI-DETECCIÓN
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="123", "Google Chrome";v="123"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
})

# ==============================
# FUNCIONES AMAZON OPTIMIZADAS
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
        time.sleep(1)  # ANTI-RATE-LIMIT
        r = session.get(url, allow_redirects=True, timeout=10)
        final_url = r.url.split("?")[0]
        return extract_asin(final_url)
    except:
        return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

def scrape_amazon_product(asin):
    url = f"https://www.amazon.es/dp/{asin}"
    try:
        time.sleep(2)  # DELAY ANTI-BAN
        r = session.get(url, timeout=12)
        if "captcha" in r.text.lower() or r.status_code != 200:
            print("🚫 Amazon bloqueó")
            return None
            
        soup = BeautifulSoup(r.text, "lxml")

        title = (soup.select_one("#productTitle") or 
                soup.select_one("span.a-size-large.a-color-base.a-text-normal"))
        title = title.get_text(strip=True) if title else "Producto Amazon"

        # Precio prioritario
        price_selectors = [
            lambda s: s.select_one(".a-price .a-price-whole"),
            lambda s: s.select_one("#priceblock_ourprice"),
            lambda s: s.select_one("#priceblock_dealprice")
        ]
        price = None
        for sel in price_selectors:
            price_whole = sel(soup)
            if price_whole:
                price_fraction = soup.select_one(".a-price .a-price-fraction")
                fraction_text = price_fraction.text.strip() if price_fraction else "00"
                price = f"{price_whole.text.strip()},{fraction_text}€"
                break

        old_price = (soup.select_one(".a-text-price .a-offscreen") or 
                    soup.select_one(".priceBlockStrikePriceString"))
        old_price = old_price.text.strip() if old_price else None

        rating = soup.select_one("#acrPopover")
        rating = rating.get("title") if rating else None

        reviews_elem = soup.select_one("#acrCustomerReviewText")
        reviews_text = ""
        if reviews_elem:
            reviews_clean = re.sub(r"[^0-9\.]", "", reviews_elem.text.strip())
            reviews_text = f"{reviews_clean} opiniones"

        # IMAGEN ULTRA-ROBUSTA (10+ selectores)
        img_selectors = [
            # 1. Dinámico principal
            lambda s: s.find(id="imgTagWrapperId") or s.select_one("#landingImage"),
            # 2. Alternativos landing
            lambda s: s.select_one("#main-image-container img"),
            lambda s: s.select_one(".a-dynamic-image"),
            # 3. Meta
            lambda s: s.select_one('meta[property="og:image"]'),
            # 4. Fallbacks
            lambda s: s.select_one("img#product-image"),
            lambda s: s.select_one("img.a-image-slide"),
        ]
        
        img_url = None
        for selector in img_selectors:
            elem = selector(soup)
            if elem:
                if elem.get("data-a-dynamic-image"):
                    try:
                        dynamic_data = json.loads(elem["data-a-dynamic-image"])
                        best_img = max(dynamic_data.items(), key=lambda x: x[1][1])[0]
                        img_url = best_img.replace("\\", "")
                        break
                    except:
                        pass
                img_url = (elem.get("data-old-hires") or elem.get("data-a-hires") or 
                          elem.get("src") or elem.get("data-src") or elem.get("content"))
                if img_url and "amazon" in img_url:
                    break

        print(f"📸 {img_url[:80] or 'SIN IMAGEN'} | Precio: {price or 'SIN'}")

        return {
            "title": title[:100],  # Telegram limit
            "price": price,
            "old_price": old_price,
            "rating": rating,
            "reviews": reviews_text,
            "image": img_url
        }
    except Exception as e:
        print(f"💥 Scraping falló: {e}")
        return None

# ==============================
# HANDLER ORIGEN (OPTIMIZADO)
# ==============================
@client.on(events.NewMessage(chats=source_channel))
async def handler_source(event):
    try:
        text = event.raw_text or ""
        links = re.findall(r'(https?://\S+)', text)
        amazon_link = next((link for link in links if "amazon" in link or "amzn" in link), None)
        if not amazon_link:
            return

        # Enlace directo
        await client.send_message(target_channel, amazon_link)

        # Oferta (con timeout)
        asin = resolve_amazon_link(amazon_link)
        if asin:
            product = scrape_amazon_product(asin)
            if product:
                message = (
                    f"🔥 OFERTA AMAZON 🔥\n"
                    f"**{product['title']}**\n"
                    f"⭐ {product['rating']} ({product['reviews']})\n"
                    f"🟢 **{product['price']}** {'🔴 ~~' + product['old_price'] + '~~' if product['old_price'] else ''}\n"
                    f"🛒 {build_affiliate_url(asin)}"
                )
                
                if product["image"]:
                    try:
                        resp = session.get(product["image"], timeout=10)
                        img = Image.open(BytesIO(resp.content)).convert("RGB")
                        
                        # Thumbnail UNIVERSAL
                        max_size = (1080, 1080)
                        try:
                            img.thumbnail(max_size, getattr(Image, 'Resampling', Image).LANCZOS)
                        except:
                            img.thumbnail(max_size, getattr(Image, 'LANCZOS', Image.BICUBIC))
                        
                        # Marco fino (ahorra memoria)
                        img = ImageOps.expand(img, border=5, fill=(255, 140, 0))
                        
                        bio = BytesIO()
                        img.save(bio, "JPEG", quality=90, optimize=True)
                        bio.seek(0)
                        
                        await client.send_file(target_channel, bio, caption=message, parse_mode="md")
                    except:
                        await client.send_message(target_channel, message, parse_mode="md")
                else:
                    await client.send_message(target_channel, message, parse_mode="md")
        
        await asyncio.sleep(3)  # PAUSA ANTI-FLOOD
        
    except Exception as e:
        print(f"Error handler_source: {e}")

# ==============================
# HANDLER PEGAR ENLACE
# ==============================
@client.on(events.NewMessage(chats=target_channel))
async def handler_target(event):
    try:
        text = event.raw_text.strip()
        if not re.match(r'^https?://.*amazon.*', text):
            return

        await event.delete()
        
        asin = resolve_amazon_link(text)
        if asin:
            product = scrape_amazon_product(asin)
            if product:
                message = (
                    f"🔥 OFERTA AMAZON 🔥\n"
                    f"**{product['title']}**\n"
                    f"⭐ {product['rating']} ({product['reviews']})\n"
                    f"🟢 **{product['price']}** {'🔴 ~~' + product['old_price'] + '~~' if product['old_price'] else ''}\n"
                    f"🛒 {build_affiliate_url(asin)}"
                )
                
                # Misma lógica foto
                if product["image"]:
                    try:
                        resp = session.get(product["image"], timeout=10)
                        img = Image.open(BytesIO(resp.content)).convert("RGB")
                        max_size = (1080, 1080)
                        try:
                            img.thumbnail(max_size, getattr(Image, 'Resampling', Image).LANCZOS)
                        except:
                            img.thumbnail(max_size, getattr(Image, 'LANCZOS', Image.BICUBIC))
                        img = ImageOps.expand(img, border=5, fill=(255, 140, 0))
                        bio = BytesIO()
                        img.save(bio, "JPEG", quality=90, optimize=True)
                        bio.seek(0)
                        await client.send_file(target_channel, bio, caption=message, parse_mode="md")
                    except:
                        await client.send_message(target_channel, message, parse_mode="md")
                else:
                    await client.send_message(target_channel, message, parse_mode="md")
        
        await asyncio.sleep(3)
        
    except Exception as e:
        print(f"Error handler_target: {e}")

# ==============================
# MAIN ESTABLE
# ==============================
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 BOT CHOLLOS v3.0 ESTABLE ✅")
    print("⏳ Delays anti-ban + memoria optimizada")
    
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
