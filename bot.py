import os
import base64
import tempfile
from datetime import datetime
from io import BytesIO

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

import anthropic
from openai import OpenAI

# ================== ENV ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ================== CLIENTS ==================

claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ================== MODELS ==================

CLAUDE_MODEL = "claude-sonnet-4-20250514"  # Sonnet 4.5 (API ID)
CHATGPT_MODEL = "gpt-5-mini"
VISION_MODEL = "gpt-4o"
IMAGE_MODEL = "gpt-image-1"
WHISPER_MODEL = "whisper-1"

# ================== STATE ==================

user_ai_choice = {}
conversation_history = {}
user_message_counts = {}

DAILY_LIMIT_TOTAL = 50
DAILY_LIMIT_IMAGES_MAX = 5
DAILY_LIMIT_VOICE_MAX = 5

# ================== COMMANDS ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    user_ai_choice[uid] = "claude"
    conversation_history[uid] = []

    await update.message.reply_text(
        "🤖 Dual AI Bot is online.\n\n"
        "Use /claude or /chatgpt to switch AI.\n"
        "Send text, images, or voice messages."
    )

async def use_claude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    user_ai_choice[uid] = "claude"
    conversation_history[uid] = []
    await update.message.reply_text("✅ Switched to Claude (Sonnet 4.5)")

async def use_chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    user_ai_choice[uid] = "chatgpt"
    conversation_history[uid] = []
    await update.message.reply_text("✅ Switched to ChatGPT")

# ================== TEXT ==================

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    text = update.message.text
    name = update.message.from_user.first_name

    user_ai_choice.setdefault(uid, "claude")
    conversation_history.setdefault(uid, [])

    await update.message.chat.send_action(ChatAction.TYPING)

    if user_ai_choice[uid] == "claude":
        reply = await get_claude_response(uid, text, name)
    else:
        reply = await get_chatgpt_response(uid, text)

    increment_message_count(uid, user_ai_choice[uid], "text")
    await update.message.reply_text(reply)

# ================== CLAUDE ==================

async def get_claude_response(uid, text, name):
    conversation_history[uid].append({"role": "user", "content": text})
    conversation_history[uid] = conversation_history[uid][-20:]

    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        system="Respond naturally and in the same language.",
        max_tokens=1000,
        messages=conversation_history[uid]
    )

    reply = response.content[0].text
    conversation_history[uid].append({"role": "assistant", "content": reply})
    return reply

# ================== CHATGPT ==================

async def get_chatgpt_response(uid, text):
    messages = [{"role": "system", "content": "Respond naturally and in the same language."}]
    messages += conversation_history[uid]
    messages.append({"role": "user", "content": text})

    response = openai_client.chat.completions.create(
        model=CHATGPT_MODEL,
        messages=messages,
        max_tokens=1000,
        temperature=0.7
    )

    reply = response.choices[0].message.content
    conversation_history[uid].append({"role": "assistant", "content": reply})
    return reply

# ================== IMAGE ANALYSIS ==================

async def analyze_image_claude(image_base64, prompt):
    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_base64
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    )
    return response.content[0].text

async def analyze_image_chatgpt(image_base64, prompt):
    response = openai_client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        max_tokens=1000
    )
    return response.choices[0].message.content

# ================== IMAGE GENERATION ==================

async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Usage: /generate description")
        return

    response = openai_client.images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        size="1024x1024"
    )

    await update.message.reply_photo(response.data[0].url)

# ================== VOICE ==================

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice_file = await update.message.voice.get_file()
    voice_bytes = await voice_file.download_as_bytearray()

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(voice_bytes)
        path = f.name

    with open(path, "rb") as audio:
        transcript = openai_client.audio.transcriptions.create(
            file=audio,
            model=WHISPER_MODEL
        )

    os.unlink(path)
    await update.message.reply_text(f"📝 {transcript.text}")

# ================== LIMITS ==================

def increment_message_count(uid, ai, t):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    user_message_counts.setdefault(uid, {}).setdefault(ai, {}).setdefault(t, {"count": 0, "date": today})
    if user_message_counts[uid][ai][t]["date"] != today:
        user_message_counts[uid][ai][t] = {"count": 0, "date": today}
    user_message_counts[uid][ai][t]["count"] += 1

# ================== MAIN ==================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("claude", use_claude))
    app.add_handler(CommandHandler("chatgpt", use_chatgpt))
    app.add_handler(CommandHandler("generate", generate_image_command))

    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))

    print("🤖 Dual AI Bot running (Claude 4.5 + ChatGPT)")
    app.run_polling()

if __name__ == "__main__":
    main()
