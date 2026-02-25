import os
import re
import requests
import json
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
import asyncio

# --- CONFIGURACIÓN ---
api_id = int(os.getenv('API_ID', 0))
api_hash = os.getenv('API_HASH', '')
bot_token = os.getenv('BOT_TOKEN', '')

target_channel = '@solochollos10'
source_channel = '@chollosdeluxe'
affiliate_tag = os.getenv('AFFILIATE_TAG', 'solochollos08-21')

client = TelegramClient('session_chollos', api_id, api_hash).start(bot_token=bot_token)

def resolve_amzn(url):
    try:
        r = requests.get(url, allow_redirects=True, timeout=15)
        return r.url
    except Exception:
        return None

def extract_asin(url):
    match = re.search(r'/dp/([A-Z0-9]{10})', url)
    return match.group(1) if match else None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

def get_product_details(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Título
        title_elem = soup.select_one('span#productTitle')
        title = title_elem.get_text(strip=True)[:120] if title_elem else "Producto Amazon"
        
        # Precios
        price_elem = soup.select_one('.a-price span.a-offscreen')
        price_current = price_elem.get_text(strip=True) if price_elem else "Consultar"
        
        old_price_elem = soup.select_one('.a-text-price span.a-offscreen')
        old_price = old_price_elem.get_text(strip=True) if old_price_elem else None
        
        # Descuento
        discount_elem = soup.select_one('.savingsPercentage')
        discount = discount_elem.get_text(strip=True) if discount_elem else None
        
        # IMAGEN (Fix para evitar 'unnamed' o archivos de 5kb)
        img_url = None
        img_elem = soup.select_one('#landingImage')
        if img_elem and img_elem.get('data-a-dynamic-image'):
            # Extrae la versión de mayor resolución del diccionario JSON
            images_dict = json.loads(img_elem.get('data-a-dynamic-image'))
            img_url = max(images_dict, key=lambda k: images_dict[k][0])
        elif img_elem:
            img_url = img_elem.get('src')

        return {
            'title': title,
            'price_current': price_current,
            'old_price': old_price,
            'discount': discount,
            'img_url': img_url
        }
    except Exception:
        return None

async def process_amazon_link(event):
    text = event.raw_text or ""
    if "🔥 OFERTA AMAZON 🔥" in text: return # Evitar bucles

    urls = re.findall(r'(https?://\S+)', text)
    amazon_urls = [u for u in urls if any(x in u.lower() for x in ['amzn.to', 'amazon.es'])]
    
    if not amazon_urls: return
        
    short_url = amazon_urls[0]
    final_url = resolve_amzn(short_url)
    if not final_url: return
    
    asin = extract_asin(final_url)
    if not asin: return
    
    # Borrar mensaje original
    try: await event.delete()
    except: pass
    
    data = get_product_details(final_url)
    if not data: return
    
    aff_url = build_affiliate_url(asin)
    
    # FORMATO SIN WEB
    oferta = f"🔥 **OFERTA AMAZON** 🔥\n\n"
    oferta += f"**{data['title']}**\n\n"
    if data['discount']: oferta += f"{data['discount']} "
    oferta += f"**{data['price_current']}**\n"
    if data['old_price']: oferta += f"**Precio anterior**: {data['old_price']}\n"
    oferta += f"\n🔰: {aff_url}"

    # ENVÍO DE FOTO INCRUSTADA
    try:
        if data['img_url']:
            # Telethon descarga y envía automáticamente desde la URL si se pasa al parámetro file
            await client.send_file(target_channel, data['img_url'], caption=oferta)
        else:
            await client.send_message(target_channel, oferta)
    except Exception:
        await client.send_message(target_channel, oferta)

@client.on(events.NewMessage(chats=[target_channel, source_channel]))
async def handler(event):
    await process_amazon_link(event)

print("🤖 Bot iniciado (v2.1) - Sin web y con fix de imagen")
client.run_until_disconnected()
