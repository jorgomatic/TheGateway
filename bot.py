import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

GATEWAY_GROUP_ID = int(os.environ.get("GATEWAY_GROUP_ID", "-1001003667836965"))
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "8391021095"))
MAIN_GROUP_INVITE = "https://t.me/+OwOZ9LFpcAozMWI5"

WELCOME_MESSAGE = (
    "👋 Welcome to *The GateWay!*\n\n"
    "This is the entry point to the *Look at Her/Us/Them* group — one of the most active and verified content communities on Telegram.\n\n"
    "📋 *To apply for access:*\n"
    "Submit your *3 best content files* right here in this group.\n\n"
    "Once your submission is reviewed, you will receive a *personal DM* with either:\n"
    "✅ *Approval* — with your invite link to the main group\n"
    "❌ *Denial* — if your content doesn't meet our standards\n\n"
    "🔥 Put your best foot forward. Good luck!"
)

pending_submissions = {}
submitted_users = set()
greeted_users = set()


def is_gateway(chat_id) -> bool:
    return int(chat_id) == GATEWAY_GROUP_ID


async def send_welcome(context, user, chat_id):
    if user.id in greeted_users:
        logger.info(f"Already greeted {user.id}, skipping")
        return
    greeted_users.add(user.id)
    name = f"@{user.username}" if user.username else user.first_name
    logger.info(f"Attempting welcome to {name} (id={user.id}) in chat {chat_id}")
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{name}\n\n{WELCOME_MESSAGE}",
            parse_mode="Markdown"
        )
        logger.info(f"✅ Welcome sent to {name}")
    except Exception as e:
        logger.error(f"❌ Welcome failed for {name}: {e}")
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{name} Welcome! Please submit 3 files to apply for access."
            )
            logger.info(f"✅ Plain welcome sent to {name}")
        except Exception as e2:
            logger.error(f"❌ Plain welcome also failed: {e2}")


# ── Handlers ──────────────────────────────────────────────────────────────

async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    logger.info(f"ChatMember event: chat={result.chat.id} status={result.new_chat_member.status}")
    if not is_gateway(result.chat.id):
        return
    if result.new_chat_member.status not in ("member", "administrator"):
        return
    user = result.new_chat_member.user
    if user.is_bot:
        return
    await send_welcome(context, user, result.chat.id)


async def on_new_member_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    logger.info(f"NEW_CHAT_MEMBERS in chat {chat_id}")
    if not is_gateway(chat_id):
        return
    for user in update.message.new_chat_members:
        if user.is_bot:
            continue
        await send_welcome(context, user, chat_id)


async def on_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    user = update.effective_user
    logger.info(f"MSG chat={chat_id} user={user.id}(@{user.username}) is_gateway={is_gateway(chat_id)}")

    if not is_gateway(chat_id) or user.is_bot or user.id == ADMIN_USER_ID:
        return

    # Fallback welcome
    if user.id not in greeted_users:
        await send_welcome(context, user, chat_id)

    # File tracking
    if update.message:
        await process_file(update, context)


async def process_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in submitted_users:
        await update.message.reply_text("✋ Your submission is already under review.")
        return

    if user.id not in pending_submissions:
        pending_submissions[user.id] = {
            "username": user.username or user.first_name,
            "user_id": user.id,
            "files": [],
        }

    entry = pending_submissions[user.id]
    file_id = file_type = None

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = "photo"
    elif update.message.video:
        file_id = update.message.video.file_id
        file_type = "video"
    elif update.message.document:
        file_id = update.message.document.file_id
        file_type = "document"

    if not file_id:
        return

    entry["files"].append((file_type, file_id))
    count = len(entry["files"])
    logger.info(f"File {count}/3 from {user.username or user.first_name}")

    if count < 3:
        await update.message.reply_text(f"📁 File {count}/3 received. Send {3 - count} more.")
    else:
        submitted_users.add(user.id)
        await update.message.reply_text("✅ All 3 files received! Under review — expect a DM soon. 🙏")
        await notify_admin(context, entry)
        del pending_submissions[user.id]


