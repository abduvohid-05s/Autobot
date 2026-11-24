import asyncio
import json
import logging
import os
import re

from aiohttp import web
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# SOZLAMALAR
TOKEN = "9100152264:AAE_YsUxig1WPP_-VtYPqc5cy1XvpcdbrVs"
PORT = int(os.getenv("PORT", "8080"))
DB_FILE = "channels.json"

MAX_TEXT_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024

MENU_BUTTONS = {
    "📢 Kanallar",
    "➕ Kanal qo'shish",
    "✏️ Xabar sozlash",
    "🗑 Kanalni o'chirish",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


# MA'LUMOTLAR
def load_data() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict) and isinstance(loaded.get("users"), dict):
                    return loaded
        except Exception as e:
            log.error("Ma'lumotlarni o'qishda xatolik: %s", e)

    return {"users": {}}


data = load_data()


def save_data() -> None:
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Ma'lumotlarni saqlashda xatolik: %s", e)


def get_user_channels(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"channels": {}}
    return data["users"][uid]["channels"]


def find_channel_config(chat_id: int) -> dict | None:
    cid = str(chat_id)
    for user_data in data["users"].values():
        channels = user_data.get("channels", {})
        if cid in channels:
            return channels[cid]
    return None


def menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📢 Kanallar", "➕ Kanal qo'shish"],
            ["✏️ Xabar sozlash", "🗑 Kanalni o'chirish"],
        ],
        resize_keyboard=True,
    )


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    context.user_data.clear()

    await update.message.reply_text(
        "🤖 KANAL BOSHQARUV BOTI\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=menu(),
    )


# KANAL TANLASH UCHUN RO'YXAT
def channel_list(user_channels: dict) -> list[str]:
    return [
        f"{i}. {info.get('title', 'Nomsiz kanal')}"
        for i, info in enumerate(user_channels.values(), 1)
    ]


def get_channel_by_number(user_channels: dict, number: int):
    channels = list(user_channels.items())
    if number < 1 or number > len(channels):
        return None
    return channels[number - 1]


# ASOSIY BOSHQARUV
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_user:
        return

    user_id = update.effective_user.id
    user_channels = get_user_channels(user_id)
    text = update.message.text.strip()

    if text in MENU_BUTTONS:
        context.user_data.clear()

    state = context.user_data.get("state")

    # KANAL QO'SHISH
    if text == "➕ Kanal qo'shish":
        context.user_data["state"] = "add_channel"
        await update.message.reply_text("Kanal havolasini yuboring.")
        return

    # KANALLAR RO'YXATI
    if text == "📢 Kanallar":
        if not user_channels:
            await update.message.reply_text("Hozircha kanallar qo'shilmagan.")
            return

        result = "📢 KANALLAR RO'YXATI\n\n"

        for i, (_, info) in enumerate(user_channels.items(), 1):
            status = (
                "✅ Xabar sozlangan"
                if info.get("message")
                else "⚠️ Xabar sozlanmagan"
            )
            result += (
                f"{i}. {info.get('title', 'Nomsiz kanal')}\n"
                f"🔗 https://t.me/{info.get('username', '')}\n"
                f"{status}\n\n"
            )

        await update.message.reply_text(result)
        return

    # XABAR SOZLASH
    if text == "✏️ Xabar sozlash":
        if not user_channels:
            await update.message.reply_text("Avval kanal qo'shing.")
            return

        context.user_data["state"] = "choose_message"
        await update.message.reply_text(
            "Xabar sozlanadigan kanal raqamini yuboring:\n\n"
            + "\n".join(channel_list(user_channels))
        )
        return

    # KANAL O'CHIRISH
    if text == "🗑 Kanalni o'chirish":
        if not user_channels:
            await update.message.reply_text("Kanallar mavjud emas.")
            return

        context.user_data["state"] = "delete_channel"
        await update.message.reply_text(
            "O'chiriladigan kanal raqamini yuboring:\n\n"
            + "\n".join(channel_list(user_channels))
        )
        return

    # --- STATE BOSQICHLARI ---
    if state == "add_channel":
        match = re.fullmatch(
            r"https://t\.me/([A-Za-z0-9_]{5,32})/?",
            text,
            re.IGNORECASE,
        )

        if not match:
            await update.message.reply_text("Kanal havolasini yuboring.")
            return

        username = match.group(1)

        try:
            chat = await context.bot.get_chat("@" + username)

            if chat.type != "channel":
                await update.message.reply_text(
                    "❌ Bu havola Telegram kanaliga tegishli emas."
                )
                return

            user_member = await context.bot.get_chat_member(chat.id, user_id)
            if user_member.status not in ("administrator", "creator"):
                await update.message.reply_text(
                    "❌ Siz ushbu kanalda admin emassiz."
                )
                return

            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if bot_member.status != "administrator":
                await update.message.reply_text(
                    "❌ Botni avval kanalga admin qiling."
                )
                return

            if not getattr(bot_member, "can_edit_messages", False):
                await update.message.reply_text(
                    "❌ Botga postlarni tahrirlash huquqini bering."
                )
                return

            cid = str(chat.id)
            old_message = user_channels.get(cid, {}).get("message", "")

            user_channels[cid] = {
                "title": chat.title or username,
                "username": username,
                "message": old_message,
            }

            save_data()
            context.user_data.clear()

            await update.message.reply_text(
                f"✅ Kanal qo'shildi!\n\n"
                f"📢 {chat.title}\n"
                f"🔗 https://t.me/{username}\n\n"
                "Endi ushbu kanal uchun xabar belgilang.",
                reply_markup=menu(),
            )

        except Exception as e:
            log.error("Kanal qo'shish xatosi: %s", e)
            await update.message.reply_text(
                "❌ Kanalni topib bo'lmadi.\n"
                "Havolani va bot adminligini tekshiring."
            )
        return

    if state == "choose_message":
        if not text.isdigit():
            await update.message.reply_text("Faqat kanal raqamini yuboring.")
            return

        selected = get_channel_by_number(user_channels, int(text))
        if not selected:
            await update.message.reply_text("Bunday kanal raqami mavjud emas.")
            return

        cid, info = selected
        context.user_data["selected_channel"] = cid
        context.user_data["state"] = "write_message"

        await update.message.reply_text(
            f"📢 Kanal: {info.get('title', 'Nomsiz kanal')}\n\n"
            "✏️ Endi post tagiga yoziladigan xabarni yuboring."
        )
        return

    if state == "write_message":
        cid = context.user_data.get("selected_channel")
        if not cid or cid not in user_channels:
            context.user_data.clear()
            await update.message.reply_text(
                "❌ Tanlangan kanal topilmadi. Qaytadan urinib ko'ring.",
                reply_markup=menu(),
            )
            return

        user_channels[cid]["message"] = text
        save_data()
        context.user_data.clear()

        await update.message.reply_text(
            "✅ Xabar muvaffaqiyatli saqlandi!\n\n"
            "Endi ushbu kanalning yangi postlariga "
            "avtomatik qo'shiladi.",
            reply_markup=menu(),
        )
        return

    if state == "delete_channel":
        if not text.isdigit():
            await update.message.reply_text("Kanal raqamini yuboring.")
            return

        selected = get_channel_by_number(user_channels, int(text))
        if not selected:
            await update.message.reply_text("Kanal topilmadi.")
            return

        cid, info = selected
        del user_channels[cid]
        save_data()
        context.user_data.clear()

        await update.message.reply_text(
            f"🗑 {info.get('title', 'Kanal')} o'chirildi.",
            reply_markup=menu(),
        )
        return


