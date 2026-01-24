import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from openai import OpenAI
import base64
from io import BytesIO

# Get from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize AI clients
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# User preferences: which AI they're using
user_ai_choice = {}  # {user_id: "claude" or "chatgpt"}

# Conversation history for each user
conversation_history = {}

# Daily message limits
from datetime import datetime, timedelta

# Track message counts: {user_id: {"claude": {...}, "chatgpt": {...}}}
user_message_counts = {}

# Daily limits per AI
DAILY_LIMIT_TOTAL = 50         # Total messages of any type
DAILY_LIMIT_IMAGES_MAX = 5     # Maximum images allowed
DAILY_LIMIT_VOICE_MAX = 5      # Maximum voice messages allowed

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    user_id = update.message.from_user.id
    user_ai_choice[user_id] = "claude"  # Default to Claude
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
    """Switch to Claude"""
    user_id = update.message.from_user.id
    user_ai_choice[user_id] = "claude"
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Switched to Claude AI 🔵\nConversation cleared. Send me a message!")

async def use_chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to ChatGPT"""
    user_id = update.message.from_user.id
    user_ai_choice[user_id] = "chatgpt"
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Switched to ChatGPT 🟢\nConversation cleared. Send me a message!")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current AI and remaining messages"""
    user_id = update.message.from_user.id
    current_ai = user_ai_choice.get(user_id, "claude")
    
    # Get counts
    total_used = get_total_used(user_id, current_ai)
    images_used = get_type_used(user_id, current_ai, "image")
    voice_used = get_type_used(user_id, current_ai, "voice")
    
    total_remaining = DAILY_LIMIT_TOTAL - total_used
    images_remaining = DAILY_LIMIT_IMAGES_MAX - images_used
    voice_remaining = DAILY_LIMIT_VOICE_MAX - voice_used
    
    if current_ai == "claude":
        status_msg = f"📊 Currently using: Claude AI 🔵\n\n"
    else:
        status_msg = f"📊 Currently using: ChatGPT 🟢\n\n"
    
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
    """Clear conversation history"""
    user_id = update.message.from_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Conversation cleared!")

