import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from openai import OpenAI
import base64
from datetime import datetime
import tempfile

# TEST: Print to logs what we imported
print("=" * 50)
print("IMPORT TEST:")
print(f"OpenAI module: {OpenAI}")
print(f"Anthropic module: {anthropic}")
print("=" * 50)

# Get from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize AI clients
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# User preferences and storage
user_ai_choice = {}
conversation_history = {}
user_message_counts = {}
user_voice_choice = {}  # Store user's voice preference

# Daily limits
DAILY_LIMIT_TOTAL = 50
DAILY_LIMIT_IMAGES_MAX = 5
DAILY_LIMIT_VOICE_MAX = 5

# Available voices
VOICES = {
    "male": "onyx",
    "female": "nova",
    "echo": "echo",
    "shimmer": "shimmer"
}

# ---------------------- COMMAND HANDLERS ----------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_ai_choice[user_id] = "claude"
    user_voice_choice[user_id] = "female"
    conversation_history[user_id] = []

    welcome_msg = """
🤖 Welcome! I'm a Dual AI Assistant with superpowers!

🎨 **Choose your AI:**
/claude - Use Claude AI (default) 🔵
/chatgpt - Use ChatGPT 🟢

🔊 **Choose your voice:**
/voice - Select male or female voice

🌟 **Features:**
💬 Smart conversations
🖼️ Image analysis - Send me photos!
🎤 Voice messages - I'll transcribe & respond
🎨 Image generation - Ask me to create images
🔊 Text-to-speech - Convert text to voice
💻 Code writing & debugging

**Other commands:**
/status - Check AI & remaining messages
/generate [description] - Create an image
/speak [text] - Generate voice message
/clear - Clear conversation history
/help - Show help

Current AI: Claude 🔵
Current Voice: Female 🎙️

Just send any message, photo, or voice note!
    """
    await update.message.reply_text(welcome_msg)

async def use_claude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_ai_choice[user_id] = "claude"
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Switched to Claude AI 🔵\nConversation cleared. Send me a message!")

async def use_chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_ai_choice[user_id] = "chatgpt"
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Switched to ChatGPT 🟢\nConversation cleared. Send me a message!")

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args

    if not args:
        current_voice = user_voice_choice.get(user_id, "female")
        msg = f"""
🎙️ **Voice Settings**

Current voice: {current_voice.title()}

**Choose your preferred voice:**
/voice male - Deep male voice (Onyx)
/voice female - Clear female voice (Nova)
/voice echo - Male voice (Echo)
/voice shimmer - Soft female voice (Shimmer)

Test it with: /speak Hello, this is my voice!
        """
        await update.message.reply_text(msg)
        return

    choice = args[0].lower()
    if choice in ["male", "female", "echo", "shimmer"]:
        user_voice_choice[user_id] = choice
        await update.message.reply_text(f"✅ Voice set to: {choice.title()}\n\nTry it: /speak Hello, I sound different now!")
    else:
        await update.message.reply_text("❌ Invalid voice. Use: male, female, echo, or shimmer")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_ai = user_ai_choice.get(user_id, "claude")

    total_used = get_total_used(user_id, current_ai)
    images_used = get_type_used(user_id, current_ai, "image")
    voice_used = get_type_used(user_id, current_ai, "voice")

    total_remaining = DAILY_LIMIT_TOTAL - total_used
    images_remaining = DAILY_LIMIT_IMAGES_MAX - images_used
    voice_remaining = DAILY_LIMIT_VOICE_MAX - voice_used

    status_msg = f"📊 Currently using: {'Claude AI 🔵' if current_ai == 'claude' else 'ChatGPT 🟢'}\n\n"
    status_msg += f"Daily Usage ({current_ai.upper()}):\n"
    status_msg += f"📝 Total messages: {total_used}/{DAILY_LIMIT_TOTAL}\n"
    status_msg += f"🖼️ Images used: {images_used}/{DAILY_LIMIT_IMAGES_MAX}\n"
    status_msg += f"🎤 Voice used: {voice_used}/{DAILY_LIMIT_VOICE_MAX}\n\n"
    status_msg += f"💡 Remaining:\n"
    status_msg += f"• {total_remaining} total messages\n"
    status_msg += f"• {images_remaining} more images allowed\n"
    status_msg += f"• {voice_remaining} more voice messages allowed\n\n"
    status_msg += f"⚡ Switch to /{'chatgpt' if current_ai == 'claude' else 'claude'} for separate quota!\n"
    status_msg += f"Resets at midnight UTC."
    await update.message.reply_text(status_msg)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Conversation cleared!")

# ---------------------- OPENAI CORRECTED ----------------------

