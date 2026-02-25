import os
import re
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
import asyncio
import time
import random

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

# ANTI-LOOP
procesados = set()
user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

client = TelegramClient("session_chollos", api_id, api_hash).start(bot_token=bot_token)

def resolve_amzn(url):
    print(f"🔍 Resolviendo: {url}")
    try:
        r = requests.get(url, allow_redirects=True, timeout=10)
        return r.url
    except:
        return url

def get_asin_from_url(url):
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    if m: 
        print(f"✅ ASIN: {m.group(1)}")
        return m.group(1)
    print(f"❌ No ASIN")
    return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

def scrape_amazon(amazon_url):
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0"
    }
    
    try:
        r = requests.get(amazon_url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # TÍTULO - Múltiples selectores 2026
        title = "Producto Amazon"
        for selector in [
            "h1#title span",
            "#productTitle",
            "h1.a-size-large",
            ".a-size-base-plus",
            "h1 span:not([class])"
        ]:
            elem = soup.select_one(selector)
            if elem:
                title = elem.get_text(strip=True)[:100]
                break
        
        # PRECIO - Selectores actualizados
        price = "Precio no disponible"
        for selector in [
            ".a-price-whole",
            "span[data-csa-price]",
            ".a-price span",
            ".celwidget .a-price-whole"
        ]:
            elems = soup.select(selector)
            for elem in elems[:3]:  # Primeros 3 resultados
                text = elem.get_text(strip=True)
                if re.search(r'[\d,]+\.?\d*', text):
                    price = text
                    break
            if price != "Precio no disponible":
                break
        
        # IMAGEN PRINCIPAL
        img_url = None
        for selector in [
            "#landingImage",
            "#main-image-container img",
            ".imgTagWrapper img",
            '[data-a-image-primary]'
        ]:
            elem = soup.select_one(selector)
            if elem and elem.get("src"):
                img_url = elem["src"]
                break
        
        # PVP (precio anterior)
        old_price = None
        for selector in [
            ".a-text-price span",
            ".a-price.a-text-price",
            ".basisPrice"
        ]:
            elem = soup.select_one(selector)
            if elem:
                old_price = elem.get_text(strip=True)
                break
        
        print(f"📦 '{title[:40]}...' | 💰 {price} | 🖼️ {img_url[:50] if img_url else 'No'}")
        return title, price, old_price, img_url
        
    except Exception as e:
        print(f"❌ Scraping falló: {str(e)[:50]}")
        return "Producto Amazon", "Consulta precio", None, None

@client.on(events.NewMessage(chats=target_channel))
async def tu_canal_handler(event):
    # ANTI-LOOP
    if event.message.id in procesados:
        return
        
    text = (event.raw_text or "").lower()
    urls = re.findall(r"https?://\S+", event.raw_text or "")
    amzn_links = [u for u in urls if any(x in u.lower() for x in ["amzn.to", "amazon.es", "amazon.com"])]
    
    if not amzn_links:
        return
        
    print(f"🔗 Detectado: {amzn_links[0]}")
    
    # ANTI-SPAM
    procesados.add(event.message.id)
    await asyncio.sleep(2)
    
    # BORRAR
    try:
        await event.delete()
        print("🗑️ BORRADO")
    except:
        pass
    
    # PROCESAR
    short_url = amzn_links[0]
    try:
        final_url = resolve_amzn(short_url)
        asin = get_asin_from_url(final_url)
        if not asin:
            await client.send_message(target_channel, "❌ Enlace inválido")
            return
        
        affiliate_url = build_affiliate_url(asin)
        title, price, old_price, img_url = scrape_amazon(final_url)
        
        # OFERTA FORMATO PROFESIONAL
        oferta = f"""🔥 **OFERTA FLASH** 🔥

**{title}**
✨ **{price}**
"""
        if old_price and old_price != price:
            oferta += f"▫️ ~~{old_price}~~\n"
        
        oferta += f"\n🔰 [{title[:30]}...]({affiliate_url})\n\n"
        oferta += f"👻 solochollos.com"
        
        # PUBLICAR
        if img_url:
            try:
                headers = {"User-Agent": random.choice(user_agents)}
                img_data = requests.get(img_url, headers=headers, timeout=12).content
                await client.send_file(target_channel, img_data, caption=oferta, parse_mode='md')
                print("✅ OFERTA CON FOTO ✓")
            except:
                await client.send_message(target_channel, oferta, parse_mode='md')
                print("✅ OFERTA SIN FOTO ✓")
        else:
            await client.send_message(target_channel, oferta, parse_mode='md')
            print("✅ OFERTA PUBLICADA ✓")
        
    except Exception as e:
        print(f"💥 Error: {e}")
        await client.send_message(target_channel, "💥 Error procesando oferta")
    
    # LIMPIEZA
    if len(procesados) > 200:
        procesados.clear()

print("🤖 Bot chollos v3.0 - ANTI-BLOQUEO AMAZON")
print("✅ Headers rotativos + 20+ selectores")
print("✅ Detecta amzn.to + amazon.es/com")
client.run_until_disconnected()
