import os
import re
import subprocess
from datetime import datetime, timedelta
import pytz
import asyncio
import threading
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler

LOCAL_TZ = pytz.timezone("Europe/Berlin")

# اختیاری: اگر در Render مقدار ADMIN_USER_ID را روی Telegram User ID خودت بگذاری،
# فقط همان اکانت می‌تواند بخش مدیریتی ربات را استفاده کند.
ADMIN_USER_ID_RAW = os.getenv("ADMIN_USER_ID", "").strip()

SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".m4b"
}

CHANNELS = {
    "chan_delgraphyha": ("@Delgraphyha", "کانال دلگرافیها"),
    "chan_ahangziba": ("@ahangzibamusic", "آهنگ زیبا موزیک"),
    "chan_test": ("@testDelgraphyha", "کانال تست دلگرافیها"),
}

scheduler = BackgroundScheduler(timezone=LOCAL_TZ)
scheduler.start()

global_app = None
background_loop = None

# راه‌اندازی سرور Flask برای پاسخ به UptimeRobot و وب‌هوق تلگرام
app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running and alive!", 200


@app.route(f"/{os.getenv('TELEGRAM_TOKEN', '')}", methods=["POST"])
def webhook():
    global global_app, background_loop
    if global_app and background_loop:
        try:
            json_data = request.get_json(force=True)
            update = Update.de_json(json_data, global_app.bot)
            asyncio.run_coroutine_threadsafe(global_app.process_update(update), background_loop)
        except Exception as e:
            print(f"Webhook error: {e}")
    return "OK", 200


def is_private_admin(update: Update) -> bool:
    """بخش مدیریتی فقط در Private Chat اجرا می‌شود؛ در صورت تنظیم ADMIN_USER_ID فقط برای همان اکانت."""
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user or chat.type != "private":
        return False

    if not ADMIN_USER_ID_RAW:
        # برای اینکه نسخه جدید بدون تنظیم اضافه هم فوراً کار کند، Private Chat مجاز است.
        # برای امنیت بیشتر ADMIN_USER_ID را در Render تنظیم کن.
        return True

    try:
        return user.id == int(ADMIN_USER_ID_RAW)
    except ValueError:
        print("❌ ADMIN_USER_ID نامعتبر است؛ باید فقط عدد باشد.")
        return False


def channel_name_from_id(channel_id: str) -> str:
    for saved_id, saved_name in CHANNELS.values():
        if saved_id.lower() == str(channel_id).lower():
            return saved_name
    return str(channel_id)


def is_valid_audio_document(document) -> bool:
    """فقط Documentهایی که واقعاً صوتی‌اند پذیرفته می‌شوند؛ عکس، PDF، استیکر و فایل عادی رد می‌شوند."""
    if not document:
        return False

    mime_type = (document.mime_type or "").lower().strip()
    file_name = (document.file_name or "").lower().strip()
    extension = os.path.splitext(file_name)[1]

    return mime_type.startswith("audio/") or extension in SUPPORTED_AUDIO_EXTENSIONS


async def button_like_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # این بخش عمداً عمومی می‌ماند تا کاربران کانال بتوانند روی لایک/قلب/آتش کلیک کنند.
    query = update.callback_query
    try:
        await query.answer("ثبت شد! ❤️")
    except Exception:
        pass

    data = query.data or ""
    if data.startswith("like_"):
        try:
            keyboard = query.message.reply_markup.inline_keyboard
            new_keyboard = []

            for row in keyboard:
                new_row = []
                for button in row:
                    if button.callback_data == data:
                        text = button.text
                        base_text = text.split("(")[0].strip()
                        count = 1
                        if "(" in text:
                            try:
                                count = int(text.split("(")[1].replace(")", "").strip()) + 1
                            except Exception:
                                count = 1
                        new_text = f"{base_text} ({count})"
                        new_row.append(InlineKeyboardButton(new_text, callback_data=button.callback_data))
                    else:
                        new_row.append(button)
                new_keyboard.append(new_row)

            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
        except Exception as e:
            print(f"Like error: {e}")


