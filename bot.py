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

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8848316617:AAHzSa7mwL6i73vMKA9Vxq5EwaYm7RkIF08")
GATEWAY_GROUP_ID = int(os.environ.get("GATEWAY_GROUP_ID", "-4914817336"))
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


def is_gateway(chat_id: int) -> bool:
    return chat_id == GATEWAY_GROUP_ID


async def send_welcome(context: ContextTypes.DEFAULT_TYPE, user, chat_id: int):
    if user.id in greeted_users:
        return
    greeted_users.add(user.id)
    name = f"@{user.username}" if user.username else user.first_name
    logger.info(f"Sending welcome to {name} in chat {chat_id}")
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"{name}\n\n{WELCOME_MESSAGE}",
        parse_mode="Markdown"
    )


# ── Join via ChatMemberHandler ─────────────────────────────────────────────
async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    logger.info(f"ChatMemberHandler fired: chat={result.chat.id} status={result.new_chat_member.status}")
    if not is_gateway(result.chat.id):
        logger.info(f"Ignoring chat {result.chat.id} (not gateway {GATEWAY_GROUP_ID})")
        return
    if result.new_chat_member.status not in ("member", "administrator"):
        return
    user = result.new_chat_member.user
    if user.is_bot:
        return
    await send_welcome(context, user, result.chat.id)


# ── Join via service message ───────────────────────────────────────────────
async def on_new_member_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    logger.info(f"NEW_CHAT_MEMBERS service message in chat {chat_id}")
    if not is_gateway(chat_id):
        return
    for user in update.message.new_chat_members:
        if user.is_bot:
            continue
        await send_welcome(context, user, chat_id)


# ── Catch-all: log every single update ────────────────────────────────────
async def debug_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else "NO_CHAT"
    user = update.effective_user
    uid = user.id if user else "NO_USER"
    uname = (user.username or user.first_name) if user else "NO_USER"
    msg_type = "unknown"
    if update.message:
        if update.message.photo: msg_type = "photo"
        elif update.message.video: msg_type = "video"
        elif update.message.document: msg_type = "document"
        elif update.message.text: msg_type = f"text: {update.message.text[:30]}"
        elif update.message.new_chat_members: msg_type = "new_chat_members"
    logger.info(f"UPDATE → chat={chat_id} user={uid}(@{uname}) type={msg_type}")

    # Welcome fallback — fire on any message in gateway from ungreeted user
    if update.effective_chat and is_gateway(chat_id) and user and not user.is_bot and user.id != ADMIN_USER_ID:
        if user.id not in greeted_users:
            logger.info(f"Fallback welcome triggered for {uname}")
            await send_welcome(context, user, chat_id)

    # File handling
    if update.message and update.effective_chat and is_gateway(chat_id) and user and not user.is_bot and user.id != ADMIN_USER_ID:
        await process_file(update, context)


async def process_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in submitted_users:
        await update.message.reply_text("✋ Your submission is already under review. Please wait for a decision via DM.")
        return

    if user.id not in pending_submissions:
        pending_submissions[user.id] = {
            "username": user.username or user.first_name,
            "user_id": user.id,
            "files": [],
        }

    entry = pending_submissions[user.id]
    file_id = None
    file_type = None

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
    logger.info(f"File {count}/3 received from {user.username or user.first_name}")

    if count < 3:
        await update.message.reply_text(f"📁 File {count}/3 received. Send {3 - count} more to complete your submission.")
    else:
        submitted_users.add(user.id)
        await update.message.reply_text(
            "✅ All 3 files received! Your submission is now under review. You'll receive a DM with the decision soon. 🙏"
        )
        await notify_admin(context, entry)
        del pending_submissions[user.id]


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, entry: dict):
    user_id = entry["user_id"]
    username = entry["username"]

    await context.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=f"📋 *New Submission*\n👤 @{username} (ID: `{user_id}`)\n\nHere are their 3 submitted files:",
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
        text=f"What's your decision for @{username}?",
        reply_markup=keyboard
    )


async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_USER_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    parts = query.data.split("_", 2)
    action = parts[0]
    target_user_id = int(parts[1])
    username = parts[2] if len(parts) > 2 else "user"

    if action == "approve":
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🎉 Congratulations! Your submission has been *approved*.\n\n"
                    f"Here is your invite link to join the main group:\n"
                    f"👉 {MAIN_GROUP_INVITE}\n\n"
                    f"Welcome to the community! 🔥"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"⚠️ Approved but couldn't DM @{username}: {e}")

        try:
            await context.bot.ban_chat_member(chat_id=GATEWAY_GROUP_ID, user_id=target_user_id)
            await context.bot.unban_chat_member(chat_id=GATEWAY_GROUP_ID, user_id=target_user_id)
        except Exception as e:
            logger.warning(f"Could not remove approved user {target_user_id}: {e}")

        await query.edit_message_text(f"✅ @{username} *approved*, sent invite link, removed from GateWay.", parse_mode="Markdown")

    elif action == "deny":
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "❌ Unfortunately, your submission has been *denied*.\n\n"
                    "Your content did not meet the standards required for access to the main group.\n\n"
                    "You are welcome to reapply in the future with different content. 🙏"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"⚠️ Denied but couldn't DM @{username}: {e}")

        try:
            await context.bot.ban_chat_member(chat_id=GATEWAY_GROUP_ID, user_id=target_user_id)
            await context.bot.unban_chat_member(chat_id=GATEWAY_GROUP_ID, user_id=target_user_id)
        except Exception as e:
            logger.warning(f"Could not remove denied user {target_user_id}: {e}")

        await query.edit_message_text(f"❌ @{username} *denied* and removed from GateWay.", parse_mode="Markdown")
        submitted_users.discard(target_user_id)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    if pending_submissions:
        lines = [f"• @{v['username']} ({len(v['files'])}/3 files)" for v in pending_submissions.values()]
        await update.message.reply_text("📋 *Pending:*\n" + "\n".join(lines), parse_mode="Markdown")
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


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug: report the current chat ID."""
    cid = update.effective_chat.id
    await update.message.reply_text(f"This chat ID is: `{cid}`\nConfigured gateway ID: `{GATEWAY_GROUP_ID}`", parse_mode="Markdown")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Join detection — all methods
    app.add_handler(ChatMemberHandler(on_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_member_message))

    # Catch-all handler — logs everything and handles files + fallback welcome
    app.add_handler(MessageHandler(filters.ALL, debug_all))

    # Buttons + commands
    app.add_handler(CallbackQueryHandler(handle_decision, pattern=r"^(approve|deny)_"))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("chatid", chatid_command))

    logger.info(f"GateWayKeeperBot started. Watching group {GATEWAY_GROUP_ID}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
