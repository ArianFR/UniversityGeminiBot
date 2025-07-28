import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler
import google.generativeai as genai
from dotenv import load_dotenv

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
    """Sends a welcome message and initializes the chat history."""
    await update.message.reply_text(
        "Welcome! You are now chatting with Gemini! I can remember our conversation. "
        "Send me your questions. To start a new conversation, use /start again. "
        "To end our chat, use /cancel."
    )
    # Initialize chat history for the new conversation
    context.user_data['chat_history'] = []
    return CHAT

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles user messages, sends them to Gemini, and replies with the response.
    Splits long responses into multiple messages.
    """
    user_input = update.message.text

    # Get or initialize the chat history
    chat_history = context.user_data.get('chat_history', [])

    try:
        # Use a more suitable model, e.g., gemini-1.5-flash
        model_name = "gemini-1.5-flash"
        gemini_model = genai.GenerativeModel(model_name)
        
        # Start a chat with the conversation history
        chat_session = gemini_model.start_chat(history=chat_history)
        
        # Send the user's message to the chat session
        gemini_response = chat_session.send_message(user_input)
        answer = gemini_response.text.strip()
        
        # Update the chat history with the new turn
        chat_history.append({'role': 'user', 'parts': [user_input]})
        chat_history.append({'role': 'model', 'parts': [answer]})
        
        # Store the updated chat history
        context.user_data['chat_history'] = chat_history

        # Split the long answer into multiple messages if needed
        response_chunks = split_message(answer)
        
        for chunk in response_chunks:
            await update.message.reply_text(chunk)

    except genai.types.StopCandidateException:
        # This error occurs when the model's response is inappropriate or blocked.
        await update.message.reply_text(
            "[Gemini Error] The response was blocked due to safety reasons. "
            "Please try rephrasing your prompt."
        )
    except genai.types.BlockedPromptException:
        await update.message.reply_text(
            "[Gemini Error] Your prompt was blocked due to safety reasons. "
            "Please try a different prompt."
        )
    except genai.types.ClientError as e:
        # Catch specific API errors from Gemini
        error_message = str(e)
        if "404" in error_message and ("model" in error_message or "not found" in error_message):
            await update.message.reply_text(
                "[Gemini Error] Model not found. Please check your API access and model name. "
                "Try updating the model name or check your Google AI Studio for available models."
            )
        else:
            await update.message.reply_text(f"[Gemini Error] A client error occurred: {error_message}")
    except Exception as e:
        # Catch any other unexpected errors
        await update.message.reply_text(f"[An unexpected error occurred] {str(e)}")

    return CHAT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ends the conversation."""
    await update.message.reply_text("Goodbye! To start a new chat, use /start.")
    # Clear chat history when the conversation ends
    if 'chat_history' in context.user_data:
        del context.user_data['chat_history']
    return ConversationHandler.END

# --- Main Application ---

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # ConversationHandler to manage the state of the chat
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