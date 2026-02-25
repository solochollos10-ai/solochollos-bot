import os
import re
import requests
from bs4 import BeautifulSoup
import io
from telethon import TelegramClient, events

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

target_channel = "@solochollos10"
source_channel = "@chollosdeluxe"
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

client = TelegramClient("session_chollos", api_id, api_hash).start(bot_token=bot_token)

def resolve_amzn(url):
    print(f"🔍 Resolviendo: {url}")
    try:
        r = requests.get(url, allow_redirects=True, timeout=15)
        final_url = r.url
        print(f"✅ URL final: {final_url}")
        return final_url
    except Exception as e:
        print(f"❌ Error resolviendo: {e}")
        return None

def extract_asin(url):
    match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if match:
        asin = match.group(1)
        print(f"✅ ASIN: {asin}")
        return asin
    print(f"❌ Sin ASIN: {url}")
    return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

def get_product_details(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    try:
        print(f"🕵️ Scraping: {url}")
        r = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # TÍTULO - Múltiples selectores
        title_selectors = [
            '#productTitle',
            'h1.a-size-large > span',
            'span#productTitle',
            'h1 span.a-size-large',
            'h1.a-heading.a-text-normal span'
        ]
        title = "Producto Amazon"
        for selector in title_selectors:
            elem = soup.select_one(selector)
            if elem:
                title = elem.get_text(strip=True)[:120]
                print(f"📦 Título: {title}")
                break
        
        # PRECIO ACTUAL
        price_selectors = [
            '.a-price .a-offscreen',
            'span.a-price-whole',
            '.a-price-symbol + .a-price-whole',
            '[data-a-price="true"]',
            '.a-price span'
        ]
        price_current = "Precio no disponible"
        for selector in price_selectors:
            elem = soup.select_one(selector)
            if elem:
                price_current = elem.get_text(strip=True)
                print(f"💰 Precio: {price_current}")
                break
        
        # PVP ANTERIOR
        old_price_selectors = [
            '.a-price.a-text-price del',
            '.a-text-price del span.a-offscreen',
            'del.a-price'
        ]
        old_price = None
        for selector in old_price_selectors:
            elem = soup.select_one(selector)
            if elem:
                old_price = elem.get_text(strip=True)
                print(f"💸 PVP anterior: {old_price}")
                break
        
        # DESCUENTO %
        discount_selectors = [
            '.savingsPercentage',
            '.a-color-price',
            '[class*="savings"]'
        ]
        discount = None
        for selector in discount_selectors:
            elem = soup.select_one(selector)
            if elem:
                discount = elem.get_text(strip=True)
                print(f"🆙 Descuento: {discount}")
                break
        
        # IMAGEN PRINCIPAL - Prioridad SL1500_
        img_selectors = [
            '#landingImage',
            'img[data-a-dynamic-image]',
            '#imgTagWrapperId img',
            '.a-dynamic-image'
        ]
        img_url = None
        for selector in img_selectors:
            img_elem = soup.select_one(selector)
            if img_elem:
                img_src = (img_elem.get('src') or 
                          img_elem.get('data-old-hires') or 
                          img_elem.get('data-a-dynamic-image'))
                if img_src:
                    # Buscar imagen grande _SL1500_
                    if '_SL1500_' in img_src:
                        img_url = img_src
                    elif '_SX' in img_src or '_SY' in img_src:
                        # Extraer dimensiones y hacer grande
                        img_url = img_src.replace('_SX300_', '_SL1500_').replace('_SY300_', '_SL1500_')
                    else:
                        img_url = img_src
                    print(f"📸 Imagen: {img_url}")
                    break
        
        return {
            'title': title,
            'price_current': price_current,
            'old_price': old_price,
            'discount': discount,
            'img_url': img_url
        }
    except Exception as e:
        print(f"💥 Error scraping completo: {e}")
        return {
            'title': "Error cargando producto",
            'price_current': "Error",
            'old_price': None,
            'discount': None,
            'img_url': None
        }

async def process_amazon_link(event):
    text = event.raw_text or ""
    urls = re.findall(r"(https?://\S+)", text)
    amazon_urls = [u for u in urls if any(x in u.lower() for x in ['amzn.to', 'amazon.es', 'amazon.com'])]
    
    if not amazon_urls:
        return
    
    print(f"🔗 Amazon detectado: {amazon_urls[0]}")
    
    # BORRAR mensaje original
    try:
        await event.delete()
        print("🗑️ Mensaje eliminado")
    except Exception as e:
        print(f"⚠️ No pudo borrar: {e}")
    
    short_url = amazon_urls[0]
    
    # RESOLVER URL
    final_url = resolve_amzn(short_url)
    if not final_url:
        await client.send_message(target_channel, "❌ Error resolviendo Amazon")
        return
    
    asin = extract_asin(final_url)
    if not asin:
        await client.send_message(target_channel, "❌ Enlace no válido")
        return
    
    # DATOS + AFILIADO
    affiliate_url = build_affiliate_url(asin)
    product_data = get_product_details(final_url)
    
    # FORMATO OFERTA FINAL
    oferta = f"""🔥 **OFERTA AMAZON** 🔥

**{product_data['title']}**
"""
    
    if product_data['discount']:
        oferta += f"{product_data['discount']} "
    oferta += f"**{product_data['price_current']}**"
    
    if product_data['old_price']:
        oferta += f"\n**Precio anterior**: {product_data['old_price']}"
    
    oferta += f"\n\n🔰 {affiliate_url}"
    
    # PUBLICAR CON FOTO FIJA
    try:
        if product_data['img_url']:
            print("📸 Procesando imagen...")
            # FIX: BytesIO con nombre de archivo
            img_response = requests.get(product_data['img_url'], timeout=20, stream=True)
            if img_response.status_code == 200:
                # Crear BytesIO con NOMBRE ARCHIVO para que NO salga "unnamed"
                img_bytes = io.BytesIO(img_response.content)
                img_bytes.name = "producto.jpg"  # ← FIX CLAVE
                
                await client.send_file(
                    target_channel,
                    file=img_bytes,
                    caption=oferta
                )
                print("✅ ✅ OFERTA CON FOTO incrustada")
            else:
                print("❌ Error descargando imagen")
                await client.send_message(target_channel, oferta)
        else:
            await client.send_message(target_channel, oferta)
            print("✅ Oferta texto simple")
    except Exception as e:
        print(f"💥 Error enviando: {e}")
        await client.send_message(target_channel, oferta)

# HANDLER TU CANAL (borra enlaces → ofertas)
@client.on(events.NewMessage(chats=target_channel))
async def tu_canal_handler(event):
    print(f"📨 @solochollos10: {event.raw_text[:60]}...")
    await process_amazon_link(event)

# HANDLER CHOLLOSDELUXE (copia ofertas)
@client.on(events.NewMessage(chats=source_channel))
async def chollosdeluxe_handler(event):
    print(f"📨 @chollosdeluxe nuevo")
    await process_amazon_link(event)

print("🤖 Bot_chollos v3.0 FIXED")
print("✅ Foto incrustada (no unnamed)")
print("✅ Sin solochollos.com")
print("✅ Scraping mejorado")
client.run_until_disconnected()
