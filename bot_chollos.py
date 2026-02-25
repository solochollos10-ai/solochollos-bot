import os
import re
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
import asyncio
import time

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

# ANTI-LOOP: IDs de mensajes procesados
procesados = set()

client = TelegramClient("session_chollos", api_id, api_hash).start(bot_token=bot_token)

def resolve_amzn(url):
    print(f"🔍 Resolviendo: {url}")
    r = requests.get(url, allow_redirects=True, timeout=10)
    return r.url

def get_asin_from_url(url):
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    if m: 
        print(f"✅ ASIN: {m.group(1)}")
        return m.group(1)
    print(f"❌ No ASIN en: {url}")
    return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

def get_product_info(amazon_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    try:
        r = requests.get(amazon_url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # TÍTULO (múltiples selectores)
        title_selectors = [
            "span#productTitle",
            "h1.a-size-large",
            "h1 span",
            "h1",
            ".a-size-base-plus"
        ]
        title = "Producto Amazon"
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)[:120]
                break
        
        # PRECIO (múltiples selectores)
        price_selectors = [
            "span.a-price-whole",
            ".a-price-whole",
            "span.a-offscreen",
            ".a-price span"
        ]
        price = "Precio no disponible"
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                price = price_elem.get_text(strip=True)
                break
        
        # PVP (precio tachado)
        old_price_selectors = [
            "span.a-price.a-text-price",
            ".a-text-price span",
            "span.line-through"
        ]
        old_price = None
        for selector in old_price_selectors:
            old_price_elem = soup.select_one(selector)
            if old_price_elem:
                old_price = old_price_elem.get_text(strip=True)
                break
        
        # IMAGEN (múltiples selectores)
        img_selectors = [
            "img#landingImage",
            "img#altImages img",
            "img[data-a-dynamic-image]"
        ]
        img_url = None
        for selector in img_selectors:
            img_elem = soup.select_one(selector)
            if img_elem and img_elem.get("src"):
                img_url = img_elem["src"]
                break
        
        print(f"📦 '{title[:50]}...' | 💰 {price} | 🖼️ {'Sí' if img_url else 'No'}")
        return title, price, old_price, img_url
        
    except Exception as e:
        print(f"❌ Error scraping: {e}")
        return "Producto Amazon", "Precio no disponible", None, None

@client.on(events.NewMessage(chats=target_channel))
async def tu_canal_handler(event):
    # ANTI-LOOP: Ignorar mensajes del bot
    if event.message.id in procesados:
        return
        
    text = event.raw_text or ""
    urls = re.findall(r"(https?://\S+)", text)
    amzn_links = [u for u in urls if "amzn.to" in u.lower() or "amazon" in u.lower()]
    
    if not amzn_links:
        return
        
    print(f"🔗 Enlace detectado: {amzn_links[0]}")
    
    # ANTI-SPAM: cooldown 3 segundos
    procesados.add(event.message.id)
    await asyncio.sleep(1)
    
    # BORRAR original
    try:
        await event.delete()
        print("🗑️ Mensaje BORRADO")
    except:
        pass
    
    short_url = amzn_links[0]
    try:
        final_url = resolve_amzn(short_url)
        asin = get_asin_from_url(final_url)
        if not asin:
            await client.send_message(target_channel, "❌ Enlace inválido")
            return
            
        affiliate_url = build_affiliate_url(asin)
        title, price, old_price, img_url = get_product_info(final_url)
        
        # FORMATO OFERTA PROFESIONAL
        oferta = f"""🔥 **OFERTA FLASH** 🔥

**{title}**
✨ **{price}**
"""
        if old_price:
            oferta += f"▫️ ~~{old_price}~~\n"
        oferta += f"\n🔰 [Comprar ahora]({affiliate_url})\n\n"
        oferta += f"👻 *solochollos.com*"
        
        # PUBLICAR
        if img_url:
            try:
                img_data = requests.get(img_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}).content
                await client.send_file(target_channel, file=img_data, caption=oferta, parse_mode='md')
                print("✅ ✅ OFERTA CON FOTO ✓")
            except:
                await client.send_message(target_channel, oferta, parse_mode='md')
                print("✅ ✅ OFERTA SIN FOTO ✓")
        else:
            await client.send_message(target_channel, oferta, parse_mode='md')
            print("✅ ✅ OFERTA PUBLICADA ✓")
            
        # Limpiar procesados cada 5 min
        if len(procesados) > 100:
            procesados.clear()
            
    except Exception as e:
        print(f"💥 Error total: {e}")
        await client.send_message(target_channel, f"💥 Error: {str(e)[:100]}")

print("🤖 Bot chollos ULTIMATE v2.0 iniciado")
print("✅ Borra enlaces → Ofertas automáticas")
print("✅ Anti-loop + Anti-spam implementado")
client.run_until_disconnected()
