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

GATEWAY_GROUP_ID = int(os.environ.get("GATEWAY_GROUP_ID", "-1003667836965"))
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "8391021095"))
MAIN_GROUP_INVITE = "https://t.me/+OwOZ9LFpcAozMWI5"
SUBMISSION_TIMEOUT = 30 * 60  # 30 minutes in seconds

WELCOME_MESSAGE = (
    "👋 Welcome to *The GateWay!*\n\n"
    "This is the entry point to the *Look at Her/Us/Them* group — one of the most active and verified content communities on Telegram.\n\n"
    "📋 *To apply for access:*\n"
    "Submit *3 files* of your best content right here in this group.\n\n"
    "📌 *Requirements:*\n"
    "• At least *1 must be a video*\n"
    "• All content must be your own\n\n"
    "⏱ *You have 30 minutes* to submit all 3 files or you will be automatically removed.\n\n"
    "Once reviewed you will receive a *personal DM* with either:\n"
    "✅ *Approval* — with your invite link to the main group\n"
    "❌ *Denial* — if your content doesn't meet our standards\n\n"
    "🔥 Put your best foot forward. Good luck!"
)

pending_submissions = {}
submitted_users = set()
greeted_users = set()


def is_gateway(chat_id) -> bool:
    return int(chat_id) == GATEWAY_GROUP_ID


async def remove_user(context, user_id, reason="timeout"):
    try:
        await context.bot.ban_chat_member(chat_id=GATEWAY_GROUP_ID, user_id=user_id)
        await context.bot.unban_chat_member(chat_id=GATEWAY_GROUP_ID, user_id=user_id)
        logger.info(f"Removed user {user_id} ({reason})")
    except Exception as e:
        logger.warning(f"Could not remove user {user_id}: {e}")


async def timeout_user(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data["user_id"]
    username = context.job.data["username"]

    if user_id in submitted_users:
        return  # Already submitted, don't remove
    if user_id not in pending_submissions and user_id not in greeted_users:
        return  # Already removed

    logger.info(f"Timeout firing for {username} ({user_id})")

    try:
        await context.bot.send_message(
            chat_id=GATEWAY_GROUP_ID,
            text=f"⏱ @{username} — your 30 minute submission window has expired. You have been removed. You are welcome to rejoin and try again."
        )
    except Exception as e:
        logger.warning(f"Could not send timeout message: {e}")

    await remove_user(context, user_id, "timeout")
    pending_submissions.pop(user_id, None)
    greeted_users.discard(user_id)


async def send_welcome(context, user, chat_id):
    if user.id in greeted_users:
        return
    greeted_users.add(user.id)
    name = f"@{user.username}" if user.username else user.first_name
    logger.info(f"Sending welcome to {name} in chat {chat_id}")
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{name}\n\n{WELCOME_MESSAGE}",
            parse_mode="Markdown"
        )
        logger.info(f"Welcome sent to {name}")
    except Exception as e:
        logger.error(f"Welcome failed for {name}: {e}")
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{name} Welcome! Submit 3 files (at least 1 video) within 30 minutes to apply."
            )
        except Exception as e2:
            logger.error(f"Plain welcome also failed: {e2}")
            return

    # Start 30 minute timeout
    context.job_queue.run_once(
        timeout_user,
        SUBMISSION_TIMEOUT,
        data={"user_id": user.id, "username": user.username or user.first_name},
        name=f"timeout_{user.id}"
    )
    logger.info(f"30-min timeout started for {name}")


async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    logger.info(f"ChatMember: chat={result.chat.id} status={result.new_chat_member.status}")
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
    logger.info(f"MSG chat={chat_id} user={user.id}(@{user.username}) gateway={is_gateway(chat_id)}")

    if not is_gateway(chat_id) or user.is_bot or user.id == ADMIN_USER_ID:
        return

    if user.id not in greeted_users:
        await send_welcome(context, user, chat_id)

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
            "has_video": False,
        }

    entry = pending_submissions[user.id]
    file_id = file_type = None

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = "photo"
    elif update.message.video:
        file_id = update.message.video.file_id
        file_type = "video"
        entry["has_video"] = True
    elif update.message.document:
        file_id = update.message.document.file_id
        file_type = "document"

    if not file_id:
        return

    entry["files"].append((file_type, file_id))
    count = len(entry["files"])
    logger.info(f"File {count}/3 ({file_type}) from {user.username or user.first_name}")

    if count < 3:
        await update.message.reply_text(f"📁 File {count}/3 received. Send {3 - count} more.")
    else:
        # Check video requirement
        if not entry["has_video"]:
            await update.message.reply_text(
                "❌ At least one of your submissions must be a *video*. Please send a video to complete your submission.",
                parse_mode="Markdown"
            )
            # Remove last file and keep waiting
            entry["files"].pop()
            return

        submitted_users.add(user.id)
        # Cancel timeout job
        jobs = context.job_queue.get_jobs_by_name(f"timeout_{user.id}")
        for job in jobs:
            job.schedule_removal()

        await update.message.reply_text(
            "✅ All 3 files received! Your submission is now under review. Expect a DM soon. 🙏"
        )
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

    # Cancel any pending timeout
    jobs = context.job_queue.get_jobs_by_name(f"timeout_{target_user_id}")
    for job in jobs:
        job.schedule_removal()

    if action == "approve":
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 Your submission has been *approved*!\n\nJoin the main group here:\n👉 {MAIN_GROUP_INVITE}\n\nWelcome! 🔥",
                parse_mode="Markdown"
            )
        except Exception as e:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"⚠️ Couldn't DM @{username}: {e}")
        await remove_user(context, target_user_id, "approved")
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
        await remove_user(context, target_user_id, "denied")
        await query.edit_message_text(f"❌ @{username} denied and removed from GateWay.", parse_mode="Markdown")
        submitted_users.discard(target_user_id)


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    await update.message.reply_text(
        f"Chat ID: `{cid}`\nGateway: `{GATEWAY_GROUP_ID}`\nMatch: `{is_gateway(cid)}`",
        parse_mode="Markdown"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    if pending_submissions:
        lines = [f"• @{v['username']} ({len(v['files'])}/3, video={'✅' if v['has_video'] else '❌'})" for v in pending_submissions.values()]
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
        jobs = context.job_queue.get_jobs_by_name(f"timeout_{uid}")
        for job in jobs:
            job.schedule_removal()
        await update.message.reply_text(f"✅ User {uid} reset.")
    except ValueError:
        await update.message.reply_text("Provide a numeric user ID.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("chatid", chatid_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(ChatMemberHandler(on_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_member_message))
    app.add_handler(CallbackQueryHandler(handle_decision, pattern=r"^(approve|deny)_"))
    app.add_handler(MessageHandler(filters.ALL, on_any_message))

    logger.info(f"GateWayKeeperBot started. Gateway={GATEWAY_GROUP_ID} Admin={ADMIN_USER_ID}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
