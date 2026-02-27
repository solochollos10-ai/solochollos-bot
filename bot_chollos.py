import os
import asyncio
import re
import requests
import random
from bs4 import BeautifulSoup
import json
from telethon import TelegramClient, events
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

# ==============================
# ANTI-BLOQUEO AMAZON
# ==============================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0"
    }

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
        # Usamos requests.get sin sesión persistente
        r = requests.get(url, headers=get_random_headers(), allow_redirects=True, timeout=15)
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
        # Petición limpia en cada llamada
        r = requests.get(url, headers=get_random_headers(), timeout=15)
        
        # LOGS DE BLOQUEO DE AMAZON
        if r.status_code != 200:
            print(f"⚠️ Amazon devolvió código HTTP: {r.status_code}")
        if "captcha" in r.text.lower() or "validateCaptcha" in r.text:
            print("🛑 ¡CUIDADO! Amazon está pidiendo CAPTCHA. Nos ha detectado.")

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
            reviews_clean = re.sub(r"[^0-9\.]", "", reviews_elem.text.strip())
            reviews_text = f"{reviews_clean} opiniones"

        # --- IMAGEN ---
        img_url = None
        img_tag_wrapper = soup.find(id="imgTagWrapperId") or soup.select_one("#landingImage")
        
        if img_tag_wrapper and img_tag_wrapper.get("data-a-dynamic-image"):
            try:
                dynamic_data = json.loads(img_tag_wrapper["data-a-dynamic-image"])
                best_img = max(dynamic_data.items(), key=lambda x: x[1][1])[0]
                img_url = best_img.replace("\\", "")
            except Exception as e:
                pass

        if not img_url:
            landing = soup.select_one("#landingImage")
            if landing:
                img_url = (landing.get("data-old-hires") or 
                          landing.get("data-a-hires") or 
                          landing.get("src"))
        
        if not img_url:
            og_img = soup.select_one('meta[property="og:image"]')
            if og_img:
                img_url = og_img.get("content")

        print(f"Imagen final detectada: {img_url or 'NINGUNA'}")

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

    try:
        await client.send_message(target_channel, amazon_link)
    except Exception as e:
        pass

    asin = resolve_amazon_link(amazon_link)
    if not asin:
        return
    
    # PEQUEÑA PAUSA ANTI-BOT
    await asyncio.sleep(2)
    
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

    if product["image"]:
        try:
            resp = requests.get(product["image"], headers=get_random_headers(), timeout=15)
            content_type = resp.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                raise ValueError("No es una imagen")
            
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            
            max_size = (1280, 1280)
            try:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            except AttributeError:
                try:
                    img.thumbnail(max_size, Image.LANCZOS)
                except AttributeError:
                    img.thumbnail(max_size, Image.BICUBIC)

            img = ImageOps.expand(img, border=10, fill=(255, 165, 0))

            bio = BytesIO()
            bio.name = "product.jpg"
            img.save(bio, "JPEG", quality=95)
            bio.seek(0)

            await client.send_file(target_channel, bio, caption=message, parse_mode="md")
            print("🎉 PUBLICADO CON FOTO (Canal)")
        except Exception as e:
            print(f"Error cargando foto: {e}")
            await client.send_message(target_channel, message, parse_mode="md")
    else:
        print("❌ Publicado sin foto (bloqueo/no encontrada)")
        await client.send_message(target_channel, message, parse_mode="md")

# ==============================
# PROCESAR ENLACES PEGADOS
# ==============================
async def process_target_message(event):
    text = event.raw_text.strip()
    if not re.match(r'^https?://\S+$', text):
        return

    asin = resolve_amazon_link(text)
    if not asin:
        return

    await event.delete()
    
    # PEQUEÑA PAUSA ANTI-BOT
    await asyncio.sleep(2)
    
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

    if product["image"]:
        try:
            resp = requests.get(product["image"], headers=get_random_headers(), timeout=15)
            content_type = resp.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                raise ValueError("No es una imagen")
            
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            
            max_size = (1280, 1280)
            try:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            except AttributeError:
                try:
                    img.thumbnail(max_size, Image.LANCZOS)
                except AttributeError:
                    img.thumbnail(max_size, Image.BICUBIC)
            
            img = ImageOps.expand(img, border=10, fill=(255, 165, 0))
            bio = BytesIO()
            bio.name = "product.jpg"
            img.save(bio, "JPEG", quality=95)
            bio.seek(0)
            await client.send_file(target_channel, bio, caption=message, parse_mode="md")
            print("🎉 Paste con foto OK")
        except Exception as e:
            print(f"Error paste foto: {e}")
            await client.send_message(target_channel, message, parse_mode="md")
    else:
        await client.send_message(target_channel, message, parse_mode="md")

# ==============================
# MAIN
# ==============================
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 BOT CHOLLOS v2.3 (Anti-Bot) ACTIVADO ✅")
    print(f"✅ @chollosdeluxe → @solochollos10")

    @client.on(events.NewMessage(chats=source_channel))
    async def handler_source(event):
        await process_source_message(event)

    @client.on(events.NewMessage(chats=target_channel))
    async def handler_target(event):
        await process_target_message(event)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
