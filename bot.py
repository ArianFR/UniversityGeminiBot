import os
import logging
import io
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
    PicklePersistence,
)
import google.generativeai as genai
from dotenv import load_dotenv
from PyPDF2 import PdfReader

# ابزار جستجوی گوگل
from google_search_tool import GoogleSearch  # ← نام صحیح بدون فاصله

# --- بارگذاری متغیرهای محیطی از فایل .env ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

if not TELEGRAM_BOT_TOKEN or not GOOGLE_API_KEY:
    raise ValueError("مقادیر TELEGRAM_BOT_TOKEN یا GOOGLE_API_KEY در فایل .env یافت نشد.")

# پیکربندی کتابخانه Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# --- دستور سیستمی مدل (System Prompt) ---
ACADEMIC_SYSTEM_INSTRUCTION = (
    "شما یک دستیار هوش مصنوعی به نام «دانشیار» هستید که فقط برای پاسخ‌گویی به پرسش‌های علمی، پژوهشی و دانشگاهی طراحی شده‌اید. "
    "وظیفه شما کمک به دانشجویان و پژوهشگران در جستجوی منابع، نگارش مقالات، تحلیل داده‌ها و موضوعات مشابه است. "
    "از پاسخ دادن به هرگونه سؤال غیرمرتبط (مانند موضوعات عمومی، طنز، سیاسی، شخصی و...) مؤدبانه خودداری کنید. "
    "اگر کاربر پرسشی غیرمرتبط پرسید، یادآوری کنید که شما دستیار تخصصی دانشگاهی هستید و او را تشویق کنید پرسش علمی مطرح کند."
)

# --- حالت‌های مکالمه ---
SELECTING_ACTION, AWAITING_SEARCH_TOPIC, AWAITING_SUMMARY_TEXT, AWAITING_REWRITE_TEXT, AWAITING_FILE = range(5)


