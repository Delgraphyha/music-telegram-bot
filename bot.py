import os
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CallbackQueryHandler, ContextTypes, filters

async def button_like_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    # بررسی اینکه کدام دکمه لایک کلیک شده است
    if data.startswith("like_"):
        # خواندن تعداد لایک‌های قبلی از متن دکمه یا ذخیره در context
        keyboard = query.message.reply_markup.inline_keyboard
        new_keyboard = []
        
        for row in keyboard:
            new_row = []
            for button in row:
                if button.callback_data == data:
                    # استخراج تعداد لایک فعلی و اضافه کردن یک واحد به آن
                    text = button.text
                    if "(" in text:
                        base_text, count_str = text.split("(")
                        count = int(count_str.replace(")", "")) + 1
                        new_text = f"{base_text.strip()} ({count})"
                    else:
                        new_text = f"{text} (1)"
                    new_row.append(InlineKeyboardButton(new_text, callback_data=button.callback_data))
                else:
                    new_row.append(button)
            new_keyboard.append(new_row)
            
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
        except Exception:
            pass
        
# تابع پردازش صوت با ffmpeg
def process_audio_clip(input_path, wav_path, ogg_path):
    clip_duration = "25"
    
    # بریدن مستقیم از ثانیه ۳۰ به بعد
    cut_cmd = ["ffmpeg", "-y", "-ss", "30", "-i", input_path, "-t", clip_duration, "-c:a", "libmp3lame", wav_path]
    res = subprocess.run(cut_cmd, capture_output=True)
    
    # اگر آهنگ کوتاه بود و ثانیه ۳۰ نداشت، از ثانیه صفر ببر
    if res.returncode != 0 or not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
        cut_cmd = ["ffmpeg", "-y", "-ss", "0", "-i", input_path, "-t", clip_duration, "-c:a", "libmp3lame", wav_path]
        subprocess.run(cut_cmd, capture_output=True)

    # تبدیل به فرمت OGG برای ویس تلگرام
    ogg_cmd = ["ffmpeg", "-y", "-i", wav_path, "-c:a", "libopus", "-b:a", "64k", ogg_path]
    subprocess.run(ogg_cmd, capture_output=True)

# دریافت عکس کاور اختصاصی
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    os.makedirs("downloads", exist_ok=True)
    photo_file = await update.message.photo[-1].get_file()
    await photo_file.download_to_drive("downloads/user_custom_thumb.jpg")
    await update.message.reply_text("✅ عکس کاور اختصاصی با موفقیت ذخیره شد! حالا موزیک را بفرستید.")

# دریافت موزیک و نمایش دکمه‌های انتخاب کانال
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ در حال پردازش هوشمند موزیک...")
    
    os.makedirs("downloads", exist_ok=True)
    input_path = os.path.join("downloads", "downloaded_song.mp3")
    wav_path = os.path.join("downloads", "temp.wav")
    voice_path = os.path.join("downloads", "best_voice.ogg")
    
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
    
    # ذخیره مسیرها در حافظه موقت
    context.user_data['input_path'] = input_path
    context.user_data['voice_path'] = voice_path
    context.user_data['title'] = title
    
    # دکمه‌های شیشه‌ای با نام کانال‌های خودت
    keyboard = [
        [
            InlineKeyboardButton("📢 دلگرافی‌ها", callback_data="chan_1"),
            InlineKeyboardButton("📢 آهنگ زیبا موزیک", callback_data="chan_2")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("✅ پردازش انجام شد. حالا انتخاب کن این پست به کدام کانال ارسال شود:", reply_markup=reply_markup)

# مدیریت کلیک روی دکمه کانال‌ها و ارسال پست
async def button_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    input_path = context.user_data.get('input_path')
    voice_path = context.user_data.get('voice_path')
    
    if not input_path or not os.path.exists(input_path):
        await query.edit_message_text("❌ اطلاعات فایل منقضی شده است. لطفاً دوباره موزیک را ارسال کنید.")
        return

    data = query.data
    if data == "chan_1":
        channel_id = "@Delgraphyha"
        chan_name = "دلگرافی‌ها"
    elif data == "chan_2":
        channel_id = "@ahangzibamusic"
        chan_name = "آهنگ زیبا موزیک"
    else:
        return

    title = context.user_data.get('title', 'Music')
    custom_thumb = "downloads/user_custom_thumb.jpg"
    final_thumb_path = custom_thumb if os.path.exists(custom_thumb) else None

    # دکمه‌های زیر پست
    keyboard = [
        [
            InlineKeyboardButton("👍 لایک", callback_data="like_btn"),
            InlineKeyboardButton("❤️ قلب", callback_data="like_heart"),
            InlineKeyboardButton("👏 دست زدن", callback_data="like_clap"),
            InlineKeyboardButton("🔥 آتش", callback_data="like_fire")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(f"⏳ در حال ارسال پست به کانال {chan_name}...")

    # ارسال عکس کاور (اگر موجود باشد)
    if final_thumb_path:
        await context.bot.send_photo(chat_id=channel_id, photo=open(final_thumb_path, 'rb'))

    # ارسال فایل صوتی اصلی با کپشن کامل
    with open(input_path, 'rb') as audio:
        await context.bot.send_audio(
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

    # ارسال ویس ۲۵ ثانیه‌ای گلچین‌شده با کپشن کامل
    with open(voice_path, 'rb') as voice:
        await context.bot.send_voice(
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
        
    await query.edit_message_text(f"✅ پست با موفقیت به کانال {chan_name} ارسال شد!")
def main():
    # خواندن توکن از متغیر محیطی سرور
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    
    if not TOKEN:
        print("❌ خطا: توکن ربات پیدا نشد!")
        return
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    app.add_handler(CallbackQueryHandler(button_channel_handler, pattern="^chan_"))
    app.add_handler(CallbackQueryHandler(button_like_handler, pattern="^like_"))
    
    print("🤖 ربات با موفقیت روشن شد و آماده به کار است...")
    app.run_polling()

if __name__ == "__main__":
    main()
