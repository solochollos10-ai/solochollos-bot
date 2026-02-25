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
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

def resolve_amzn(url):
    """Resuelve amzn.to SIN tag"""
    print(f"🔍 Resolviendo: {url}")
    try:
        clean_url = re.sub(r'\?tag=[^&\s]+', '', url)
        r = requests.get(clean_url, allow_redirects=True, timeout=15, headers=get_amazon_session())
        final_url = r.url.split('?')[0]
        print(f"✅ URL final: {final_url}")
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
    """EXTRACTION PRECISA según HTML que proporcionaste"""
    session = requests.Session()
    session.headers.update(get_amazon_session())
    time.sleep(random.uniform(2, 4))
    
    try:
        print(f"🕵️ Scraping detallado: {url}")
        r = session.get(url, timeout=25)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 🎯 TÍTULO - Múltiples selectores
        title_selectors = [
            '#productTitle', 'h1 span.a-size-large', '.a-hero-title span',
            'span#productTitle', 'h1.a-size-large'
        ]
        title = None
        for selector in title_selectors:
            elem = soup.select_one(selector)
            if elem and elem.get_text(strip=True):
                title = elem.get_text(strip=True).strip()[:140]
                print(f"✅ TÍTULO: {title[:60]}...")
                break
        
        # ⭐ VALORACIONES (TU HTML exacto)
        rating = None
        reviews_count = None
        
        # Buscar div#averageCustomerReviews_feature_div
        rating_div = soup.find('div', id='averageCustomerReviews_feature_div')
        if rating_div:
            # Extraer "4,6" del span.a-size-small.a-color-base
            rating_span = rating_div.select_one('.a-size-small.a-color-base')
            if rating_span:
                rating = rating_span.get_text(strip=True)
                print(f"⭐ VALORACIÓN: {rating}")
            
            # Extraer "(3.386)" del span#acrCustomerReviewText
            reviews_span = soup.select_one('#acrCustomerReviewText')
            if reviews_span:
                reviews_count = reviews_span.get_text(strip=True).strip('()')
                print(f"📊 RESERÑAS: {reviews_count}")
        
        # 💰 PRECIO ACTUAL (span.a-price-whole + fraction)
        price_current = None
        price_whole = soup.select_one('.a-price-whole')
        price_fraction = soup.select_one('.a-price-fraction')
        price_symbol = soup.select_one('.a-price-symbol')
        
        if price_whole:
            price_text = price_whole.get_text(strip=True)
            if price_fraction:
                price_text += ',' + price_fraction.get_text(strip=True)
            if price_symbol:
                price_text += price_symbol.get_text(strip=True)
            price_current = price_text
            print(f"✅ PRECIO ACTUAL: {price_current}")
        
        # 💸 PRECIO ANTERIOR (basisPrice)
        old_price = None
        basis_price = soup.select_one('.basisPrice .a-price.a-text-price .a-offscreen')
        if not basis_price:
            basis_price = soup.select_one('.a-price.a-text-price .a-offscreen')
        
        if basis_price:
            old_price = basis_price.get_text(strip=True)
            print(f"✅ PRECIO ANTERIOR: {old_price}")
        
        # 📸 IMAGEN PRINCIPAL (prioridad SL1500)
        img_url = None
        img_selectors = ['#landingImage', '#imgTagWrapperId img', 'img[data-a-image-primary]']
        for selector in img_selectors:
            img_elem = soup.select_one(selector)
            if img_elem:
                img_src = img_elem.get('src') or img_elem.get('data-old-hires')
                if img_src and '_SL1500_' in img_src:
                    img_url = img_src
                    print(f"✅ IMAGEN SL1500: {img_url[-60:]}")
                    break
                elif img_src:
                    img_url = img_src
                    print(f"✅ IMAGEN: {img_src[-60:]}")
                    break
        
        return {
            'title': title or "Producto Amazon",
            'rating': rating,
            'reviews_count': reviews_count,
            'price_current': price_current or "Precio no disponible",
            'old_price': old_price,
            'img_url': img_url
        }
        
    except Exception as e:
        print(f"💥 Error scraping: {e}")
        return {
            'title': "Producto Amazon",
            'rating': None,
            'reviews_count': None,
            'price_current': "Consulta precio",
            'old_price': None,
            'img_url': None
        }

async def process_amazon_link(event):
    text = event.raw_text or ""
    urls = re.findall(r"(https?://\S+)", text)
    amazon_urls = [u for u in urls if any(x in u.lower() for x in ['amzn.to', 'amazon.es', 'amazon.com'])]
    
    if not amazon_urls:
        return
        
    print(f"🔗 Amazon detectado: {amazon_urls[0]}")
    
    # 🗑️ BORRAR mensaje original
    try:
        await event.delete()
        print("🗑️ Mensaje eliminado")
    except:
        pass
    
    # 🔍 PROCESAR
    final_url = resolve_amzn(amazon_urls[0])
    if not final_url:
        await client.send_message(target_channel, "❌ Error resolviendo Amazon")
        return
        
    asin = extract_asin(final_url)
    if not asin:
        await client.send_message(target_channel, "❌ ASIN inválido")
        return
    
    affiliate_url = build_affiliate_url(asin)
    product = get_product_details(final_url)
    
    # 📝 OFERTA COMPLETA con VALORACIONES
    oferta = f"""🔥 **OFERTA AMAZON** 🔥

**{product['title']}**
"""
    
    # ⭐ VALORACIONES
    if product['rating'] and product['reviews_count']:
        oferta += f"⭐ **{product['rating']}** ({product['reviews_count']} reseñas)\n"
    
    # 💰 PRECIOS
    oferta += f"**{product['price_current']}**"
    
    if product['old_price']:
        oferta += f"\n**Antes**: {product['old_price']}"
    
    oferta += f"""

🔰 {affiliate_url}

👻 solochollos.com"""
    
    # 📤 PUBLICAR
    try:
        if product['img_url']:
            img_resp = requests.get(product['img_url'], timeout=20, headers=get_amazon_session())
            await client.send_file(target_channel, img_resp.content, caption=oferta)
            print("✅ ✅ OFERTA COMPLETA con FOTO")
        else:
            await client.send_message(target_channel, oferta)
            print("✅ OFERTA sin foto")
    except Exception as e:
        print(f"💥 Error publicación: {e}")
        await client.send_message(target_channel, oferta)

@client.on(events.NewMessage(chats=target_channel))
async def handler(event):
    print(f"📨 Nuevo en {target_channel}: {event.raw_text[:60]}...")
    await process_amazon_link(event)

print("🤖 Bot_chollos PRO v3.0")
print("✅ VALORACIONES ⭐ 4,6 (3.386)")
print("✅ Precio actual/fraction")
print("✅ Precio basisPrice ANTERIOR")
print("✅ Foto SL1500 automática")
client.run_until_disconnected()