async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate image with DALL-E"""
    user_id = update.message.from_user.id
    current_ai = user_ai_choice.get(user_id, "claude")
    
    # Check total limit
    total_used = get_total_used(user_id, current_ai)
    if total_used >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text(f"⚠️ Daily limit reached for {current_ai.upper()}! (50 messages/day)\n\n💡 Try /{'chatgpt' if current_ai == 'claude' else 'claude'} for separate quota!")
        return
    
    # Check image-specific limit
    images_used = get_type_used(user_id, current_ai, "image")
    if images_used >= DAILY_LIMIT_IMAGES_MAX:
        await update.message.reply_text(f"⚠️ Maximum images reached for {current_ai.upper()}! (5 images/day)\n\nYou can still send {DAILY_LIMIT_TOTAL - total_used} text messages today.")
        return
    
    # Get the prompt
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Usage: /generate [description]\n\nExample: /generate a cute cat wearing sunglasses")
        return
    
    await update.message.reply_text(f"🎨 Generating image: '{prompt}'\nThis may take 10-20 seconds...")
    
    try:
        # Generate image with DALL-E 3
        response = openai.Image.create(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        
        image_url = response.data[0].url
        
        # Increment both image count and total count
        increment_message_count(user_id, current_ai, "image")
        
        # Send the image
        await update.message.reply_photo(
            photo=image_url,
            caption=f"🎨 Generated: {prompt}"
        )
        
        # Show remaining
        total_after = DAILY_LIMIT_TOTAL - get_total_used(user_id, current_ai)
        images_after = DAILY_LIMIT_IMAGES_MAX - get_type_used(user_id, current_ai, "image")
        await update.message.reply_text(f"✅ Remaining: {total_after} total messages, {images_after} more images allowed")
            
    except Exception as e:
        print(f"Image generation error: {e}")
        await update.message.reply_text(f"❌ Failed to generate image. Error: {str(e)}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help message"""
    help_text = """
🤖 Dual AI Assistant - Help

**Available AIs:**
🔵 Claude - Better for essays, writing, nuanced responses
🟢 ChatGPT - Better for casual chat, real-time facts

**Commands:**
/claude - Switch to Claude AI
/chatgpt - Switch to ChatGPT
/status - Check current AI & remaining messages
/generate [text] - Create an image
/clear - Clear conversation history
/start - Restart
/help - Show this message

**Features:**
💬 Send text messages for AI chat
🖼️ Send photos for AI to analyze
🎤 Send voice messages for transcription + response
🎨 Use /generate to create images

Both AIs remember your conversation!
Switch anytime to compare responses.
    """
    await update.message.reply_text(help_text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages - AI analyzes the image"""
    user_id = update.message.from_user.id
    
    # Initialize if new user
    if user_id not in user_ai_choice:
        user_ai_choice[user_id] = "claude"
    
    current_ai = user_ai_choice[user_id]
    
    # Check total limit
    total_used = get_total_used(user_id, current_ai)
    if total_used >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text(f"⚠️ Daily limit reached for {current_ai.upper()}! (50 messages/day)\n\n💡 Try /{'chatgpt' if current_ai == 'claude' else 'claude'} for separate quota!")
        return
    
    # Check image-specific limit
    images_used = get_type_used(user_id, current_ai, "image")
    if images_used >= DAILY_LIMIT_IMAGES_MAX:
        await update.message.reply_text(f"⚠️ Maximum images reached for {current_ai.upper()}! (5 images/day)\n\nYou can still send {DAILY_LIMIT_TOTAL - total_used} text messages today.")
        return
    
    await update.message.chat.send_action("typing")
    
    try:
        # Get the largest photo
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        
        # Download photo as bytes
        photo_bytes = await photo_file.download_as_bytearray()
        photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')
        
        # Get caption if provided
        caption = update.message.caption or "What's in this image?"
        
        # Analyze with current AI
        if current_ai == "claude":
            response_text = await analyze_image_claude(photo_base64, caption)
        else:
            response_text = await analyze_image_chatgpt(photo_base64, caption)
        
        increment_message_count(user_id, current_ai, "image")
        
        await update.message.reply_text(f"🖼️ Image Analysis:\n\n{response_text}")
        
        # Show remaining
        total_after = DAILY_LIMIT_TOTAL - get_total_used(user_id, current_ai)
        images_after = DAILY_LIMIT_IMAGES_MAX - get_type_used(user_id, current_ai, "image")
        await update.message.reply_text(f"✅ Remaining: {total_after} total messages, {images_after} more images allowed")
            
    except Exception as e:
        print(f"Photo analysis error: {e}")
        await update.message.reply_text(f"❌ Error analyzing image: {str(e)}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages - transcribe and respond"""
    user_id = update.message.from_user.id
    
    # Initialize if new user
    if user_id not in user_ai_choice:
        user_ai_choice[user_id] = "claude"
    
    current_ai = user_ai_choice[user_id]
    
    # Check total limit
    total_used = get_total_used(user_id, current_ai)
    if total_used >= DAILY_LIMIT_TOTAL:
        await update.message.reply_text(f"⚠️ Daily limit reached for {current_ai.upper()}! (50 messages/day)\n\n💡 Try /{'chatgpt' if current_ai == 'claude' else 'claude'} for separate quota!")
        return
    
    # Check voice-specific limit
    voice_used = get_type_used(user_id, current_ai, "voice")
    if voice_used >= DAILY_LIMIT_VOICE_MAX:
        await update.message.reply_text(f"⚠️ Maximum voice messages reached for {current_ai.upper()}! (5 voice/day)\n\nYou can still send {DAILY_LIMIT_TOTAL - total_used} text messages today.")
        return
    
    await update.message.reply_text("🎤 Transcribing your voice message...")
    
    try:
        # Download voice file
        voice_file = await update.message.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
        
        # Transcribe with Whisper
        # Save temporarily to file (Whisper API needs file)
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
            temp_file.write(voice_bytes)
            temp_file_path = temp_file.name
        
        # Transcribe
        with open(temp_file_path, "rb") as audio_file:
            transcript = openai.Audio.transcribe("whisper-1", audio_file)
        
        transcribed_text = transcript.text
        
        # Clean up temp file
        os.unlink(temp_file_path)
        
        # Send transcription
        await update.message.reply_text(f"📝 Transcription:\n\"{transcribed_text}\"\n\n🤖 Generating response...")
        
        # Get AI response to the transcribed text
        if current_ai == "claude":
            ai_reply = await get_claude_response(user_id, transcribed_text, update.message.from_user.first_name)
        else:
            ai_reply = await get_chatgpt_response(user_id, transcribed_text, update.message.from_user.first_name)
        
        increment_message_count(user_id, current_ai, "voice")
        
        await update.message.reply_text(ai_reply)
        
        # Show remaining
        total_after = DAILY_LIMIT_TOTAL - get_total_used(user_id, current_ai)
        voice_after = DAILY_LIMIT_VOICE_MAX - get_type_used(user_id, current_ai, "voice")
        await update.message.reply_text(f"✅ Remaining: {total_after} total messages, {voice_after} more voice allowed")
            
    except Exception as e:
        print(f"Voice message error: {e}")
        await update.message.reply_text(f"❌ Error processing voice: {str(e)}")

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate AI response based on user's choice"""
    user_message = update.message.text
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    # Initialize if new user
    if user_id not in user_ai_choice:
        user_ai_choice[user_id] = "claude"
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    
    current_ai = user_ai_choice[user_id]
    
    # Check total limit
    total_used = get_total_used(user_id, current_ai)
    if total_used >= DAILY_LIMIT_TOTAL:
        limit_msg = f"⚠️ Daily limit reached for {current_ai.upper()}! (50 messages/day)\n\n"
        
        # Check if other AI has messages left
        other_ai = "chatgpt" if current_ai == "claude" else "claude"
        other_total = get_total_used(user_id, other_ai)
        
        if other_total < DAILY_LIMIT_TOTAL:
            limit_msg += f"💡 Try switching to {other_ai.upper()}! You have {DAILY_LIMIT_TOTAL - other_total} messages left.\n"
            limit_msg += f"Use /{other_ai} to switch."
        else:
            limit_msg += f"Both AIs have reached daily limits.\n"
            limit_msg += f"Limits reset at midnight UTC. Come back tomorrow! 😊"
        
        await update.message.reply_text(limit_msg)
        return
    
    # Show typing indicator
    await update.message.chat.send_action("typing")
    
    try:
        if current_ai == "claude":
            # Use Claude
            ai_reply = await get_claude_response(user_id, user_message, user_name)
        else:
            # Use ChatGPT
            ai_reply = await get_chatgpt_response(user_id, user_message, user_name)
        
        # Increment text message count
        increment_message_count(user_id, current_ai, "text")
        
        # Log interaction
        print(f"[{current_ai.upper()}] User {user_name}: {user_message}")
        print(f"[{current_ai.upper()}] Reply: {ai_reply}\n")
        
        # Add remaining messages info if low
        total_after = DAILY_LIMIT_TOTAL - get_total_used(user_id, current_ai)
        if total_after <= 5:
            ai_reply += f"\n\n⚠️ You have {total_after} messages left today for {current_ai.upper()}."
        
        # Send response
        await update.message.reply_text(ai_reply)
        
    except Exception as e:
        print(f"Error with {current_ai}: {e}")
        error_msg = f"⚠️ Error with {current_ai.upper()}. Please try again or switch AI with /claude or /chatgpt"
        await update.message.reply_text(error_msg)

async def analyze_image_claude(image_base64, prompt):
    """Analyze image with Claude"""
    response = claude_client.messages.create(
        model="claude-sonnet-4-5-20250929",
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
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ],
            }
        ],
    )
    return response.content[0].text

