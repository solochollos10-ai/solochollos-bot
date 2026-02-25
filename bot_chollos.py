import os
import re
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
from io import BytesIO

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

target_channel = "@solochollos10"
source_channel = "@chollosdeluxe"
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

client = TelegramClient("session_chollos", api_id, api_hash).start(bot_token=bot_token)

def resolve_amzn(url):
    """Resuelve amzn.to → Amazon real"""
    print(f"🔍 Resolviendo: {url}")
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        r = session.get(url, allow_redirects=True, timeout=15)
        print(f"✅ URL final: {r.url}")
        return r.url
    except Exception as e:
        print(f"❌ Error resolviendo: {e}")
        return None

def extract_asin(url):
    """Extrae ASIN de cualquier URL Amazon"""
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'ASIN: ([A-Z0-9]{10})',
        r'B0[A-Z0-9]{9}'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            asin = match.group(1)
            print(f"✅ ASIN: {asin}")
            return asin
    print(f"❌ No ASIN en: {url}")
    return None

def build_affiliate_url(asin):
    """Crea tu enlace de afiliado"""
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

def get_product_details(url):
    """Scraping AVANZADO Amazon 2026 - Múltiples selectores"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="122", "Google Chrome";v="122"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    try:
        print(f"🕵️ Scraping: {url}")
        r = session.get(url, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 🎯 TÍTULO - 15+ selectores Amazon 2026
        title_selectors = [
            'h1#title span',
            'h1.a-size-large.a-spacing-none',
            '#productTitle',
            'h1 span.a-size-large',
            '.a-size-base-plus',
            'h1[class*="title"] span',
            '.product-title span'
        ]
        title = "Producto Amazon"
        for selector in title_selectors:
            elem = soup.select_one(selector)
            if elem and elem.get_text(strip=True):
                title = elem.get_text(strip=True)[:140]
                print(f"📦 Título OK: {title[:50]}...")
                break
        
        # 💰 PRECIO ACTUAL - Múltiples formatos
        price_selectors = [
            '.a-price span.a-offscreen',
            '.a-price-whole',
            '[data-a-price]',
            '.a-price span',
            '.priceblock_dealprice',
            '.a-color-price'
        ]
        price_current = "Precio no disponible"
        for selector in price_selectors:
            elem = soup.select_one(selector)
            if elem and elem.get_text(strip=True):
                price_text = elem.get_text(strip=True).replace('€', '€ ').strip()
                if any(char.isdigit() for char in price_text):
                    price_current = price_text
                    print(f"💰 Precio: {price_current}")
                    break
        
        # 💸 PVP Anterior
        old_price_selectors = [
            '.a-text-price del',
            '.a-price.a-text-price del span',
            '[class*="list-price"]',
            '.a-color-secondary'
        ]
        old_price = None
        for selector in old_price_selectors:
            elem = soup.select_one(selector)
            if elem:
                old_price = elem.get_text(strip=True)
                print(f"💸 PVP anterior: {old_price}")
                break
        
        # 📸 IMAGEN PRINCIPAL - Prioridad alta calidad
        img_selectors = [
            '#landingImage',
            '#imgTagWrapperId img',
            'img[data-a-image-primary]',
            '.a-dynamic-image',
            'img[src*="media-amazon.com"]'
        ]
        img_url = None
        
        for selector in img_selectors:
            img_elem = soup.select_one(selector)
            if img_elem:
                img_src = (img_elem.get('data-old-hires') or 
                          img_elem.get('data-a-dynamic-image') or 
                          img_elem.get('src'))
                if img_src:
                    # Buscar imagen grande
                    if '._SL1500_' in img_src or '._AC_SL1500_' in img_src:
                        img_url = img_src
                        break
                    img_url = img_src
                    break
        
        # Buscar en data-a-dynamic-image (JSON con imágenes)
        dynamic_img = soup.select_one('[data-a-dynamic-image]')
        if dynamic_img and not img_url:
            img_data = dynamic_img.get('data-a-dynamic-image', '{}')
            import json
            try:
                images = json.loads(img_data)
                if images:
                    best_img = max(images.keys(), key=lambda x: int(x.split('_')[1]))
                    img_url = images[best_img]
            except:
                pass
        
        # % DESCUENTO
        discount_selectors = [
            '.savingsPercentage',
            '[class*="saving"]',
            '.a-color-price'
        ]
        discount = None
        for selector in discount_selectors:
            elem = soup.select_one(selector)
            if elem and '%' in elem.get_text():
                discount = elem.get_text(strip=True)
                print(f"🆙 Descuento: {discount}")
                break
        
        print(f"📸 Imagen final: {img_url[:70]}..." if img_url else "❌ Sin imagen")
        return {
            'title': title,
            'price_current': price_current,
            'old_price': old_price,
            'discount': discount,
            'img_url': img_url
        }
    except Exception as e:
        print(f"💥 Error scraping: {e}")
        return {
            'title': "Error al cargar producto",
            'price_current': "Error",
            'old_price': None,
            'discount': None,
            'img_url': None
        }

async def process_amazon_link(event, is_self_post=True):
    """Procesa UN enlace Amazon → oferta completa"""
    text = event.raw_text or ""
    
    # 🎯 SOLO enlaces ORIGINALES Amazon (evita bucle)
    amazon_urls = [u for u in re.findall(r"(https?://\S+)", text) 
                   if any(x in u.lower() for x in ['amzn.to', 'amazon.es']) 
                   and affiliate_tag not in u]  # ← CLAVE: evita tu propio enlace
    
    if not amazon_urls:
        return
        
    original_url = amazon_urls[0]
    print(f"🔗 Procesando ORIGINAL: {original_url}")
    
    # 🗑️ BORRAR mensaje original
    try:
        await event.delete()
        print("🗑️ Mensaje original BORRADO")
    except:
        print("⚠️ Sin permisos para borrar")
    
    # 🔍 RESOLVER + DATOS
    final_url = resolve_amzn(original_url)
    if not final_url:
        await client.send_message(target_channel, "❌ Error resolviendo Amazon")
        return
    
    asin = extract_asin(final_url)
    if not asin:
        await client.send_message(target_channel, "❌ Producto no válido")
        return
    
    affiliate_url = build_affiliate_url(asin)
    product_data = get_product_details(final_url)
    
    # 📝 OFERTA LIMPIA (SIN solochollos.com)
    oferta = f"""🔥 **OFERTA AMAZON** 🔥

