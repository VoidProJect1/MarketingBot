"""
bot.py — Telegram Marketing Bot (Control Center)

Features:
  • Add/remove Telegram accounts (API ID + Hash + Phone + OTP, 2FA support)
  • Add/remove marketing messages
  • Start / stop forwarding per-account or all accounts
  • Edit message delay
  • Live status dashboard
  • Persistent sessions (survives restarts)
"""
import asyncio
import logging
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telethon.errors import SessionPasswordNeededError

import storage
import userbot
from config import BOT_TOKEN, ADMIN_IDS, DEFAULT_DELAY

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logging.getLogger("telethon").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ─── Conversation states ─────────────────────────────────────────────────────

(
    # Add account
    S_API_ID, S_API_HASH, S_PHONE, S_OTP, S_2FA,
    # Add message
    S_MSG_TEXT, S_MSG_PICK_ACCOUNTS,
    # Edit delay
    S_NEW_DELAY,
) = range(8)


# ─── Auth guard ──────────────────────────────────────────────────────────────

def is_admin(uid: int) -> bool:
    return (not ADMIN_IDS) or (uid in ADMIN_IDS)

def admin_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("🚫 Unauthorized.")
            return ConversationHandler.END
        return await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


# ─── Keyboards ───────────────────────────────────────────────────────────────

MAIN_KB = ReplyKeyboardMarkup(
    [
        ["📱 Add Account",     "🗑 Remove Account"],
        ["📝 Add Message",     "🗑 Remove Message"],
        ["▶️ Start Forwarding", "⏹ Stop Forwarding"],
        ["⏱ Edit Delay",       "📊 Status"],
        ["❓ Help"],
    ],
    resize_keyboard=True,
)


# ─── /start ──────────────────────────────────────────────────────────────────

@admin_only
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Welcome, *{name}*!\n\n"
        "🤖 *Telegram Marketing Bot* is online.\n"
        "Use the menu below to manage accounts and forwarding.",
        parse_mode="Markdown",
        reply_markup=MAIN_KB,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  ADD ACCOUNT  (5-step conversation)
# ═══════════════════════════════════════════════════════════════════════════════

@admin_only
async def add_account_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "📱 *Add Account — Step 1 / 4*\n\n"
        "Enter your *API ID* (numbers only)\n\n"
        "🔗 Get it at: https://my.telegram.org → App API",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return S_API_ID


async def got_api_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ API ID must be numbers only. Try again:")
        return S_API_ID
    ctx.user_data["api_id"] = text
    await update.message.reply_text("*Step 2 / 4:* Enter your *API Hash*", parse_mode="Markdown")
    return S_API_HASH


