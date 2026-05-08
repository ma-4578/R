import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
from motor.motor_asyncio import AsyncIOMotorClient

# --- Configuration (ဒီနေရာမှာ အချက်အလက်မှန်အောင် ဖြည့်ပေးပါ) ---
API_ID = 12345                     # သင်၏ API ID
API_HASH = "your_api_hash"          # သင်၏ API HASH
BOT_TOKEN = "your_bot_token"        # သင်၏ BOT TOKEN
MONGO_URL = "mongodb+srv://..."     # သင်၏ MongoDB Connection URL
OWNER_ID = 123456789                # သင့် User ID (နံပါတ်သက်သက်)

app = Client("shwe_mm_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["shwe_db"]
replies = db["auto_replies"]
users_db = db["users"]

# --- Database Indexing (မလေးအောင် လုပ်ပေးတဲ့အပိုင်း) ---
async def create_indexes():
    await replies.create_index("trigger")
    await users_db.create_index("user_id")
    print("Database Indexes Created/Verified.")

# --- 1. Start Menu & User Tracking ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    # Broadcast အတွက် user id ကို database ထဲမှတ်သားခြင်း
    await users_db.update_one(
        {"user_id": message.from_user.id},
        {"$set": {"username": message.from_user.username}},
        upsert=True
    )
    
    welcome_text = (
        f"ဟလို {message.from_user.mention} ✨\n\n"
        "ကျွန်တော်က Auto Reply နဲ့ Group Management Bot တစ်ခုဖြစ်ပါတယ်။\n"
        "အောက်က Button တွေကိုနှိပ်ပြီး လေ့လာနိုင်ပါတယ်ဗျာ။\n"
        "အရာအားလုံးအကောင်းလို့ပဲ မြင်ပါတယ်😔"
    )
    
    # Link Button ၅ ခု
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Channel 📢", url="https://t.me/myanmarbot_music"),
            InlineKeyboardButton("Developer 👨‍💻", url="http://t.me/HANTHAR999")
        ],
        [
            InlineKeyboardButton("Group 👥", url="https://t.me/myanmar_music_Bot2027"),
            InlineKeyboardButton("🌐", url="https://t.me/myanmarbot_music/29")
        ],
        [
            InlineKeyboardButton("Add Me To Your Group", url="https://t.me/catlover_2026bot?startgroup=true")
        ]
    ])
    await message.reply_text(welcome_text, reply_markup=buttons)

# --- 2. Broadcast System (Owner Only) ---
@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID) & filters.reply)
async def broadcast(client, message: Message):
    msg = message.reply_to_message
    all_users = users_db.find()
    
    done = 0
    failed = 0
    total = await users_db.count_documents({})
    
    status_msg = await message.reply(f"🚀 Broadcast စတင်နေပါပြီ... (စုစုပေါင်း: {total})")
    
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
            
    await status_msg.edit(f"✅ Broadcast ပို့ဆောင်ပြီးစီးပါပြီ!\n\n✨ အောင်မြင်: {done}\n❌ ကျရှုံး: {failed}")

# --- 3. Group Logic (Auto-Learn, Reply & Anti-Link) ---
@app.on_message(filters.group & ~filters.bot)
async def group_handler(client, message: Message):
    # --- Anti-Link & Bio ---
    has_link = False
    if message.entities or message.caption_entities:
        for entity in (message.entities or message.caption_entities):
            if entity.type in ["url", "text_link", "mention"]:
                has_link = True
                break
    
    if has_link:
        try:
            await message.delete()
            warn = await message.reply(f"⚠️ {message.from_user.mention} Link/Bio များ မပို့ရပါ။")
            await asyncio.sleep(5)
            await warn.delete()
            return
        except: pass

    # --- Auto Learn & Reply ---
    if message.reply_to_message:
        reply_to = message.reply_to_message
        
        # Sticker ဆိုရင် Unique ID နဲ့ မှတ်မယ်
        trigger = reply_to.text.lower() if reply_to.text else reply_to.sticker.file_unique_id if reply_to.sticker else None
        
        # Reply (အဖြေ) စစ်ဆေးခြင်း
        reply_val = message.text if message.text else message.sticker.file_id if message.sticker else None
        reply_type = "text" if message.text else "sticker" if message.sticker else None

        if trigger and reply_val:
            # Duplicate Check: မှတ်ပြီးသားဆို ထပ်မမှတ်ဘူး
            exists = await replies.find_one({"trigger": trigger})
            if not exists:
                await replies.insert_one({
                    "trigger": trigger,
                    "reply": reply_val,
                    "type": reply_type
                })
    
    # Auto Reply Logic
    else:
        trigger = message.text.lower() if message.text else message.sticker.file_unique_id if message.sticker else None
        if trigger:
            found = await replies.find_one({"trigger": trigger})
            if found:
                if found["type"] == "text":
                    await message.reply_text(found["reply"])
                elif found["type"] == "sticker":
                    await message.reply_sticker(found["reply"])

# --- 4. Tag All For Admins (/all) ---
@app.on_message(filters.command("all") & filters.group)
async def mention_all(client, message: Message):
    member = await client.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["administrator", "creator"]:
        return
    
    mentions = []
    async for m in client.get_chat_members(message.chat.id):
        if not m.user.is_bot:
            mentions.append(m.user.mention)
            
    for i in range(0, len(mentions), 5):
        await client.send_message(message.chat.id, f"📢 အဖွဲ့ဝင်များ အားလုံးအတွက် -\n\n" + ", ".join(mentions[i:i+5]))
        await asyncio.sleep(1.5)

# --- 5. Delete Data (Owner Only) ---
@app.on_message(filters.command("del") & filters.user(OWNER_ID))
async def delete_reply(client, message: Message):
    if not message.reply_to_message:
        return await message.reply("ဖျက်ချင်တဲ့ စာသား ဒါမှမဟုတ် Sticker ကို Reply ပြန်ပြီး /del လို့ ရိုက်ပါ။")
    
    target = message.reply_to_message
    trigger = target.text.lower() if target.text else target.sticker.file_unique_id if target.sticker else None
    
    if trigger:
        result = await replies.delete_one({"trigger": trigger})
        if result.deleted_count > 0:
            await message.reply("✅ Database ထဲက အောင်မြင်စွာ ဖျက်လိုက်ပါပြီ။")
        else:
            await message.reply("❌ ဒီစာသားက Database ထဲမှာ မရှိသေးပါဘူး။")

# --- အလိုအလျောက် ပြန်ပွင့်စေမယ့် Logic (Auto-Restart) ---
if __name__ == "__main__":
    while True:
        try:
            # Indexing ကို background မှာ run ခိုင်းခြင်း
            loop = asyncio.get_event_loop()
            loop.run_until_complete(create_indexes())
            
            print("Bot is starting...")
            app.run()
        except Exception as e:
            print(f"Bot crashed with error: {e}. Restarting in 5 seconds...")
            time.sleep(5)
            continue