async def analyze_image_chatgpt(image_base64, prompt):
    """Analyze image with ChatGPT Vision"""
    response = openai.ChatCompletion.create(
        model="gpt-4o",  # Vision model
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ],
            }
        ],
        max_tokens=1000,
    )
    return response.choices[0].message.content

async def get_claude_response(user_id, user_message, user_name):
    """Get response from Claude"""
    # Add to history
    conversation_history[user_id].append({
        "role": "user",
        "content": user_message
    })
    
    # Keep last 20 messages
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]
    
    # Call Claude API
    response = claude_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1000,
        system="You are a helpful, friendly AI assistant. Provide thoughtful, accurate responses. Always respond in the same language as the user's message.",
        messages=conversation_history[user_id]
    )
    
    ai_reply = response.content[0].text
    
    # Add to history
    conversation_history[user_id].append({
        "role": "assistant",
        "content": ai_reply
    })
    
    return ai_reply

async def get_chatgpt_response(user_id, user_message, user_name):
    """Get response from ChatGPT"""
    # Build message history for ChatGPT format
    messages = [
        {
            "role": "system",
            "content": "You are a helpful AI assistant. Provide accurate, friendly responses. Always respond in the same language as the user's message."
        }
    ]
    
    # Add conversation history
    for msg in conversation_history[user_id]:
        messages.append(msg)
    
    # Add current message
    messages.append({
        "role": "user",
        "content": user_message
    })
    
    # Call ChatGPT API
    response = openai.ChatCompletion.create(
        model="gpt-5-mini",
        messages=messages,
        max_tokens=1000,
        temperature=0.7
    )
    
    ai_reply = response.choices[0].message.content
    
    # Update history
    conversation_history[user_id].append({
        "role": "user",
        "content": user_message
    })
    conversation_history[user_id].append({
        "role": "assistant",
        "content": ai_reply
    })
    
    # Keep last 20 messages
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]
    
    return ai_reply

