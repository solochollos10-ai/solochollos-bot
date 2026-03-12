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
from PIL import Image
from io import BytesIO

# ==============================
# VARIABLES DE ENTORNO (RAILWAY)
# ==============================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
affiliate_tag = os.getenv("AFFILIATE_TAG", "solochollos08-21")

paapi_access_key = os.getenv("PAAPI_ACCESS_KEY")
paapi_secret_key = os.getenv("PAAPI_SECRET_KEY")

source_channel = os.getenv("SOURCE_CHANNEL", "@chollosdeluxe")
target_channel = os.getenv("TARGET_CHANNEL", "@solochollos10")

PRODUCT_MAX_RETRIES = int(os.getenv("PRODUCT_MAX_RETRIES", "4"))
PRODUCT_RETRY_BASE_SECONDS = float(os.getenv("PRODUCT_RETRY_BASE_SECONDS", "1.8"))
REQUIRED_FIELDS = [x.strip() for x in os.getenv("REQUIRED_FIELDS", "title,price,image").split(",") if x.strip()]
PAAPI_MIN_INTERVAL_SECONDS = float(os.getenv("PAAPI_MIN_INTERVAL_SECONDS", "1.1"))

# ==============================
# PLANTILLA / COMPOSICIÓN
# ==============================
TEMPLATE_IMAGE_PATH = os.getenv("TEMPLATE_IMAGE_PATH", "plantilla.jpg")

SAFE_MARGIN_LEFT = int(os.getenv("SAFE_MARGIN_LEFT", "35"))
SAFE_MARGIN_RIGHT = int(os.getenv("SAFE_MARGIN_RIGHT", "35"))
SAFE_MARGIN_TOP = int(os.getenv("SAFE_MARGIN_TOP", "125"))
SAFE_MARGIN_BOTTOM = int(os.getenv("SAFE_MARGIN_BOTTOM", "135"))
PRODUCT_INNER_PADDING = int(os.getenv("PRODUCT_INNER_PADDING", "8"))
PRODUCT_SCALE_BOOST = float(os.getenv("PRODUCT_SCALE_BOOST", "1.15"))
PRODUCT_BORDER = int(os.getenv("PRODUCT_BORDER", "0"))
OUTPUT_BG_COLOR = tuple(map(int, os.getenv("OUTPUT_BG_COLOR", "255,255,255").split(",")))
OUTPUT_QUALITY = int(os.getenv("OUTPUT_QUALITY", "95"))

client = TelegramClient("session_bot_chollos", api_id, api_hash)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

