import os
import re
import requests
import random
import time
from bs4 import BeautifulSoup
from telethon import TelegramClient, events

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

target_channel = "@solochollos10"
source_channel = "@chollosdeluxe"
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

client = TelegramClient("session_chollos", api_id, api_hash).start(bot_token=bot_token)

def get_amazon_session():
    """Headers rotativos anti-ban"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    
    return {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    }

def resolve_amzn(url):
    """Resuelve amzn.to SIN tag de afiliado"""
    print(f"🔍 Resolviendo: {url}")
    try:
        # LIMPIAR tag antes de resolver
        clean_url = re.sub(r'\?tag=[^&\s]+', '', url)
        r = requests.get(clean_url, allow_redirects=True, timeout=15, headers=get_amazon_session())
        final_url = r.url.split('?')[0]  # Quitar parámetros
        print(f"✅ URL limpia: {final_url}")
        return final_url
    except Exception as e:
        print(f"❌ Error resolviendo: {e}")
        return None

def extract_asin(url):
    match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if match:
        print(f"✅ ASIN: {match.group(1)}")
        return match.group(1)
    return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

def get_product_details(url):
    """Scraping ANTI-BLOQUEO mejorado"""
    session = requests.Session()
    session.headers.update(get_amazon_session())
    
    # Delay anti-bot
    time.sleep(random.uniform(2, 4))
    
    try:
        print(f"🕵️ Scraping: {url}")
        r = session.get(url, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 🔍 BÚSQUEDA AGRESIVA DE TÍTULO
        title = None
        title_selectors = [
            '#productTitle',
            'h1 span.a-size-large',
            'h1.a-size-large',
            '.a-hero-title span',
            'span#productTitle'
        ]
        for selector in title_selectors:
            elem = soup.select_one(selector)
            if elem and elem.get_text(strip=True):
                title = elem.get_text(strip=True).strip()[:150]
                print(f"✅ TÍTULO: {title[:60]}...")
                break
        
        # 💰 PRECIO - Múltiples métodos
        price = None
        price_selectors = [
            '.a-price span.a-offscreen',
            '#priceblock_ourprice',
            '#priceblock_dealprice',
            '.a-price-whole',
            'span.a-price span',
            '.priceblock_dealprice'
        ]
        for selector in price_selectors:
            elem = soup.select_one(selector)
            if elem and elem.get_text(strip=True):
                price = elem.get_text(strip=True).strip()
                print(f"✅ PRECIO: {price}")
                break
        
        # 💸 PVP Anterior
        old_price = None
        old_selectors = [
            '.a-text-price del',
            '.a-price.a-text-price del span',
            '#listPrice'
        ]
        for selector in old_selectors:
            elem = soup.select_one(selector)
            if elem:
                old_price = elem.get_text(strip=True)
                print(f"✅ PVP Anterior: {old_price}")
                break
        
        # 📸 IMAGEN - Prioridad SL1500
        img_url = None
        img_selectors = [
            '#landingImage',
            '#imgTagWrapperId img',
            'img[data-a-image-primary]',
            '.a-dynamic-image + img'
        ]
        for selector in img_selectors:
            img_elem = soup.select_one(selector)
            if img_elem:
                img_src = img_elem.get('src') or img_elem.get('data-old-hires') or img_elem.get('data-a-dynamic-image')
                if img_src:
                    # Buscar imagen grande
                    if '_SL1500_' in img_src:
                        img_url = img_src
                    elif '_SL' in img_src:
                        img_url = img_src
                    else:
                        img_url = img_src
                    print(f"✅ IMAGEN: {img_url[-50:]}")
                    break
        
        return {
            'title': title or "Producto Amazon",
            'price': price or "Precio no disponible",
            'old_price': old_price,
            'img_url': img_url
        }
        
    except Exception as e:
        print(f"💥 Scraping falló: {e}")
        return {
            'title': "Producto Amazon", 
            'price': "Consulta precio",
            'old_price': None,
            'img_url': None
        }

async def process_amazon_link(event):
    text = event.raw_text or ""
    urls = re.findall(r"(https?://\S+)", text)
    amazon_urls = [u for u in urls if any(x in u.lower() for x in ['amzn.to', 'amazon.es', 'amazon.com'])]
    
    if not amazon_urls:
        return
        
    print(f"🔗 Amazon: {amazon_urls[0]}")
    
    # BORRAR mensaje
    try:
        await event.delete()
        print("🗑️ Mensaje borrado")
    except:
        pass
    
    # PROCESAR
    final_url = resolve_amzn(amazon_urls[0])
    if not final_url:
        await client.send_message(target_channel, "❌ Error con enlace Amazon")
        return
        
    asin = extract_asin(final_url)
    if not asin:
        await client.send_message(target_channel, "❌ Producto no válido")
        return
    
    affiliate_url = build_affiliate_url(asin)
    product = get_product_details(final_url)
    
    # FORMATO OFERTA
    oferta = f"""🔥 **OFERTA AMAZON** 🔥

**{product['title']}**
**{product['price']}**"""
    
    if product['old_price']:
        oferta += f"\n**Antes**: {product['old_price']}"
    
    oferta += f"""

🔰 {affiliate_url}

👻 solochollos.com"""
    
    # PUBLICAR
    try:
        if product['img_url']:
            print("📸 Subiendo foto...")
            img_resp = requests.get(product['img_url'], timeout=20, headers=get_amazon_session())
            await client.send_file(target_channel, img_resp.content, caption=oferta)
            print("✅ OFERTA con FOTO")
        else:
            await client.send_message(target_channel, oferta)
            print("✅ OFERTA sin foto")
    except:
        await client.send_message(target_channel, oferta)
        print("✅ Fallback texto")

@client.on(events.NewMessage(chats=target_channel))
async def handler(event):
    print(f"📨 @{target_channel}: {event.raw_text[:60]}")
    await process_amazon_link(event)

print("🤖 Bot anti-ban ULTIMATE")
print("✅ Headers rotativos")
print("✅ Delays anti-bot") 
print("✅ Limpieza de tags")
client.run_until_disconnected()
