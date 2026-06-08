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
GATEWAY_GROUP_ID = -4914817336
ADMIN_USER_ID = 8391021095
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

# pending_submissions[user_id] = {"username": str, "files": [file_id, ...], "user_id": int}
pending_submissions = {}

# submitted_users[user_id] = True  — tracks who already submitted
submitted_users = set()


async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greet new members in the gateway group."""
    result = update.chat_member
    if result.new_chat_member.status not in ("member", "administrator"):
        return
    if result.chat.id != GATEWAY_GROUP_ID:
        return

    user = result.new_chat_member.user
    if user.is_bot:
        return

    await context.bot.send_message(
        chat_id=GATEWAY_GROUP_ID,
        text=f"@{user.username or user.first_name}\n\n{WELCOME_MESSAGE}",
        parse_mode="Markdown"
    )


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track files submitted by users in the gateway group."""
    if update.effective_chat.id != GATEWAY_GROUP_ID:
        return

    user = update.effective_user
    if user.id == ADMIN_USER_ID or user.is_bot:
        return

    if user.id in submitted_users:
        await update.message.reply_text(
            "✋ Your submission is already under review. Please wait for a decision via DM."
        )
        return

    # Initialize tracking for this user
    if user.id not in pending_submissions:
        pending_submissions[user.id] = {
            "username": user.username or user.first_name,
            "user_id": user.id,
            "files": [],
            "message_ids": []
        }

    entry = pending_submissions[user.id]

    # Get file_id from whatever was sent
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
    entry["message_ids"].append(update.message.message_id)
    count = len(entry["files"])

    if count < 3:
        await update.message.reply_text(
            f"📁 File {count}/3 received. Send {3 - count} more to complete your submission."
        )
    else:
        # All 3 files received — notify admin
        submitted_users.add(user.id)
        await update.message.reply_text(
            "✅ All 3 files received! Your submission is now under review. "
            "You'll receive a DM with the decision soon. 🙏"
        )
        await notify_admin(context, entry)
        # Clear pending but keep in submitted_users
        del pending_submissions[user.id]


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, entry: dict):
    """Send all 3 files to admin DM with Approve/Deny buttons."""
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

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}_{username}"),
            InlineKeyboardButton("❌ Deny", callback_data=f"deny_{user_id}_{username}"),
        ]
    ])

    await context.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=f"What's your decision for @{username}?",
        reply_markup=keyboard
    )


async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin tapping Approve or Deny button."""
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_USER_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    data = query.data
    parts = data.split("_", 2)
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
            await query.edit_message_text(f"✅ @{username} has been *approved* and sent the invite link.", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(
                f"✅ Approved, but couldn't DM @{username} — they may have DMs disabled.\nError: {e}"
            )

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
            await query.edit_message_text(f"❌ @{username} has been *denied*.", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(
                f"❌ Denied, but couldn't DM @{username} — they may have DMs disabled.\nError: {e}"
            )

        # Remove from submitted so they can reapply
        submitted_users.discard(target_user_id)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to check pending submissions."""
    if update.effective_user.id != ADMIN_USER_ID:
        return
    if pending_submissions:
        lines = [f"• @{v['username']} ({len(v['files'])}/3 files)" for v in pending_submissions.values()]
        await update.message.reply_text("📋 *Pending submissions:*\n" + "\n".join(lines), parse_mode="Markdown")
    else:
        await update.message.reply_text("No pending submissions right now.")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to reset a user so they can resubmit. Usage: /reset @username or /reset user_id"""
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
        await update.message.reply_text(f"✅ User {uid} has been reset and can resubmit.")
    except ValueError:
        await update.message.reply_text("Please provide a numeric user ID.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(ChatMemberHandler(on_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(
        filters.Chat(GATEWAY_GROUP_ID) & (filters.PHOTO | filters.VIDEO | filters.Document.ALL),
        handle_file
    ))
    app.add_handler(CallbackQueryHandler(handle_decision, pattern=r"^(approve|deny)_"))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("reset", reset_command))

    logger.info("GateWayKeeperBot started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
