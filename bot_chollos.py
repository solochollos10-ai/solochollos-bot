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
from html import escape
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

source_channel = os.getenv("SOURCE_CHANNEL", "@chollosdeluxe")
target_channel = os.getenv("TARGET_CHANNEL", "@solochollos10")

PRODUCT_MAX_RETRIES = int(os.getenv("PRODUCT_MAX_RETRIES", "6"))
PRODUCT_RETRY_BASE_SECONDS = float(os.getenv("PRODUCT_RETRY_BASE_SECONDS", "2.0"))
REQUIRED_FIELDS = [x.strip() for x in os.getenv("REQUIRED_FIELDS", "title,price,image").split(",") if x.strip()]
PAAPI_MIN_INTERVAL_SECONDS = float(os.getenv("PAAPI_MIN_INTERVAL_SECONDS", "1.1"))

TEMPLATE_IMAGE_PATH = os.getenv("TEMPLATE_IMAGE_PATH", "plantilla.jpg")
PRODUCT_MAX_SIZE = int(os.getenv("PRODUCT_MAX_SIZE", "1280"))
PRODUCT_BORDER = int(os.getenv("PRODUCT_BORDER", "10"))
PRODUCT_BORDER_COLOR = tuple(map(int, os.getenv("PRODUCT_BORDER_COLOR", "255,165,0").split(",")))
CANVAS_BG_COLOR = tuple(map(int, os.getenv("CANVAS_BG_COLOR", "255,255,255").split(",")))
TEMPLATE_MARGIN_TOP = int(os.getenv("TEMPLATE_MARGIN_TOP", "0"))
TEMPLATE_SIDE_PADDING = int(os.getenv("TEMPLATE_SIDE_PADDING", "0"))
TEMPLATE_BOTTOM_PADDING = int(os.getenv("TEMPLATE_BOTTOM_PADDING", "0"))
UPSCALE_TEMPLATE_TO_PRODUCT = os.getenv("UPSCALE_TEMPLATE_TO_PRODUCT", "true").lower() == "true"

client = TelegramClient("session_bot_chollos", api_id, api_hash)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

http = requests.Session()


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


def clean_text(text):
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def normalize_price(text):
    text = clean_text(text).replace("€", "")
    text = text.replace(".", "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d{1,2})?)", text)
    if not m:
        return None
    value = m.group(1)
    if "." in value:
        whole, frac = value.split(".", 1)
        value = whole + "." + frac[:2].ljust(2, "0")
    else:
        value = value + ".00"
    return f"{float(value):.2f}€".replace(".", ",")


def normalize_rating(text):
    text = clean_text(text).replace(",", ".")
    m = re.search(r"(\d+(?:\.\d)?)", text)
    return m.group(1).replace(".", ",") if m else None


def normalize_reviews_count(text):
    text = clean_text(text)
    m = re.search(r"(\d[\d\.,]*)", text)
    if not m:
        return None
    return re.sub(r"[^\d]", "", m.group(1))


def first_text(soup, selectors):
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            txt = clean_text(node.get_text(" ", strip=True))
            if txt:
                return txt
    return None


def first_attr(soup, selectors, attr):
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            txt = clean_text(node.get(attr) or "")
            if txt:
                return txt
    return None


def extract_now_price(soup):
    selectors = [
        "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price.aok-align-center .a-offscreen",
        "#corePrice_feature_div .priceToPay .a-offscreen",
        "#corePrice_feature_div .a-price .a-offscreen",
        "#apex_desktop .a-price .a-offscreen",
        ".offer-display-feature-text .a-price .a-offscreen",
        "#priceblock_dealprice",
        "#priceblock_ourprice",
    ]
    return normalize_price(first_text(soup, selectors))


def extract_old_price(soup):
    selectors = [
        "#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-text-price .a-offscreen",
        "#corePrice_feature_div .basisPrice .a-offscreen",
        "#corePrice_feature_div .a-text-price .a-offscreen",
        ".priceBlockStrikePriceString",
    ]
    return normalize_price(first_text(soup, selectors))


def extract_rating(soup):
    txt = first_attr(soup, ["#acrPopover"], "title")
    if not txt:
        txt = first_text(soup, [
            "#averageCustomerReviews_feature_div .a-icon-alt",
            "#acrPopover .a-size-base.a-color-base",
        ])
    return normalize_rating(txt)


