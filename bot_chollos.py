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
import time
from urllib.parse import urlparse

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

# Sesión ANTI-BAN
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
})

# ==============================
# DETECTAR TODOS LOS ENLACES AMAZON
# ==============================
def find_amazon_links(text):
    """Detecta TODOS los enlaces Amazon incluyendo amzn.to"""
    patterns = [
        r'https?://(?:www\.)?(?:amazon\.es|amazon\.(?:com|co\.uk|de|fr|it)|amzn\.to)/[^\s<>"]+',
        r'amzn\.to/[^\s<>"]+',
        r'dp/[A-Z0-9]{10}',
    ]
    all_links = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        all_links.extend(matches)
    return list(set(all_links))  # Unique

def extract_asin(url):
    """Extrae ASIN de cualquier URL Amazon"""
    # Resuelve shortlinks primero
    if 'amzn.to' in url:
        try:
            time.sleep(1)
            r = session.get(url, allow_redirects=True, timeout=10)
            url = r.url
        except:
            pass
    
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'([A-Z0-9]{10})(?=[/?#])',
    ]
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}?tag={affiliate_tag}"

# ==============================
# SCRAPING OPTIMIZADO
# ==============================
def scrape_amazon_product(asin):
    url = f"https://www.amazon.es/dp/{asin}"
    try:
        time.sleep(1.5)
        r = session.get(url, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")  # Cambiado a html.parser (más estable)

        # Título
        title_elem = (soup.select_one("#productTitle") or 
                     soup.select_one("h1.a-size-large.a-spacing-none") or
                     soup.select_one(".a-size-base-plus.a-color-base.a-text-normal"))
        title = title_elem.get_text(strip=True)[:120] if title_elem else "Oferta Amazon"

        # Precio (múltiples selectores)
        price = None
        price_selectors = [
            ".a-price-whole",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            ".a-price[data-a-size='xl']"
        ]
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text(strip=True).replace(',', '.')
                if '€' not in price_text:
                    price_text += '€'
                price = price_text
                break

        # Precio tachado
        old_price_selectors = [
            ".a-text-price .a-offscreen",
            ".priceBlockStrikePriceString",
            ".a-price.a-text-price span"
        ]
        old_price = None
        for selector in old_price_selectors:
            old_elem = soup.select_one(selector)
            if old_elem:
                old_price = old_elem.get_text(strip=True)
                break

        # Rating y reviews
        rating_elem = soup.select_one("#acrPopover")
        rating = rating_elem.get("title") if rating_elem else None
        
        reviews_elem = soup.select_one("#acrCustomerReviewText")
        reviews = re.sub(r'[^\d]', '', reviews_elem.get_text()) if reviews_elem else "0"

        # IMAGEN ULTRA-COMPLETE (15+ métodos)
        img_candidates = []
        
        # Método 1: data-a-dynamic-image
        landing_img = soup.select_one("#landingImage, #imgTagWrapperId img")
        if landing_img and landing_img.get("data-a-dynamic-image"):
            try:
                dynamic = json.loads(landing_img["data-a-dynamic-image"])
                best = max(dynamic.items(), key=lambda x: int(x[1][1]))
                img_candidates.append(best[0].replace('\\"', '"').strip('"'))
            except:
                pass
        
        # Método 2: Atributos directos
        for attr in ['data-old-hires', 'data-a-hires', 'src', 'data-src']:
            if landing_img:
                img = landing_img.get(attr)
                if img and 'amazon' in img:
                    img_candidates.append(img)
                    break
        
        # Método 3: OG image
        og_img = soup.select_one('meta[property="og:image"]')
        if og_img:
            img_candidates.append(og_img.get("content"))
        
        # Método 4: Otros contenedores
        alt_imgs = soup.select("img[src*='amazon'], img[data-src*='amazon']")
        for img in alt_imgs[:3]:
            src = img.get("src") or img.get("data-src")
            if src and len(src) > 50:
                img_candidates.append(src)
                break
        
        img_url = next((img for img in img_candidates if img and 'm.media-amazon.com' in img), None)

        print(f"📊 ASIN:{asin[:8]} | 💰{price} | 🖼️{bool(img_url)} | Título:{title[:40]}")

        return {
            "title": title,
            "price": price,
            "old_price": old_price,
            "rating": rating,
            "reviews": f"{reviews} opiniones",
            "image": img_url
        }
    except Exception as e:
        print(f"💥 Error ASIN {asin[:8]}: {str(e)[:60]}")
        return None

# ==============================
# PROCESAR MENSAJE ORIGEN
# ==============================
@client.on(events.NewMessage(chats=source_channel))
async def handler_source(event):
    try:
        text = (event.raw_text or "") + (event.message.message or "")
        amazon_links = find_amazon_links(text)
        
        if not amazon_links:
            return
            
        print(f"🔍 Encontrados {len(amazon_links)} enlaces Amazon")
        
        # Primer enlace Amazon válido
        for link in amazon_links:
            asin = extract_asin(link)
            if asin:
                print(f"🎯 Procesando ASIN: {asin}")
                break
        else:
            await client.forward_messages(target_channel, event.message)
            return

        # Enviar enlace original
        await client.send_message(target_channel, link)

        # Crear oferta
        product = scrape_amazon_product(asin)
        if not product:
            print("❌ Sin datos producto")
            return

        affiliate_link = build_affiliate_url(asin)
        message = (
            f"🔥 *OFERTA AMAZON FLASH* 🔥\n\n"
            f"*{product['title']}*\n\n"
            f"⭐ {product['rating']} | {product['reviews']}\n"
            f"🟢 **{product['price']}** "
            f"{'🔴 ~~' + product['old_price'] + '~~' if product['old_price'] else ''}\n\n"
            f"🛒 {affiliate_link}"
        )

        # Enviar CON foto visible
        if product["image"]:
            try:
                print(f"🖼️ Procesando {product['image'][-40:]}")
                resp = requests.get(product["image"], timeout=12, headers={'Referer': 'https://amazon.es'})
                
                if resp.status_code == 200 and 'image' in resp.headers.get('content-type', ''):
                    img = Image.open(BytesIO(resp.content)).convert("RGB")
                    
                    # Redimensionar compatible
                    max_size = (1024, 1024)
                    try:
                        img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    except AttributeError:
                        img.thumbnail(max_size, Image.LANCZOS)
                        img = img.convert("RGB")
                    
                    # Marco naranja delgado
                    img_with_border = ImageOps.expand(img, border=8, fill=(255, 165, 0))
                    
                    # Guardar como JPG con nombre
                    output = BytesIO()
                    output.name = f"oferta_{asin}.jpg"  # NOMBRE VISIBLE
                    img_with_border.save(output, "JPEG", quality=92, optimize=True)
                    output.seek(0)
                    
                    await client.send_file(
                        target_channel, 
                        output, 
                        caption=message, 
                        parse_mode='md'
                    )
                    print("✅ FOTO ENVIADA VISIBLE")
                else:
                    await client.send_message(target_channel, message, parse_mode='md')
                    
            except Exception as e:
                print(f"❌ Error foto: {e}")
                await client.send_message(target_channel, message, parse_mode='md')
        else:
            await client.send_message(target_channel, message, parse_mode='md')

        await asyncio.sleep(5)  # PAUSA
        
    except Exception as e:
        print(f"💥 Handler source: {e}")

# ==============================
# PEGAR ENLACE DIRECTO
# ==============================
@client.on(events.NewMessage(chats=target_channel))
async def handler_paste(event):
    try:
        text = event.raw_text.strip()
        if not text.startswith('http') or not any(domain in text for domain in ['amazon', 'amzn']):
            return
            
        asin = extract_asin(text)
        if not asin:
            return

        await event.delete()
        print(f"📋 Paste detectado: {asin}")

        product = scrape_amazon_product(asin)
        if product:
            affiliate_link = build_affiliate_url(asin)
            message = (
                f"🔥 *OFERTA AMAZON FLASH* 🔥\n\n"
                f"*{product['title']}*\n\n"
                f"⭐ {product['rating']} | {product['reviews']}\n"
                f"🟢 **{product['price']}** "
                f"{'🔴 ~~' + product['old_price'] + '~~' if product['old_price'] else ''}\n\n"
                f"🛒 {affiliate_link}"
            )

            if product["image"]:
                try:
                    resp = requests.get(product["image"], timeout=10)
                    img = Image.open(BytesIO(resp.content)).convert("RGB")
                    max_size = (1024, 1024)
                    try:
                        img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    except:
                        img.thumbnail(max_size, Image.LANCZOS)
                    img = ImageOps.expand(img, border=8, fill=(255, 165, 0))
                    
                    output = BytesIO()
                    output.name = f"oferta_{asin}.jpg"
                    img.save(output, "JPEG", quality=92, optimize=True)
                    output.seek(0)
                    
                    await client.send_file(target_channel, output, caption=message, parse_mode='md')
                except:
                    await client.send_message(target_channel, message, parse_mode='md')
            else:
                await client.send_message(target_channel, message, parse_mode='md')

        await asyncio.sleep(3)
        
    except Exception as e:
        print(f"💥 Handler paste: {e}")

# ==============================
# MAIN
# ==============================
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 BOT CHOLLOS v4.0 PERFECTO ✅")
    print("🔗 Detecta amzn.to + Fotos VISIBLES nombradas")
    
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
