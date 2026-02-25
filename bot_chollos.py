import os
import re
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, events

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        r = requests.get(amazon_url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # TÍTULO
        title = (soup.find("span", id="productTitle") or 
                soup.find("h1", class_=re.compile("a-size-large")) or 
                soup.find("h1")).get_text(strip=True)[:100]
        
        # PRECIO
        price = (soup.find("span", class_="a-price-whole") or 
                soup.find("span", class_=re.compile("a-price.*whole")) or 
                soup.find("span", string=re.compile(r"\d+,\d+")))
        price = price.get_text(strip=True) if price else "Precio no disponible"
        
        # PVP (precio original tachado)
        old_price = soup.find("span", class_=re.compile("a-price.*off.*whole"))
        old_price = old_price.get_text(strip=True) if old_price else None
        
        # IMAGEN PRINCIPAL
        img_tag = (soup.find("img", id="landingImage") or 
                  soup.find("img", {"data-a-dynamic-image": True}))
        img_url = img_tag["src"] if img_tag and img_tag.get("src") else None
        
        print(f"📦 Producto: {title[:50]}...")
        print(f"💰 Precio: {price}")
        return title, price, old_price, img_url
    except:
        print("❌ Error scraping Amazon")
        return "Producto Amazon", "Precio no disponible", None, None

@client.on(events.NewMessage(chats=target_channel))  # ← ESCUCHA TU CANAL
async def tu_canal_handler(event):
    text = event.raw_text or ""
    urls = re.findall(r"(https?://\S+)", text)
    amzn_links = [u for u in urls if "amzn.to" in u or "amazon.es" in u]
    
    if not amzn_links:
        return
        
    print(f"🔗 Enlace detectado en TU canal: {amzn_links[0]}")
    
    # ❌ BORRAR mensaje original
    await event.delete()
    print("🗑️ Mensaje original BORRADO")
    
    short_url = amzn_links[0]
    try:
        # 🔍 RESOLVER URL
        final_url = resolve_amzn(short_url)
        asin = get_asin_from_url(final_url)
        if not asin:
            await client.send_message(target_channel, "❌ No se pudo obtener ASIN del enlace")
            return
            
        # 🛒 INFO PRODUCTO + AFILIADO
        affiliate_url = build_affiliate_url(asin)
        title, price, old_price, img_url = get_product_info(final_url)
        
        # 📝 FORMATO OFERTA (igual que chollosdeluxe)
        oferta = f"""🔥 **OFERTA FLASH** 🔥

**{title}**
✨ {price}
"""
        if old_price:
            oferta += f"▫️ **PVP**: {old_price}\n"
        oferta += f"\n🔰: {affiliate_url}\n\n"
        oferta += f"👻 solochollos.com"
        
        # 📤 PUBLICAR
        if img_url:
            img_data = requests.get(img_url, timeout=15).content
            await client.send_file(target_channel, file=img_data, caption=oferta)
            print("✅ ✅ OFERTA CON FOTO publicada")
        else:
            await client.send_message(target_channel, oferta)
            print("✅ ✅ OFERTA SIN FOTO publicada")
            
    except Exception as e:
        print(f"💥 Error completo: {e}")
        await client.send_message(target_channel, "💥 Error procesando el enlace")

# MANTIENER VIEJO HANDLER para @chollosdeluxe
@client.on(events.NewMessage(chats=source_channel))
async def chollosdeluxe_handler(event):
    print(f"📨 Chollosdeluxe nuevo mensaje")
    # ... código anterior ...

print("🤖 Bot chollos ULTIMATE iniciado")
print("✅ Escucha @solochollos10 (borra enlaces → ofertas)")
print("✅ Escucha @chollosdeluxe (copia ofertas)")
client.run_until_disconnected()