async def got_api_hash(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["api_hash"] = update.message.text.strip()
    await update.message.reply_text(
        "*Step 3 / 4:* Enter *Phone Number* with country code\n\n"
        "Example: `+919876543210`",
        parse_mode="Markdown",
    )
    return S_PHONE


async def got_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip().replace(" ", "")
    ctx.user_data["phone"] = phone
    msg = await update.message.reply_text("⏳ Sending OTP to Telegram…")
    try:
        await userbot.begin_add_account(phone, ctx.user_data["api_id"], ctx.user_data["api_hash"])
        await msg.edit_text(
            "📨 *Step 4 / 4:* OTP sent!\n\n"
            "Enter the code exactly as you received it.\n"
            "_Tip: if it shows `12345` in Telegram, type `12345`_",
            parse_mode="Markdown",
        )
        return S_OTP
    except Exception as e:
        await msg.edit_text(f"❌ Failed to send OTP:\n`{e}`\n\nUse /cancel and try again.", parse_mode="Markdown")
        return ConversationHandler.END


async def got_otp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().replace(" ", "")
    phone = ctx.user_data.get("phone")
    msg = await update.message.reply_text("⏳ Verifying OTP…")
    try:
        acc_id = await userbot.complete_add_account(phone, code)
        acc = storage.get_account(acc_id)
        await msg.edit_text(
            f"✅ *Account Added Successfully!*\n\n"
            f"📱 Phone: `{acc['phone']}`\n"
            f"🔑 Account ID: `{acc_id}`",
            parse_mode="Markdown",
            reply_markup=None,
        )
        return ConversationHandler.END

    except SessionPasswordNeededError:
        await msg.edit_text(
            "🔐 *2FA Required*\n\n"
            "This account has Two-Factor Authentication.\n"
            "Enter your *2FA password*:",
            parse_mode="Markdown",
        )
        return S_2FA

    except ValueError as e:
        await msg.edit_text(f"❌ {e}\n\nUse /cancel and try again.")
        return ConversationHandler.END

    except Exception as e:
        await msg.edit_text(f"❌ Unexpected error: `{e}`", parse_mode="Markdown")
        return ConversationHandler.END


async def got_2fa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    phone = ctx.user_data.get("phone")
    msg = await update.message.reply_text("⏳ Verifying 2FA…")
    try:
        acc_id = await userbot.complete_add_account_2fa(phone, password)
        acc = storage.get_account(acc_id)
        await msg.edit_text(
            f"✅ *Account Added!* (2FA unlocked)\n\n"
            f"📱 `{acc['phone']}` → ID: `{acc_id}`",
            parse_mode="Markdown",
        )
    except Exception as e:
        await msg.edit_text(f"❌ 2FA failed: `{e}`", parse_mode="Markdown")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
#  REMOVE ACCOUNT
# ═══════════════════════════════════════════════════════════════════════════════

@admin_only
async def remove_account_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = storage.get_accounts()
    if not accounts:
        await update.message.reply_text("❌ No accounts saved.")
        return

    buttons = []
    for acc_id, acc in accounts.items():
        icon = "🟢" if userbot.is_client_connected(acc_id) else "🔴"
        fwd  = " ▶️" if userbot.is_forwarding(acc_id) else ""
        buttons.append([InlineKeyboardButton(
            f"{icon}{fwd} {acc['phone']}", callback_data=f"delacc:{acc_id}"
        )])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])

    await update.message.reply_text(
        "Select account to remove:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def cb_remove_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    acc_id = q.data.split(":")[1]
    acc = storage.get_account(acc_id)
    if acc:
        await userbot.disconnect_account(acc_id)
        storage.remove_account(acc_id)
        await q.edit_message_text(f"✅ Removed account `{acc['phone']}`", parse_mode="Markdown")
    else:
        await q.edit_message_text("❌ Account not found.")


# ═══════════════════════════════════════════════════════════════════════════════
#  ADD MESSAGE  (2-step conversation)
# ═══════════════════════════════════════════════════════════════════════════════

@admin_only
async def add_message_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = storage.get_accounts()
    if not accounts:
        await update.message.reply_text("❌ Add at least one account first.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📝 *Add Marketing Message — Step 1 / 2*\n\n"
        "Send or forward the message you want to broadcast.\n"
        "_(Text, emoji, links — everything works)_",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return S_MSG_TEXT


async def got_msg_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Accept forwarded or typed message
    text = (
        update.message.text
        or update.message.caption
        or ""
    )
    if not text.strip():
        await update.message.reply_text("❌ Message cannot be empty. Send text:")
        return S_MSG_TEXT

    ctx.user_data["msg_text"] = text
    ctx.user_data["sel_accounts"] = []
    await _show_account_picker(update, ctx, edit=False)
    return S_MSG_PICK_ACCOUNTS


async def _show_account_picker(update_or_q, ctx, edit: bool):
    accounts = storage.get_accounts()
    sel: list = ctx.user_data.get("sel_accounts", [])

    buttons = []
    for acc_id, acc in accounts.items():
        icon  = "🟢" if userbot.is_client_connected(acc_id) else "🔴"
        check = "✅ " if acc_id in sel else ""
        buttons.append([InlineKeyboardButton(
            f"{check}{icon} {acc['phone']}", callback_data=f"macc:{acc_id}"
        )])
    buttons.append([InlineKeyboardButton("🌐 All Accounts", callback_data="macc:ALL")])
    buttons.append([InlineKeyboardButton(f"💾 Save ({len(sel)} selected)", callback_data="macc:DONE")])
    kb = InlineKeyboardMarkup(buttons)
    txt = "📱 *Step 2 / 2:* Pick accounts for this message:"

    if edit:
        await update_or_q.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb)
    else:
        await update_or_q.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb)


