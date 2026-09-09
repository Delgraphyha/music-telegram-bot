import os
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from datetime import datetime, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler

LOCAL_TZ = pytz.timezone('Europe/Berlin')

scheduler = BackgroundScheduler(timezone=LOCAL_TZ)
scheduler.start()

global_app = None

async def button_like_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer("ثبت شد! ❤️")
    except Exception:
        pass
    
    data = query.data
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
                            except:
                                count = 1
                        new_text = f"{base_text} ({count})"
                        new_row.append(InlineKeyboardButton(new_text, callback_data=button.callback_data))
                    else:
                        new_row.append(button)
                new_keyboard.append(new_row)
                
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
        except Exception as e:
            print(f"Like error: {e}")

def process_audio_clip(input_path, wav_path, ogg_path):
    clip_duration = "25"
    
    cut_cmd = ["ffmpeg", "-y", "-ss", "30", "-i", input_path, "-t", clip_duration, "-c:a", "libmp3lame", wav_path]
    res = subprocess.run(cut_cmd, capture_output=True)
    
    if res.returncode != 0 or not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
        cut_cmd = ["ffmpeg", "-y", "-ss", "0", "-i", input_path, "-t", clip_duration, "-c:a", "libmp3lame", wav_path]
        subprocess.run(cut_cmd, capture_output=True)

    ogg_cmd = ["ffmpeg", "-y", "-i", wav_path, "-c:a", "libopus", "-b:a", "64k", ogg_path]
    subprocess.run(ogg_cmd, capture_output=True)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    os.makedirs("downloads", exist_ok=True)
    user_id = update.effective_user.id
    photo_file = await update.message.photo[-1].get_file()
    custom_thumb_path = os.path.join("downloads", f"custom_thumb_{user_id}.jpg")
    await photo_file.download_to_drive(custom_thumb_path)
    
    context.user_data['custom_thumb_path'] = custom_thumb_path
    await update.message.reply_text("✅ عکس کاور اختصاصی ذخیره شد! حالا موزیک را بفرستید.")

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_custom_hours'):
        text = update.message.text
        try:
            hours = int(text)
            input_path = context.user_data.get('input_path')
            voice_path = context.user_data.get('voice_path')
            title = context.user_data.get('title', 'Music')
            channel_id = "@testDelgraphyha"
            chan_name = "Test Channel"
            
            if not input_path or not os.path.exists(input_path):
                await update.message.reply_text("❌ اطلاعات فایل منقضی شده است. دوباره موزیک را بفرستید.")
                context.user_data['waiting_for_custom_hours'] = False
                return

            run_time = datetime.now(LOCAL_TZ) + timedelta(hours=hours)
            scheduler.add_job(
                scheduled_job_wrapper,
                'date',
                run_date=run_time,
                args=[channel_id, chan_name, input_path, voice_path, title, context.user_data]
            )
            context.user_data['waiting_for_custom_hours'] = False
            await update.message.reply_text(f"⏰ پست برای **{hours} ساعت دیگر** (ساعت {run_time.strftime('%H:%M')}) زمان‌بندی شد!")
            return
        except ValueError:
            await update.message.reply_text("❌ لطفاً فقط یک عدد صحیح وارد کنید:")
            return

    await update.message.reply_text("⏳ در حال پردازش هوشمند موزیک...")
    
    os.makedirs("downloads", exist_ok=True)
    user_id = update.effective_user.id
    input_path = os.path.join("downloads", f"song_{user_id}.mp3")
    wav_path = os.path.join("downloads", f"temp_{user_id}.wav")
    voice_path = os.path.join("downloads", f"voice_{user_id}.ogg")
    
    if update.message.audio:
        audio_msg = update.message.audio
        audio_file = await audio_msg.get_file()
        title = audio_msg.title or audio_msg.file_name or "موزیک"
    elif update.message.document:
        audio_msg = update.message.document
        audio_file = await audio_msg.get_file()
        title = audio_msg.file_name or "موزیک"
    else:
        await update.message.reply_text("❌ لطفاً یک فایل صوتی معتبر ارسال کنید.")
        return

    try:
        await audio_file.download_to_drive(input_path, read_timeout=60, write_timeout=60, connect_timeout=60)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در دانلود فایل: {e}")
        return

    process_audio_clip(input_path, wav_path, voice_path)
    
    context.user_data['input_path'] = input_path
    context.user_data['voice_path'] = voice_path
    context.user_data['title'] = title
    context.user_data['user_id'] = user_id
    
    keyboard = [
        [
            InlineKeyboardButton("🚀 ارسال آنی", callback_data="send_now"),
            InlineKeyboardButton("⚡ تست (۱ دقیقه‌ای)", callback_data="sched_1min")
        ],
        [
            InlineKeyboardButton("⏱ ۶ ساعت دیگر", callback_data="sched_6h"),
            InlineKeyboardButton("⏳ ۱۲ ساعت دیگر", callback_data="sched_12h")
        ],
        [
            InlineKeyboardButton("✏️ ورود ساعت دلخواه", callback_data="sched_custom")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("✅ پردازش انجام شد. زمان انتشار پست را انتخاب کن:", reply_markup=reply_markup)

async def send_post_to_channel(bot, channel_id, chan_name, input_path, voice_path, title, user_data):
    custom_thumb = user_data.get('custom_thumb_path')
    final_thumb_path = custom_thumb if (custom_thumb and os.path.exists(custom_thumb)) else None

    keyboard = [
        [
            InlineKeyboardButton("👍 لایک", callback_data="like_btn"),
            InlineKeyboardButton("❤️ قلب", callback_data="like_heart"),
            InlineKeyboardButton("👏 دست زدن", callback_data="like_clap"),
            InlineKeyboardButton("🔥 آتش", callback_data="like_fire")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if final_thumb_path and os.path.exists(final_thumb_path):
            with open(final_thumb_path, 'rb') as photo:
                await bot.send_photo(chat_id=channel_id, photo=photo)
            try:
                os.remove(final_thumb_path)
                user_data.pop('custom_thumb_path', None)
            except:
                pass

        with open(input_path, 'rb') as audio:
            await bot.send_audio(
                chat_id=channel_id,
                audio=audio,
                title=title,
                caption=(
                    "🎵 **نسخه کامل موزیک**\n\n"
                    "🌐 سابسکرایب در یوتوب: [YouTube Channel](https://youtube.com/@delgraphyha?sub_confirmation=1)\n"
                    "🎬 تیک‌تاک: [TikTok Profile](https://tiktok.com/@wanderovlog)"
                ),
                parse_mode="Markdown",
                reply_markup=reply_markup
            )

        with open(voice_path, 'rb') as voice:
            await bot.send_voice(
                chat_id=channel_id,
                voice=voice,
                caption=(
                    "✨ بخش جذاب آهنگ\n\n"
                    "🎵 **گلچین ۲۵ ثانیه طلایی و پرانرژی موزیک**\n\n"
                    "✨ لذت ببرید و نظرات خود را با ما در میان بگذارید.\n\n"
                    "🌐 سابسکرایب در یوتوب: [YouTube Channel](https://youtube.com/@delgraphyha?sub_confirmation=1)\n"
                    "🎬 ما را در تیک‌تاک دنبال کنید: [TikTok Profile](https://tiktok.com/@wanderovlog)"
                ),
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        print(f"✅ پست با موفقیت به کانال {chan_name} ارسال شد.")
    except Exception as e:
        print(f"❌ خطا در ارسال پست: {e}")

def scheduled_job_wrapper(channel_id, chan_name, input_path, voice_path, title, user_data):
    global global_app
    if global_app:
        import asyncio
        asyncio.run_coroutine_threadsafe(
            send_post_to_channel(global_app.bot, channel_id, chan_name, input_path, voice_path, title, user_data),
            global_app.loop
        )

async def button_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    channel_id = "@testDelgraphyha"
    chan_name = "Test Channel"
    
    input_path = context.user_data.get('input_path')
    voice_path = context.user_data.get('voice_path')
    
    if not input_path or not os.path.exists(input_path):
        await query.edit_message_text("❌ اطلاعات فایل منقضی شده است. لطفاً دوباره موزیک را ارسال کنید.")
        return

    title = context.user_data.get('title', 'Music')
    now = datetime.now(LOCAL_TZ)

    if data == "send_now":
        await query.edit_message_text(f"⏳ در حال ارسال مستقیم پست به کانال {chan_name}...")
        await send_post_to_channel(context.bot, channel_id, chan_name, input_path, voice_path, title, context.user_data)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ پست با موفقیت به کانال ارسال شد!")
        return

    if data == "sched_custom":
        context.user_data['waiting_for_custom_hours'] = True
        await query.edit_message_text("✍️ لطفاً تعداد ساعت مد نظر خود را به صورت عدد (مثلاً `8` یا `12`) در چت بفرستید:")
        return

    if data == "sched_1min":
        run_time = now + timedelta(minutes=1)
        time_text = "۱ دقیقه دیگر"
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
        'date',
        run_date=run_time,
        args=[channel_id, chan_name, input_path, voice_path, title, context.user_data]
    )
    
    await query.edit_message_text(f"⏰ پست با موفقیت برای **{time_text}** (ساعت {run_time.strftime('%H:%M')}) زمان‌بندی شد!")

import time
import asyncio
from telegram import Bot

def main():
    global global_app
    TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    
    if not TOKEN:
        print("❌ خطا: توکن ربات پیدا نشد!")
        return
    
    # پاک کردن اجباری هرگونه وب‌هوک یا اتصال قبلی معلق از روی سرور تلگرام
    print("🧹 در حال پاکسازی اتصال‌های قبلی از سرور تلگرام...")
    try:
        temp_bot = Bot(TOKEN)
        asyncio.run(temp_bot.delete_webhook(drop_pending_updates=True))
    except Exception as e:
        print(f"⚠️ خطا در پاکسازی وب‌هوک: {e}")

    print("⏳ مکث ۵ ثانیه‌ای برای تثبیت توکن...")
    time.sleep(5)
    
    global_app = ApplicationBuilder().token(TOKEN).build()
    
    global_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    global_app.add_handler(MessageHandler(filters.AUDIO | filters.Document.ALL | (filters.TEXT & ~filters.COMMAND), handle_audio))
    global_app.add_handler(CallbackQueryHandler(button_mode_handler, pattern="^(send_now|sched_)"))
    global_app.add_handler(CallbackQueryHandler(button_like_handler, pattern="^like_"))

    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running!")

    def run_web_server():
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(("0.0.0.0", port), SimpleHandler)
        server.serve_forever()

    threading.Thread(target=run_web_server, daemon=True).start()

    print("🤖 ربات با موفقیت روشن شد و آماده به کار است...")
    global_app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
