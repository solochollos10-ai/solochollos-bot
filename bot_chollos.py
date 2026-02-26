#!/usr/bin/env python3
import os
import asyncio
import re
import json
import html
import requests
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from PIL import Image, ImageOps
from io import BytesIO

# ==============================
# CONFIG (variables de entorno)
# ==============================
try:
    api_id = int(os.getenv("API_ID"))
except Exception:
    raise RuntimeError("API_ID no definido o no es un entero en las variables de entorno.")

api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

if not api_hash or not bot_token:
    raise RuntimeError("API_HASH o BOT_TOKEN no definidos en variables de entorno.")

source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"

client = TelegramClient("session_bot_chollos", api_id, api_hash)

# ==============================
# SESSION HTTP (headers realistas)
# ==============================
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Referer": "https://www.amazon.es/"
})

# ==============================
# UTILIDADES AMAZON
# ==============================
def extract_asin(url):
    patterns = [r"/dp/([A-Z0-9]{10})", r"/gp/product/([A-Z0-9]{10})"]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None

def resolve_amazon_link(url):
    """Resuelve amzn.to o enlaces cortos a la URL final y extrae ASIN."""
    try:
        r = session.get(url, allow_redirects=True, timeout=15)
        final = r.url.split("?")[0]
        return extract_asin(final)
    except Exception as e:
        print("Error resolviendo enlace:", e)
        return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

# ==============================
# SCRAPING ROBUSTO (imagen + precios)
# ==============================
def _pick_best_from_dynamic_image(data_str):
    """
    data_str es el contenido de data-a-dynamic-image (JSON-like).
    Devuelve la URL con mayor resolución (mayor área).
    """
    try:
        s = html.unescape(data_str)
        # A veces viene con comillas dobles ya JSON compatibles
        d = json.loads(s)
        best = None
        best_area = 0
        for url, size in d.items():
            if isinstance(size, (list, tuple)) and len(size) >= 2:
                area = int(size[0]) * int(size[1])
            else:
                area = 0
            if area > best_area:
                best = url
                best_area = area
        return best
    except Exception:
        return None

def scrape_amazon_product(asin):
    """
    Scrapea la página /dp/ASIN y devuelve dict con:
    title, price, old_price, rating, reviews, image
    Usa selectores específicos (apex-pricetopay-value, apex-basisprice-value, #landingImage).
    """
    url = f"https://www.amazon.es/dp/{asin}"
    try:
        r = session.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        # ---------- TITLE ----------
        title_elem = soup.select_one("#productTitle")
        if not title_elem:
            title_elem = soup.select_one("span.a-size-large.a-color-base.a-text-normal")
        title = title_elem.get_text(strip=True) if title_elem else "Producto Amazon"

        # ---------- PRICE (AHORA) ----------
        price = None
        # Principal: apex core price offscreen
        price_elem = soup.select_one(".apex-pricetopay-value .a-offscreen")
        if price_elem:
            price = price_elem.get_text(strip=True)

        # fallback: priceblock (ourprice / dealprice)
        if not price:
            alt = soup.select_one("#priceblock_ourprice, #priceblock_dealprice, #corePriceDisplay_desktop_feature_div .a-offscreen")
            if alt:
                price = alt.get_text(strip=True)

        # ---------- OLD PRICE (ANTES / precio recomendado) ----------
        old_price = None
        old_elem = soup.select_one(".apex-basisprice-value .a-offscreen")
        if old_elem:
            old_price = old_elem.get_text(strip=True)
        else:
            alt_old = soup.select_one(".a-text-price .a-offscreen, #priceblock_listprice")
            if alt_old:
                old_price = alt_old.get_text(strip=True)

        # ---------- RATING ----------
        rating_elem = soup.select_one("#acrPopover")
        rating = ""
        if rating_elem and rating_elem.has_attr("title"):
            rating = rating_elem["title"].strip()
        else:
            # fallback: starAverage
            ra = soup.select_one("i.a-icon-star span.a-icon-alt")
            if ra:
                rating = ra.get_text(strip=True)

        # ---------- REVIEWS ----------
        reviews_elem = soup.select_one("#acrCustomerReviewText")
        reviews = ""
        if reviews_elem:
            reviews = reviews_elem.get_text(strip=True)
        else:
            r_alt = soup.select_one("#acrCustomerReviewText, span#acrCustomerReviewText")
            if r_alt:
                reviews = r_alt.get_text(strip=True)

        # ---------- IMAGE: landingImage data-old-hires OR data-a-dynamic-image ----------
        img_url = None
        landing = soup.select_one("#landingImage")
        if landing:
            # data-old-hires first
            img_url = landing.get("data-old-hires") or landing.get("src")
            # data-a-dynamic-image more robust (choose biggest)
            dyn = landing.get("data-a-dynamic-image")
            if dyn:
                best = _pick_best_from_dynamic_image(dyn)
                if best:
                    img_url = best

        # fallback og:image
        if not img_url:
            og = soup.select_one('meta[property="og:image"]')
            if og and og.get("content"):
                img_url = og.get("content")

        # Try to upgrade some SX size urls to SL1500 if possible (best-effort)
        if img_url and "_AC_SX" in img_url and "_SL" not in img_url:
            img_url = re.sub(r"(_AC_SX)\d+_", "_AC_SL1500_", img_url)

        return {
            "title": title,
            "price": price,
            "old_price": old_price,
            "rating": rating,
            "reviews": reviews,
            "image": img_url
        }
    except Exception as e:
        print("Error scraping:", e)
        return None