def get_audio_duration(input_path: str) -> float:
    """مدت آهنگ را با ffprobe می‌گیرد. در صورت خطا صفر برمی‌گرداند."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception as e:
        print(f"ffprobe duration error: {e}")
    return 0.0


def get_segment_mean_volume(input_path: str, start_seconds: float, duration_seconds: int = 25):
    """میانگین بلندی صدا را برای یک بازه می‌سنجد. عدد بزرگ‌تر (نزدیک‌تر به صفر) یعنی پرانرژی‌تر."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-ss", str(max(0, start_seconds)),
        "-i", input_path,
        "-t", str(duration_seconds),
        "-af", "volumedetect",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        output = (result.stderr or "") + "\n" + (result.stdout or "")
        match = re.search(r"mean_volume:\s*(-?[0-9.]+)\s*dB", output)
        if match:
            return float(match.group(1))
    except Exception as e:
        print(f"Volume analysis error at {start_seconds}s: {e}")
    return None


def choose_best_clip_start(input_path: str, clip_duration: int = 25) -> float:
    """
    چند نقطه از آهنگ را بررسی می‌کند و بازه‌ای با انرژی صوتی بیشتر را انتخاب می‌کند.
    هدف تشخیص هوشمندتر از برش ثابت ثانیه ۳۰ است، نه تشخیص کامل Chorus با هوش مصنوعی.
    """
    duration = get_audio_duration(input_path)

    if duration <= clip_duration + 2:
        return 0.0

    latest_start = max(0.0, duration - clip_duration - 1)

    # از شروع و پایان خیلی نزدیک دور می‌شویم تا Intro/Outro آرام کمتر انتخاب شود.
    search_start = min(15.0, latest_start)
    search_end = max(search_start, min(latest_start, duration * 0.82))

    if search_end <= search_start:
        return min(30.0, latest_start)

    # حداکثر 12 نمونه تا روی Render فشار بیهوده وارد نشود.
    sample_count = min(12, max(4, int(duration // 30)))
    if sample_count <= 1:
        candidates = [search_start]
    else:
        step = (search_end - search_start) / (sample_count - 1)
        candidates = [search_start + (step * i) for i in range(sample_count)]

    best_start = min(30.0, latest_start)
    best_score = None

    for start in candidates:
        score = get_segment_mean_volume(input_path, start, clip_duration)
        if score is None:
            continue
        if best_score is None or score > best_score:
            best_score = score
            best_start = start

    print(f"🎯 Best 25s clip starts at {best_start:.1f}s (score={best_score})")
    return best_start


def process_audio_clip(input_path, wav_path, ogg_path):
    clip_duration = 25
    best_start = choose_best_clip_start(input_path, clip_duration)

    cut_cmd = [
        "ffmpeg", "-y",
        "-ss", str(best_start),
        "-i", input_path,
        "-t", str(clip_duration),
        "-vn",
        "-c:a", "libmp3lame",
        wav_path,
    ]
    res = subprocess.run(cut_cmd, capture_output=True)

    if res.returncode != 0 or not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
        # fallback امن
        fallback_start = "30" if get_audio_duration(input_path) > 60 else "0"
        cut_cmd = [
            "ffmpeg", "-y", "-ss", fallback_start,
            "-i", input_path,
            "-t", str(clip_duration),
            "-vn", "-c:a", "libmp3lame", wav_path,
        ]
        subprocess.run(cut_cmd, capture_output=True)

    ogg_cmd = [
        "ffmpeg", "-y", "-i", wav_path,
        "-vn", "-c:a", "libopus", "-b:a", "64k", ogg_path,
    ]
    subprocess.run(ogg_cmd, capture_output=True)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_admin(update):
        return

    os.makedirs("downloads", exist_ok=True)
    user_id = update.effective_user.id
    photo_file = await update.message.photo[-1].get_file()
    custom_thumb_path = os.path.join("downloads", f"custom_thumb_{user_id}.jpg")
    await photo_file.download_to_drive(custom_thumb_path)

    context.user_data["custom_thumb_path"] = custom_thumb_path
    await update.message.reply_text("✅ عکس کاور ذخیره شد. حالا فایل موزیک را بفرست.")


async def handle_text_or_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_admin(update):
        return

    # پیام عادی هیچ کاری نمی‌کند؛ فقط وقتی ربات منتظر ساعت دلخواه است متن را پردازش می‌کند.
    if not context.user_data.get("waiting_for_custom_hours"):
        return

    text = (update.message.text or "").strip()
    try:
        hours = int(text)
        if hours <= 0:
            raise ValueError

        input_path = context.user_data.get("input_path")
        voice_path = context.user_data.get("voice_path")
        title = context.user_data.get("title", "Music")
        channel_id = context.user_data.get("selected_channel", "@Delgraphyha")
        chan_name = channel_name_from_id(channel_id)

        if not input_path or not os.path.exists(input_path):
            await update.message.reply_text("❌ اطلاعات فایل منقضی شده است. دوباره موزیک را بفرست.")
            context.user_data["waiting_for_custom_hours"] = False
            return

        run_time = datetime.now(LOCAL_TZ) + timedelta(hours=hours)
        scheduler.add_job(
            scheduled_job_wrapper,
            "date",
            run_date=run_time,
            args=[channel_id, chan_name, input_path, voice_path, title, dict(context.user_data)],
        )
        context.user_data["waiting_for_custom_hours"] = False
        await update.message.reply_text(
            f"⏰ پست برای {hours} ساعت دیگر در {chan_name} زمان‌بندی شد."
        )
    except ValueError:
        await update.message.reply_text("❌ فقط تعداد ساعت را به صورت عدد صحیح مثبت بفرست؛ مثلاً 8 یا 12.")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_admin(update):
        return

    if not update.message:
        return

    # اول واقعاً مطمئن می‌شویم فایل صوتی است. Document.ALL دیگر مساوی «موزیک» نیست، خوشبختانه.
    if update.message.audio:
        audio_msg = update.message.audio
        audio_file = await audio_msg.get_file()
        title = audio_msg.title or audio_msg.file_name or "موزیک"
    elif update.message.document and is_valid_audio_document(update.message.document):
        audio_msg = update.message.document
        audio_file = await audio_msg.get_file()
        title = audio_msg.file_name or "موزیک"
    else:
        # فایل غیرصوتی، استیکر، عکس، PDF و بقیه چیزهای بشری را بی‌سروصدا نادیده می‌گیریم.
        return

    await update.message.reply_text("⏳ در حال پردازش موزیک و انتخاب بخش ۲۵ ثانیه‌ای بهتر...")

    os.makedirs("downloads", exist_ok=True)
    user_id = update.effective_user.id
    input_path = os.path.join("downloads", f"song_{user_id}.mp3")
    wav_path = os.path.join("downloads", f"temp_{user_id}.mp3")
    voice_path = os.path.join("downloads", f"voice_{user_id}.ogg")

    try:
        await audio_file.download_to_drive(
            input_path,
            read_timeout=60,
            write_timeout=60,
            connect_timeout=60,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در دانلود فایل: {e}")
        return

    try:
        process_audio_clip(input_path, wav_path, voice_path)
    except Exception as e:
        print(f"Audio processing error: {e}")
        await update.message.reply_text("❌ پردازش فایل صوتی ناموفق بود.")
        return

    if not os.path.exists(voice_path) or os.path.getsize(voice_path) == 0:
        await update.message.reply_text("❌ ساخت بخش ۲۵ ثانیه‌ای ناموفق بود.")
        return

    context.user_data["input_path"] = input_path
    context.user_data["voice_path"] = voice_path
    context.user_data["title"] = title
    context.user_data["user_id"] = user_id

    keyboard = [
        [InlineKeyboardButton("📢 دلگرافیها (@Delgraphyha)", callback_data="chan_delgraphyha")],
        [InlineKeyboardButton("🎶 آهنگ زیبا (@ahangzibamusic)", callback_data="chan_ahangziba")],
        [InlineKeyboardButton("🧪 کانال تست (@testDelgraphyha)", callback_data="chan_test")],
    ]

    await update.message.reply_text(
        "✅ موزیک آماده شد. مقصد را انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def send_post_to_channel(bot, channel_id, chan_name, input_path, voice_path, title, user_data):
    custom_thumb = user_data.get("custom_thumb_path")
    final_thumb_path = custom_thumb if (custom_thumb and os.path.exists(custom_thumb)) else None

    keyboard = [
        [
            InlineKeyboardButton("👍 لایک", callback_data="like_btn"),
            InlineKeyboardButton("❤️ قلب", callback_data="like_heart"),
        ],
        [
            InlineKeyboardButton("👏 دست زدن", callback_data="like_clap"),
            InlineKeyboardButton("🔥 آتش", callback_data="like_fire"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if final_thumb_path and os.path.exists(final_thumb_path):
            with open(final_thumb_path, "rb") as photo:
                await bot.send_photo(chat_id=channel_id, photo=photo)
            try:
                os.remove(final_thumb_path)
                user_data.pop("custom_thumb_path", None)
            except Exception:
                pass

        with open(input_path, "rb") as audio:
            await bot.send_audio(
                chat_id=channel_id,
                audio=audio,
                title=title,
                caption=(
                    "🎵 **نسخه کامل موزیک**\n\n"
                    "🌐 سابسکرایب در یوتوب: [YouTube Channel](https://youtube.com/@delgraphyha?sub_confirmation=1)\n"
                    "🎬 تیک‌تاک: [TikTok Profile](https://tiktok.com/@delgraphyha)\n"
                    "📷 اینستاگرام: [Instagram Profile](https://instagram.com/delgraphyha)"
                ),
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )

        with open(voice_path, "rb") as voice:
            await bot.send_voice(
                chat_id=channel_id,
                voice=voice,
                caption=(
                    "✨ بخش جذاب آهنگ\n\n"
                    "🎵 **گلچین ۲۵ ثانیه طلایی**\n\n"
                    "✨ لذت ببرید و نظرات خود را با ما در میان بگذارید.\n\n"
                    "🌐 سابسکرایب در یوتوب: [YouTube Channel](https://youtube.com/@delgraphyha?sub_confirmation=1)\n"
                    "🎬 ما را در تیک‌تاک دنبال کنید: [TikTok Profile](https://tiktok.com/@delgraphyha)\n"
                    "📷 اینستاگرام: [Instagram Profile](https://instagram.com/delgraphyha)"
                ),
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )

        print(f"✅ پست با موفقیت به کانال {chan_name} ارسال شد.")
    except Exception as e:
        print(f"❌ خطا در ارسال پست: {e}")
        raise


def scheduled_job_wrapper(channel_id, chan_name, input_path, voice_path, title, user_data):
    global global_app, background_loop
    if global_app and background_loop:
        try:
            future = asyncio.run_coroutine_threadsafe(
                send_post_to_channel(
                    global_app.bot,
                    channel_id,
                    chan_name,
                    input_path,
                    voice_path,
                    title,
                    user_data,
                ),
                background_loop,
            )

            def log_result(f):
                try:
                    f.result()
                except Exception as exc:
                    print(f"❌ Scheduled send failed: {exc}")

            future.add_done_callback(log_result)
        except Exception as e:
            print(f"❌ Scheduler execution error: {e}")


async def button_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not is_private_admin(update):
        try:
            await query.answer()
        except Exception:
            pass
        return

    await query.answer()
    data = query.data or ""

    if data in CHANNELS:
        channel_id, chan_title = CHANNELS[data]
        context.user_data["selected_channel"] = channel_id

        keyboard = [
            [
                InlineKeyboardButton("🚀 ارسال آنی", callback_data="send_now"),
                InlineKeyboardButton("⚡ تست ۱ دقیقه‌ای", callback_data="sched_1min"),
            ],
            [
                InlineKeyboardButton("⏱ ۱۰ دقیقه دیگر", callback_data="sched_10min"),
                InlineKeyboardButton("⏱ ۳۰ دقیقه دیگر", callback_data="sched_30min"),
            ],
            [
                InlineKeyboardButton("⏱ ۶ ساعت دیگر", callback_data="sched_6h"),
                InlineKeyboardButton("⏳ ۱۲ ساعت دیگر", callback_data="sched_12h"),
            ],
            [InlineKeyboardButton("✏️ ساعت دلخواه", callback_data="sched_custom")],
        ]
        await query.edit_message_text(
            f"✅ مقصد: {chan_title}\nحالا زمان انتشار را انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    channel_id = context.user_data.get("selected_channel", "@Delgraphyha")
    chan_name = channel_name_from_id(channel_id)

    input_path = context.user_data.get("input_path")
    voice_path = context.user_data.get("voice_path")

    if not input_path or not os.path.exists(input_path) or not voice_path or not os.path.exists(voice_path):
        await query.edit_message_text("❌ اطلاعات فایل منقضی شده است. دوباره موزیک را بفرست.")
        return

    title = context.user_data.get("title", "Music")
    now = datetime.now(LOCAL_TZ)

    if data == "send_now":
        await query.edit_message_text(f"⏳ در حال ارسال به {chan_name}...")
        try:
            await send_post_to_channel(
                context.bot,
                channel_id,
                chan_name,
                input_path,
                voice_path,
                title,
                context.user_data,
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"✅ پست با موفقیت به {chan_name} ارسال شد.",
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ ارسال ناموفق بود: {e}",
            )
        return

    if data == "sched_custom":
        context.user_data["waiting_for_custom_hours"] = True
        await query.edit_message_text("✍️ تعداد ساعت را فقط به صورت عدد بفرست؛ مثلاً 8 یا 12.")
        return

    if data == "sched_1min":
        run_time = now + timedelta(minutes=1)
        time_text = "۱ دقیقه دیگر"
    elif data == "sched_10min":
        run_time = now + timedelta(minutes=10)
        time_text = "۱۰ دقیقه دیگر"
    elif data == "sched_30min":
        run_time = now + timedelta(minutes=30)
        time_text = "۳۰ دقیقه دیگر"
    elif data == "sched_6h":
        run_time = now + timedelta(hours=6)
        time_text = "۶ ساعت دیگر"
    elif data == "sched_12h":
        run_time = now + timedelta(hours=12)
        time_text = "۱۲ ساعت دیگر"
    else:
        return

    scheduler.add_job(
        scheduled_job_wrapper,
        "date",
        run_date=run_time,
        args=[channel_id, chan_name, input_path, voice_path, title, dict(context.user_data)],
    )

    await query.edit_message_text(
        f"⏰ پست برای {time_text} در {chan_name}، ساعت {run_time.strftime('%H:%M')} زمان‌بندی شد."
    )


def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


def main():
    global global_app, background_loop

    TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")

    if not TOKEN:
        print("❌ خطا: توکن ربات پیدا نشد!")
        return

    if not ADMIN_USER_ID_RAW:
        print("⚠️ ADMIN_USER_ID تنظیم نشده؛ بخش مدیریتی فقط به Private Chat محدود است، ولی برای امنیت بهتر ID خودت را تنظیم کن.")

    global_app = ApplicationBuilder().token(TOKEN).build()

    background_loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_background_loop, args=(background_loop,), daemon=True)
    t.start()

    async def init_bot():
        await global_app.initialize()
        await global_app.start()
        if RENDER_EXTERNAL_URL:
            base_url = RENDER_EXTERNAL_URL.rstrip("/")
            webhook_url = f"{base_url}/{TOKEN}"
            print(f"🌐 در حال تنظیم وب‌هوق روی: {webhook_url}")
            await global_app.bot.set_webhook(webhook_url)

    future = asyncio.run_coroutine_threadsafe(init_bot(), background_loop)
    future.result()

    # Photo فقط در خود تابع و فقط برای Private Admin پردازش می‌شود.
    global_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Document.ALL باقی مانده تا MP3هایی که تلگرام به صورت Document می‌فرستد هم گرفته شوند؛
    # اما handle_audio قبل از هر کاری MIME/پسوند را بررسی می‌کند و فایل غیرصوتی را بی‌صدا رد می‌کند.
    global_app.add_handler(MessageHandler(filters.AUDIO | filters.Document.ALL, handle_audio))

    # متن عادی دیگر پاسخ نمی‌گیرد؛ فقط وقتی منتظر ساعت دلخواه هستیم استفاده می‌شود.
    global_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_or_hours))

    global_app.add_handler(
        CallbackQueryHandler(button_mode_handler, pattern="^(chan_delgraphyha|chan_ahangziba|chan_test|send_now|sched_)"),
    )
    global_app.add_handler(CallbackQueryHandler(button_like_handler, pattern="^like_"))

    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 راه‌اندازی سرور روی پورت {port}...")
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