def extract_reviews_text(soup):
    txt = first_text(soup, ["#acrCustomerReviewText"])
    count = normalize_reviews_count(txt)
    return f"{count} opiniones" if count else ""


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
        r = http.post(PAAPI_ENDPOINT, data=request_body, headers=headers, timeout=20)
        if r.status_code != 200:
            print(f"⚠️ PAAPI HTTP {r.status_code}: {r.text[:200]}")
            return None

        data = r.json()
        items = (data.get("ItemsResult") or {}).get("Items") or []
        if not items:
            return None

        item = items[0]
        title = (((item.get("ItemInfo") or {}).get("Title") or {}).get("DisplayValue")) or None
        img_url = (((((item.get("Images") or {}).get("Primary") or {}).get("Large") or {}).get("URL")) or None)

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
            "image": img_url,
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

            r = http.get(current, headers=get_random_headers(), allow_redirects=False, timeout=15)
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
        r = http.get(url, headers=get_random_headers(), timeout=15)
        if ("captcha" in r.text.lower()) or ("validateCaptcha" in r.text):
            print("🛑 CAPTCHA detectado en HTML (fallback).")
            return None

        soup = BeautifulSoup(r.text, "lxml")

        title = first_text(soup, [
            "#productTitle",
            "span.a-size-large.a-color-base.a-text-normal",
        ])

        price = extract_now_price(soup)
        old_price = extract_old_price(soup)
        rating = extract_rating(soup)
        reviews_text = extract_reviews_text(soup)

        img_url = None
        landing = soup.select_one("#landingImage")
        if landing:
            img_url = landing.get("data-old-hires") or landing.get("data-a-hires") or landing.get("src")

        if not img_url:
            wrapper = soup.find(id="imgTagWrapperId")
            if wrapper and wrapper.get("data-a-dynamic-image"):
                try:
                    dynamic_data = json.loads(wrapper["data-a-dynamic-image"])
                    best_img = max(dynamic_data.items(), key=lambda x: x[1][1])[0]
                    img_url = best_img.replace("\\\\", "")
                except Exception:
                    pass

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
            "image": img_url,
        }
    except Exception as e:
        print("Error scraping HTML:", e)
        return None


async def fetch_product_once(asin):
    pa = await paapi_get_product_throttled(asin)
    if pa:
        return pa
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
        wait = min(wait, 40.0)
        print(f"⚠️ Producto incompleto (intento {attempt}/{PRODUCT_MAX_RETRIES}). Faltan: {missing}. Reintento en {wait:.1f}s")
        await asyncio.sleep(wait)

    print("❌ No se pudo obtener producto completo tras reintentos.")
    return last_product


# ==============================
# IMAGEN FINAL: PRODUCTO + PLANTILLA
# ==============================
def _resample_filter():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        try:
            return Image.LANCZOS
        except AttributeError:
            return Image.BICUBIC


def open_local_template():
    if not os.path.exists(TEMPLATE_IMAGE_PATH):
        raise FileNotFoundError(f"No existe la plantilla: {TEMPLATE_IMAGE_PATH}")
    return Image.open(TEMPLATE_IMAGE_PATH).convert("RGB")


def prepare_product_image(img):
    img = img.convert("RGB")

    max_size = (PRODUCT_MAX_SIZE, PRODUCT_MAX_SIZE)
    img.thumbnail(max_size, _resample_filter())

    if PRODUCT_BORDER > 0:
        img = ImageOps.expand(img, border=PRODUCT_BORDER, fill=PRODUCT_BORDER_COLOR)

    return img


def resize_template_to_width(template_img, target_width):
    if TEMPLATE_SIDE_PADDING * 2 >= target_width:
        usable_width = target_width
    else:
        usable_width = target_width - (TEMPLATE_SIDE_PADDING * 2)

    if usable_width <= 0:
        usable_width = target_width

    if template_img.width == usable_width:
        return template_img

    if template_img.width < usable_width and not UPSCALE_TEMPLATE_TO_PRODUCT:
        return template_img

    new_height = int(template_img.height * (usable_width / template_img.width))
    return template_img.resize((usable_width, new_height), _resample_filter())


