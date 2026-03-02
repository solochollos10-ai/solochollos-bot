import os
import asyncio
import re
import requests
import random
import json
import hashlib
import hmac
import datetime
import time
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from PIL import Image, ImageOps
from io import BytesIO

# ==============================
# VARIABLES DE ENTORNO (RAILWAY)
# ==============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
affiliate_tag = os.getenv("AFFILIATE_TAG")

paapi_access_key = os.getenv("PAAPI_ACCESS_KEY")
paapi_secret_key = os.getenv("PAAPI_SECRET_KEY")

source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"

# NUEVOS PARÁMETROS (REINTENTOS / CAMPOS OBLIGATORIOS)
PRODUCT_MAX_RETRIES = int(os.getenv("PRODUCT_MAX_RETRIES", "6"))
PRODUCT_RETRY_BASE_SECONDS = float(os.getenv("PRODUCT_RETRY_BASE_SECONDS", "2.0"))
# Por defecto exigimos: título + precio + imagen (lo que más falla)
REQUIRED_FIELDS = [x.strip() for x in os.getenv("REQUIRED_FIELDS", "title,price,image").split(",") if x.strip()]

# Throttle PA-API (evita 429 por ráfagas)
PAAPI_MIN_INTERVAL_SECONDS = float(os.getenv("PAAPI_MIN_INTERVAL_SECONDS", "1.1"))

client = TelegramClient("session_bot_chollos", api_id, api_hash)

# ==============================
# ANTI-BLOQUEO AMAZON (SCRAPING)
# ==============================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }

# ==============================
# AMAZON PA-API (GetItems)
# ==============================
PAAPI_HOST = "webservices.amazon.es"
PAAPI_REGION = "eu-west-1"
PAAPI_SERVICE = "ProductAdvertisingAPI"
PAAPI_ENDPOINT = f"https://{PAAPI_HOST}/paapi5/getitems"
PAAPI_TARGET = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems"

_paapi_lock = asyncio.Lock()
_paapi_last_call = 0.0

def _sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

def _get_signature_key(key, date_stamp, region_name, service_name):
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = hmac.new(k_date, region_name.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service_name.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, "aws4_request".encode("utf-8"), hashlib.sha256).digest()
    return k_signing

