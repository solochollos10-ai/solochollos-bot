import os
import re
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
import asyncio

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

target_channel = "@solochollos10"
source_channel = "@chollosdeluxe"
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

client = TelegramClient("session_chollos", api_id, api_hash).start(bot_token=bot_token)

def resolve_amzn(url):
    """Resuelve amzn.to a URL real de Amazon"""
    print(f"🔍 Resolviendo: {url}")
    try:
        r = requests.get(url, allow_redirects=True, timeout=15)
        final_url = r.url
        print(f"✅ URL final: {final_url}")
        return final_url
    except Exception as e:
        print(f"❌ Error resolviendo URL: {e}")
        return None

def extract_asin(url):
    """Extrae ASIN de URL Amazon"""
    match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if match:
        asin = match.group(1)
        print(f"✅ ASIN encontrado: {asin}")
        return asin
    print(f"❌ No se encontró ASIN en: {url}")
    return None

def build_affiliate_url(asin):
    """Construye enlace de afiliado"""
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

def get_product_details(url):
    """Extrae TODOS los datos del producto Amazon"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "es-ES,es;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }
    
    try:
        print(f"🕵️ Scraping producto: {url}")
        r = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 🎯 TÍTULO (múltiples selectores)
        title_selectors = [
            'span#productTitle',
            'h1.a-size-large span',
            'h1 span.a-size-large',
            'h1.a-heading.a-text-normal'
        ]
        title = None
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)[:120]
                break
        
        # 💰 PRECIO ACTUAL
        price_selectors = [
            'span.a-price.a-text-price span.a-offscreen',
            '.a-price span.a-offscreen',
            'span.a-price-whole',
            '.a-price-symbol + .a-price-whole',
            '[data-a-price="true"]'
        ]
        price_current = None
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                price_current = price_elem.get_text(strip=True)
                break
        
        # 💸 PVP (PRECIO ANTERIOR)
        old_price_selectors = [
            'span.a-price.a-text-price span.a-offscreen + del span',
            '.a-text-price del',
            '.a-price.a-text-price del span.a-offscreen'
        ]
        old_price = None
        for selector in old_price_selectors:
            old_elem = soup.select_one(selector)
            if old_elem:
                old_price = old_elem.get_text(strip=True)
                break
        
        # 📸 IMAGEN PRINCIPAL (prioridad alta calidad)
        img_selectors = [
            'img#landingImage',
            'img[data-a-dynamic-image]',
            '.a-dynamic-image',
            '#imgTagWrapperId img'
        ]
        img_url = None
        for selector in img_selectors:
            img_elem = soup.select_one(selector)
            if img_elem:
                img_src = img_elem.get('src') or img_elem.get('data-old-hires') or img_elem.get('data-a-dynamic-image')
                if img_src:
                    # Priorizar imagen grande _SL1500_
                    if '._SL1500_.jpg' in img_src:
                        img_url = img_src
                        break
                    img_url = img_src
                    break
        
        # % DESCUENTO
        discount_elem = soup.select_one('.savingsPercentage')
        discount = discount_elem.get_text(strip=True) if discount_elem else None
        
        print(f"📦 Título: {title[:50]}..." if title else "❌ Sin título")
        print(f"💰 Precio actual: {price_current}")
        print(f"💸 PVP anterior: {old_price}")
        print(f"📸 Imagen: {img_url[:60]}..." if img_url else "❌ Sin imagen")
        print(f"🆙 Descuento: {discount}")
        
        return {
            'title': title or "Producto Amazon",
            'price_current': price_current or "Precio no disponible",
            'old_price': old_price,
            'discount': discount,
            'img_url': img_url
        }
    except Exception as e:
        print(f"💥 Error scraping: {e}")
        return {
            'title': "Error cargando producto",
            'price_current': "Error",
            'old_price': None,
            'discount': None,
            'img_url': None
        }

async def process_amazon_link(event):
    """Procesa enlace Amazon → oferta completa"""
    text = event.raw_text or ""
    urls = re.findall(r"(https?://\S+)", text)
    amazon_urls = [u for u in urls if any(x in u.lower() for x in ['amzn.to', 'amazon.es', 'amazon.com'])]
    
    if not amazon_urls:
        return
        
    print(f"🔗 Amazon detectado: {amazon_urls[0]}")
    
    # 🗑️ BORRAR mensaje original
    try:
        await event.delete()
        print("🗑️ Mensaje original eliminado")
    except:
        print("⚠️ No se pudo borrar (sin permisos)")
    
    short_url = amazon_urls[0]
    
    # 🔍 RESOLVER + EXTRAER DATOS
    final_url = resolve_amzn(short_url)
    if not final_url:
        await client.send_message(target_channel, "❌ Error resolviendo enlace Amazon")
        return
        
    asin = extract_asin(final_url)
    if not asin:
        await client.send_message(target_channel, "❌ No se encontró producto válido")
        return
    
    # 🛒 AFILIADO + INFO
    affiliate_url = build_affiliate_url(asin)
    product_data = get_product_details(final_url)
    
    # 📝 FORMATO OFERTA (exactamente como pediste)
    oferta = f"""🔥 **OFERTA AMAZON** 🔥

**{product_data['title']}**
"""
    
    if product_data['discount']:
        oferta += f"{product_data['discount']} "
    oferta += f"**{product_data['price_current']}**"
    
    if product_data['old_price']:
        oferta += f"\n**Precio anterior**: {product_data['old_price']}"
    
    oferta += f"\n\n🔰: {affiliate_url}\n\n"
    oferta += f"👻 solochollos.com"
    
    # 📤 PUBLICAR
    try:
        if product_data['img_url']:
            print("📸 Descargando imagen...")
            img_response = requests.get(product_data['img_url'], timeout=20)
            if img_response.status_code == 200:
                await client.send_file(
                    target_channel, 
                    file=img_response.content,
                    caption=oferta
                )
                print("✅ ✅ OFERTA CON FOTO publicada")
            else:
                await client.send_message(target_channel, oferta)
                print("✅ Oferta sin foto (error imagen)")
        else:
            await client.send_message(target_channel, oferta)
            print("✅ Oferta sin foto (no encontrada)")
            
    except Exception as e:
        print(f"💥 Error publicando: {e}")
        await client.send_message(target_channel, f"💥 Error: {oferta}")

# 🎯 HANDLER PRINCIPAL: escucha TU canal
@client.on(events.NewMessage(chats=target_channel))
async def tu_canal_handler(event):
    print(f"📨 Nuevo mensaje en @solochollos10: {event.raw_text[:50]}...")
    await process_amazon_link(event)

# 🔄 HANDLER SECUNDARIO: copia de @chollosdeluxe
@client.on(events.NewMessage(chats=source_channel))
async def chollosdeluxe_handler(event):
    print(f"📨 Nuevo en @chollosdeluxe")
    await process_amazon_link(event)

print("🤖 Bot_chollos ULTIMATE v2.0")
print("✅ Detecta enlaces en @solochollos10 → Borra → Oferta completa")
print("✅ Copia ofertas de @chollosdeluxe")
print("✅ Extrae: foto, título, precios, descuento")
print("✅ Tu tag de afiliado automático")
client.run_until_disconnected()
