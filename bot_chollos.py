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
# CONFIG IMAGEN
# ==============================

TEMPLATE_PATH = "plantilla.jpg"

# ==============================
# VARIABLES DE ENTORNO
# ==============================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
affiliate_tag = os.getenv("AFFILIATE_TAG")

source_channel = "@chollosdeluxe"
target_channel = "@solochollos10"

client = TelegramClient("session_bot_chollos", api_id, api_hash)

http = requests.Session()

# ==============================
# HEADERS
# ==============================

USER_AGENTS = [
"Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
"Mozilla/5.0 (X11; Linux x86_64)"
]

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS)
    }

# ==============================
# MENSAJE
# ==============================

def build_message(product, affiliate_url):

    title = escape(product.get("title") or "Producto Amazon")
    rating = escape(product.get("rating") or "")
    reviews = escape(product.get("reviews") or "")
    price = escape(product.get("price") or "")
    old_price = escape(product.get("old_price") or "")

    lines = [
        "🔥🔥🔥 <b>OFERTA AMAZON</b> 🔥🔥🔥",
        f"<b>{title}</b>",
    ]

    if rating:
        lines.append(f"⭐ {rating} {reviews}")

    if price and old_price:
        lines.append(f"🟢 <b>{price}</b> 🔴 <s>{old_price}</s>")
    elif price:
        lines.append(f"🟢 <b>{price}</b>")

    lines.append(f"🔰 {affiliate_url}")

    return "\n".join(lines)

# ==============================
# CREAR IMAGEN OFERTA
# ==============================

def create_offer_image(product_image_bytes):

    fondo = Image.open(TEMPLATE_PATH).convert("RGB")

    producto = Image.open(BytesIO(product_image_bytes)).convert("RGBA")

    fondo_w, fondo_h = fondo.size

    max_w = int(fondo_w * 0.65)
    max_h = int(fondo_h * 0.65)

    producto.thumbnail((max_w, max_h), Image.LANCZOS)

    prod_w, prod_h = producto.size

    x = (fondo_w - prod_w) // 2
    y = (fondo_h - prod_h) // 2

    fondo.paste(producto, (x, y), producto)

    salida = BytesIO()
    salida.name = "oferta.jpg"

    fondo.save(salida, "JPEG", quality=95)
    salida.seek(0)

    return salida

# ==============================
# ENVIO TELEGRAM
# ==============================

async def safe_send_message(chat, text, **kwargs):
    while True:
        try:
            return await client.send_message(chat, text, **kwargs)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)

async def safe_send_file(chat, file, **kwargs):
    while True:
        try:
            return await client.send_file(chat, file, **kwargs)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)

# ==============================
# PUBLICAR OFERTA
# ==============================

async def publish_offer(target, product, affiliate_url):

    message = build_message(product, affiliate_url)
    img_url = product.get("image")

    if not img_url:
        await safe_send_message(target, message, parse_mode="html")
        return

    try:

        resp = http.get(img_url, headers=get_random_headers(), timeout=20)

        if not resp.headers.get("content-type","").startswith("image"):
            raise ValueError("No es imagen")

        final_img = create_offer_image(resp.content)

        await safe_send_file(
            target,
            final_img,
            caption=message,
            parse_mode="html"
        )

    except Exception as e:

        print("Error creando imagen:", e)

        await safe_send_message(target, message, parse_mode="html")

# ==============================
# HANDLER SIMPLE
# ==============================

@client.on(events.NewMessage(chats=source_channel))
async def handler_source(event):

    text = event.raw_text or ""

    links = re.findall(r'(https?://\S+)', text)

    if not links:
        return

    amazon_link = links[0]

    product = {
        "title": "Producto Amazon",
        "price": "",
        "old_price": "",
        "rating": "",
        "reviews": "",
        "image": amazon_link
    }

# ==============================
# MAIN
# ==============================

async def main():

    await client.start(bot_token=bot_token)

    print("BOT OFERTAS CON PLANTILLA ACTIVADO")

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