async def notify_admin(context, entry):
    user_id = entry["user_id"]
    username = entry["username"]

    await context.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=f"📋 *New Submission*\n👤 @{username} (ID: `{user_id}`)\n\nHere are their 3 files:",
        parse_mode="Markdown"
    )
    for i, (file_type, file_id) in enumerate(entry["files"], 1):
        caption = f"File {i}/3"
        if file_type == "photo":
            await context.bot.send_photo(chat_id=ADMIN_USER_ID, photo=file_id, caption=caption)
        elif file_type == "video":
            await context.bot.send_video(chat_id=ADMIN_USER_ID, video=file_id, caption=caption)
        elif file_type == "document":
            await context.bot.send_document(chat_id=ADMIN_USER_ID, document=file_id, caption=caption)

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}_{username}"),
        InlineKeyboardButton("❌ Deny", callback_data=f"deny_{user_id}_{username}"),
    ]])
    await context.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=f"Decision for @{username}?",
        reply_markup=keyboard
    )


async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_USER_ID:
        return

    parts = query.data.split("_", 2)
    action = parts[0]
    target_user_id = int(parts[1])
    username = parts[2] if len(parts) > 2 else "user"

    if action == "approve":
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 Your submission has been *approved*!\n\nJoin the main group here:\n👉 {MAIN_GROUP_INVITE}\n\nWelcome! 🔥",
                parse_mode="Markdown"
            )
        except Exception as e:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"⚠️ Couldn't DM @{username}: {e}")
        try:
            await context.bot.ban_chat_member(chat_id=GATEWAY_GROUP_ID, user_id=target_user_id)
            await context.bot.unban_chat_member(chat_id=GATEWAY_GROUP_ID, user_id=target_user_id)
        except Exception as e:
            logger.warning(f"Remove failed: {e}")
        await query.edit_message_text(f"✅ @{username} approved and removed from GateWay.", parse_mode="Markdown")

    elif action == "deny":
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ Your submission has been *denied*.\n\nYou may reapply in the future with different content. 🙏",
                parse_mode="Markdown"
            )
        except Exception as e:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"⚠️ Couldn't DM @{username}: {e}")
        try:
            await context.bot.ban_chat_member(chat_id=GATEWAY_GROUP_ID, user_id=target_user_id)
            await context.bot.unban_chat_member(chat_id=GATEWAY_GROUP_ID, user_id=target_user_id)
        except Exception as e:
            logger.warning(f"Remove failed: {e}")
        await query.edit_message_text(f"❌ @{username} denied and removed from GateWay.", parse_mode="Markdown")
        submitted_users.discard(target_user_id)


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    logger.info(f"/chatid called from {cid}, gateway={GATEWAY_GROUP_ID}, match={is_gateway(cid)}")
    try:
        await update.message.reply_text(
            f"Chat ID: `{cid}`\nGateway: `{GATEWAY_GROUP_ID}`\nMatch: `{is_gateway(cid)}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"/chatid reply failed: {e}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    if pending_submissions:
        lines = [f"• @{v['username']} ({len(v['files'])}/3)" for v in pending_submissions.values()]
        await update.message.reply_text("📋 Pending:\n" + "\n".join(lines))
    else:
        await update.message.reply_text("No pending submissions.")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /reset <user_id>")
        return
    try:
        uid = int(args[0])
        submitted_users.discard(uid)
        pending_submissions.pop(uid, None)
        greeted_users.discard(uid)
        await update.message.reply_text(f"✅ User {uid} reset.")
    except ValueError:
        await update.message.reply_text("Provide a numeric user ID.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands first
    app.add_handler(CommandHandler("chatid", chatid_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("reset", reset_command))

    # Join detection
    app.add_handler(ChatMemberHandler(on_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_member_message))

    # Callback buttons
    app.add_handler(CallbackQueryHandler(handle_decision, pattern=r"^(approve|deny)_"))

    # All messages (fallback welcome + file tracking)
    app.add_handler(MessageHandler(filters.ALL, on_any_message))

    logger.info(f"GateWayKeeperBot started. Gateway={GATEWAY_GROUP_ID} Admin={ADMIN_USER_ID}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
