import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler
import google.generativeai as genai
from dotenv import load_dotenv

# --- بخش تنظیمات و بارگیری کلیدها ---
# Load environment variables from .env file
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Check if environment variables are loaded
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found. Please set it in your .env file.")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found. Please set it in your .env file.")

# Configure Gemini API
genai.configure(api_key=GOOGLE_API_KEY)

# --- تعریف پرامپت‌های آماده دانشگاهی ---
PROMPT_MAP = {
    "🔍 جستجوی منابع": "من در حال تحقیق روی یک موضوع هستم. لطفاً به عنوان یک دستیار پژوهشی، ۵ مقاله علمی کلیدی و معتبر در مورد موضوعی که در ادامه تایپ می‌کنم، به همراه خلاصه‌ای کوتاه از هر کدام، به من معرفی کن. نام نویسندگان و سال انتشار را نیز ذکر کن.",
    "📝 ایجاد ساختار تحقیق": "برای یک مقاله پژوهشی با موضوعی که در ادامه مشخص می‌کنم، یک ساختار (outline) استاندارد ایجاد کن. این ساختار باید شامل بخش‌های اصلی مانند مقدمه، پیشینه تحقیق، روش تحقیق، یافته‌ها، و نتیجه‌گیری باشد.",
    "📄 نوشتن چکیده مقاله": "من متن اصلی تحقیق خود را برایت ارسال می‌کنم. لطفاً بر اساس این متن، یک چکیده (Abstract) ساختاریافته در حدود ۲۰۰ کلمه بنویس که شامل هدف، روش، نتایج کلیدی و نتیجه‌گیری اصلی باشد.",
    "✍️ بازنویسی پاراگراف": "لطفاً پاراگرافی که در ادامه برایت می‌فرستم را با حفظ معنای اصلی، به شکلی روان‌تر و با واژگان آکادمیک بازنویسی کن تا وضوح و کیفیت آن بهبود یابد."
}


# Define states for the ConversationHandler
CHAT = 0

# --- Helper Functions ---
def split_message(text, limit=4096):
    """Splits a long string into a list of strings, each within the specified limit."""
    chunks = []
    current_chunk = ""
    for line in text.splitlines():
        if len(current_chunk) + len(line) + 1 > limit:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message with a custom keyboard and initializes the chat history."""
    # ایجاد کیبورد با دکمه‌های تعریف شده
    keyboard = [list(PROMPT_MAP.keys())[i:i + 2] for i in range(0, len(PROMPT_MAP.keys()), 2)]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    await update.message.reply_text(
        "خوش آمدید! شما با دستیار دانشگاهی Gemini گفتگو می‌کنید. 🎓\n"
        "می‌توانید از دکمه‌های زیر برای ارسال دستورات آماده استفاده کنید یا سوال خود را تایپ کنید.\n"
        "برای شروع مجدد /start و برای پایان /cancel را بزنید.",
        reply_markup=reply_markup
    )
    # Initialize chat history for the new conversation
    context.user_data['chat_history'] = []
    return CHAT

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles user messages (from text or button clicks), sends them to Gemini, and replies with the response.
    """
    user_input = update.message.text
    
    # بررسی می‌کند که آیا ورودی کاربر یکی از دکمه‌ها است یا خیر
    # اگر بود، پرامپت کامل را از دیکشنری برمی‌دارد
    prompt_to_send = PROMPT_MAP.get(user_input, user_input)

    # نمایش پیام "در حال پردازش" برای بهبود تجربه کاربری
    processing_message = await update.message.reply_text("⏳ در حال پردازش...")

    chat_history = context.user_data.get('chat_history', [])

    try:
        model_name = "gemini-1.5-flash"
        gemini_model = genai.GenerativeModel(model_name)
        
        chat_session = gemini_model.start_chat(history=chat_history)
        
        gemini_response = chat_session.send_message(prompt_to_send)
        answer = gemini_response.text.strip()
        
        # آپدیت تاریخچه گفتگو
        chat_history.append({'role': 'user', 'parts': [prompt_to_send]}) # پرامپت واقعی را ذخیره می‌کنیم
        chat_history.append({'role': 'model', 'parts': [answer]})
        
        context.user_data['chat_history'] = chat_history

        # حذف پیام "در حال پردازش"
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)

        # ارسال پاسخ نهایی
        response_chunks = split_message(answer)
        for chunk in response_chunks:
            await update.message.reply_text(chunk)

    except Exception as e:
        # حذف پیام "در حال پردازش" در صورت بروز خطا
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
        await update.message.reply_text(f"[خطا] مشکلی پیش آمد: {str(e)}")

    return CHAT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ends the conversation."""
    await update.message.reply_text("خداحافظ! برای شروع مجدد /start را بزنید.")
    if 'chat_history' in context.user_data:
        del context.user_data['chat_history']
    return ConversationHandler.END

# --- Main Application ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    
    app.add_handler(conv_handler)
    
    print("Bot is running...")
    app.run_polling()
