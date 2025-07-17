import json
import asyncio
import logging
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.types import BotCommand, BotCommandScopeDefault
from dotenv import load_dotenv

from aiogram.client.bot import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

# --- Настройки ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
THREAD_ID = int(os.getenv("THREAD_ID", "0"))
OWNER_ID = int(os.getenv("OWNER_ID"))  # Твой Telegram ID — только ты можешь менять админов

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    session=AiohttpSession()
)

dp = Dispatcher()
scheduler = AsyncIOScheduler()
DATA_FILE = "data.json"

# --- Работа с данными ---
def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"admins": [], "events": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_admin(user_id: int) -> bool:
    return user_id in load_data().get("admins", [])

# --- Клавиатура ---
def main_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="➕ Добавить"))
    kb.add(KeyboardButton(text="📋 Расписание"))
    kb.add(KeyboardButton(text="📆 Сегодня"))
    kb.add(KeyboardButton(text="🗓 Неделя"))
    kb.add(KeyboardButton(text="❓ Помощь"))
    return kb.as_markup(resize_keyboard=True)

def back_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="⬅ Назад"))
    return kb.as_markup(resize_keyboard=True)

# --- Форматирование даты ---
def format_date_ddmmyyyy(date_str_iso: str) -> str:
    try:
        dt = datetime.strptime(date_str_iso, "%Y-%m-%d")
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return date_str_iso

# --- Безопасная отправка сообщений ---
async def safe_send_message(chat_id, text, thread_id=None):
    try:
        if thread_id and thread_id != 0:
            await bot.send_message(chat_id=chat_id, message_thread_id=thread_id, text=text)
        else:
            await bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logging.warning(f"Ошибка с thread_id={thread_id}: {e}")
        try:
            await bot.send_message(chat_id=chat_id, text=text)
        except Exception as e2:
            logging.error(f"Ошибка без thread_id: {e2}")

# --- Команды ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(f"Привет, <b>{message.from_user.first_name}</b>!", reply_markup=main_keyboard())

@dp.message(Command("help"))
@dp.message(F.text.lower() == "❓ помощь")
async def cmd_help(message: Message):
    await message.answer(
        "<b>Команды:</b>\n\n"
        "/add — Добавить событие\n"
        "/list — Показать расписание\n"
        "/today — Расписание на сегодня\n"
        "/week — Расписание на неделю\n"
        "/getthreadid — Узнать ID темы\n"
        "/addadmin &lt;user_id&gt; — Добавить админа (только владелец)\n"
        "/removeadmin &lt;user_id&gt; — Удалить админа (только владелец)",
        reply_markup=main_keyboard()
    )

@dp.message(Command("getthreadid"))
async def get_thread_id(message: Message):
    info = (
        f"<b>chat_id</b>: <code>{message.chat.id}</code>\n"
        f"<b>thread_id</b>: <code>{message.message_thread_id or '—'}</code>\n"
        f"<b>user_id</b>: <code>{message.from_user.id}</code>"
    )
    await message.answer(info)

@dp.message(Command("today"))
async def cmd_today(message: Message):
    await send_today_schedule(message.chat.id, message.message_thread_id)

@dp.message(Command("week"))
async def cmd_week(message: Message):
    await send_weekly_schedule(message.chat.id, message.message_thread_id)