def paapi_get_product_sync(asin):
    if not (paapi_access_key and paapi_secret_key and affiliate_tag):
        return None

    payload = {
        "ItemIds": [asin],
        "ItemIdType": "ASIN",
        "PartnerTag": affiliate_tag,
        "PartnerType": "Associates",
        "Marketplace": "www.amazon.es",
        "Resources": [
            "ItemInfo.Title",
            "Images.Primary.Large",
            "Offers.Listings.Price",
            "Offers.Listings.SavingBasis",
            "CustomerReviews.Count",
            "CustomerReviews.StarRating",
        ],
    }

    request_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    t = datetime.datetime.utcnow()
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    canonical_uri = "/paapi5/getitems"
    canonical_querystring = ""

    canonical_headers = (
        "content-encoding:amz-1.0\n"
        "content-type:application/json; charset=utf-8\n"
        f"host:{PAAPI_HOST}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{PAAPI_TARGET}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
    payload_hash = hashlib.sha256(request_body).hexdigest()

    canonical_request = (
        "POST\n"
        f"{canonical_uri}\n"
        f"{canonical_querystring}\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{payload_hash}"
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{PAAPI_REGION}/{PAAPI_SERVICE}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    signing_key = _get_signature_key(paapi_secret_key, date_stamp, PAAPI_REGION, PAAPI_SERVICE)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization_header = (
        f"{algorithm} "
        f"Credential={paapi_access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    headers = {
        "Content-Encoding": "amz-1.0",
        "Content-Type": "application/json; charset=utf-8",
        "Host": PAAPI_HOST,
        "X-Amz-Date": amz_date,
        "X-Amz-Target": PAAPI_TARGET,
        "Authorization": authorization_header,
    }

    try:
        r = requests.post(PAAPI_ENDPOINT, data=request_body, headers=headers, timeout=20)
        if r.status_code != 200:
            print(f"⚠️ PAAPI HTTP {r.status_code}: {r.text[:200]}")
            return None

        data = r.json()
        items = (data.get("ItemsResult") or {}).get("Items") or []
        if not items:
            return None

        item = items[0]
        title = (((item.get("ItemInfo") or {}).get("Title") or {}).get("DisplayValue")) or None
        img_url = (((((item.get("Images") or {}).get("Primary") or {}).get("Large") or {}).get("URL"))) or None

        price = None
        old_price = None
        listings = (((item.get("Offers") or {}).get("Listings")) or [])
        if listings:
            l0 = listings[0]
            price = (((l0.get("Price") or {}).get("DisplayAmount"))) or None
            old_price = (((l0.get("SavingBasis") or {}).get("DisplayAmount"))) or None

        rating = (((item.get("CustomerReviews") or {}).get("StarRating") or {}).get("DisplayValue")) or None
        reviews_count = (((item.get("CustomerReviews") or {}).get("Count") or {}).get("DisplayValue")) or ""
        reviews_text = f"{reviews_count} opiniones" if reviews_count else ""

        return {
            "title": title,
            "price": price,
            "old_price": old_price,
            "rating": rating,
            "reviews": reviews_text,
            "image": img_url
        }
    except Exception as e:
        print(f"Error PAAPI: {e}")
        return None

async def paapi_get_product_throttled(asin):
    global _paapi_last_call
    if not (paapi_access_key and paapi_secret_key and affiliate_tag):
        return None

    async with _paapi_lock:
        now = time.monotonic()
        wait = PAAPI_MIN_INTERVAL_SECONDS - (now - _paapi_last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _paapi_last_call = time.monotonic()

    return await asyncio.to_thread(paapi_get_product_sync, asin)

# ==============================
# AMAZON: ASIN + SCRAPING fallback
# ==============================
def extract_asin(url):
    patterns = [r"/dp/([A-Z0-9]{10})", r"/gp/product/([A-Z0-9]{10})"]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def resolve_amazon_link(url):
    try:
        current = url
        for _ in range(6):
            asin_here = extract_asin(current.split("?")[0])
            if asin_here:
                return asin_here

            r = requests.get(current, headers=get_random_headers(), allow_redirects=False, timeout=15)
            loc = r.headers.get("Location")

            if loc and loc.startswith("http"):
                current = loc
                continue

            final_url = r.url.split("?")[0]
            return extract_asin(final_url)

        return extract_asin(current.split("?")[0])
    except Exception as e:
        print("Error resolviendo enlace:", e)
        return None

def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"

def scrape_amazon_product_html_sync(asin):
    url = f"https://www.amazon.es/dp/{asin}"
    try:
        r = requests.get(url, headers=get_random_headers(), timeout=15)
        if ("captcha" in r.text.lower()) or ("validateCaptcha" in r.text):
            print("🛑 CAPTCHA detectado en HTML (fallback).")
            return None

        soup = BeautifulSoup(r.text, "lxml")

        title = soup.select_one("#productTitle")
        if not title:
            title = soup.select_one("span.a-size-large.a-color-base.a-text-normal")
        title = title.get_text(strip=True) if title else None

        price = None
        price_whole = soup.select_one(".a-price .a-price-whole")
        price_fraction = soup.select_one(".a-price .a-price-fraction")
        if price_whole:
            fraction_text = price_fraction.text.strip() if price_fraction else "00"
            price = f"{price_whole.text.strip()},{fraction_text}€"
        else:
            price_alt = soup.select_one("#priceblock_ourprice") or soup.select_one("#priceblock_dealprice")
            price = price_alt.text.strip() if price_alt else None

        old_price = None
        text_content = soup.get_text(separator=" ").replace("\xa0", " ")
        match = re.search(r'(?:Precio recomendado|Precio anterior):\s*([0-9.,]+[\s]*€?)', text_content, re.IGNORECASE)
        if match:
            old_price = match.group(1).strip()
            if "€" not in old_price:
                old_price += "€"

        rating_elem = soup.select_one("#acrPopover")
        rating = rating_elem.get("title") if rating_elem else None

        reviews_elem = soup.select_one("#acrCustomerReviewText")
        reviews_text = ""
        if reviews_elem:
            reviews_clean = re.sub(r"[^0-9\.]", "", reviews_elem.text.strip())
            reviews_text = f"{reviews_clean} opiniones"

        img_url = None
        img_tag_wrapper = soup.find(id="imgTagWrapperId") or soup.select_one("#landingImage")
        if img_tag_wrapper and img_tag_wrapper.get("data-a-dynamic-image"):
            try:
                dynamic_data = json.loads(img_tag_wrapper["data-a-dynamic-image"])
                best_img = max(dynamic_data.items(), key=lambda x: x[1][1])[0]
                img_url = best_img.replace("\\", "")
            except Exception:
                pass

        if not img_url:
            landing = soup.select_one("#landingImage")
            if landing:
                img_url = landing.get("data-old-hires") or landing.get("data-a-hires") or landing.get("src")

        if not img_url:
            og_img = soup.select_one('meta[property="og:image"]')
            if og_img:
                img_url = og_img.get("content")

        return {
            "title": title,
            "price": price,
            "old_price": old_price,
            "rating": rating,
            "reviews": reviews_text,
            "image": img_url
        }
    except Exception as e:
        print("Error scraping HTML:", e)
        return None

async def fetch_product_once(asin):
    # 1) PA-API primero
    pa = await paapi_get_product_throttled(asin)
    if pa:
        return pa
    # 2) Fallback HTML en thread (no bloquea el loop)
    return await asyncio.to_thread(scrape_amazon_product_html_sync, asin)

def product_missing_fields(product, required_fields):
    if not product:
        return required_fields
    missing = []
    for k in required_fields:
        v = product.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            missing.append(k)
    return missing

async def fetch_product_complete(asin):
    last_product = None
    for attempt in range(1, PRODUCT_MAX_RETRIES + 1):
        prod = await fetch_product_once(asin)
        last_product = prod

        missing = product_missing_fields(prod, REQUIRED_FIELDS)
        if not missing:
            return prod

        wait = (PRODUCT_RETRY_BASE_SECONDS * (2 ** (attempt - 1))) + random.uniform(0.0, 1.0)
        wait = min(wait, 40.0)  # tope para no congelarte
        print(f"⚠️ Producto incompleto (intento {attempt}/{PRODUCT_MAX_RETRIES}). Faltan: {missing}. Reintento en {wait:.1f}s")
        await asyncio.sleep(wait)

    # Si no se consigue completo, devolvemos None (modo estricto)
    print("❌ No se pudo obtener producto completo tras reintentos.")
    return None

# ==============================
# ENVÍO A TELEGRAM (con FloodWait)
# ==============================
async def safe_send_message(chat, text, **kwargs):
    while True:
        try:
            return await client.send_message(chat, text, **kwargs)
        except FloodWaitError as e:
            print(f"⏳ FloodWait send_message: {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)

async def safe_send_file(chat, file, **kwargs):
    while True:
        try:
            return await client.send_file(chat, file, **kwargs)
        except FloodWaitError as e:
            print(f"⏳ FloodWait send_file: {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)

def build_message(product, affiliate_url):
    rating_text = product["rating"] if product.get("rating") else ""
    reviews_text = product["reviews"] if product.get("reviews") else ""
    price_text = product["price"].replace(",,", ",") if product.get("price") else ""

    if product.get("old_price"):
        price_line = f"🟢 **AHORA {price_text}** 🔴 ~~ANTES: {product['old_price']}~~"
    else:
        price_line = f"🟢 **AHORA {price_text}**"

    return (
        f"🔥🔥🔥 OFERTA AMAZON 🔥🔥🔥\n"
        f"**{product.get('title') or 'Producto Amazon'}**\n"
        f"⭐ {rating_text} y {reviews_text}\n"
        f"{price_line}\n"
        f"🔰 {affiliate_url}"
    )

async def publish_offer(target, product, affiliate_url):
    message = build_message(product, affiliate_url)

    img_url = product.get("image")
    if not img_url:
        # En modo estricto nunca deberías llegar aquí si REQUIRED_FIELDS incluye image
        await safe_send_message(target, message, parse_mode="md")
        return

    try:
        resp = requests.get(img_url, headers=get_random_headers(), timeout=20)
        content_type = resp.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            raise ValueError(f"Contenido no imagen: {content_type}")

        img = Image.open(BytesIO(resp.content)).convert("RGB")

        max_size = (1280, 1280)
        try:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
        except AttributeError:
            try:
                img.thumbnail(max_size, Image.LANCZOS)
            except AttributeError:
                img.thumbnail(max_size, Image.BICUBIC)

        img = ImageOps.expand(img, border=10, fill=(255, 165, 0))

        bio = BytesIO()
        bio.name = "product.jpg"
        img.save(bio, "JPEG", quality=95)
        bio.seek(0)

        await safe_send_file(target, bio, caption=message, parse_mode="md")
    except Exception as e:
        print(f"Error publicando imagen: {e}")
        # Si falla la imagen, reintentamos regenerar producto completo (puede venir otra URL)
        return False

    return True

# ==============================
# HANDLERS
# ==============================
async def process_source_message(event):
    text = event.raw_text or ""
    links = re.findall(r'(https?://\S+)', text)
    if not links:
        return

    amazon_link = None
    for link in links:
        if "amzn.to" in link or "amazon.es" in link:
            amazon_link = link
            break
    if not amazon_link:
        return

    # Mantengo tu comportamiento: copiar enlace directo
    await safe_send_message(target_channel, amazon_link)

    asin = resolve_amazon_link(amazon_link)
    if not asin:
        return

    affiliate_url = build_affiliate_url(asin)

    # NUEVO: reintenta hasta conseguir el producto COMPLETO
    product = await fetch_product_complete(asin)
    if not product:
        # Si no conseguimos datos completos, publicamos solo enlace afiliado (y no “medio anuncio”)
        await safe_send_message(target_channel, f"🔰 {affiliate_url}", parse_mode="md")
        return

    # Si el envío con foto falla (por descarga/imagen), reintentamos regenerar y re-publicar
    for attempt in range(1, PRODUCT_MAX_RETRIES + 1):
        ok = await publish_offer(target_channel, product, affiliate_url)
        if ok:
            print("✅ Oferta publicada completa (source).")
            return
        wait = (PRODUCT_RETRY_BASE_SECONDS * (2 ** (attempt - 1))) + random.uniform(0.0, 1.0)
        wait = min(wait, 30.0)
        print(f"⚠️ Falló envío con foto (intento {attempt}/{PRODUCT_MAX_RETRIES}). Reintento en {wait:.1f}s")
        await asyncio.sleep(wait)
        product = await fetch_product_complete(asin)
        if not product:
            break

    await safe_send_message(target_channel, build_message(product, affiliate_url), parse_mode="md")

async def process_target_message(event):
    text = (event.raw_text or "").strip()
    if not re.match(r'^https?://\S+$', text):
        return

    asin = resolve_amazon_link(text)
    if not asin:
        return

    await event.delete()

    affiliate_url = build_affiliate_url(asin)

    product = await fetch_product_complete(asin)
    if not product:
        await safe_send_message(target_channel, f"🔰 {affiliate_url}", parse_mode="md")
        return

    for attempt in range(1, PRODUCT_MAX_RETRIES + 1):
        ok = await publish_offer(target_channel, product, affiliate_url)
        if ok:
            print("🎉 Paste con oferta completa OK")
            return
        wait = (PRODUCT_RETRY_BASE_SECONDS * (2 ** (attempt - 1))) + random.uniform(0.0, 1.0)
        wait = min(wait, 30.0)
        print(f"⚠️ Falló envío con foto (paste) intento {attempt}/{PRODUCT_MAX_RETRIES}. Reintento en {wait:.1f}s")
        await asyncio.sleep(wait)
        product = await fetch_product_complete(asin)
        if not product:
            break

    await safe_send_message(target_channel, build_message(product, affiliate_url), parse_mode="md")

# ==============================
# MAIN
# ==============================
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 BOT CHOLLOS v2.6 (modo estricto + reintentos) ACTIVADO ✅")
    print(f"✅ {source_channel} → {target_channel}")
    print(f"✅ REQUIRED_FIELDS={REQUIRED_FIELDS} | PRODUCT_MAX_RETRIES={PRODUCT_MAX_RETRIES}")

    @client.on(events.NewMessage(chats=source_channel))
    async def handler_source(event):
        await process_source_message(event)

    @client.on(events.NewMessage(chats=target_channel))
    async def handler_target(event):
        await process_target_message(event)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
