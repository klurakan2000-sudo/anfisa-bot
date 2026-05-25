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

    if user_text == "📦 Каталог":
        await update.message.reply_text(
            "Наш ассортимент:\n\n"
            "👗 Платье Спорт Шик, арт. 2554\n"
            "Цена: 2500 руб.\n"
            "Размеры: 42-54\n"
            "Состав: 95% хлопок, 5% эластан\n"
            "Цвет: Navy Blue\n"
            "Длина: миди, А-силуэт"
        )
    elif user_text == "📏 Таблица размеров":
        await update.message.reply_text(
            "📏 Таблица размеров (см):\n\n"
            "42 — грудь 84, талия 66, бёдра 92, плечо 25,7, высота груди 26\n"
            "44 — грудь 88, талия 70, бёдра 96, плечо 27,2, высота груди 27\n"
            "46 — грудь 92, талия 74, бёдра 100, плечо 28,8, высота груди 28\n"
            "48 — грудь 96, талия 78, бёдра 104, плечо 30,2, высота груди 29\n"
            "50 — грудь 100, талия 82, бёдра 108, плечо 31,5, высота груди 30\n"
            "52 — грудь 104, талия 86, бёдра 112, плечо 32,8, высота груди 31\n"
            "54 — грудь 108, талия 90, бёдра 116, плечо 34, высота груди 32\n"
            "56 — грудь 112, талия 94, бёдра 120, плечо 35,2, высота груди 33\n"
            "58 — грудь 116, талия 98, бёдра 124, плечо 36,2, высота груди 34\n"
            "60 — грудь 120, талия 102, бёдра 128, плечо 37,5, высота груди 35"
        )
    elif user_text == "🚚 Доставка":
        await update.message.reply_text(
            "🚚 Доставка:\n\n"
            "Работаем с: СДЭК, ПЭК, Энергия, DPD\n\n"
            "✅ Доставка до транспортной компании — бесплатно\n"
            "📦 Отправка в день оплаты\n"
            "🏪 Самовывоз — Новосибирск (уточните адрес у менеджера)"
        )
    elif user_text == "💬 Задать вопрос":
        await update.message.reply_text(
            "Конечно! Задавайте — я отвечу 😊"
        )
    else:
        if "history" not in context.user_data:
            context.user_data["history"] = []
        context.user_data["history"].append({"role": "user", "content": user_text})
        response = client.chat.completions.create(
            model="nvidia/nemotron-3-super-120b-a12b:free",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *context.user_data["history"]
            ]
        )
        reply = response.choices[0].message.content
        context.user_data["history"].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer))
app.run_polling()
