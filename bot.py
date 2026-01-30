import os
import base64
import tempfile
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from openai import OpenAI

# ----------------------------
# Environment variables
# ----------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ----------------------------
# AI Clients
# ----------------------------
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ----------------------------
# User storage & preferences
# ----------------------------
user_ai_choice = {}
conversation_history = {}
user_message_counts = {}
user_voice_choice = {}

# Daily limits
DAILY_LIMIT_TOTAL = 50
DAILY_LIMIT_IMAGES_MAX = 5
DAILY_LIMIT_VOICE_MAX = 5

# Voices
VOICES = {
    "male": "onyx",
    "female": "nova",
    "echo": "echo",
    "shimmer": "shimmer"
}

# ----------------------------
# Helper functions
# ----------------------------
def get_total_used(user_id, ai_type):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}},
            "chatgpt": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}}
        }
    return sum(user_message_counts[user_id][ai_type][t]["count"] for t in ["text", "image", "voice"])

def get_type_used(user_id, ai_type, message_type):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}},
            "chatgpt": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}}
        }
    if message_type not in user_message_counts[user_id][ai_type]:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    if user_message_counts[user_id][ai_type][message_type]["date"] != today:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    return user_message_counts[user_id][ai_type][message_type]["count"]

def increment_message_count(user_id, ai_type, message_type):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}},
            "chatgpt": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}}
        }
    if message_type not in user_message_counts[user_id][ai_type]:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    if user_message_counts[user_id][ai_type][message_type]["date"] != today:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    user_message_counts[user_id][ai_type][message_type]["count"] += 1

# ----------------------------
# Telegram command handlers
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_ai_choice[user_id] = "claude"
    conversation_history[user_id] = []
    user_voice_choice[user_id] = "female"
    
    welcome_msg = """
🤖 Welcome! Dual AI Assistant

Use /claude or /chatgpt to switch AI
Use /voice to select voice (male/female/echo/shimmer)
Send any message, photo, or voice note
    """
    await update.message.reply_text(welcome_msg)

async def use_claude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_ai_choice[user_id] = "claude"
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Switched to Claude AI 🔵\nConversation cleared!")

async def use_chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_ai_choice[user_id] = "chatgpt"
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Switched to ChatGPT 🟢\nConversation cleared!")

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args
    if not args:
        current_voice = user_voice_choice.get(user_id, "female")
        msg = f"Current voice: {current_voice}\nUse: /voice male/female/echo/shimmer"
        await update.message.reply_text(msg)
        return
    choice = args[0].lower()
    if choice in VOICES:
        user_voice_choice[user_id] = choice
        await update.message.reply_text(f"✅ Voice set to: {choice}")
    else:
        await update.message.reply_text("❌ Invalid voice")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_ai = user_ai_choice.get(user_id, "claude")
    total_used = get_total_used(user_id, current_ai)
    images_used = get_type_used(user_id, current_ai, "image")
    voice_used = get_type_used(user_id, current_ai, "voice")
    total_remaining = DAILY_LIMIT_TOTAL - total_used
    images_remaining = DAILY_LIMIT_IMAGES_MAX - images_used
    voice_remaining = DAILY_LIMIT_VOICE_MAX - voice_used
    msg = f"AI: {current_ai}\nTotal: {total_used}/{DAILY_LIMIT_TOTAL}\nImages: {images_used}/{DAILY_LIMIT_IMAGES_MAX}\nVoice: {voice_used}/{DAILY_LIMIT_VOICE_MAX}"
    await update.message.reply_text(msg)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Conversation cleared!")

# ----------------------------
# OpenAI / Claude response helpers
# ----------------------------
async def get_claude_response(user_id, user_message, user_name):
    conversation_history[user_id].append({"role": "user", "content": user_message})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]
    response = claude_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1000,
        system="You are a helpful AI assistant.",
        messages=conversation_history[user_id]
    )
    ai_reply = response.content[0].text
    conversation_history[user_id].append({"role": "assistant", "content": ai_reply})
    return ai_reply

async def get_chatgpt_response(user_id, user_message, user_name):
    messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
    for msg in conversation_history.get(user_id, []):
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})
    
    # ✅ Correct OpenAI 1.x call
    response = openai_client.chat.completions.create(
        model="gpt-5-mini",
        messages=messages,
        max_tokens=1000,
        temperature=0.7
    )
    
    ai_reply = response.choices[0].message.content
    conversation_history.setdefault(user_id, []).append({"role": "user", "content": user_message})
    conversation_history[user_id].append({"role": "assistant", "content": ai_reply})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]
    return ai_reply

# ----------------------------
# Telegram text handler
# ----------------------------
async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    user_message = update.message.text
    
    current_ai = user_ai_choice.get(user_id, "claude")
    if get_total_used(user_id, current_ai) >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text(f"⚠️ Daily limit reached!")
        return
    
    await update.message.chat.send_action("typing")
    if current_ai == "claude":
        reply = await get_claude_response(user_id, user_message, user_name)
    else:
        reply = await get_chatgpt_response(user_id, user_message, user_name)
    increment_message_count(user_id, current_ai, "text")
    await update.message.reply_text(reply)

# ----------------------------
# Telegram photo handler
# ----------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_ai = user_ai_choice.get(user_id, "claude")
    
    if get_total_used(user_id, current_ai) >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text("⚠️ Daily limit reached!")
        return
    if get_type_used(user_id, current_ai, "image") >= DAILY_LIMIT_IMAGES_MAX:
        await update.message.reply_text("⚠️ Image limit reached!")
        return
    
    await update.message.chat.send_action("typing")
    
    try:
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')
        caption = update.message.caption or "What's in this image?"
        
        if current_ai == "claude":
            response = claude_client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": photo_base64}},
                        {"type": "text", "text": caption}
                    ]
                }]
            )
            result = response.content[0].text
        else:
            response = openai_client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": caption}],
                max_tokens=1000
            )
            result = response.choices[0].message.content
        
        increment_message_count(user_id, current_ai, "image")
        await update.message.reply_text(f"🖼️ Image Analysis:\n{result}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ----------------------------
# Telegram voice handler
# ----------------------------
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_ai = user_ai_choice.get(user_id, "claude")
    
    if get_total_used(user_id, current_ai) >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text("⚠️ Daily limit reached!")
        return
    if get_type_used(user_id, current_ai, "voice") >= DAILY_LIMIT_VOICE_MAX:
        await update.message.reply_text("⚠️ Voice limit reached!")
        return
    
    await update.message.reply_text("🎤 Transcribing...")
    voice_file = await update.message.voice.get_file()
    voice_bytes = await voice_file.download_as_bytearray()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp:
        temp.write(voice_bytes)
        temp_path = temp.name
    
    with open(temp_path, "rb") as audio:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio
        )
    os.unlink(temp_path)
    text = transcript.text
    
    await update.message.reply_text(f"📝 Transcription:\n{text}\n🤖 Responding...")
    
    if current_ai == "claude":
        reply = await get_claude_response(user_id, text, update.message.from_user.first_name)
    else:
        reply = await get_chatgpt_response(user_id, text, update.message.from_user.first_name)
    
    increment_message_count(user_id, current_ai, "voice")
    await update.message.reply_text(reply)

# ----------------------------
# Run the bot
# ----------------------------
def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("claude", use_claude))
    app.add_handler(CommandHandler("chatgpt", use_chatgpt))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("clear", clear_command))
    
    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    print("🤖 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    run_bot()