http = requests.Session()
PAAPI_DISABLED = False


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
    if not text:
        return None

    text = clean_text(text)
    text = text.replace("€", "").replace("EUR", "").replace("\u202f", " ").replace("\xa0", " ").strip()
    m = re.search(r"(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})|\d+(?:,\d{2})|\d+(?:\.\d{2}))", text)
    if not m:
        return None

    value = m.group(1).replace(" ", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    else:
        if value.count(".") > 1:
            value = value.replace(".", "")

    try:
        return f"{float(value):.2f}€".replace(".", ",")
    except Exception:
        return None


def price_to_float(price_text):
    if not price_text:
        return None

    txt = clean_text(str(price_text))
    txt = txt.replace("€", "").replace("EUR", "").replace("\u202f", " ").replace("\xa0", " ").strip()

    m = re.search(r"(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})|\d+(?:,\d{2})|\d+(?:\.\d{2})|\d+)", txt)
    if not m:
        return None

    value = m.group(1).replace(" ", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    else:
        if value.count(".") > 1:
            value = value.replace(".", "")

    try:
        return float(value)
    except Exception:
        return None


def has_invalid_price_relation(product):
    if not product:
        return False

    now_price = price_to_float(product.get("price"))
    old_price = price_to_float(product.get("old_price"))

    if now_price is None or old_price is None:
        return False

    return old_price < now_price


def sanitize_price_relation(product):
    if not product:
        return product

    cleaned = dict(product)
    if has_invalid_price_relation(cleaned):
        print(
            f"⚠️ old_price inválido detectado y eliminado antes de publicar. "
            f"old_price={cleaned.get('old_price')} | price={cleaned.get('price')}"
        )
        cleaned["old_price"] = None
    return cleaned


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


def first_price_from_selectors(soup, selectors):
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            txt = node.get("content") or node.get("value") or node.get_text(" ", strip=True)
            price = normalize_price(txt)
            if price:
                return price
    return None


def price_from_whole_fraction(container):
    if not container:
        return None

    whole = container.select_one(".a-price-whole")
    frac = container.select_one(".a-price-fraction")
    if whole and frac:
        txt = f"{clean_text(whole.get_text())},{clean_text(frac.get_text())}"
        price = normalize_price(txt)
        if price:
            return price

    offscreen = container.select_one(".a-offscreen")
    if offscreen:
        price = normalize_price(offscreen.get_text(" ", strip=True))
        if price:
            return price

    text = clean_text(container.get_text(" ", strip=True))
    return normalize_price(text)


def price_from_json_ld(soup):
    scripts = soup.select('script[type="application/ld+json"]')
    for script in scripts:
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                offers = item.get("offers")
                if isinstance(offers, dict):
                    price = offers.get("price") or offers.get("lowPrice")
                    normalized = normalize_price(str(price)) if price else None
                    if normalized:
                        return normalized
        except Exception:
            continue
    return None


def extract_now_price(soup):
    direct_selectors = [
        "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .reinventPricePriceToPayMargin .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price.aok-align-center .a-offscreen",
        "#corePrice_feature_div .priceToPay .a-offscreen",
        "#corePrice_feature_div .reinventPricePriceToPayMargin .a-offscreen",
        "#corePrice_feature_div .a-price .a-offscreen",
        "#apex_desktop .priceToPay .a-offscreen",
        "#apex_desktop .a-price .a-offscreen",
        ".apexPriceToPay .a-offscreen",
        ".priceToPay .a-offscreen",
        ".reinventPricePriceToPayMargin .a-offscreen",
        "#priceblock_dealprice",
        "#priceblock_ourprice",
        "#price_inside_buybox",
        "input#attach-base-product-price",
        "span[data-a-color='price'] .a-offscreen",
        "span[data-a-size='xl'] .a-offscreen",
    ]

    price = first_price_from_selectors(soup, direct_selectors)
    if price:
        return price

    block_selectors = [
        "#corePriceDisplay_desktop_feature_div .priceToPay",
        "#corePriceDisplay_desktop_feature_div .a-price",
        "#corePrice_feature_div .priceToPay",
        "#corePrice_feature_div .a-price",
        "#apex_desktop .priceToPay",
        "#apex_desktop .a-price",
        ".priceToPay",
        ".apex-pricetopay-value",
        ".a-price",
    ]

    for selector in block_selectors:
        container = soup.select_one(selector)
        price = price_from_whole_fraction(container)
        if price:
            return price

    label = soup.select_one("#apex-pricetopay-accessibility-label")
    if label:
        price = normalize_price(label.get_text(" ", strip=True))
        if price:
            return price

    price = price_from_json_ld(soup)
    if price:
        return price

    page_text = clean_text(soup.get_text(" ", strip=True))
    patterns = [
        r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*€\s*con un ahorro",
        r"Oferta de Primavera.*?(\d{1,3}(?:\.\d{3})*,\d{2})\s*€",
        r"Compra única.*?(\d{1,3}(?:\.\d{3})*,\d{2})\s*€",
        r"Precio:\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*€",
    ]

    for pattern in patterns:
        m = re.search(pattern, page_text, re.I)
        if m:
            price = normalize_price(m.group(1))
            if price:
                return price

    return None


def extract_old_price(soup):
    direct_selectors = [
        "#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-text-price .a-offscreen",
        "#corePrice_feature_div .basisPrice .a-offscreen",
        "#corePrice_feature_div .a-text-price .a-offscreen",
        ".priceBlockStrikePriceString",
        ".basisPrice .a-offscreen",
        ".a-text-price .a-offscreen",
    ]

    price = first_price_from_selectors(soup, direct_selectors)
    if price:
        return price

    page_text = clean_text(soup.get_text(" ", strip=True))
    patterns = [
        r"Precio recomendado:?\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*€",
        r"Precio mediano:?\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*€",
        r"El precio más bajo de los últimos 30 días:?\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*€",
    ]

    for pattern in patterns:
        m = re.search(pattern, page_text, re.I)
        if m:
            price = normalize_price(m.group(1))
            if price:
                return price

    return None


def extract_rating(soup):
    txt = first_attr(soup, ["#acrPopover"], "title")
    if not txt:
        txt = first_text(soup, [
            "#averageCustomerReviews_feature_div .a-icon-alt",
            "#acrPopover .a-size-base.a-color-base",
        ])

    if txt:
        return normalize_rating(txt)

    scripts = soup.select('script[type="application/ld+json"]')
    for script in scripts:
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                agg = item.get("aggregateRating")
                if isinstance(agg, dict) and agg.get("ratingValue"):
                    return normalize_rating(str(agg.get("ratingValue")))
        except Exception:
            continue

    return None


def extract_reviews_text(soup):
    txt = first_text(soup, ["#acrCustomerReviewText"])
    count = normalize_reviews_count(txt)
    if count:
        return f"{count} opiniones"

    scripts = soup.select('script[type="application/ld+json"]')
    for script in scripts:
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                agg = item.get("aggregateRating")
                if isinstance(agg, dict) and agg.get("ratingCount"):
                    return f"{normalize_reviews_count(str(agg.get('ratingCount')))} opiniones"
        except Exception:
            continue

    return ""


def extract_image_url(soup):
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

    if not img_url:
        scripts = soup.select('script[type="application/ld+json"]')
        for script in scripts:
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
                candidates = data if isinstance(data, list) else [data]
                for item in candidates:
                    if not isinstance(item, dict):
                        continue
                    image = item.get("image")
                    if isinstance(image, str):
                        return image
                    if isinstance(image, list) and image:
                        return image[0]
            except Exception:
                continue

    return img_url


def merge_products(primary, fallback):
    primary = primary or {}
    fallback = fallback or {}
    merged = {}
    keys = ["title", "price", "old_price", "rating", "reviews", "image"]
    for key in keys:
        merged[key] = primary.get(key) or fallback.get(key)
    return merged


# ==============================
# AMAZON: RESOLUCIÓN DE ENLACES
# ==============================
def extract_asin(url):
    url = (url or "").split("?")[0].strip()

    patterns = [
        r"/dp/([A-Z0-9]{10})",
        r"/gp/product/([A-Z0-9]{10})",
        r"/product/([A-Z0-9]{10})",
        r"/ASIN/([A-Z0-9]{10})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    direct = re.search(r"\b([A-Z0-9]{10})\b", url, re.IGNORECASE)
    if direct:
        return direct.group(1).upper()

    return None


def resolve_amazon_link(url):
    try:
        current = (url or "").strip()

        asin_here = extract_asin(current)
        if asin_here:
            return asin_here

        r = http.get(current, headers=get_random_headers(), allow_redirects=True, timeout=15)
        final_url = str(r.url).split("?")[0]
        asin_final = extract_asin(final_url)
        if asin_final:
            return asin_final

        loc = r.headers.get("Location")
        if loc:
            if loc.startswith("/"):
                loc = "https://www.amazon.es" + loc
            elif not loc.startswith("http"):
                loc = "https://" + loc.lstrip("/")
            return extract_asin(loc)

        return None
    except Exception as e:
        print(f"Error resolviendo enlace: {e}")
        return None


def build_affiliate_url(asin):
    return f"https://www.amazon.es/dp/{asin}/?tag={affiliate_tag}"


# ==============================
# AMAZON PA-API
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
    global PAAPI_DISABLED

    if PAAPI_DISABLED:
        return None

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

    t = datetime.datetime.now(datetime.timezone.utc)
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

        if r.status_code == 403 and "AssociateNotEligible" in r.text:
            PAAPI_DISABLED = True
            print("⛔ PAAPI desactivada: AssociateNotEligible. Se usará solo scraping HTML.")
            return None

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
            "price": normalize_price(price) if price else None,
            "old_price": normalize_price(old_price) if old_price else None,
            "rating": normalize_rating(str(rating)) if rating else None,
            "reviews": reviews_text,
            "image": img_url
        }
    except Exception as e:
        print(f"Error PAAPI: {e}")
        return None


async def paapi_get_product_throttled(asin):
    global _paapi_last_call

    if PAAPI_DISABLED:
        return None

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
# SCRAPING HTML AMAZON
# ==============================
def scrape_amazon_page_sync(url):
    try:
        r = http.get(url, headers=get_random_headers(), timeout=18)
        if ("captcha" in r.text.lower()) or ("validateCaptcha" in r.text):
            print("🛑 CAPTCHA detectado en HTML.")
            return None

        soup = BeautifulSoup(r.text, "lxml")

        title = first_text(soup, [
            "#productTitle",
            "span.a-size-large.a-color-base.a-text-normal",
            "h1 span",
        ])

        price = extract_now_price(soup)
        old_price = extract_old_price(soup)
        rating = extract_rating(soup)
        reviews_text = extract_reviews_text(soup)
        img_url = extract_image_url(soup)

        return {
            "title": title,
            "price": price,
            "old_price": old_price,
            "rating": rating,
            "reviews": reviews_text,
            "image": img_url
        }
    except Exception as e:
        print(f"Error scraping HTML en {url}: {e}")
        return None


def scrape_amazon_product_html_sync(asin):
    urls = [
        f"https://www.amazon.es/dp/{asin}",
        f"https://www.amazon.es/dp/{asin}?th=1&psc=1&language=es_ES",
        f"https://www.amazon.es/gp/product/{asin}?language=es_ES",
    ]

    merged = {}
    for url in urls:
        data = scrape_amazon_page_sync(url)
        merged = merge_products(merged, data)
        if merged.get("title") and merged.get("price") and merged.get("image"):
            break

    return merged if merged else None


async def fetch_product_once(asin):
    html_product = await asyncio.to_thread(scrape_amazon_product_html_sync, asin)
    pa_product = await paapi_get_product_throttled(asin)
    return merge_products(html_product, pa_product)


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
        invalid_price_relation = has_invalid_price_relation(prod)

        if not missing and not invalid_price_relation:
            return sanitize_price_relation(prod)

        wait = (PRODUCT_RETRY_BASE_SECONDS * (2 ** (attempt - 1))) + random.uniform(0.0, 0.8)
        wait = min(wait, 18.0)

        if invalid_price_relation:
            print(
                f"⚠️ Relación de precios inválida (intento {attempt}/{PRODUCT_MAX_RETRIES}). "
                f"ANTES={prod.get('old_price')} | AHORA={prod.get('price')}. "
                f"Reintentando en {wait:.1f}s"
            )
        else:
            print(
                f"⚠️ Producto incompleto (intento {attempt}/{PRODUCT_MAX_RETRIES}). "
                f"Faltan: {missing}. Reintento en {wait:.1f}s"
            )

        await asyncio.sleep(wait)

    print("❌ No se pudo obtener producto completamente válido tras reintentos.")
    return sanitize_price_relation(last_product)


# ==============================
# IMAGEN FINAL
# ==============================
def get_resample_filter():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        try:
            return Image.LANCZOS
        except AttributeError:
            return Image.BICUBIC


def open_template_image():
    if not os.path.exists(TEMPLATE_IMAGE_PATH):
        raise FileNotFoundError(f"No existe la plantilla: {TEMPLATE_IMAGE_PATH}")
    return Image.open(TEMPLATE_IMAGE_PATH).convert("RGB")


def fit_image_inside_box(img, max_w, max_h):
    if max_w <= 0 or max_h <= 0:
        raise ValueError("La zona segura de la plantilla no es válida.")

    img = img.convert("RGB")
    ratio = min(max_w / img.width, max_h / img.height)
    new_w = max(1, int(img.width * ratio))
    new_h = max(1, int(img.height * ratio))
    return img.resize((new_w, new_h), get_resample_filter())


def scale_image(img, factor):
    new_w = max(1, int(img.width * factor))
    new_h = max(1, int(img.height * factor))
    return img.resize((new_w, new_h), get_resample_filter())


def compose_product_on_template(product_img, product=None):
    template = open_template_image()
    product_img = product_img.convert("RGB")

    usable_left = SAFE_MARGIN_LEFT + PRODUCT_INNER_PADDING
    usable_top = SAFE_MARGIN_TOP + PRODUCT_INNER_PADDING
    usable_right = template.width - SAFE_MARGIN_RIGHT - PRODUCT_INNER_PADDING
    usable_bottom = template.height - SAFE_MARGIN_BOTTOM - PRODUCT_INNER_PADDING

    usable_width = usable_right - usable_left
    usable_height = usable_bottom - usable_top

    product_fitted = fit_image_inside_box(product_img, usable_width, usable_height)
    product_scaled = scale_image(product_fitted, PRODUCT_SCALE_BOOST)

    if product_scaled.width <= usable_width and product_scaled.height <= usable_height:
        final_product = product_scaled
    else:
        final_product = fit_image_inside_box(product_scaled, usable_width, usable_height)

    canvas = Image.new("RGB", template.size, OUTPUT_BG_COLOR)
    canvas.paste(template, (0, 0))

    x = usable_left + (usable_width - final_product.width) // 2
    y = usable_top + (usable_height - final_product.height) // 2
    canvas.paste(final_product, (x, y))

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
    product = sanitize_price_relation(product)

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
    product = sanitize_price_relation(product)
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
        final_img = compose_product_on_template(product_img, product)

        bio = BytesIO()
        bio.name = "product_template.jpg"
        final_img.save(bio, "JPEG", quality=OUTPUT_QUALITY)
        bio.seek(0)

        await safe_send_file(target, bio, caption=message, parse_mode="html")
        return True
    except Exception as e:
        print(f"Error publicando imagen: {e}")
        await safe_send_message(target, message, parse_mode="html")
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

    await safe_send_message(target_channel, amazon_link)

    asin = resolve_amazon_link(amazon_link)
    if not asin:
        print(f"❌ No se pudo resolver ASIN desde enlace source: {amazon_link}")
        return

    affiliate_url = build_affiliate_url(asin)
    product = await fetch_product_complete(asin)

    if not product:
        await safe_send_message(target_channel, f"🔰 {affiliate_url}", parse_mode="html")
        return

    await publish_offer(target_channel, product, affiliate_url)
    print("✅ Oferta procesada desde source.")


async def process_target_message(event):
    text = (event.raw_text or "").strip()
    if not re.match(r'^https?://\S+$', text):
        return

    asin = resolve_amazon_link(text)
    if not asin:
        print(f"❌ No se pudo resolver ASIN desde enlace target: {text}")
        return

    await event.delete()

    affiliate_url = build_affiliate_url(asin)
    product = await fetch_product_complete(asin)

    if not product:
        await safe_send_message(target_channel, f"🔰 {affiliate_url}", parse_mode="html")
        return

    await publish_offer(target_channel, product, affiliate_url)
    print("🎉 Paste con oferta completa OK")


# ==============================
# MAIN
# ==============================
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 BOT CHOLLOS v3.7 (validación de precios) ACTIVADO ✅")
    print(f"✅ {source_channel} → {target_channel}")
    print(f"✅ REQUIRED_FIELDS={REQUIRED_FIELDS} | PRODUCT_MAX_RETRIES={PRODUCT_MAX_RETRIES}")
    print(f"✅ TEMPLATE_IMAGE_PATH={TEMPLATE_IMAGE_PATH}")
    print(f"✅ SAFE ZONE: left={SAFE_MARGIN_LEFT}, right={SAFE_MARGIN_RIGHT}, top={SAFE_MARGIN_TOP}, bottom={SAFE_MARGIN_BOTTOM}")
    print(f"✅ PRODUCT_SCALE_BOOST={PRODUCT_SCALE_BOOST} | PRODUCT_BORDER={PRODUCT_BORDER}")
    print("✅ Regla activa: old_price nunca puede ser menor que price")

    @client.on(events.NewMessage(chats=source_channel))
    async def handler_source(event):
        await process_source_message(event)

    @client.on(events.NewMessage(chats=target_channel))
    async def handler_target(event):
        await process_target_message(event)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
