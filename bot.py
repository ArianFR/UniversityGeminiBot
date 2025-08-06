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
from google_search_tool import GoogleSearch

# --- بخش تنظیمات و بارگیری کلیدها ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

if not TELEGRAM_BOT_TOKEN or not GOOGLE_API_KEY:
    raise ValueError("TELEGRAM_BOT_TOKEN or GOOGLE_API_KEY not found in .env file.")

genai.configure(api_key=GOOGLE_API_KEY)

# --- ۱. تعریف دستور سیستمی برای محدود کردن ربات ---
ACADEMIC_SYSTEM_INSTRUCTION = (
    "شما یک دستیار هوش مصنوعی به نام «دانشیار» هستید که منحصراً برای پاسخگویی به سوالات علمی، پژوهشی و دانشگاهی طراحی شده‌اید. "
    "وظیفه شما کمک به دانشجویان و محققان در زمینه جستجوی منابع، نگارش مقالات، تحلیل داده‌ها و موارد مشابه است. "
    "از پاسخ دادن به هرگونه سوال غیرمرتبط (مانند سوالات عمومی، طنز، سیاسی، شخصی و...) مؤدبانه امتناع کنید. "
    "اگر کاربر سوالی غیرمرتبط پرسید، به او یادآوری کنید که شما یک دستیار تخصصی دانشگاهی هستید و او را به طرح سوالات علمی تشویق کنید."
)

# --- تعریف حالت‌های مکالمه ---
SELECTING_ACTION, AWAITING_SEARCH_TOPIC, AWAITING_SUMMARY_TEXT, AWAITING_REWRITE_TEXT, AWAITING_FILE = range(5)

