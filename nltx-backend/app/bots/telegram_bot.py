"""
NLTX Telegram Bot
Commands:
  /start      — Welcome & link account
  /send       — Send crypto via NLP
  /balance    — Check wallet balances
  /price      — Live token prices
  /history    — Last 5 transactions
  /limits     — Spending limits
  /help       — All commands

Any plain text message is parsed as an NLP command.
"""
import logging
import asyncio
import json
import uuid
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.config import get_settings
from app.services.nlp_service import get_nlp_service

logger = logging.getLogger(__name__)
settings = get_settings()

API_BASE = f"http://localhost:{settings.API_PORT}"

# ===================================================
#  HELPER: Call NLTX REST API
# ===================================================
async def api_call(method: str, endpoint: str, data: dict = None, token: str = None) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{API_BASE}{endpoint}"
            fn = getattr(session, method.lower())
            kwargs = {"headers": headers}
            if data is not None:
                kwargs["json"] = data
            async with fn(url, **kwargs) as resp:
                text = await resp.text()
                try:
                    body = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    body = {"detail": text}
                if resp.status >= 400:
                    err = body.get("detail", body)
                    if isinstance(err, list) and err:
                        e0 = err[0]
                        err = e0.get("msg", str(e0)) if isinstance(e0, dict) else str(e0)
                    return {"_http_error": True, "status_code": resp.status, "error": err, **body}
                return body
    except Exception as e:
        logger.error(f"API call failed: {e}")
        return {"_http_error": True, "error": str(e)}


USER_TOKENS: dict = {}  # telegram_id -> JWT
LAST_TX: dict = {}  # telegram_id -> last transaction_id (for /undo)
PENDING_SEND: dict = {}  # short_id -> pending send payload


def _network_for_token(tok: str) -> str:
    t = (tok or "USDT").upper()
    if t == "ETH":
        return "ethereum"
    if t == "MATIC":
        return "polygon"
    if t == "SOL":
        return "solana"
    return "polygon"


def _normalize_recipient(entities: dict) -> tuple:
    """Returns (to_username or None, to_address or None)."""
    to_u = entities.get("to_username")
    to_a = entities.get("to_address")
    if to_a:
        return None, str(to_a).strip()
    if to_u:
        s = str(to_u).strip()
        if s.startswith("0x"):
            return None, s
        return s.lstrip("@").lower(), None
    return None, None