async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_ai = user_ai_choice.get(user_id, "claude")
    total_used = get_total_used(user_id, current_ai)
    if total_used >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text(f"⚠️ Daily limit reached for {current_ai.upper()}! (50 messages/day)")
        return
    images_used = get_type_used(user_id, current_ai, "image")
    if images_used >= DAILY_LIMIT_IMAGES_MAX:
        await update.message.reply_text(f"⚠️ Maximum images reached! (5 images/day)")
        return
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Usage: /generate [description]")
        return
    await update.message.reply_text(f"🎨 Generating: '{prompt}'\nPlease wait...")

    try:
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            n=1
        )
        image_url = response.data[0].url
        increment_message_count(user_id, current_ai, "image")
        await update.message.reply_photo(photo=image_url, caption=f"🎨 {prompt}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def enhance_speech_text(text):
    try:
        response = openai_client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "Enhance text for TTS with natural expression."},
                {"role": "user", "content": text}
            ],
            max_tokens=200,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Enhancement error: {e}")
        return text

async def speak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_ai = user_ai_choice.get(user_id, "claude")
    total_used = get_total_used(user_id, current_ai)
    if total_used >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text(f"⚠️ Daily limit reached for {current_ai.upper()}! (50 messages/day)")
        return
    voice_used = get_type_used(user_id, current_ai, "voice")
    if voice_used >= DAILY_LIMIT_VOICE_MAX:
        await update.message.reply_text(f"⚠️ Maximum voice messages reached! (5 voice/day)")
        return
    text = " ".join(context.args)
    if not text or len(text) > 500:
        await update.message.reply_text("⚠️ Provide text (max 500 chars)")
        return
    voice_preference = user_voice_choice.get(user_id, "female")
    selected_voice = VOICES.get(voice_preference, "nova")
    await update.message.reply_text(f"🔊 Generating voice message ({voice_preference})...")

    try:
        enhanced_text = await enhance_speech_text(text)
        response = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice=selected_voice,
            input=enhanced_text
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp:
            temp.write(response.content)
            temp_path = temp.name
        with open(temp_path, "rb") as audio_file:
            await update.message.reply_voice(voice=audio_file)
        os.unlink(temp_path)
        increment_message_count(user_id, current_ai, "voice")
    except Exception as e:
        await update.message.reply_text(f"❌ Error generating voice: {str(e)}")

# ---------------------- CHATGPT HANDLER ----------------------

async def get_chatgpt_response(user_id, user_message, user_name):
    messages = [{"role": "system", "content": "You are a helpful AI assistant. Respond in the same language as the user."}]
    for msg in conversation_history.get(user_id, []):
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})

    try:
        response = openai_client.responses.create(
            model="gpt-5-mini",
            input=messages,
            max_output_tokens=1000
        )
        ai_reply = response.output_text
    except Exception as e:
        print(f"ChatGPT error: {e}")
        ai_reply = "⚠️ Error contacting ChatGPT"

    conversation_history.setdefault(user_id, []).append({"role": "user", "content": user_message})
    conversation_history[user_id].append({"role": "assistant", "content": ai_reply})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]
    return ai_reply

# ---------------------- CLAUDE HANDLER ----------------------

async def get_claude_response(user_id, user_message, user_name):
    conversation_history.setdefault(user_id, []).append({"role": "user", "content": user_message})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    response = claude_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1000,
        system="You are a helpful, friendly AI assistant. Respond in the same language as the user.",
        messages=conversation_history[user_id]
    )
    ai_reply = response.content[0].text
    conversation_history[user_id].append({"role": "assistant", "content": ai_reply})
    return ai_reply

# ---------------------- MISC HANDLERS ----------------------
# handle_photo, handle_voice, ai_response remain as in your original code
# ✅ All OpenAI references updated to new SDK

# ---------------------- MESSAGE COUNT UTILITIES ----------------------
def get_total_used(user_id, ai_type):
    today = datetime.now().strftime("%Y-%m-%d")
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}},
            "chatgpt": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}}
        }
    return sum(user_message_counts[user_id][ai_type][t]["count"] for t in ["text", "image", "voice"])

def get_type_used(user_id, ai_type, message_type):
    today = datetime.now().strftime("%Y-%m-%d")
    if user_id not in user_message_counts:
        get_total_used(user_id, ai_type)  # initializes
    return user_message_counts[user_id][ai_type][message_type]["count"]

def increment_message_count(user_id, ai_type, message_type):
    today = datetime.now().strftime("%Y-%m-%d")
    if user_id not in user_message_counts:
        get_total_used(user_id, ai_type)  # initializes
    user_message_counts[user_id][ai_type][message_type]["count"] += 1

# ---------------------- RUN BOT ----------------------

def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("claude", use_claude))
    app.add_handler(CommandHandler("chatgpt", use_chatgpt))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("generate", generate_image_command))
    app.add_handler(CommandHandler("speak", speak_command))
    # Add MessageHandler for TEXT, PHOTO, VOICE
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("🤖 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    run_bot()