# ... (بقیه توابع start, button_handler, handle_file و غیره بدون تغییر باقی می‌مانند)
# ... (من برای کوتاهی از تکرار آن‌ها خودداری می‌کنم، شما نیازی به تغییر آن‌ها ندارید)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("🔍 جستجوی زنده منابع", callback_data="live_search_sources")],
        [InlineKeyboardButton("📄 خلاصه کردن فایل (PDF/TXT)", callback_data="summarize_file")],
        [InlineKeyboardButton("📝 ایجاد ساختار تحقیق", callback_data="create_outline")],
        [InlineKeyboardButton("✍️ بازنویسی پاراگراف", callback_data="rewrite_text")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if 'chat_history' not in context.user_data:
        context.user_data['chat_history'] = []
    message_text = (
        "سلام! من «دانشیار»، دستیار تخصصی دانشگاهی شما هستم. 🎓\n"
        "وظیفه من کمک به شما در امور پژوهشی است. لطفاً یک گزینه را انتخاب کنید:"
    )
    if update.message:
        await update.message.reply_text(message_text, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(text=message_text, reply_markup=reply_markup)
    return SELECTING_ACTION


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "live_search_sources":
        await query.edit_message_text(text="بسیار خب. لطفاً موضوع مورد نظر برای جستجوی زنده در وب را تایپ کنید:")
        return AWAITING_SEARCH_TOPIC
    elif action == "summarize_file":
        await query.edit_message_text(text="لطفاً فایل PDF یا TXT خود را برای خلاصه‌سازی آپلود کنید.")
        return AWAITING_FILE
    elif action == "rewrite_text":
        await query.edit_message_text(text="لطفاً پاراگرافی که نیاز به بازنویسی دارد را برایم بفرستید:")
        return AWAITING_REWRITE_TEXT
    elif action == "create_outline":
        await query.edit_message_text(text="لطفاً موضوع تحقیق خود را برای ایجاد ساختار ارسال کنید:")
        context.user_data['action_prompt'] = "برای یک مقاله پژوهشی با موضوع زیر، یک ساختار (outline) استاندارد و دقیق ایجاد کن:"
        return AWAITING_REWRITE_TEXT
    return SELECTING_ACTION

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    document = update.message.document
    if not document or not document.file_name.lower().endswith(('.pdf', '.txt')):
        await update.message.reply_text("فرمت فایل پشتیبانی نمی‌شود. لطفاً فایل PDF یا TXT ارسال کنید.")
        return AWAITING_FILE
        
    processing_msg = await update.message.reply_text("⏳ در حال دانلود و پردازش فایل...")
    try:
        file = await document.get_file()
        file_content_bytes = await file.download_as_bytearray()
        file_stream = io.BytesIO(file_content_bytes)
        
        extracted_text = ""
        if document.file_name.lower().endswith('.pdf'):
            reader = PdfReader(file_stream)
            for page in reader.pages:
                extracted_text += page.extract_text() + "\n"
        else:
            extracted_text = file_stream.read().decode('utf-8')

        if not extracted_text.strip():
            await processing_msg.edit_text("متنی در فایل یافت نشد یا فایل قابل خواندن نیست.")
            return ConversationHandler.END

        await processing_msg.edit_text("✅ فایل پردازش شد. در حال ارسال به هوش مصنوعی برای خلاصه‌سازی...")
        prompt = f"لطفاً متن استخراج شده از فایل زیر را به دقت خلاصه کن و نکات کلیدی آن را به صورت یک چکیده علمی ارائه بده:\n\n---\n{extracted_text[:15000]}\n---"
        await send_to_gemini(update, context, prompt)
    except Exception as e:
        logger.error(f"Error handling file: {e}")
        await processing_msg.edit_text(f"خطایی در پردازش فایل رخ داد: {e}")

    await update.message.reply_text("چه کار دیگری برایتان انجام دهم؟ برای دیدن گزینه‌ها /start را بزنید.")
    return ConversationHandler.END

async def handle_live_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_topic = update.message.text
    await update.message.reply_text(f"⏳ در حال جستجوی زنده در وب برای: \"{user_topic}\"...")
    try:
        search_results = Google Search(queries=[f"{user_topic} scientific review", f"{user_topic} key articles"])
        if not search_results:
            await update.message.reply_text("نتیجه‌ای در جستجوی زنده یافت نشد. لطفاً موضوع دیگری را امتحان کنید.")
            return ConversationHandler.END

        prompt = (f"بر اساس نتایج جستجوی زنده زیر درباره '{user_topic}', لطفاً ۵ منبع علمی معتبر را شناسایی و معرفی کن."
                  "برای هر کدام، عنوان، خلاصه‌ای کوتاه و در صورت امکان لینک را ذکر کن.\n\n"
                  "--- نتایج جستجو ---\n"
                  f"{search_results}\n"
                  "--- پایان نتایج ---")
        await update.message.reply_text("✅ نتایج یافت شد. در حال تحلیل و جمع‌بندی...")
        await send_to_gemini(update, context, prompt)
    except Exception as e:
        logger.error(f"Error in live search: {e}")
        await update.message.reply_text(f"خطایی در جستجوی زنده رخ داد: {e}")

    await update.message.reply_text("چه کار دیگری برایتان انجام دهم؟ برای دیدن گزینه‌ها /start را بزنید.")
    return ConversationHandler.END

async def handle_simple_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_text = update.message.text
    # اگر کاربر یک سوال عمومی بپرسد، این تابع اجرا می‌شود
    # دستور سیستمی که در send_to_gemini تزریق می‌شود، جلوی پاسخ به سوالات نامرتبط را می‌گیرد.
    base_prompt = context.user_data.pop('action_prompt', user_text) # اگر پرامپت آماده نبود، خود متن کاربر را بفرست
    
    # اگر متن از یک دکمه آمده باشد، موضوع را به آن اضافه می‌کنیم
    if base_prompt != user_text:
        full_prompt = f"{base_prompt}\n\n{user_text}"
    else:
        full_prompt = user_text

    await update.message.reply_text("⏳ در حال پردازش...")
    await send_to_gemini(update, context, full_prompt)
    
    await update.message.reply_text("چه کار دیگری برایتان انجام دهم؟ برای دیدن گزینه‌ها /start را بزنید.")
    return ConversationHandler.END


async def send_to_gemini(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    """تابع کمکی برای ارسال درخواست به Gemini با اعمال دستور سیستمی."""
    chat_history = context.user_data.get('chat_history', [])
    try:
        # --- ۲. تزریق دستور سیستمی هنگام ساخت مدل ---
        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            system_instruction=ACADEMIC_SYSTEM_INSTRUCTION
        )
        
        chat_session = model.start_chat(history=chat_history)
        response = chat_session.send_message(prompt)
        answer = response.text.strip()
        
        # آپدیت تاریخچه
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
        await update.message.reply_text(f"[خطا] مشکلی در ارتباط با هوش مصنوعی پیش آمد: {e}")

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.message.reply_text("✅ حافظه مکالمه پاک شد. می‌توانید یک موضوع جدید را شروع کنید.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.edit_message_text("فعالیت لغو شد.")
    else:
        await update.message.reply_text("فعالیت لغو شد.")
    return ConversationHandler.END


def main() -> None:
    """ساخت و اجرای ربات."""
    persistence = PicklePersistence(filepath="bot_persistence.pkl")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()
    
    # برای سوالات عمومی که در هیچ حالتی نیستند، یک MessageHandler جداگانه اضافه می‌کنیم
    # این اطمینان می‌دهد که حتی اگر کاربر خارج از مکالمه چیزی تایپ کند، باز هم محدودیت اعمال شود
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
    app.add_handler(general_handler) # این هندلر را در آخر اضافه می‌کنیم

    print("Bot is running as a Specialist Academic Assistant...")
    app.run_polling()

if __name__ == "__main__":
    main()
