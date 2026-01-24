import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

# Get from environment variables (NOT hardcoded)
BOT_TOKEN = os.getenv("BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Initialize Claude client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Customize your AI's personality and behavior
YOUR_NAME = "Diyorbek"  # Change this to your actual name

SYSTEM_PROMPT = f"""You are {YOUR_NAME}'s personal assistant, responding to messages on their behalf. 
Keep responses brief, natural, and conversational. Always respond in the same language as the incoming message.
Be helpful, polite, and firm. You're helping {YOUR_NAME} by managing their messages."""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "👋 Hello! I'm an AI-powered auto-reply bot. Send me any message and I'll respond intelligently in your language!"
    )

async def ai_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate AI response to messages"""
    user_message = update.message.text
    sender_name = update.message.from_user.first_name
    
    # Show typing indicator
    await update.message.chat.send_action("typing")
    
    try:
        # Generate AI response using Claude
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"{sender_name} sent you this message: {user_message}\n\nRespond naturally as {YOUR_NAME}."
                }
            ]
        )
        
        # Extract the response text
        ai_response = message.content[0].text
        
        # Log the interaction (optional)
        print(f"From {sender_name}: {user_message}")
        print(f"AI Reply: {ai_response}\n")
        
        # Send the AI-generated response
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error. Please try again later."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
🤖 AI Auto-Reply Bot

I automatically respond to your messages using AI.

Commands:
/start - Start the bot
/help - Show this help message

Just send me any message in any language and I'll respond intelligently!
    """
    await update.message.reply_text(help_text)

def main():
    """Start the bot"""
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_auto_reply))
    
    # Start the bot
    print("🤖 AI Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()