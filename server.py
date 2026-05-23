# -*- coding: utf-8 -*-

import nest_asyncio
nest_asyncio.apply()

from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_KEY,
)

SYSTEM_PROMPT = """Ты — Анфиса, менеджер по продажам бренда Mari-Line.
Веди диалог как живой вежливый человек:
- Ты женщина по имени Анфиса. ВСЕГДА используй женский род: "рада", "помогла", "ответила". НИКОГДА не используй мужской род.
- Здоровайся ТОЛЬКО один раз — в самом первом сообщении диалога. Дальше — сразу по делу, без приветствий.
- Не вываливай всю информацию сразу
- Отвечай коротко и только на то что спросили
- НИКОГДА не придумывай товары которых нет в списке ассортимента. Если товара нет — честно скажи что его нет.
- Не будь навязчивой

АССОРТИМЕНТ:
Платье Спорт Шик, арт. 2554
Цена: 2500 руб.
Размеры: 42-54
Состав: 95% хлопок, 5% эластан (футер двухнитка)
Цвет: Navy Blue (глубокий тёмно-синий)
Описание: А-силуэт, спущенное плечо, карман-арка сзади, длина миди."""

MENU = ReplyKeyboardMarkup(
    [["📦 Каталог", "📏 Таблица размеров"],
     ["🚚 Доставка", "💬 Задать вопрос"]],
    resize_keyboard=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Сбрасываем историю при /start
    context.user_data["history"] = []
    await update.message.reply_text(
        "Привет! Я Анфиса, менеджер Mari-Line 👗\nЧем могу помочь?",
        reply_markup=MENU
    )

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    # Инициализируем историю если её нет
    if "history" not in context.user_data:
        context.user_data["history"] = []

    # Добавляем сообщение пользователя
    context.user_data["history"].append({"role": "user", "content": user_text})

    response = client.chat.completions.create(
        model="nvidia/nemotron-3-super-120b-a12b:free",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            *context.user_data["history"]
        ]
    )

    reply = response.choices[0].message.content

    # Сохраняем ответ Анфисы в историю
    context.user_data["history"].append({"role": "assistant", "content": reply})

    await update.message.reply_text(reply)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer))
app.run_polling()