async def cb_msg_pick_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    action = q.data.split(":")[1]
    accounts = storage.get_accounts()

    if action == "DONE":
        sel = ctx.user_data.get("sel_accounts", [])
        if not sel:
            await q.answer("⚠️ Select at least one account!", show_alert=True)
            return S_MSG_PICK_ACCOUNTS
        msg_id = storage.add_message(ctx.user_data["msg_text"], sel)
        preview = ctx.user_data["msg_text"][:60].replace("\n", " ")
        await q.edit_message_text(
            f"✅ *Message Saved!*\n\n"
            f"🆔 `{msg_id}`\n"
            f"📝 _{preview}…_\n"
            f"📱 Accounts: {len(sel)}",
            parse_mode="Markdown",
        )
        await q.answer("Message saved!")
        return ConversationHandler.END

    elif action == "ALL":
        ctx.user_data["sel_accounts"] = list(accounts.keys())
        await q.answer(f"Selected all {len(accounts)} accounts")

    else:
        sel: list = ctx.user_data.get("sel_accounts", [])
        if action in sel:
            sel.remove(action)
            await q.answer("Deselected")
        else:
            sel.append(action)
            await q.answer("Selected")
        ctx.user_data["sel_accounts"] = sel

    await _show_account_picker(q, ctx, edit=True)
    return S_MSG_PICK_ACCOUNTS


# ═══════════════════════════════════════════════════════════════════════════════
#  REMOVE MESSAGE
# ═══════════════════════════════════════════════════════════════════════════════

