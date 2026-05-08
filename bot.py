import os
import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
from motor.motor_asyncio import AsyncIOMotorClient

# --- Configuration (Railway Variables ကနေ ဖတ်ပါမယ်) ---
API_ID = int(os.environ.get("API_ID", 12345)) # မင်းရဲ့ ID ထည့်ပါ
API_HASH = os.environ.get("API_HASH", "your_api_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
MONGO_URL = os.environ.get("MONGO_URL")
OWNER_ID = int(os.environ.get("OWNER_ID", 123456789))

# Bot Client ဆောက်ခြင်း
app = Client("shwe_mm_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Database ချိတ်ဆက်ခြင်း
if MONGO_URL:
    db_client = AsyncIOMotorClient(MONGO_URL)
    db = db_client["shwe_db"]
    replies = db["auto_replies"]
    users_db = db["users"]
else:
    print("❌ MONGO_URL is missing! Please add it in Railway Variables.")

# --- Database Indexing (မြန်အောင်လုပ်ခြင်း) ---
async def create_indexes():
    try:
        await replies.create_index("trigger")
        await users_db.create_index("user_id")
        print("✅ Database Connected & Indexes Verified.")
    except Exception as e:
        print(f"❌ Database Error: {e}")

# --- 1. Start Menu & User Tracking ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    # User ID မှတ်သားခြင်း
    await users_db.update_one(
        {"user_id": message.from_user.id},
        {"$set": {"username": message.from_user.username}},
        upsert=True
    )
    
    welcome_text = (
        f"ဟလို {message.from_user.mention} ✨\n\n"
        "ကျွန်တော်က Auto Reply နဲ့ Group Management Bot တစ်ခုဖြစ်ပါတယ်။\n"
        "အောက်က Button တွေကိုနှိပ်ပြီး လေ့လာနိုင်ပါတယ်ဗျာ။"
    )
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Channel 📢", url="https://t.me/myanmarbot_music"),
            InlineKeyboardButton("Developer 👨‍💻", url="http://t.me/HANTHAR999")
        ],
        [
            InlineKeyboardButton("Group 👥", url="https://t.me/myanmar_music_Bot2027"),
            InlineKeyboardButton("🌐 Update", url="https://t.me/myanmarbot_music/29")
        ],
        [
            InlineKeyboardButton("Add Me To Your Group ➕", url="https://t.me/catlover_2026bot?startgroup=true")
        ]
    ])
    await message.reply_text(welcome_text, reply_markup=buttons)

# --- 2. Broadcast System ---
@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID) & filters.reply)
async def broadcast(client, message: Message):
    msg = message.reply_to_message
    all_users = users_db.find()
    total = await users_db.count_documents({})
    done, failed = 0, 0
    
    status_msg = await message.reply(f"🚀 Broadcast စတင်နေပါပြီ... (Total: {total})")
    
    async for user in all_users:
        try:
            await msg.copy(chat_id=user["user_id"])
            done += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await msg.copy(chat_id=user["user_id"])
            done += 1
        except (UserIsBlocked, InputUserDeactivated):
            await users_db.delete_one({"user_id": user["user_id"]})
            failed += 1
        except Exception:
            failed += 1
            
    await status_msg.edit(f"✅ Broadcast ပြီးစီးပါပြီ!\n✨ အောင်မြင်: {done}\n❌ ကျရှုံး: {failed}")

# --- 3. Group Logic (Anti-Link & Auto-Reply) ---
@app.on_message(filters.group & ~filters.bot)
async def group_handler(client, message: Message):
    # Anti-Link
    if message.entities or message.caption_entities:
        for entity in (message.entities or message.caption_entities):
            if entity.type in ["url", "text_link", "mention"]:
                try:
                    await message.delete()
                    warn = await message.reply(f"⚠️ {message.from_user.mention} Link/Bio မပို့ရပါ။")
                    await asyncio.sleep(5)
                    await warn.delete()
                    return
                except: pass

    # Auto Learn & Reply
    if message.reply_to_message:
        reply_to = message.reply_to_message
        trigger = reply_to.text.lower() if reply_to.text else reply_to.sticker.file_unique_id if reply_to.sticker else None
        reply_val = message.text if message.text else message.sticker.file_id if message.sticker else None
        reply_type = "text" if message.text else "sticker" if message.sticker else None

        if trigger and reply_val:
            exists = await replies.find_one({"trigger": trigger})
            if not exists:
                await replies.insert_one({"trigger": trigger, "reply": reply_val, "type": reply_type})
    else:
        trigger = message.text.lower() if message.text else message.sticker.file_unique_id if message.sticker else None
        if trigger:
            found = await replies.find_one({"trigger": trigger})
            if found:
                if found["type"] == "text":
                    await message.reply_text(found["reply"])
                elif found["type"] == "sticker":
                    await message.reply_sticker(found["reply"])

# --- 4. Tag All ---
@app.on_message(filters.command("all") & filters.group)
async def mention_all(client, message: Message):
    member = await client.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["administrator", "creator"]:
        return
    mentions = [m.user.mention async for m in client.get_chat_members(message.chat.id) if not m.user.is_bot]
    for i in range(0, len(mentions), 5):
        await client.send_message(message.chat.id, ", ".join(mentions[i:i+5]))
        await asyncio.sleep(1.5)

# --- 5. Delete Data ---
@app.on_message(filters.command("del") & filters.user(OWNER_ID))
async def delete_reply(client, message: Message):
    if not message.reply_to_message:
        return await message.reply("Reply ပြန်ပြီး /del ရိုက်ပါ။")
    target = message.reply_to_message
    trigger = target.text.lower() if target.text else target.sticker.file_unique_id if target.sticker else None
    if trigger:
        await replies.delete_one({"trigger": trigger})
        await message.reply("✅ ဖျက်လိုက်ပါပြီ။")

# --- Auto-Restart Loop ---
if __name__ == "__main__":
    while True:
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(create_indexes())
            print("Bot is starting...")
            app.run()
        except Exception as e:
            print(f"Crashed: {e}. Restarting in 5s...")
            time.sleep(5)
            continue