# BARCHA YANGI KANAL POSTLARI
async def channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = update.channel_post
    if not post:
        return

    info = find_channel_config(post.chat_id)
    if not info:
        return

    message = (info.get("message") or "").strip()
    if not message:
        return

    try:
        if post.caption is not None or any([
            post.photo,
            post.video,
            post.animation,
            post.document,
            post.audio,
        ]):
            old_caption = post.caption or ""

            if old_caption.endswith(message):
                return

            new_caption = (
                f"{old_caption}\n\n{message}" if old_caption else message
            )

            if len(new_caption) > MAX_CAPTION_LENGTH:
                log.warning(
                    "Caption chegarasi oshdi (%s/%s): post_id=%s",
                    len(new_caption),
                    MAX_CAPTION_LENGTH,
                    post.message_id,
                )
                return

            await context.bot.edit_message_caption(
                chat_id=post.chat_id,
                message_id=post.message_id,
                caption=new_caption,
                caption_entities=post.caption_entities,
            )

        elif post.text:
            if post.text.endswith(message):
                return

            new_text = f"{post.text}\n\n{message}"

            if len(new_text) > MAX_TEXT_LENGTH:
                log.warning(
                    "Matn chegarasi oshdi (%s/%s): post_id=%s",
                    len(new_text),
                    MAX_TEXT_LENGTH,
                    post.message_id,
                )
                return

            await context.bot.edit_message_text(
                chat_id=post.chat_id,
                message_id=post.message_id,
                text=new_text,
                entities=post.entities,
            )

        else:
            log.info(
                "Ushbu post turiga matn/caption qo'shib bo'lmaydi: post_id=%s",
                post.message_id,
            )
            return

        log.info("Postga xabar qo'shildi: post_id=%s", post.message_id)

    except Exception as e:
        log.error("Postni tahrirlashda xatolik (post_id=%s): %s", post.message_id, e)


# UPTIMEROBOT UCHUN AIOHTTP SERVER
async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK", status=200)


async def start_web_server(port: int) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    log.info("HTTP server 0.0.0.0:%s portda ishga tushdi", port)
    return runner


# BOT VA SERVERNI BIRGA ISHLATISH
async def run_bot_and_server() -> None:
    tg_app = Application.builder().token(TOKEN).build()

    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )
    tg_app.add_handler(
        MessageHandler(
            filters.ChatType.CHANNEL & ~filters.UpdateType.EDITED_CHANNEL_POST,
            channel_post,
        )
    )

    web_runner = await start_web_server(PORT)

    try:
        await tg_app.initialize()
        await tg_app.start()
        if tg_app.updater:
            await tg_app.updater.start_polling(
                allowed_updates=[Update.MESSAGE, Update.CHANNEL_POST]
            )
        log.info("BOT ISHGA TUSHDI!")

        await asyncio.Event().wait()
    finally:
        log.info("To'xtatish jarayoni boshlandi...")
        if tg_app.updater and tg_app.updater.running:
            await tg_app.updater.stop()
        if tg_app.running:
            await tg_app.stop()
        await tg_app.shutdown()
        await web_runner.cleanup()


def main() -> None:
    asyncio.run(run_bot_and_server())


if __name__ == "__main__":
    main()