def get_total_used(user_id, ai_type):
    """Get total messages used (all types combined)"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Initialize if needed
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {
                "text": {"count": 0, "date": today},
                "image": {"count": 0, "date": today},
                "voice": {"count": 0, "date": today}
            },
            "chatgpt": {
                "text": {"count": 0, "date": today},
                "image": {"count": 0, "date": today},
                "voice": {"count": 0, "date": today}
            }
        }
    
    # Initialize AI if missing
    if ai_type not in user_message_counts[user_id]:
        user_message_counts[user_id][ai_type] = {
            "text": {"count": 0, "date": today},
            "image": {"count": 0, "date": today},
            "voice": {"count": 0, "date": today}
        }
    
    # Reset counts if new day
    for msg_type in ["text", "image", "voice"]:
        if msg_type not in user_message_counts[user_id][ai_type]:
            user_message_counts[user_id][ai_type][msg_type] = {"count": 0, "date": today}
        if user_message_counts[user_id][ai_type][msg_type]["date"] != today:
            user_message_counts[user_id][ai_type][msg_type] = {"count": 0, "date": today}
    
    # Sum all message types
    total = (user_message_counts[user_id][ai_type]["text"]["count"] +
             user_message_counts[user_id][ai_type]["image"]["count"] +
             user_message_counts[user_id][ai_type]["voice"]["count"])
    
    return total

def get_type_used(user_id, ai_type, message_type):
    """Get count for specific message type"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Initialize if needed
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {
                "text": {"count": 0, "date": today},
                "image": {"count": 0, "date": today},
                "voice": {"count": 0, "date": today}
            },
            "chatgpt": {
                "text": {"count": 0, "date": today},
                "image": {"count": 0, "date": today},
                "voice": {"count": 0, "date": today}
            }
        }
    
    # Initialize AI if missing
    if ai_type not in user_message_counts[user_id]:
        user_message_counts[user_id][ai_type] = {
            "text": {"count": 0, "date": today},
            "image": {"count": 0, "date": today},
            "voice": {"count": 0, "date": today}
        }
    
    # Initialize message type if missing
    if message_type not in user_message_counts[user_id][ai_type]:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    
    # Reset if new day
    if user_message_counts[user_id][ai_type][message_type]["date"] != today:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    
    return user_message_counts[user_id][ai_type][message_type]["count"]

def increment_message_count(user_id, ai_type, message_type):
    """Increment message count for user"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Initialize if needed
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {
                "text": {"count": 0, "date": today},
                "image": {"count": 0, "date": today},
                "voice": {"count": 0, "date": today}
            },
            "chatgpt": {
                "text": {"count": 0, "date": today},
                "image": {"count": 0, "date": today},
                "voice": {"count": 0, "date": today}
            }
        }
    
    # Initialize AI if missing
    if ai_type not in user_message_counts[user_id]:
        user_message_counts[user_id][ai_type] = {
            "text": {"count": 0, "date": today},
            "image": {"count": 0, "date": today},
            "voice": {"count": 0, "date": today}
        }
    
    # Initialize message type if missing
    if message_type not in user_message_counts[user_id][ai_type]:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    
    # Reset if new day
    if user_message_counts[user_id][ai_type][message_type]["date"] != today:
        user_message_counts[user_id][ai_type][message_type] = {"count": 0, "date": today}
    
    # Increment
    user_message_counts[user_id][ai_type][message_type]["count"] += 1

def main():
    """Start the bot"""
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("claude", use_claude))
    app.add_handler(CommandHandler("chatgpt", use_chatgpt))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("generate", generate_image_command))
    app.add_handler(CommandHandler("help", help_command))
    
    # Media handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    # Text handler (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))
    
    print("🤖 Dual AI Bot is running (Claude + ChatGPT + Vision + Voice + Image Gen)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

from aiohttp import web

async def handle(request):
    return web.Response(text="Bot is running")

async def start_webserver():
    app = web.Application()
    app.add_routes([web.get("/", handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8000)))
    await site.start()

# Add this inside main() before app.run_polling()
import asyncio
asyncio.get_event_loop().create_task(start_webserver())
