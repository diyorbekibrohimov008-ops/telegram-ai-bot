import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from openai import OpenAI
import base64
from datetime import datetime
from threading import Thread
from flask import Flask

# Flask app for Render web service (keeps port open)
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "🤖 Telegram Bot is Running!", 200

@flask_app.route('/health')
def health():
    return "OK", 200

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

# Daily limits
DAILY_LIMIT_TOTAL = 50
DAILY_LIMIT_IMAGES_MAX = 5
DAILY_LIMIT_VOICE_MAX = 5

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    user_id = update.message.from_user.id
    user_ai_choice[user_id] = "claude"
    conversation_history[user_id] = []
    
    welcome_msg = """
🤖 Welcome! I'm a Dual AI Assistant with superpowers!

🎨 **Choose your AI:**
/claude - Use Claude AI (default) 🔵
/chatgpt - Use ChatGPT 🟢

🌟 **Features:**
💬 Smart conversations
🖼️ Image analysis - Send me photos!
🎤 Voice messages - I'll transcribe & respond
🎨 Image generation - Ask me to create images
💻 Code writing & debugging

**Other commands:**
/status - Check AI & remaining messages
/generate [description] - Create an image
/clear - Clear conversation history
/help - Show help

Current AI: Claude 🔵

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

async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_ai = user_ai_choice.get(user_id, "claude")
    
    total_used = get_total_used(user_id, current_ai)
    if total_used >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text(f"⚠️ Daily limit reached for {current_ai.upper()}! (50 messages/day)")
        return
    
    images_used = get_type_used(user_id, current_ai, "image")
    if images_used >= DAILY_LIMIT_IMAGES_MAX:
        await update.message.reply_text(f"⚠️ Maximum images reached! (5 images/day)\n\nYou can still send {DAILY_LIMIT_TOTAL - total_used} text messages.")
        return
    
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Usage: /generate [description]\n\nExample: /generate a cute cat wearing sunglasses")
        return
    
    await update.message.reply_text(f"🎨 Generating: '{prompt}'\nPlease wait 10-20 seconds...")
    
    try:
        # Updated for openai 1.x
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        
        image_url = response.data[0].url
        
        increment_message_count(user_id, current_ai, "image")
        await update.message.reply_photo(photo=image_url, caption=f"🎨 {prompt}")
        
        total_after = DAILY_LIMIT_TOTAL - get_total_used(user_id, current_ai)
        images_after = DAILY_LIMIT_IMAGES_MAX - get_type_used(user_id, current_ai, "image")
        await update.message.reply_text(f"✅ Remaining: {total_after} total, {images_after} images")
    except Exception as e:
        print(f"Image generation error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 Dual AI Assistant - Help

**Commands:**
/claude - Switch to Claude AI
/chatgpt - Switch to ChatGPT
/status - Check usage & limits
/generate [text] - Create an image
/clear - Clear conversation
/help - Show this message

**Features:**
💬 Text chat, 🖼️ Image analysis, 🎤 Voice transcription, 🎨 Image generation

**Limits:** 50 total messages/day per AI (max 5 images, 5 voice)
    """
    await update.message.reply_text(help_text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_ai = user_ai_choice.get(user_id, "claude")
    
    if get_total_used(user_id, current_ai) >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text("⚠️ Daily limit reached!")
        return
    
    if get_type_used(user_id, current_ai, "image") >= DAILY_LIMIT_IMAGES_MAX:
        await update.message.reply_text("⚠️ Maximum images reached! (5/day)")
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
            # Updated for openai 1.x with vision
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": caption},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{photo_base64}"
                            }
                        }
                    ]
                }],
                max_tokens=1000
            )
            result = response.choices[0].message.content
        
        increment_message_count(user_id, current_ai, "image")
        await update.message.reply_text(f"🖼️ Image Analysis:\n\n{result}")
        
        total_after = DAILY_LIMIT_TOTAL - get_total_used(user_id, current_ai)
        images_after = DAILY_LIMIT_IMAGES_MAX - get_type_used(user_id, current_ai, "image")
        await update.message.reply_text(f"✅ Remaining: {total_after} total, {images_after} images")
    except Exception as e:
        print(f"Photo error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_ai = user_ai_choice.get(user_id, "claude")
    
    if get_total_used(user_id, current_ai) >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text("⚠️ Daily limit reached!")
        return
    
    if get_type_used(user_id, current_ai, "voice") >= DAILY_LIMIT_VOICE_MAX:
        await update.message.reply_text("⚠️ Maximum voice messages reached! (5/day)")
        return
    
    await update.message.reply_text("🎤 Transcribing...")
    
    try:
        voice_file = await update.message.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
        
        # Save to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp:
            temp.write(voice_bytes)
            temp_path = temp.name
        
        # Updated for openai 1.x
        with open(temp_path, "rb") as audio:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio
            )
        
        os.unlink(temp_path)
        text = transcript.text
        
        await update.message.reply_text(f"📝 Transcription:\n\"{text}\"\n\n🤖 Responding...")
        
        if current_ai == "claude":
            ai_reply = await get_claude_response(user_id, text, update.message.from_user.first_name)
        else:
            ai_reply = await get_chatgpt_response(user_id, text, update.message.from_user.first_name)
        
        increment_message_count(user_id, current_ai, "voice")
        await update.message.reply_text(ai_reply)
        
        total_after = DAILY_LIMIT_TOTAL - get_total_used(user_id, current_ai)
        voice_after = DAILY_LIMIT_VOICE_MAX - get_type_used(user_id, current_ai, "voice")
        await update.message.reply_text(f"✅ Remaining: {total_after} total, {voice_after} voice")
    except Exception as e:
        print(f"Voice error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    if user_id not in user_ai_choice:
        user_ai_choice[user_id] = "claude"
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    
    current_ai = user_ai_choice[user_id]
    
    if get_total_used(user_id, current_ai) >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text(f"⚠️ Daily limit reached! (50/day)\n\nTry /{'chatgpt' if current_ai == 'claude' else 'claude'} for separate quota!")
        return
    
    await update.message.chat.send_action("typing")
    
    try:
        if current_ai == "claude":
            ai_reply = await get_claude_response(user_id, user_message, user_name)
        else:
            ai_reply = await get_chatgpt_response(user_id, user_message, user_name)
        
        increment_message_count(user_id, current_ai, "text")
        
        total_after = DAILY_LIMIT_TOTAL - get_total_used(user_id, current_ai)
        if total_after <= 5:
            ai_reply += f"\n\n⚠️ {total_after} messages left today"
        
        await update.message.reply_text(ai_reply)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def get_claude_response(user_id, user_message, user_name):
    conversation_history[user_id].append({"role": "user", "content": user_message})
    
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

async def get_chatgpt_response(user_id, user_message, user_name):
    messages = [{"role": "system", "content": "You are a helpful AI assistant. Respond in the same language as the user."}]
    
    for msg in conversation_history[user_id]:
        messages.append(msg)
    
    messages.append({"role": "user", "content": user_message})
    
    # Fixed for openai==0.28.0
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # Changed from gpt-5-mini (doesn't exist in 0.28.0)
        messages=messages,
        max_tokens=1000,
        temperature=0.7
    )
    
    ai_reply = response.choices[0].message.content
    
    conversation_history[user_id].append({"role": "user", "content": user_message})
    conversation_history[user_id].append({"role": "assistant", "content": ai_reply})
    
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]
    
    return ai_reply

