# -*- coding: utf-8 -*-
"""
Анфиса — ИИ-менеджер Mari-Line
Flask (веб-виджет) + Telegram (@Afisa_bot) + gemini-2.0-flash + каталог 798 товаров

Переменные окружения Railway:
  TELEGRAM_TOKEN  — токен бота
  GEMINI_KEY      — ключ Google AI Studio
  PORT            — порт (Railway подставляет сам)
"""

import os
import json
import re
import logging
import threading
import asyncio
from collections import Counter
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from google import genai
from google.genai import types
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ─── Конфиг ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY     = os.environ.get("GEMINI_KEY")
PORT           = int(os.environ.get("PORT", 5000))

# ─── Каталог ─────────────────────────────────────────────────────────────────
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "mariline_catalog_clean.json")
_catalog: list | None = None

def load_catalog() -> list:
    global _catalog
    if _catalog is None:
        with open(CATALOG_PATH, encoding="utf-8") as f:
            _catalog = json.load(f).get("products", [])
        log.info("Каталог загружен: %d товаров", len(_catalog))
    return _catalog

def catalog_summary() -> str:
    products = load_catalog()
    cats = Counter(p["category"] for p in products)
    cat_str = ", ".join(f"{c} ({n})" for c, n in cats.most_common(7))
    return f"В каталоге {len(products)} позиций: {cat_str}."

CATEGORY_KEYWORDS = {
    "Платья":     ["платье", "платья", "сарафан"],
    "Блузы":      ["блуза", "блузка", "блузы"],
    "Юбки":       ["юбка", "юбки"],
    "Брюки":      ["брюки", "штаны"],
    "Костюмы":    ["костюм", "комплект"],
    "Джемперы":   ["джемпер", "пуловер"],
    "Кардиганы":  ["кардиган"],
    "Жакеты":     ["жакет", "пиджак"],
    "Туники":     ["туника"],
    "Топы":       ["топ"],
    "Комбинезоны":["комбинезон"],
    "Водолазки":  ["водолазка"],
}

def search_catalog(query: str, max_results: int = 5) -> str:
    products = load_catalog()
    q = query.lower()

    matched_cat = next(
        (cat for cat, kws in CATEGORY_KEYWORDS.items() if any(kw in q for kw in kws)),
        None
    )
    size_m = re.search(r"\b(4[02468]|5[02468]|6[0246])\b", query)
    target_size = size_m.group(0) if size_m else None

    scored = []
    for p in products:
        score = 0
        if matched_cat and p.get("category") == matched_cat:
            score += 10
        if target_size and target_size in p.get("sizes", ""):
            score += 5
        if p.get("article") and p["article"].lower() in q:
            score += 20
        for word in q.split():
            if len(word) > 3 and word in p.get("name", "").lower():
                score += 3
        if score > 0:
            scored.append((score, p))

    if not scored:
        return ""

    scored.sort(key=lambda x: -x[0])
    lines = ["Нашла в каталоге:"]
    for _, p in scored[:max_results]:
        price = f"{p['price']} ₽" if p.get("price") else "цена уточняется"
        line = f"• {p['name']}, арт. {p['article']} | размеры: {p.get('sizes') or 'не указаны'} | {price}"
        if p.get("composition"):
            line += f" | {p['composition']}"
        lines.append(line)
    return "\n".join(lines)

# ─── Системный промпт ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Ты — Анфиса, менеджер по продажам бренда Mari-Line (женская одежда, Новосибирск).

Правила:
- Ты женщина. Всегда женский род: «рада», «помогла», «ответила». Никогда мужской.
- Здоровайся только один раз — в самом первом сообщении. Дальше — сразу по делу.
- Отвечай коротко, только на то, что спросили. Не вываливай всё сразу.
- Никогда не придумывай товары, которых нет в каталоге. Если нет — честно скажи.
- Не будь навязчивой.

Доставка: СДЭК, ПЭК, Энергия, DPD. До транспортной компании — бесплатно. Отправка в день оплаты. Самовывоз — Новосибирск (адрес уточните у менеджера).
Оплата: безналичный расчёт, для юрлиц — по счёту.