# شروع مکالمه
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("🔍 جستجوی زنده منابع", callback_data="live_search_sources")],
        [InlineKeyboardButton("📄 خلاصه‌سازی فایل (PDF/TXT)", callback_data="summarize_file")],
        [InlineKeyboardButton("📝 ایجاد ساختار تحقیق", callback_data="create_outline")],
        [InlineKeyboardButton("✍️ بازنویسی پاراگراف", callback_data="rewrite_text")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if 'chat_history' not in context.user_data:
        context.user_data['chat_history'] = []

    message_text = (
        "سلام! من «دانشیار»، دستیار تخصصی دانشگاهی شما هستم. 🎓\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
    )

    if update.message:
        await update.message.reply_text(message_text, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(text=message_text, reply_markup=reply_markup)

    return SELECTING_ACTION


# مدیریت کلیک روی دکمه‌ها
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "live_search_sources":
        await query.edit_message_text(text="لطفاً موضوع مورد نظر برای جستجو را وارد کنید:")
        return AWAITING_SEARCH_TOPIC
    elif action == "summarize_file":
        await query.edit_message_text(text="لطفاً فایل PDF یا TXT خود را ارسال کنید.")
        return AWAITING_FILE
    elif action == "rewrite_text":
        await query.edit_message_text(text="لطفاً پاراگرافی که باید بازنویسی شود را ارسال کنید:")
        return AWAITING_REWRITE_TEXT
    elif action == "create_outline":
        await query.edit_message_text(text="موضوع تحقیق خود را برای ایجاد ساختار ارسال کنید:")
        context.user_data['action_prompt'] = "برای یک مقاله پژوهشی با موضوع زیر، یک ساختار استاندارد و دقیق ایجاد کن:"
        return AWAITING_REWRITE_TEXT

    return SELECTING_ACTION


# مدیریت فایل PDF/TXT
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    document = update.message.document
    if not document or not document.file_name.lower().endswith(('.pdf', '.txt')):
        await update.message.reply_text("فرمت فایل پشتیبانی نمی‌شود. فقط PDF یا TXT ارسال کنید.")
        return AWAITING_FILE

    processing_msg = await update.message.reply_text("⏳ در حال پردازش فایل...")
    try:
        file = await document.get_file()
        file_content_bytes = await file.download_as_bytearray()
        file_stream = io.BytesIO(file_content_bytes)

        extracted_text = ""
        if document.file_name.lower().endswith('.pdf'):
            reader = PdfReader(file_stream)
            for page in reader.pages:
                text = page.extract_text() or ""
                extracted_text += text + "\n"
        else:
            extracted_text = file_stream.read().decode('utf-8', errors='ignore')

        if not extracted_text.strip():
            await processing_msg.edit_text("متنی در فایل یافت نشد یا فایل قابل خواندن نیست.")
            return ConversationHandler.END

        await processing_msg.edit_text("✅ فایل پردازش شد. در حال خلاصه‌سازی...")
        prompt = f"لطفاً متن زیر را خلاصه کرده و نکات کلیدی آن را به شکل چکیده علمی ارائه بده:\n\n---\n{extracted_text[:15000]}\n---"
        await send_to_gemini(update, context, prompt)

    except Exception as e:
        logger.error(f"Error handling file: {e}")
        await processing_msg.edit_text(f"خطایی در پردازش فایل رخ داد: {e}")

    await update.message.reply_text("برای شروع دوباره /start را بزنید.")
    return ConversationHandler.END


# مدیریت جستجوی زنده
async def handle_live_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_topic = update.message.text
    await update.message.reply_text(f"⏳ در حال جستجو برای: «{user_topic}» ...")
    try:
        search_results = GoogleSearch(queries=[f"{user_topic} scientific review", f"{user_topic} key articles"])
        if not search_results:
            await update.message.reply_text("نتیجه‌ای یافت نشد. موضوع دیگری را امتحان کنید.")
            return ConversationHandler.END

        prompt = (
            f"بر اساس نتایج جستجو درباره '{user_topic}', لطفاً ۵ منبع علمی معتبر را معرفی کن "
            f"و برای هر یک عنوان، خلاصه کوتاه و لینک ارائه بده.\n\n---\n{search_results}\n---"
        )
        await update.message.reply_text("✅ نتایج یافت شد. در حال تحلیل...")
        await send_to_gemini(update, context, prompt)

    except Exception as e:
        logger.error(f"Error in live search: {e}")
        await update.message.reply_text(f"خطایی در جستجو رخ داد: {e}")

    await update.message.reply_text("برای شروع دوباره /start را بزنید.")
    return ConversationHandler.END


# مدیریت ورودی متنی ساده
async def handle_simple_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_text = update.message.text
    base_prompt = context.user_data.pop('action_prompt', user_text)

    if base_prompt != user_text:
        full_prompt = f"{base_prompt}\n\n{user_text}"
    else:
        full_prompt = user_text

    await update.message.reply_text("⏳ در حال پردازش...")
    await send_to_gemini(update, context, full_prompt)

    await update.message.reply_text("برای شروع دوباره /start را بزنید.")
    return ConversationHandler.END


# ارسال درخواست به Gemini
async def send_to_gemini(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    chat_history = context.user_data.get('chat_history', [])
    try:
        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            system_instruction=ACADEMIC_SYSTEM_INSTRUCTION
        )
        chat_session = model.start_chat(history=chat_history)

        # ممکن است متد async باشد؛ بسته به نسخه کتابخانه
        response = chat_session.send_message(prompt)
        answer = response.text.strip()

        chat_history.append({'role': 'user', 'parts': [prompt]})
        chat_history.append({'role': 'model', 'parts': [answer]})
        context.user_data['chat_history'] = chat_history

        limit = 4096
        if len(answer) > limit:
            for i in range(0, len(answer), limit):
                await update.message.reply_text(answer[i:i + limit])
        else:
            await update.message.reply_text(answer)

    except Exception as e:
        logger.error(f"Error in send_to_gemini: {e}")
        await update.message.reply_text(f"[خطا] مشکل در ارتباط با هوش مصنوعی: {e}")


# پاک کردن تاریخچه مکالمه
async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.message.reply_text("✅ تاریخچه مکالمه پاک شد.")


# لغو عملیات
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.edit_message_text("عملیات لغو شد.")
    else:
        await update.message.reply_text("عملیات لغو شد.")
    return ConversationHandler.END


# اجرای ربات
def main() -> None:
    persistence = PicklePersistence(filepath="bot_persistence.pkl")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()

    general_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_simple_prompt)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ACTION: [CallbackQueryHandler(button_handler)],
            AWAITING_SEARCH_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_live_search)],
            AWAITING_FILE: [MessageHandler(filters.Document.ALL, handle_file)],
            AWAITING_REWRITE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_simple_prompt)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        persistent=True,
        name="main_conversation_handler"
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(general_handler)

    print("Bot is running as a Specialist Academic Assistant...")
    app.run_polling()


if __name__ == "__main__":
    main()