**{product_data['title']}**
"""
    
    if product_data['discount']:
        oferta += f"{product_data['discount']} "
    oferta += f"**{product_data['price_current']}**"
    
    if product_data['old_price']:
        oferta += f"\n**Precio anterior**: {product_data['old_price']}"
    
    oferta += f"\n\n🔰 {affiliate_url}"
    
    # 📤 PUBLICAR CON FOTO FIJA
    try:
        if product_data['img_url']:
            print("📸 Descargando imagen HD...")
            img_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.amazon.es/'
            }
            img_response = requests.get(product_data['img_url'], headers=img_headers, timeout=25, stream=True)
            
            if img_response.status_code == 200 and len(img_response.content) > 5000:
                # ✅ FIJO: BytesIO para foto correcta
                img_file = BytesIO(img_response.content)
                img_file.name = "product.jpg"  # ← NOMBRE FIJO
                
                await client.send_file(
                    target_channel, 
                    file=img_file,
                    caption=oferta
                )
                print("✅ ✅ ✅ FOTO HD PUBLICADA")
            else:
                print(f"❌ Imagen falló: {len(img_response.content)} bytes")
                await client.send_message(target_channel, oferta)
        else:
            await client.send_message(target_channel, oferta)
            print("✅ Sin foto disponible")
            
    except Exception as e:
        print(f"💥 Error publicación: {e}")
        await client.send_message(target_channel, oferta)

# 🎯 TU CANAL: enlaces → ofertas
@client.on(events.NewMessage(chats=target_channel))
async def tu_canal_handler(event):
    print(f"📨 @solochollos10: {event.raw_text[:60]}...")
    await process_amazon_link(event, is_self_post=True)

# 🔄 @chollosdeluxe: copia ofertas
@client.on(events.NewMessage(chats=source_channel))
async def chollosdeluxe_handler(event):
    print(f"📨 @chollosdeluxe nuevo")
    await process_amazon_link(event, is_self_post=False)

print("🤖 Bot_chollos v3.0 - FIXED")
print("✅ Foto HD (BytesIO + nombre)")
print("✅ Sin solochollos.com") 
print("✅ Anti-bucle (solo enlaces ORIGINALES)")
print("✅ Headers Amazon 2026")
client.run_until_disconnected()