# ==============================
# PROCESADO DE IMAGEN: REDIMENSIONAR + MARCO
# ==============================
def process_image_to_bytes(image_url, max_dim=1280, border_px=10, border_color="#ffa500"):
    """
    Descarga la imagen, la redimensiona (manteniendo proporción) para que
    su mayor lado <= max_dim - 2*border_px, añade un borde y devuelve BytesIO listo para enviar.
    """
    if not image_url:
        return None
    try:
        resp = session.get(image_url, timeout=15)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")

        # calcular target size para thumbnail (restar borde)
        target = (max_dim - 2 * border_px, max_dim - 2 * border_px)
        img.thumbnail(target, Image.LANCZOS)

        # expandir con borde
        border_rgb = border_color
        try:
            # Pillow acepta string hex for fill from v8+, else convert
            framed = ImageOps.expand(img, border=border_px, fill=border_rgb)
        except Exception:
            # fallback: convert hex to rgb tuple
            hexv = border_color.lstrip("#")
            border_tuple = tuple(int(hexv[i:i+2], 16) for i in (0, 2, 4))
            framed = ImageOps.expand(img, border=border_px, fill=border_tuple)

        out = BytesIO()
        out.name = "product.jpg"
        framed.save(out, format="JPEG", quality=90)
        out.seek(0)
        return out
    except Exception as e:
        print("Error procesando imagen:", e)
        return None

