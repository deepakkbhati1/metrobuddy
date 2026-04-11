import re
import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from pymongo import MongoClient

# 🔐 ENV VARIABLES
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

print("Bot starting...")
print("Token loaded:", BOT_TOKEN is not None)

# 🧠 MongoDB (Atlas)
client = MongoClient(MONGO_URI)
db = client["metro"]
collection = db["users"]

# Temporary memory
users = {}

# Group links (edit as needed)
group_links = {
    ("vaishali", "rajiv chowk", "morning"): "https://t.me/link1",
    ("sector 52", "noida city center", "morning"): "https://t.me/link2",
    ("rajiv chowk", "vaishali", "morning"): "https://t.me/link3",
}

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

# ⏰ Time bucket


def get_time_bucket(time_str):
    try:
        hour = int(time_str.split(":")[0])
    except:
        return "morning"

    if 6 <= hour < 12:
        return "morning"
    elif 12 <= hour < 18:
        return "afternoon"
    else:
        return "evening"

# 🔍 Related routes


def find_related_groups(source, destination, bucket):
    results = []

    for (src, dest, bkt), link in group_links.items():
        if bkt != bucket:
            continue

        if src == source and dest != destination:
            results.append(f"From {src} → {dest}\n{link}")
        elif dest == destination and src != source:
            results.append(f"From {src} → {dest}\n{link}")
        elif src == destination and dest == source:
            results.append(f"Reverse: {src} → {dest}\n{link}")

    return results[:3]

# 🚀 Start


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    users[user_id] = {"referral_by": None}

    keyboard = [["Skip"]]

    await update.message.reply_text(
        f"Welcome 🚇\n\nYour referral code: {user_id}\n\nEnter referral code or skip:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# 🧩 Handle messages


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    text = update.message.text.strip().lower()

    if user_id not in users:
        await update.message.reply_text("Type /start to begin")
        return

    # Referral step
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
        users[user_id]["source"] = text
        await update.message.reply_text("Enter your destination station:")

    # Destination
    elif "destination" not in users[user_id]:
        users[user_id]["destination"] = text
        await update.message.reply_text("Enter your travel time (e.g. 9am):")

    # Time
    elif "time" not in users[user_id]:
        normalized = normalize_time(text)
        users[user_id]["time"] = normalized

        keyboard = [["Yes", "No"]]

        await update.message.reply_text(
            f"Time set as {normalized}\nDo you travel daily?",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

    # Final step
    elif "recurring" not in users[user_id]:
        users[user_id]["recurring"] = text
        users[user_id]["user_id"] = user_id

        await update.message.reply_text(
            "Processing...",
            reply_markup=ReplyKeyboardRemove()
        )

        collection.delete_many({"user_id": user_id})
        collection.insert_one(users[user_id])

        await update.message.reply_text("✅ Registered successfully!")

        matches = list(collection.find({
            "source": users[user_id]["source"],
            "destination": users[user_id]["destination"]
        }))

        valid_matches = [m for m in matches if m["user_id"] != user_id]
        match_count = len(valid_matches)

        bucket = get_time_bucket(users[user_id]["time"])

        key = (
            users[user_id]["source"],
            users[user_id]["destination"],
            bucket
        )

        if match_count > 0:
            await update.message.reply_text(f"🎉 Found {match_count} people!")

            if key in group_links:
                await update.message.reply_text(
                    f"🚇 Join your travel group:\n{group_links[key]}"
                )
            else:
                await update.message.reply_text("Group coming soon.")
        else:
            await update.message.reply_text("No exact match found.")

            related = find_related_groups(
                users[user_id]["source"],
                users[user_id]["destination"],
                bucket
            )

            if related:
                msg = "👉 Similar routes:\n\n" + "\n\n".join(related)
                await update.message.reply_text(msg)
            else:
                await update.message.reply_text(
                    "We’ll notify you once more people join."
                )

        user_data = collection.find_one({"user_id": user_id})

        if user_data and user_data.get("referral_count", 0) >= 3:
            await update.message.reply_text("🏆 You are now a VIP user!")

# 🚀 App
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND, handle_message))

print("🚀 Bot running...")
app.run_polling()
