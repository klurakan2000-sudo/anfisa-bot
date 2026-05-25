# -*- coding: utf-8 -*-

import nest_asyncio
nest_asyncio.apply()

from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
import os
from PIL import Image, ImageDraw, ImageFont
import io

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
        sizes = [
            ("Разм", "Гр", "Тал", "Бд", "Пл", "Выс"),
            ("42", "84", "66", "92", "25,7", "26"),
            ("44", "88", "70", "96", "27,2", "27"),
            ("46", "92", "74", "100", "28,8", "28"),
            ("48", "96", "78", "104", "30,2", "29"),
            ("50", "100", "82", "108", "31,5", "30"),
            ("52", "104", "86", "112", "32,8", "31"),
            ("54", "108", "90", "116", "34", "32"),
            ("56", "112", "94", "120", "35,2", "33"),
            ("58", "116", "98", "124", "36,2", "34"),
            ("60", "120", "102", "128", "37,5", "35"),
        ]
        col_w = [70, 55, 55, 55, 60, 55]
        row_h = 36
        pad = 20
        w = sum(col_w) + pad * 2
        h = row_h * len(sizes) + pad * 2 + 30
        img = Image.new("RGB", (w, h), "#1a1a2e")
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        draw.text((pad, pad), "📏 Таблица размеров Mari-Line", fill="#e8d5b7", font=font)
        y = pad + 30
        for i, row in enumerate(sizes):
            x = pad
            bg = "#222244" if i == 0 else ("#1e1e3a" if i % 2 == 0 else "#1a1a2e")
            draw.rectangle([pad, y, w - pad, y + row_h], fill=bg)
            for j, cell in enumerate(row):
                color = "#ffffff" if j == 0 else "#cccccc"
                if i == 0:
                    color = "#888888"
                draw.text((x + 6, y + 10), cell, fill=color, font=font)
                x += col_w[j]
            y += row_h
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        await update.message.reply_photo(photo=buf)
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