# ==============================
# HANDLERS
# ==============================
async def process_source_message(event):
    """
    Copia directamente el enlace corto/amzn.to del canal origen al destino,
    y además intenta publicar una oferta bonita (con foto y datos) en el destino.
    """
    text = event.raw_text or ""
    links = re.findall(r"(https?://\S+)", text)
    if not links:
        return

    amazon_link = next((l for l in links if "amzn.to" in l or "amazon.es" in l), None)
    if not amazon_link:
        return

    # 1) Copia directa del enlace (tal cual)
    try:
        await client.send_message(target_channel, amazon_link)
        print("🔗 Copiado enlace directo:", amazon_link)
    except Exception as e:
        print("Error copiando enlace directo:", e)

    # 2) Generar oferta (si se puede obtener ASIN y datos)
    asin = resolve_amazon_link(amazon_link)
    if not asin:
        return

    product = scrape_amazon_product(asin)
    if not product:
        return

    # Construir message: formateos y safe-fallbacks
    rating_text = product["rating"] or ""
    reviews_text = product["reviews"] or ""
    price_text = product["price"] or ""
    old_price_text = product["old_price"] or ""

    # Limpiezas básicas
    price_text = price_text.replace(" ,", ",").replace(",,", ",")
    old_price_text = old_price_text.replace(" ,", ",").replace(",,", ",")

    affiliate_url = build_affiliate_url(asin)

    message_lines = [
        "🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥",
        f"**{product['title']}**",
    ]
    if rating_text or reviews_text:
        message_lines.append(f"⭐ {rating_text} { '|' if rating_text and reviews_text else ''} {reviews_text}".strip())
    if price_text:
        message_lines.append(f"🟢 **AHORA {price_text}**")
    if old_price_text:
        message_lines.append(f"🔴 ~~ANTES: {old_price_text}~~")
    message_lines.append(f"🔰 {affiliate_url}")
    message = "\n".join([line for line in message_lines if line.strip()])

    # Procesar imagen y enviar
    img_bytes = process_image_to_bytes(product.get("image"))
    try:
        if img_bytes:
            await client.send_file(target_channel, img_bytes, caption=message, parse_mode="md")
        else:
            await client.send_message(target_channel, message, parse_mode="md")
        print("✅ Oferta publicada con datos e imagen (si disponible).")
    except FloodWaitError as e:
        print("FloodWait, durmiendo:", e.seconds)
        await asyncio.sleep(e.seconds)
    except Exception as e:
        print("Error publicando oferta:", e)

async def process_target_message(event):
    """
    Cuando pegas SOLO un enlace en tu canal, borra el mensaje y publica
    la oferta formateada con foto + afiliado.
    """
    text = (event.raw_text or "").strip()
    if not re.match(r"^https?://\S+$", text):
        return

    asin = resolve_amazon_link(text)
    if not asin:
        return

    # borrar original
    try:
        await event.delete()
    except Exception:
        pass

    product = scrape_amazon_product(asin)
    if not product:
        return

    rating_text = product["rating"] or ""
    reviews_text = product["reviews"] or ""
    price_text = product["price"] or ""
    old_price_text = product["old_price"] or ""

    price_text = price_text.replace(" ,", ",").replace(",,", ",")
    old_price_text = old_price_text.replace(" ,", ",").replace(",,", ",")

    affiliate_url = build_affiliate_url(asin)

    message_lines = [
        "🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥",
        f"**{product['title']}**",
    ]
    if rating_text or reviews_text:
        message_lines.append(f"⭐ {rating_text} { '|' if rating_text and reviews_text else ''} {reviews_text}".strip())
    if price_text:
        message_lines.append(f"🟢 **AHORA {price_text}**")
    if old_price_text:
        message_lines.append(f"🔴 ~~ANTES: {old_price_text}~~")
    message_lines.append(f"🔰 {affiliate_url}")
    message = "\n".join([line for line in message_lines if line.strip()])

    img_bytes = process_image_to_bytes(product.get("image"))
    try:
        if img_bytes:
            await client.send_file(target_channel, img_bytes, caption=message, parse_mode="md")
        else:
            await client.send_message(target_channel, message, parse_mode="md")
        print("✅ Oferta generada desde enlace en tu canal.")
    except Exception as e:
        print("Error publicando oferta desde enlace:", e)

# ==============================
# MAIN
# ==============================
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 BOT ACTIVADO")
    print(f"✅ Copia {source_channel} → {target_channel}")
    print("✅ Generación automática de ofertas con fotos y afiliado")

    @client.on(events.NewMessage(chats=source_channel))
    async def _on_source(event):
        await process_source_message(event)

    @client.on(events.NewMessage(chats=target_channel))
    async def _on_target(event):
        await process_target_message(event)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