@dp.message(Command("addadmin"))
async def cmd_add_admin(message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.answer("❌ Только владелец может добавлять админов.")
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        return await message.answer("❌ Использование: /addadmin <user_id>")
    user_id = int(args[1])
    data = load_data()
    admins = data.get("admins", [])
    if user_id in admins:
        return await message.answer("ℹ️ Пользователь уже является админом.")
    admins.append(user_id)
    data["admins"] = admins
    save_data(data)
    await message.answer(
        f"✅ Пользователь <a href='tg://user?id={user_id}'>пользователь</a> добавлен в админы."
    )

@dp.message(Command("removeadmin"))
async def cmd_remove_admin(message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.answer("❌ Только владелец может удалять админов.")
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        return await message.answer("❌ Использование: /removeadmin <user_id>")
    user_id = int(args[1])
    data = load_data()
    admins = data.get("admins", [])
    if user_id not in admins:
        return await message.answer("ℹ️ Пользователь не является админом.")
    admins.remove(user_id)
    data["admins"] = admins
    save_data(data)
    await message.answer(
        f"✅ Пользователь <a href='tg://user?id={user_id}'>пользователь</a> удалён из админов."
    )

# --- Кнопки ---
@dp.message(F.text.lower() == "📆 сегодня")
async def btn_today(message: Message):
    await send_today_schedule(message.chat.id, message.message_thread_id)

@dp.message(F.text.lower() == "🗓 неделя")
async def btn_week(message: Message):
    await send_weekly_schedule(message.chat.id, message.message_thread_id)

@dp.message(F.text.lower() == "➕ добавить")
async def add_event_start(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ У тебя нет прав для добавления событий.")
    await message.answer(
        "📥 Введите событие в формате:\n"
        "Название и тренер\n"
        "Дата (ДД.ММ.ГГГГ)\n"
        "Время (ЧЧ:ММ)\n"
        "Место\n"
        "Комментарий (опционально)",
        reply_markup=back_keyboard()
    )

@dp.message(F.text.lower() == "📋 расписание")
@dp.message(Command("list"))
async def show_list(message: Message):
    data = load_data()
    events = data.get("events", [])
    if not events:
        return await message.answer("📭 Список событий пуст.")

    text_lines = []
    builder = InlineKeyboardBuilder()

    for i, e in enumerate(events):
        text_lines.append(
            f"<b>{i+1}.</b> {e['title']}\n"
            f"🗓 {format_date_ddmmyyyy(e['date'])} {e['time']}\n"
            f"📍 {e['location']}\n📝 {e['comment'] or '-'}"
        )
        if is_admin(message.from_user.id):
            builder.button(text=f"❌ Удалить {i+1}", callback_data=f"remove_{i}")

    await message.answer("\n\n".join(text_lines), reply_markup=builder.as_markup())

@dp.message(F.text.lower() == "⬅ назад")
async def go_back(message: Message):
    await message.answer("🔙 Возврат в меню", reply_markup=main_keyboard())

# --- Обработка ввода события ---
@dp.message()
async def handle_event_input(message: Message):
    if not is_admin(message.from_user.id):
        return

    lines = message.text.strip().split("\n")
    if len(lines) < 4:
        return

    title, date_str_input, time_str, location = lines[:4]
    comment = "\n".join(lines[4:]) if len(lines) > 4 else ""

    try:
        dt = datetime.strptime(date_str_input.strip(), "%d.%m.%Y")
        date_str = dt.strftime("%Y-%m-%d")
        datetime.strptime(time_str.strip(), "%H:%M")
    except ValueError:
        return await message.answer("❌ Ошибка формата даты или времени.")

    data = load_data()
    data["events"].append({
        "title": title.strip(),
        "date": date_str,
        "time": time_str.strip(),
        "location": location.strip(),
        "comment": comment.strip()
    })
    save_data(data)
    await message.answer("✅ Событие добавлено!", reply_markup=main_keyboard())

# --- Удаление события ---
@dp.callback_query(F.data.startswith("remove_"))
async def remove_event(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ Нет прав.", show_alert=True)

    index = int(callback.data.split("_")[-1])
    data = load_data()
    events = data.get("events", [])
    if 0 <= index < len(events):
        removed = events.pop(index)
        save_data(data)
        await callback.message.edit_text(
            f"🗑 Удалено: <b>{removed['title']}</b> — {format_date_ddmmyyyy(removed['date'])} {removed['time']}"
        )
    else:
        await callback.answer("❌ Не найдено.", show_alert=True)

# --- Отправка сводок ---
async def send_today_schedule(chat_id, thread_id=None):
    data = load_data()
    today_str = datetime.now().strftime("%Y-%m-%d")
    events = [e for e in data["events"] if e["date"] == today_str]

    text = "<b>Сегодня нет событий.</b>" if not events else "<b>Сегодняшние события:</b>\n\n" + "\n\n".join(
        f"<b>{e['title']}</b>\n🕒 {e['time']}\n📍 {e['location']}\n📝 {e['comment'] or '-'}" for e in events
    )

    await safe_send_message(chat_id, text, thread_id or THREAD_ID)

async def send_weekly_schedule(chat_id, thread_id=None):
    data = load_data()
    today = datetime.now()
    week_end = today + timedelta(days=7)
    weekly_events = [
        e for e in data["events"]
        if today <= datetime.strptime(e["date"], "%Y-%m-%d") < week_end
    ]

    text = "<b>На этой неделе событий нет 😴</b>" if not weekly_events else "<b>События на неделю:</b>\n\n" + "\n\n".join(
        f"<b>{e['title']}</b> — {format_date_ddmmyyyy(e['date'])} {e['time']}\n📍 {e['location']}\n📝 {e['comment'] or '-'}"
        for e in sorted(weekly_events, key=lambda x: (x["date"], x["time"]))
    )

    await safe_send_message(chat_id, text, thread_id or THREAD_ID)

# --- Запуск бота ---
async def main():
    logging.basicConfig(level=logging.INFO)

    # Автоподстановка команд (чтобы в Telegram отображались подсказки)
    commands = [
        BotCommand(command="start", description="Запуск бота"),
        BotCommand(command="help", description="Помощь и команды"),
        BotCommand(command="add", description="Добавить событие"),
        BotCommand(command="list", description="Показать расписание"),
        BotCommand(command="today", description="Расписание на сегодня"),
        BotCommand(command="week", description="Расписание на неделю"),
        BotCommand(command="getthreadid", description="Узнать ID темы"),
        BotCommand(command="addadmin", description="Добавить админа (только владелец)"),
        BotCommand(command="removeadmin", description="Удалить админа (только владелец)"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

    # Планировщик заданий
    scheduler.add_job(send_weekly_schedule, "cron", day_of_week="sun", hour=22, minute=0, args=[GROUP_ID, THREAD_ID])
    scheduler.add_job(send_today_schedule, "cron", hour=7, minute=0, args=[GROUP_ID, THREAD_ID])
    scheduler.add_job(send_weekly_schedule, "cron", hour=15, minute=20, args=[GROUP_ID, THREAD_ID])  # пробное
    scheduler.add_job(send_today_schedule, "cron", hour=15, minute=25, args=[GROUP_ID, THREAD_ID])   # пробное
    scheduler.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
