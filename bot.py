import re
import os
import certifi
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from pymongo import MongoClient

# 🔐 ENV
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

print("Bot starting...")
print("Token loaded:", BOT_TOKEN is not None)

# 🧠 Mongo
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["metro"]
collection = db["users"]

users = {}

# ⏰ Normalize time
def normalize_time(time_str):
    time_str = time_str.lower().replace(" ", "")
    match = re.match(r"(\d{1,2})(:(\d{1,2}))?(am|pm)", time_str)

    if not match:
        return time_str

    hour = int(match.group(1))
    minute = int(match.group(3)) if match.group(3) else 0
    period = match.group(4).upper()

    return f"{hour:02d}:{minute:02d} {period}"

# 🚀 START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    users[user_id] = {"referral_by": None}

    keyboard = [["Skip"]]

    await update.message.reply_text(
        f"Welcome 🚇\n\nYour referral code: {user_id}\n\nEnter referral code or skip:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# 🧩 HANDLER
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    text = update.message.text.strip().lower()

    if user_id not in users:
        await update.message.reply_text("Type /start to begin")
        return

    # Referral
    if "referral_done" not in users[user_id]:
        users[user_id]["referral_done"] = True

        if text != "skip":
            try:
                ref_id = int(text)
                users[user_id]["referral_by"] = ref_id

                collection.update_one(
                    {"user_id": ref_id},
                    {"$inc": {"referral_count": 1}},
                    upsert=True
                )
            except:
                pass

        await update.message.reply_text("Enter your source metro station:")
        return

    # Source
    if "source" not in users[user_id]:
        users[user_id]["source"] = text.lower()
        await update.message.reply_text("Enter your destination station:")
        return

    # Destination
    elif "destination" not in users[user_id]:
        users[user_id]["destination"] = text.lower()
        await update.message.reply_text("Enter your travel time (e.g. 9am):")
        return

    # Time
    elif "time" not in users[user_id]:
        normalized = normalize_time(text)
        users[user_id]["time"] = normalized

        keyboard = [["Yes", "No"]]

        await update.message.reply_text(
            f"Time set as {normalized}\nDo you travel daily?",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return

    # Final step
    elif "recurring" not in users[user_id]:
        users[user_id]["recurring"] = text
        users[user_id]["user_id"] = user_id

        await update.message.reply_text(
            "Processing...",
            reply_markup=ReplyKeyboardRemove()
        )

        print("Saving user:", users[user_id])

        # Save
        try:
            collection.delete_many({"user_id": user_id})
            collection.insert_one(users[user_id])
        except Exception as e:
            print("Mongo Save Error:", e)

        await update.message.reply_text("✅ Registered successfully!")

        # Match
        try:
            matches = list(collection.find({
                "source": users[user_id]["source"],
                "destination": users[user_id]["destination"]
            }))
        except Exception as e:
            print("Mongo Error:", e)
            matches = []

        valid_matches = [m for m in matches if m["user_id"] != user_id]
        count = len(valid_matches)

        print("Matches found:", count)

        if count > 0:
            await update.message.reply_text(f"🎉 Found {count} people travelling with you!")
        else:
            await update.message.reply_text("No match found yet. We’ll notify you.")

        # FINAL SAFETY RESPONSE
        await update.message.reply_text("✅ Done. You are registered.")

# 🚀 RUN
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --- DUMMY WEB SERVER FOR RENDER ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()
# -----------------------------------

print("🚀 Bot running...")
app.run_polling()