@admin_only
async def remove_message_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    messages = storage.get_messages()
    if not messages:
        await update.message.reply_text("❌ No messages saved.")
        return

    buttons = []
    for msg_id, msg in messages.items():
        preview = msg["text"][:40].replace("\n", " ")
        buttons.append([InlineKeyboardButton(f"🗑 {preview}", callback_data=f"delmsg:{msg_id}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])

    await update.message.reply_text(
        "Select message to delete:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def cb_remove_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    msg_id = q.data.split(":")[1]
    msg = storage.get_message(msg_id)
    if msg:
        storage.remove_message(msg_id)
        await q.edit_message_text("✅ Message deleted.")
    else:
        await q.edit_message_text("❌ Message not found.")


# ═══════════════════════════════════════════════════════════════════════════════
#  START FORWARDING
# ═══════════════════════════════════════════════════════════════════════════════

@admin_only
async def start_forwarding_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    messages = storage.get_messages()
    if not messages:
        await update.message.reply_text("❌ No messages saved. Add one first.")
        return

    buttons = []
    for msg_id, msg in messages.items():
        preview = msg["text"][:45].replace("\n", " ")
        n_accs = len(msg.get("account_ids", []))
        buttons.append([InlineKeyboardButton(
            f"📝 {preview} [{n_accs} accs]", callback_data=f"fwdstart:{msg_id}"
        )])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])

    await update.message.reply_text(
        "▶️ *Select message to forward:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cb_fwd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    msg_id = q.data.split(":")[1]
    msg = storage.get_message(msg_id)
    if not msg:
        await q.edit_message_text("❌ Message not found.")
        return

    delay    = storage.get_delay()
    accounts = storage.get_accounts()
    started, already, no_client = [], [], []

    for acc_id in msg["account_ids"]:
        if not userbot.is_client_connected(acc_id):
            no_client.append(acc_id)
            continue
        if userbot.is_forwarding(acc_id):
            already.append(acc_id)
            continue
        ok = userbot.start_forwarding(acc_id, msg["text"], delay)
        if ok:
            started.append(accounts.get(acc_id, {}).get("phone", acc_id))

    lines = ["▶️ *Forwarding Started!*\n"]
    preview = msg["text"][:50].replace("\n", " ")
    lines.append(f"📝 `{preview}…`")
    lines.append(f"⏱ Delay: *{delay}s* between groups")
    lines.append(f"✅ Started on: {len(started)} account(s)")
    if started:
        lines.append("  " + "\n  ".join(f"• {p}" for p in started))
    if already:
        lines.append(f"⚠️ Already running: {len(already)}")
    if no_client:
        lines.append(f"🔴 Not connected: {len(no_client)}")

    await q.edit_message_text("\n".join(lines), parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════════════════
#  STOP FORWARDING
# ═══════════════════════════════════════════════════════════════════════════════

@admin_only
async def stop_forwarding_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    active = userbot.get_active_forwarders()
    if not active:
        await update.message.reply_text("ℹ️ No active forwarding sessions right now.")
        return

    accounts = storage.get_accounts()
    buttons = []
    for acc_id in active:
        phone = accounts.get(acc_id, {}).get("phone", acc_id)
        stats = userbot.get_stats(acc_id)
        buttons.append([InlineKeyboardButton(
            f"⏹ {phone}  (✉️ {stats['sent']} sent)",
            callback_data=f"fwdstop:{acc_id}"
        )])
    buttons.append([InlineKeyboardButton("⏹ Stop ALL", callback_data="fwdstop:ALL")])
    buttons.append([InlineKeyboardButton("❌ Cancel",   callback_data="cancel")])

    await update.message.reply_text(
        "⏹ *Select forwarding to stop:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cb_fwd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target = q.data.split(":")[1]

    if target == "ALL":
        n = userbot.stop_all_forwarding()
        await q.edit_message_text(f"⏹ Stopped all *{n}* forwarding sessions.", parse_mode="Markdown")
    else:
        acc = storage.get_account(target)
        phone = acc["phone"] if acc else target
        userbot.stop_forwarding(target)
        await q.edit_message_text(f"⏹ Stopped forwarding for `{phone}`", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════════════════
#  EDIT DELAY
# ═══════════════════════════════════════════════════════════════════════════════

@admin_only
async def edit_delay_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cur = storage.get_delay()
    await update.message.reply_text(
        f"⏱ *Edit Message Delay*\n\n"
        f"Current: *{cur} seconds* between each group send.\n\n"
        f"Enter new delay (minimum 5 seconds):",
        parse_mode="Markdown",
        reply_markup=_cancel_kb(),
    )
    return S_NEW_DELAY


async def got_new_delay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 5:
        await update.message.reply_text("❌ Must be a number ≥ 5. Try again:")
        return S_NEW_DELAY
    delay = int(text)
    storage.set_delay(delay)
    await update.message.reply_text(
        f"✅ Delay updated to *{delay} seconds*\n"
        f"_(Takes effect on next forwarding loop)_",
        parse_mode="Markdown",
        reply_markup=MAIN_KB,
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
#  STATUS DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@admin_only
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = storage.get_accounts()
    messages = storage.get_messages()
    delay    = storage.get_delay()
    now      = datetime.now().strftime("%d %b %Y %H:%M")

    lines = [f"📊 *Bot Status* — `{now}`\n"]

    # Accounts
    lines.append(f"━━━ 📱 Accounts ({len(accounts)}) ━━━")
    if accounts:
        for acc_id, acc in accounts.items():
            conn = "🟢 Online" if userbot.is_client_connected(acc_id) else "🔴 Offline"
            fwd  = " | ▶️ Forwarding" if userbot.is_forwarding(acc_id) else ""
            st   = userbot.get_stats(acc_id)
            sent = f" ({st['sent']} sent)" if userbot.is_forwarding(acc_id) else ""
            lines.append(f"  • `{acc['phone']}` — {conn}{fwd}{sent}")
    else:
        lines.append("  _No accounts added_")

    # Messages
    lines.append(f"\n━━━ 📝 Messages ({len(messages)}) ━━━")
    if messages:
        for msg_id, msg in messages.items():
            preview  = msg["text"][:50].replace("\n", " ")
            n_accs   = len(msg.get("account_ids", []))
            lines.append(f"  • `{msg_id}` [{n_accs} accs]: _{preview}_")
    else:
        lines.append("  _No messages saved_")

    # Settings
    active_count = len(userbot.get_active_forwarders())
    lines.append(f"\n━━━ ⚙️ Settings ━━━")
    lines.append(f"  ⏱ Delay: *{delay}s*")
    lines.append(f"  ▶️ Active sessions: *{active_count}*")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════════════════
#  HELP
# ═══════════════════════════════════════════════════════════════════════════════

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ *How to use this bot*\n\n"
        "1️⃣ *Add Account* — connect your Telegram account using API credentials\n"
        "2️⃣ *Add Message* — save the marketing text you want to broadcast\n"
        "3️⃣ *Start Forwarding* — pick a message and start sending to all groups\n"
        "4️⃣ *Stop Forwarding* — halt any active session\n"
        "5️⃣ *Edit Delay* — set seconds between each group message\n"
        "6️⃣ *Status* — live overview of all accounts and sessions\n\n"
        "🔗 Get API credentials: https://my.telegram.org\n"
        "⚠️ Use /cancel any time to abort an operation.",
        parse_mode="Markdown",
    )


# ─── Cancel helpers ──────────────────────────────────────────────────────────

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Cancelled.", reply_markup=MAIN_KB)
    return ConversationHandler.END


async def cb_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("❌ Cancelled.")


def _cancel_kb():
    return ReplyKeyboardMarkup([["❌ /cancel"]], resize_keyboard=True, one_time_keyboard=True)


# ─── Post-init: reconnect saved accounts ─────────────────────────────────────

async def post_init(application: Application) -> None:
    logger.info("🔄  Reconnecting saved accounts…")
    await userbot.start_existing_clients()
    n = len([a for a in storage.get_accounts() if userbot.is_client_connected(a)])
    logger.info(f"✅  {n} account(s) connected and ready.")


# ─── Build and run ───────────────────────────────────────────────────────────

def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # — Add Account —
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📱 Add Account$"), add_account_entry)],
        states={
            S_API_ID:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_api_id)],
            S_API_HASH:[MessageHandler(filters.TEXT & ~filters.COMMAND, got_api_hash)],
            S_PHONE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_phone)],
            S_OTP:     [MessageHandler(filters.TEXT & ~filters.COMMAND, got_otp)],
            S_2FA:     [MessageHandler(filters.TEXT & ~filters.COMMAND, got_2fa)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # — Add Message —
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📝 Add Message$"), add_message_entry)],
        states={
            S_MSG_TEXT:         [MessageHandler(filters.TEXT & ~filters.COMMAND, got_msg_text)],
            S_MSG_PICK_ACCOUNTS:[CallbackQueryHandler(cb_msg_pick_accounts, pattern=r"^macc:")],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # — Edit Delay —
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^⏱ Edit Delay$"), edit_delay_entry)],
        states={
            S_NEW_DELAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_new_delay)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    ))

    # — Simple commands —
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help",   cmd_help))

    # — Menu buttons —
    app.add_handler(MessageHandler(filters.Regex(r"^🗑 Remove Account$"),  remove_account_menu))
    app.add_handler(MessageHandler(filters.Regex(r"^🗑 Remove Message$"),  remove_message_menu))
    app.add_handler(MessageHandler(filters.Regex(r"^▶️ Start Forwarding$"), start_forwarding_menu))
    app.add_handler(MessageHandler(filters.Regex(r"^⏹ Stop Forwarding$"),  stop_forwarding_menu))
    app.add_handler(MessageHandler(filters.Regex(r"^📊 Status$"),          cmd_status))
    app.add_handler(MessageHandler(filters.Regex(r"^❓ Help$"),             cmd_help))

    # — Inline callbacks —
    app.add_handler(CallbackQueryHandler(cb_remove_account,  pattern=r"^delacc:"))
    app.add_handler(CallbackQueryHandler(cb_remove_message,  pattern=r"^delmsg:"))
    app.add_handler(CallbackQueryHandler(cb_fwd_start,       pattern=r"^fwdstart:"))
    app.add_handler(CallbackQueryHandler(cb_fwd_stop,        pattern=r"^fwdstop:"))
    app.add_handler(CallbackQueryHandler(cb_cancel,          pattern=r"^cancel$"))

    return app


def main():
    app = build_app()
    logger.info("🤖  Bot is running…  (Ctrl+C to stop)")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
