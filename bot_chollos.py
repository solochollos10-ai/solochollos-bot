import os
import re
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, events

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

# PRUEBA CON @ ANTES
source_channel = "@chollosdeluxe"  # ← CAMBIO AQUÍ
target_channel = "@solochollos10"  # ← Y AQUÍ
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

client = TelegramClient("session_chollos", api_id, api_hash).start(bot_token=bot_token)

def resolve_amzn(url):
    print(f"🔍 Resolviendo: {url}")  # DEBUG
    r = requests.get(url, allow_redirects=True, timeout=10)
    return r.url

def get_asin_from_url(url):
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    if m: 
        print(f"✅ ASIN encontrado: {m.group(1)}")  # DEBUG
        return m.group(1)
    print(f"❌ No ASIN en: {url}")  # DEBUG
    return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

def get_main_image(amazon_url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(amazon_url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        img_tag = soup.find("img", id="landingImage") or soup.find("img", {"data-a-dynamic-image": True})
        if img_tag and img_tag.get("src"):
            print(f"✅ Imagen: {img_tag['src'][:50]}...")  # DEBUG
            return img_tag["src"]
    except:
        pass
    print("❌ No imagen")  # DEBUG
    return None

@client.on(events.NewMessage(chats=source_channel))
async def handler(event):
    print(f"📨 NUEVO MENSAJE de {event.chat.username or event.chat_id}")  # DEBUG IMPORTANTE
    text = event.raw_text or ""
    urls = re.findall(r"(https?://\S+)", text)
    amzn_links = [u for u in urls if "amzn.to" in u]
    
    print(f"🔗 Enlaces amzn.to encontrados: {len(amzn_links)}")  # DEBUG
    
    if not amzn_links: 
        print("❌ Sin enlaces amzn.to")  # DEBUG
        return
    
    short_url = amzn_links[0]
    try:
        final_url = resolve_amzn(short_url)
        asin = get_asin_from_url(final_url)
        if not asin: return
        
        affiliate_url = build_affiliate_url(asin)
        img_url = get_main_image(final_url)
        nuevo_texto = text.replace(short_url, affiliate_url)
        
        print(f"🚀 PUBLICANDO con tag: {affiliate_url}")  # DEBUG
        
        if img_url:
            img_data = requests.get(img_url, timeout=10).content
            await client.send_file(target_channel, file=img_data, caption=nuevo_texto)
        else:
            await client.send_message(target_channel, nuevo_texto)
            
        print("✅ PUBLICADO CORRECTAMENTE!")
            
    except Exception as e:
        print(f"💥 ERROR: {e}")

print("🤖 Bot chollos iniciado - escuchando...")
client.run_until_disconnected()
