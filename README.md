# UniversityGeminiBot



# Gemini Telegram Bot

A Telegram bot that allows you to chat with Google's Gemini models directly within Telegram. The bot is designed to be easy to set up and provides a seamless conversational experience with the ability to remember the context of your chat.

## ✨ Features

  * **Continuous Conversation:** The bot remembers your chat history, allowing for natural, back-and-forth conversations.
  * **Long Message Handling:** Automatically splits long responses (like code blocks) into multiple messages to avoid Telegram's character limits.
  * **Robust Error Handling:** Provides clear, user-friendly messages for common issues like API errors or safety blocks.
  * **Easy Setup:** Simple and quick deployment using Docker.

## 🚀 Setup

### 1\. Prerequisites

Before you begin, you'll need two API keys:

  * **Telegram Bot Token:** Get this by talking to BotFather on Telegram.
  * **Google Gemini API Key:** Obtain this from the [Google AI Studio](https://aistudio.google.com/app/apikey).

### 2\. Clone the Repository

Clone your project repository and navigate into the directory.

```bash
git clone <your-repo-url>
cd gemini-telegram-bot
```

### 3\. Configure Environment Variables

Create a file named `.env` in the root of the project. Fill it with your API keys:

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
GOOGLE_API_KEY=your_google_gemini_api_key_here
```

### 4\. Run the Bot

The easiest way to run the bot is with Docker.

  * **Build the Docker image:**

    ```bash
    docker build -t gemini-telegram-bot .
    ```

  * **Run the container:**

    ```bash
    docker run --env-file .env gemini-telegram-bot
    ```

The bot is now running. You can find it on Telegram and start chatting.

## 🤖 Usage

  * **`/start`**: Begin a new conversation. This command will clear the bot's memory of any previous chat.
  * **`/cancel`**: End the current conversation.
  * **Chatting:** Simply send your messages. The bot will respond based on the current chat history.