Когда пользователь спрашивает о товарах — используй данные из каталога, которые я добавлю в сообщение в блоке [КАТАЛОГ].
"""

# ─── Gemini клиент ────────────────────────────────────────────────────────────
gemini_client = genai.Client(api_key=GEMINI_KEY)
GEMINI_CONFIG  = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)

def new_chat():
    return gemini_client.chats.create(model="gemini-2.0-flash", config=GEMINI_CONFIG)

def ask_gemini(chat, user_text: str) -> str:
    catalog_ctx = search_catalog(user_text)
    msg = user_text
    if catalog_ctx:
        msg = f"{user_text}\n\n[КАТАЛОГ]\n{catalog_ctx}"
    try:
        resp = chat.send_message(msg)
        return resp.text
    except Exception as e:
        log.error("Gemini error: %s", e)
        return "Извините, произошла ошибка. Попробуйте ещё раз."

# ─── Flask ────────────────────────────────────────────────────────────────────
flask_app = Flask(__name__)
CORS(flask_app)

web_sessions = {}

HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Анфиса — Mari-Line</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f5f5f5; display: flex; justify-content: center;
         align-items: center; min-height: 100vh; }
  #chat-box { width: 400px; height: 600px; background: #fff;
              border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,.12);
              display: flex; flex-direction: column; overflow: hidden; }
  #header { background: #1a1a2e; color: #fff; padding: 16px 20px;
            font-size: 16px; font-weight: 600; letter-spacing: .3px; }
  #header span { font-size: 13px; font-weight: 400; opacity: .7; display: block; margin-top: 2px; }
  #messages { flex: 1; overflow-y: auto; padding: 16px; display: flex;
              flex-direction: column; gap: 10px; }
  .msg { max-width: 80%; padding: 10px 14px; border-radius: 14px;
         font-size: 14px; line-height: 1.5; white-space: pre-wrap; }
  .msg.user { background: #1a1a2e; color: #fff; align-self: flex-end;
              border-bottom-right-radius: 4px; }
  .msg.bot  { background: #f0f0f5; color: #1a1a2e; align-self: flex-start;
              border-bottom-left-radius: 4px; }
  .msg.bot.typing { opacity: .5; font-style: italic; }
  #input-row { display: flex; gap: 8px; padding: 12px 16px;
               border-top: 1px solid #eee; background: #fff; }
  #input { flex: 1; border: 1px solid #ddd; border-radius: 20px;
           padding: 10px 16px; font-size: 14px; outline: none;
           transition: border-color .2s; }
  #input:focus { border-color: #1a1a2e; }
  #send { background: #1a1a2e; color: #fff; border: none; border-radius: 20px;
          padding: 10px 18px; font-size: 14px; cursor: pointer;
          transition: opacity .2s; }
  #send:hover { opacity: .85; }
  #send:disabled { opacity: .4; cursor: default; }
</style>
</head>
<body>
<div id="chat-box">
  <div id="header">Анфиса <span>Менеджер Mari-Line</span></div>
  <div id="messages"></div>
  <div id="input-row">
    <input id="input" type="text" placeholder="Напишите вопрос..." autocomplete="off">
    <button id="send">→</button>
  </div>
</div>
<script>
  const messages = document.getElementById('messages');
  const input    = document.getElementById('input');
  const sendBtn  = document.getElementById('send');
  const SESSION  = Math.random().toString(36).slice(2);

  function addMsg(text, who) {
    const d = document.createElement('div');
    d.className = 'msg ' + who;
    d.textContent = text;
    messages.appendChild(d);
    messages.scrollTop = messages.scrollHeight;
    return d;
  }

  async function send() {
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    sendBtn.disabled = true;
    addMsg(text, 'user');
    const typing = addMsg('Печатает...', 'bot typing');
    try {
      const r = await fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({session_id: SESSION, message: text})
      });
      const data = await r.json();
      typing.remove();
      addMsg(data.reply || '...', 'bot');
    } catch(e) {
      typing.remove();
      addMsg('Ошибка соединения. Попробуйте ещё раз.', 'bot');
    }
    sendBtn.disabled = false;
    input.focus();
  }

  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
</script>
</body>
</html>"""

@flask_app.route("/")
def index():
    return render_template_string(HTML)

@flask_app.route("/chat", methods=["POST"])
def chat_endpoint():
    data = request.get_json(force=True)
    sid = data.get("session_id", "default")
    user_text = (data.get("message") or "").strip()
    if not user_text:
        return jsonify({"reply": ""})
    if sid not in web_sessions:
        web_sessions[sid] = new_chat()
    reply = ask_gemini(web_sessions[sid], user_text)
    return jsonify({"reply": reply})

@flask_app.route("/health")
def health():
    return jsonify({"status": "ok", "catalog": len(load_catalog())})

# ─── Telegram ─────────────────────────────────────────────────────────────────
MENU = ReplyKeyboardMarkup(
    [["📦 Каталог", "📏 Размеры"],
     ["🚚 Доставка", "💬 Задать вопрос"]],
    resize_keyboard=True
)

tg_sessions = {}

async def tg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    tg_sessions[uid] = new_chat()
    await update.message.reply_text(
        "Привет! Я Анфиса, менеджер Mari-Line 👗\nЧем могу помочь?",
        reply_markup=MENU
    )

async def tg_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text

    if text == "📦 Каталог":
        cats = Counter(p["category"] for p in load_catalog())
        lines = ["📦 Ассортимент Mari-Line:\n"]
        for cat, n in cats.most_common(10):
            lines.append(f"• {cat} — {n} моделей")
        lines.append("\nСпросите о нужной категории или артикуле!")
        await update.message.reply_text("\n".join(lines))
        return

    if text == "📏 Размеры":
        await update.message.reply_text(
            "📏 Размерный ряд: 40–66 (российская шкала)\n\n"
            "Уточните категорию или модель — скажу точные размеры."
        )
        return

    if text == "🚚 Доставка":
        await update.message.reply_text(
            "🚚 Доставка:\n\n"
            "Работаем с: СДЭК, ПЭК, Энергия, DPD\n"
            "✅ До транспортной компании — бесплатно\n"
            "📦 Отправка в день оплаты\n"
            "🏪 Самовывоз — Новосибирск"
        )
        return

    if text == "💬 Задать вопрос":
        await update.message.reply_text("Конечно, спрашивайте! 😊")
        return

    if uid not in tg_sessions:
        tg_sessions[uid] = new_chat()
    chat = tg_sessions[uid]
    reply = await asyncio.to_thread(ask_gemini, chat, text)
    await update.message.reply_text(reply)

def run_telegram():
    if not TELEGRAM_TOKEN:
        log.warning("TELEGRAM_TOKEN не задан — Telegram-бот не запущен")
        return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tg_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", tg_start))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tg_message))
    log.info("Telegram-бот запущен")
    loop.run_until_complete(tg_app.run_polling())

# ─── Точка входа ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_KEY не задан!")
    load_catalog()
    tg_thread = threading.Thread(target=run_telegram, daemon=True)
    tg_thread.start()
    log.info("Flask запущен на порту %d", PORT)
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