def get_total_used(user_id, ai_type):
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}},
            "chatgpt": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}}
        }
    
    if ai_type not in user_message_counts[user_id]:
        user_message_counts[user_id][ai_type] = {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}}
    
    for msg_type in ["text", "image", "voice"]:
        if msg_type not in user_message_counts[user_id][ai_type]:
            user_message_counts[user_id][ai_type][msg_type] = {"count": 0, "date": today}
        if user_message_counts[user_id][ai_type][msg_type]["date"] != today:
            user_message_counts[user_id][ai_type][msg_type] = {"count": 0, "date": today}
    
    return sum(user_message_counts[user_id][ai_type][t]["count"] for t in ["text", "image", "voice"])

def get_type_used(user_id, ai_type, message_type):
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}},
            "chatgpt": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}}
        }
    
    if ai_type not in user_message_counts[user_id]:
        user_message_counts[user_id][ai_type] = {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}}
    
    if message_type not in user_message_counts[user_id][ai_type]:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    
    if user_message_counts[user_id][ai_type][message_type]["date"] != today:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    
    return user_message_counts[user_id][ai_type][message_type]["count"]

def increment_message_count(user_id, ai_type, message_type):
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}},
            "chatgpt": {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}}
        }
    
    if ai_type not in user_message_counts[user_id]:
        user_message_counts[user_id][ai_type] = {"text": {"count": 0, "date": today}, "image": {"count": 0, "date": today}, "voice": {"count": 0, "date": today}}
    
    if message_type not in user_message_counts[user_id][ai_type]:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    
    if user_message_counts[user_id][ai_type][message_type]["date"] != today:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    
    user_message_counts[user_id][ai_type][message_type]["count"] += 1

def run_bot():
    """Run telegram bot"""
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("claude", use_claude))
    app.add_handler(CommandHandler("chatgpt", use_chatgpt))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("generate", generate_image_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))
    
    print("🤖 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Start Flask in background thread
    port = int(os.environ.get('PORT', 10000))
    flask_thread = Thread(target=lambda: flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()
    
    print(f"🌐 Flask running on port {port}")
    
    # Run telegram bot in main thread
    run_bot()