# ===================================================
#  /start
# ===================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    if args and args[0].startswith("NLTX-"):
        code = args[0]
        await update.message.reply_text(f"⏳ Verifying coupling code `{code}`...")
        
        # Call backend to verify
        res = await api_call(
            "post",
            "/api/users/platform/link-verify",
            data={
                "platform": "telegram",
                "code": code,
                "platform_id": str(user.id),
                "platform_username": user.username or "",
            },
        )
        
        if res.get("status") in ["success", "already_linked"]:
            if res.get("access_token"):
                USER_TOKENS[user.id] = res["access_token"]
            await update.message.reply_text(
                "✅ *Account Linked Successfully!*\n\n"
                "Your Telegram is now paired with your NLTX wallet.\n"
                "You can send crypto, view balances, and confirm transactions from here.",
                parse_mode="Markdown",
            )
        else:
            err = res.get("error") or res.get("detail", "Invalid code")
            await update.message.reply_text(f"❌ *Linking Failed*: {err}", parse_mode="Markdown")

    keyboard = [
        [InlineKeyboardButton("💰 Check Balance", callback_data="balance"),
         InlineKeyboardButton("📈 Live Prices", callback_data="prices")],
        [InlineKeyboardButton("📜 Transaction History", callback_data="history"),
         InlineKeyboardButton("🔒 Spending Limits", callback_data="limits")],
        [InlineKeyboardButton("🌐 Open Web App", url="http://localhost:8080/dashboard.html")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 Welcome to *NLTX*, {user.first_name}!\n\n"
        "🤖 I'm your AI-powered crypto payment assistant.\n"
        "Send me natural language commands like:\n\n"
        "• `Send 50 USDT to Alice for dinner`\n"
        "• `What's my ETH balance?`\n"
        "• `Swap 0.1 ETH to USDC`\n"
        "• `Schedule $200 USDT monthly to savings`\n\n"
        "Or use the buttons below to get started 👇",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


# ===================================================
#  /help
# ===================================================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *NLTX Bot Commands*\n\n"
        "💬 *Natural Language (just type normally!)*\n"
        "`Send 50 USDT to @alice for coffee`\n"
        "`What is my ETH balance?`\n"
        "`Swap 100 USDT to ETH`\n"
        "`Price of Bitcoin`\n"
        "`Schedule 200 USDT monthly to @savings`\n\n"
        "📌 *Slash Commands*\n"
        "/send — Send crypto\n"
        "/balance — Check balances\n"
        "/price — Token prices\n"
        "/history — Recent transactions\n"
        "/limits — Spending limits\n"
        "/undo — Undo last send (within undo window)\n"
        "/help — This help message\n\n"
        "🔒 Secured with MPC wallets + 30s undo window",
        parse_mode="Markdown"
    )


# ===================================================
#  /balance
# ===================================================
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    await em.reply_text("🔄 Fetching your balances...")
    token = USER_TOKENS.get(update.effective_user.id)

    if token:
        data = await api_call("get", "/api/wallet/balances", token=token)
        if data.get("_http_error"):
            await em.reply_text(f"⚠️ Could not load balances: {data.get('error')}")
            return
        balances = data.get("balances", [])
        total = data.get("total_usd", 0)
        if balances:
            lines = []
            for b in balances[:12]:
                change = b.get("change_24h", 0)
                emoji = "🟢" if change >= 0 else "🔴"
                lines.append(f"{emoji} *{b['token']}* ({b['network'].capitalize()})\n"
                             f"   {b['balance']:.4f} ≈ ${b['usd_value']:,.2f} ({change:+.1f}%)")
            msg = "💎 *Your Portfolio*\n\n" + "\n\n".join(lines) + f"\n\n💰 *Total: ${total:,.2f}*"
            await em.reply_text(msg, parse_mode="Markdown")
            return

    await em.reply_text(
        "💎 *Your Portfolio (Demo)*\n\n"
        "🟢 *ETH* (Ethereum)\n   2.4831 ≈ $6,183.40 (+2.4%)\n\n"
        "🟢 *USDT* (Ethereum)\n   1,766.50 ≈ $1,766.50 (stable)\n\n"
        "🟢 *MATIC* (Polygon)\n   12,500 ≈ $2,987.50 (+1.1%)\n\n"
        "🔴 *SOL* (Solana)\n   18.92 ≈ $1,909.92 (-0.8%)\n\n"
        "💰 *Total: $12,847.32*\n\n"
        "💡 Link your account to see real balances.",
        parse_mode="Markdown"
    )


# ===================================================
#  /price
# ===================================================
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        token = args[0].upper()
    else:
        token = "ETH"

    await update.effective_message.reply_text(f"📈 Fetching {token} price...")
    data = await api_call("get", f"/api/wallet/price/{token}")

    if "error" in data or data.get("price_usd", 0) == 0:
        # Fallback prices
        prices = {"ETH": 2489.0, "BTC": 65430.0, "SOL": 101.0, "MATIC": 0.24, "USDT": 1.0, "BNB": 380.0}
        price = prices.get(token, 0)
        source = "Demo"
    else:
        price = data["price_usd"]
        change = data.get("change_24h", 0)
        source = data.get("source", "")

    change_val = data.get("change_24h", 0)
    emoji = "📈" if change_val >= 0 else "📉"

    await update.effective_message.reply_text(
        f"{emoji} *{token} Price*\n\n"
        f"💵 ${price:,.2f} USD\n"
        f"24h: {change_val:+.2f}%\n"
        f"Source: {source.capitalize()}\n\n"
        f"Usage: `/price SOL`, `/price BTC`, `/price MATIC`",
        parse_mode="Markdown"
    )


# ===================================================
#  /history
# ===================================================
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    token = USER_TOKENS.get(update.effective_user.id)
    if token:
        data = await api_call("get", "/api/transactions/?limit=5", token=token)
        if not data.get("_http_error") and data.get("transactions"):
            lines = []
            for i, tx in enumerate(data["transactions"][:5], 1):
                amt = tx.get("amount", "?")
                tok = tx.get("token", "")
                to = tx.get("to_username") or (tx.get("to_address") or "")[:10] + "…"
                st = tx.get("status", "")
                lines.append(f"{i}. {amt} {tok} → `{to}` · {st}")
            msg = "📜 *Recent Transactions*\n\n" + "\n".join(lines)
            await em.reply_text(msg, parse_mode="Markdown")
            return
    await em.reply_text(
        "📜 *Recent Transactions (Demo)*\n\n"
        "Link your account for live history.\n"
        "Or open the NLTX web app → Transactions.",
        parse_mode="Markdown",
    )


# ===================================================
#  /limits
# ===================================================
async def limits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    token = USER_TOKENS.get(update.effective_user.id)
    if token:
        data = await api_call("get", "/api/wallet/spending-limits", token=token)
        if not data.get("_http_error") and "daily_limit" in data:
            await em.reply_text(
                "🔒 *Your Spending Limits*\n\n"
                f"📅 Daily: ${data.get('daily_limit', 0):,.0f} "
                f"(${data.get('daily_used', 0):,.0f} used)\n"
                f"📆 Weekly: ${data.get('weekly_limit', 0):,.0f}\n"
                f"🗓 Monthly: ${data.get('monthly_limit', 0):,.0f}\n"
                f"💳 Single TX Max: ${data.get('single_tx_max', 0):,.0f}\n"
                f"🔐 2FA above: ${data.get('require_2fa_above', 0):,.0f}\n\n"
                "✅ 30-second undo after each send",
                parse_mode="Markdown",
            )
            return
    await em.reply_text(
        "🔒 *Spending Limits*\n\n"
        "Link your account to see your real limits.\n"
        "Web app → Settings.",
        parse_mode="Markdown",
    )


# ===================================================
#  NATURAL LANGUAGE MESSAGE HANDLER
# ===================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parse any natural language message as an NLP command."""
    text = (update.effective_message.text or "").strip()
    if not text:
        return

    # Show typing indicator
    await context.bot.send_chat_action(update.effective_chat.id, action="typing")

    # Parse with NLP service
    nlp = get_nlp_service()
    result = await nlp.parse_command(text)
    intent = result.get("intent", "UNKNOWN")
    entities = result.get("entities", {})
    confidence = result.get("confidence", 0)

    # Handle by intent
    if intent == "BALANCE":
        await balance_command(update, context)

    elif intent == "PRICE":
        token = entities.get("query_token") or "ETH"
        context.args = [token]
        await price_command(update, context)

    elif intent == "HISTORY":
        await history_command(update, context)

    elif intent == "LIMITS":
        await limits_command(update, context)

    elif intent == "HELP":
        await help_command(update, context)

    elif intent == "SEND" and confidence > 0.6:
        try:
            amt_f = float(entities.get("amount"))
        except (TypeError, ValueError):
            await update.effective_message.reply_text(
                "Please include a numeric amount, e.g. `Send 50 USDT to alice`",
                parse_mode="Markdown",
            )
            return

        tok = entities.get("token") or "USDT"
        memo = entities.get("memo") or ""
        net = (entities.get("network") or _network_for_token(tok)).lower()
        if net not in ("ethereum", "polygon", "solana"):
            net = _network_for_token(tok)

        to_user, to_addr = _normalize_recipient(entities)
        if not to_user and not to_addr:
            await update.effective_message.reply_text(
                "Who should receive this? Example: `Send 10 USDT to priya`",
                parse_mode="Markdown",
            )
            return

        pid = uuid.uuid4().hex[:12]
        PENDING_SEND[pid] = {
            "amount": amt_f,
            "token": tok.upper(),
            "network": net,
            "memo": memo or None,
            "to_username": to_user,
            "to_address": to_addr,
        }

        display_to = to_addr or f"@{to_user}"
        keyboard = [
            [
                InlineKeyboardButton(f"✅ Confirm send", callback_data=f"cs:{pid}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_tx"),
            ]
        ]
        await update.effective_message.reply_text(
            f"💸 *Transaction Preview*\n\n"
            f"Amount: `{amt_f} {tok}`\n"
            f"To: `{display_to}`\n"
            f"Memo: {memo or 'N/A'}\n"
            f"Network: `{net}`\n\n"
            f"⚠️ After confirm you have *{settings.UNDO_WINDOW_SECONDS}s to undo* with /undo",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif intent == "SWAP":
        from_tok = entities.get("from_token", "ETH")
        to_tok = entities.get("to_token", "USDC")
        amt = entities.get("amount", "?")
        await update.effective_message.reply_text(
            f"🔄 *Swap Preview*\n\n"
            f"{amt} {from_tok} → {to_tok}\n"
            f"Route: Best DEX Rate\n"
            f"Slippage: 0.5%\n\n"
            f"Use the web app to execute swaps:\nnltx.io/dashboard",
            parse_mode="Markdown"
        )

    elif intent == "SCHEDULE":
        await update.effective_message.reply_text(
            f"⏰ Recurring payment setup requires web app.\n"
            f"Visit: nltx.io/dashboard\n"
            f"Or use: `/schedule` command (coming soon)",
            parse_mode="Markdown"
        )

    else:
        nlp_response = result.get("response_text", "")
        await update.effective_message.reply_text(
            f"🤖 {nlp_response or 'I understood your request. Please be more specific.'}\n\n"
            f"Confidence: {int(confidence * 100)}%\n"
            f"Try: `Send 50 USDT to Alice` or type /help",
            parse_mode="Markdown"
        )


# ===================================================
#  /undo — cancel last send within undo window
# ===================================================
async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    token = USER_TOKENS.get(update.effective_user.id)
    if not token:
        await em.reply_text("Link your account first: `/start NLTX-…`", parse_mode="Markdown")
        return

    tid = None
    if context.args:
        tid = context.args[0].strip()
    else:
        tid = LAST_TX.get(update.effective_user.id)

    if not tid:
        await em.reply_text(
            "No transaction id. Right after a send, use `/undo`, or `/undo <transaction_id>`."
        )
        return

    res = await api_call("post", f"/api/transactions/undo/{tid}", token=token)
    if res.get("_http_error") or res.get("error"):
        err = res.get("error", res.get("detail", str(res)))
        await em.reply_text(f"Could not undo: {err}")
    else:
        await em.reply_text(res.get("message", "Transaction undone."))


# ===================================================
#  CALLBACK HANDLER (Button clicks)
# ===================================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "balance":
        await balance_command(update, context)
    elif data == "prices":
        context.args = ["ETH"]
        await price_command(update, context)
    elif data == "history":
        await history_command(update, context)
    elif data == "limits":
        await limits_command(update, context)
    elif data == "cancel_tx":
        await query.edit_message_text("❌ Transaction cancelled.")
    elif data.startswith("cs:"):
        pid = data[3:]
        pending = PENDING_SEND.pop(pid, None)
        if not pending:
            await query.edit_message_text("⏱ This confirmation expired. Send your payment again.")
            return

        tg_uid = update.effective_user.id
        jwt_tok = USER_TOKENS.get(tg_uid)
        if not jwt_tok:
            await query.edit_message_text(
                "❌ Link your NLTX account first: web app → Settings → Telegram code, then `/start NLTX-…`"
            )
            return

        body = {
            "amount": pending["amount"],
            "token": pending["token"],
            "network": pending["network"],
            "memo": pending.get("memo"),
            "confirmed": True,
        }
        if pending.get("to_address"):
            body["to_address"] = pending["to_address"]
        if pending.get("to_username"):
            body["to_username"] = pending["to_username"]

        res = await api_call("post", "/api/transactions/send", data=body, token=jwt_tok)
        if res.get("transaction_id"):
            LAST_TX[tg_uid] = res["transaction_id"]
            gas = res.get("gas_usd", 0)
            th = res.get("tx_hash", "")
            await query.edit_message_text(
                f"✅ *Sent*\n\n"
                f"`{pending['amount']} {pending['token']}` → "
                f"`{pending.get('to_address') or pending.get('to_username')}`\n"
                f"Network: `{pending['network']}`\n"
                f"Gas: ~${gas}\n"
                f"Hash: `{th}`\n\n"
                f"⏱ Undo within *{settings.UNDO_WINDOW_SECONDS}s*: `/undo`",
                parse_mode="Markdown",
            )
        else:
            err = res.get("error", res.get("detail", str(res)))
            if "2FA" in str(err).upper():
                err = f"{err} Complete 2FA in the web app, or use OTP in API."
            await query.edit_message_text(f"❌ *Send failed*\n\n`{err}`", parse_mode="Markdown")


# ===================================================
#  BOT RUNNER
# ===================================================
def run_telegram_bot():
    if not settings.TELEGRAM_BOT_TOKEN or "your-telegram" in settings.TELEGRAM_BOT_TOKEN:
        logger.warning("⚠️  Telegram bot token not configured. Add TELEGRAM_BOT_TOKEN to .env")
        print("⚠️  Telegram bot skipped — no token in .env")
        return

    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("limits", limits_command))
    app.add_handler(CommandHandler("undo", undo_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 NLTX Telegram Bot is running... Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_telegram_bot()
