import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
import openai

# Get from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize AI clients
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai.api_key = OPENAI_API_KEY

# User preferences: which AI they're using
user_ai_choice = {}  # {user_id: "claude" or "chatgpt"}

# Conversation history for each user
conversation_history = {}

# Daily message limits
from datetime import datetime, timedelta

# Track message counts: {user_id: {"claude": {"count": 0, "date": "2025-01-24"}, "chatgpt": {...}}}
user_message_counts = {}

# Daily limits per AI
DAILY_LIMIT_CLAUDE = 50
DAILY_LIMIT_CHATGPT = 50

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    user_id = update.message.from_user.id
    user_ai_choice[user_id] = "claude"  # Default to Claude
    conversation_history[user_id] = []
    
    welcome_msg = """
🤖 Welcome! I'm a Dual AI Assistant.

Choose your AI:
/claude - Use Claude AI (default) 🔵
/chatgpt - Use ChatGPT 🟢

Other commands:
/status - Check which AI you're using
/clear - Clear conversation history
/help - Show help

Current AI: Claude 🔵

Just send any message and I'll respond!
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
    
    # Get remaining messages
    claude_remaining = get_remaining_messages(user_id, "claude")
    chatgpt_remaining = get_remaining_messages(user_id, "chatgpt")
    
    if current_ai == "claude":
        status_msg = f"📊 Currently using: Claude AI 🔵\n\n"
    else:
        status_msg = f"📊 Currently using: ChatGPT 🟢\n\n"
    
    status_msg += f"Daily Messages Remaining:\n"
    status_msg += f"🔵 Claude: {claude_remaining}/{DAILY_LIMIT_CLAUDE}\n"
    status_msg += f"🟢 ChatGPT: {chatgpt_remaining}/{DAILY_LIMIT_CHATGPT}\n\n"
    status_msg += f"Limits reset at midnight UTC."
    
    await update.message.reply_text(status_msg)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear conversation history"""
    user_id = update.message.from_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Conversation cleared!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help message"""
    help_text = """
🤖 Dual AI Assistant - Help

Available AIs:
🔵 Claude - Better for essays, writing, nuanced responses
🟢 ChatGPT - Better for casual chat, real-time facts

Commands:
/claude - Switch to Claude AI
/chatgpt - Switch to ChatGPT
/status - Check current AI
/clear - Clear conversation history
/start - Restart
/help - Show this message

Both AIs remember your conversation!
Switch anytime to compare responses.
    """
    await update.message.reply_text(help_text)

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
    
    # Check daily limit
    remaining = get_remaining_messages(user_id, current_ai)
    if remaining <= 0:
        limit_msg = f"⚠️ Daily limit reached for {current_ai.upper()}!\n\n"
        limit_msg += f"You've used all {DAILY_LIMIT_CLAUDE if current_ai == 'claude' else DAILY_LIMIT_CHATGPT} messages today.\n\n"
        
        # Check if other AI has messages left
        other_ai = "chatgpt" if current_ai == "claude" else "claude"
        other_remaining = get_remaining_messages(user_id, other_ai)
        
        if other_remaining > 0:
            limit_msg += f"💡 Try switching to {other_ai.upper()}! You have {other_remaining} messages left.\n"
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
        
        # Increment message count
        increment_message_count(user_id, current_ai)
        
        # Log interaction
        print(f"[{current_ai.upper()}] User {user_name}: {user_message}")
        print(f"[{current_ai.upper()}] Reply: {ai_reply}\n")
        
        # Add remaining messages info if low
        remaining_after = get_remaining_messages(user_id, current_ai)
        if remaining_after <= 5:
            ai_reply += f"\n\n⚠️ You have {remaining_after} messages left today for {current_ai.upper()}."
        
        # Send response
        await update.message.reply_text(ai_reply)
        
    except Exception as e:
        print(f"Error with {current_ai}: {e}")
        error_msg = f"⚠️ Error with {current_ai.upper()}. Please try again or switch AI with /claude or /chatgpt"
        await update.message.reply_text(error_msg)

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
        model="claude-sonnet-4-20250514",
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
        model="gpt-3.5-turbo",  # Cheaper option, or use "gpt-4o" for better quality
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

def get_remaining_messages(user_id, ai_type):
    """Get remaining messages for user for specific AI"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Initialize if needed
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {"count": 0, "date": today},
            "chatgpt": {"count": 0, "date": today}
        }
    
    # Reset if it's a new day
    if user_message_counts[user_id][ai_type]["date"] != today:
        user_message_counts[user_id][ai_type] = {"count": 0, "date": today}
    
    # Calculate remaining
    limit = DAILY_LIMIT_CLAUDE if ai_type == "claude" else DAILY_LIMIT_CHATGPT
    used = user_message_counts[user_id][ai_type]["count"]
    
    return limit - used

def increment_message_count(user_id, ai_type):
    """Increment message count for user"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Initialize if needed
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            "claude": {"count": 0, "date": today},
            "chatgpt": {"count": 0, "date": today}
        }
    
    # Reset if it's a new day
    if user_message_counts[user_id][ai_type]["date"] != today:
        user_message_counts[user_id][ai_type] = {"count": 0, "date": today}
    
    # Increment
    user_message_counts[user_id][ai_type]["count"] += 1

def main():
    """Start the bot"""
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("claude", use_claude))
    app.add_handler(CommandHandler("chatgpt", use_chatgpt))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))
    
    print("🤖 Dual AI Bot is running (Claude + ChatGPT)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