def compose_offer_image(product_img):
    product_img = prepare_product_image(product_img)
    template_img = open_local_template()
    template_img = resize_template_to_width(template_img, product_img.width)

    canvas_width = max(product_img.width, template_img.width + (TEMPLATE_SIDE_PADDING * 2))
    canvas_height = (
        product_img.height
        + TEMPLATE_MARGIN_TOP
        + template_img.height
        + TEMPLATE_BOTTOM_PADDING
    )

    canvas = Image.new("RGB", (canvas_width, canvas_height), CANVAS_BG_COLOR)

    product_x = (canvas_width - product_img.width) // 2
    template_x = (canvas_width - template_img.width) // 2
    template_y = product_img.height + TEMPLATE_MARGIN_TOP

    canvas.paste(product_img, (product_x, 0))
    canvas.paste(template_img, (template_x, template_y))

    return canvas


# ==============================
# ENVÍO A TELEGRAM
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
    title = escape(product.get("title") or "Producto Amazon")
    rating = escape(product.get("rating") or "")
    reviews = escape(product.get("reviews") or "")
    price = escape((product.get("price") or "").replace(",,", ","))
    old_price = escape(product.get("old_price") or "")

    lines = [
        "🔥🔥🔥 <b>OFERTA AMAZON</b> 🔥🔥🔥",
        f"<b>{title}</b>",
    ]

    if rating and reviews:
        lines.append(f"⭐ {rating} · {reviews}")
    elif rating:
        lines.append(f"⭐ {rating}")
    elif reviews:
        lines.append(f"🗳️ {reviews}")

    if price and old_price:
        lines.append(f"🟢 <b>AHORA {price}</b> 🔴 <s>ANTES: {old_price}</s>")
    elif price:
        lines.append(f"🟢 <b>AHORA {price}</b>")

    lines.append(f"🔰 {escape(affiliate_url)}")
    return "\n".join(lines)


async def publish_offer(target, product, affiliate_url):
    message = build_message(product, affiliate_url)

    img_url = product.get("image")
    if not img_url:
        await safe_send_message(target, message, parse_mode="html")
        return True

    try:
        resp = http.get(img_url, headers=get_random_headers(), timeout=20)
        content_type = resp.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            raise ValueError(f"Contenido no imagen: {content_type}")

        product_img = Image.open(BytesIO(resp.content)).convert("RGB")
        final_img = compose_offer_image(product_img)

        bio = BytesIO()
        bio.name = "product_with_template.jpg"
        final_img.save(bio, "JPEG", quality=95)
        bio.seek(0)

        await safe_send_file(target, bio, caption=message, parse_mode="html")
        return True
    except Exception as e:
        print(f"Error publicando imagen: {e}")
        return False


# ==============================
# HANDLERS
# ==============================
async def process_source_message(event):
    text = event.raw_text or ""
    links = re.findall(r"(https?://\S+)", text)
    if not links:
        return

    amazon_link = None
    for link in links:
        if "amzn.to" in link or "amazon.es" in link:
            amazon_link = link
            break
    if not amazon_link:
        return

    await safe_send_message(target_channel, amazon_link)

    asin = resolve_amazon_link(amazon_link)
    if not asin:
        return

    affiliate_url = build_affiliate_url(asin)

    product = await fetch_product_complete(asin)
    if not product:
        await safe_send_message(target_channel, f"🔰 {affiliate_url}", parse_mode="html")
        return

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

    await safe_send_message(target_channel, build_message(product, affiliate_url), parse_mode="html")


async def process_target_message(event):
    text = (event.raw_text or "").strip()
    if not re.match(r"^https?://\S+$", text):
        return

    asin = resolve_amazon_link(text)
    if not asin:
        return

    await event.delete()

    affiliate_url = build_affiliate_url(asin)

    product = await fetch_product_complete(asin)
    if not product:
        await safe_send_message(target_channel, f"🔰 {affiliate_url}", parse_mode="html")
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

    await safe_send_message(target_channel, build_message(product, affiliate_url), parse_mode="html")


# ==============================
# MAIN
# ==============================
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 BOT CHOLLOS v2.8 (plantilla inferior en imagen) ACTIVADO ✅")
    print(f"✅ {source_channel} → {target_channel}")
    print(f"✅ REQUIRED_FIELDS={REQUIRED_FIELDS} | PRODUCT_MAX_RETRIES={PRODUCT_MAX_RETRIES}")
    print(f"✅ TEMPLATE_IMAGE_PATH={TEMPLATE_IMAGE_PATH}")

    @client.on(events.NewMessage(chats=source_channel))
    async def handler_source(event):
        await process_source_message(event)

    @client.on(events.NewMessage(chats=target_channel))
    async def handler_target(event):
        await process_target_message(event)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
