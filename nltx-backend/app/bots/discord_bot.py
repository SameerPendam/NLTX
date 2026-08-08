"""
NLTX Discord Bot
Slash commands + Natural Language message parsing
Commands:
  !nltx send <amount> <token> to <user>
  !nltx balance
  !nltx price <token>
  !nltx history
  !nltx help
"""
import discord
import json
import logging
import asyncio
from discord.ext import commands
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.config import get_settings
from app.services.nlp_service import get_nlp_service
import aiohttp

API_BASE = f"http://localhost:{get_settings().API_PORT}"

logger = logging.getLogger(__name__)
settings = get_settings()

USER_TOKENS: dict = {}
LAST_TX: dict = {}


def _network_for_token(tok: str) -> str:
    t = (tok or "USDT").upper()
    if t == "ETH":
        return "ethereum"
    if t == "MATIC":
        return "polygon"
    if t == "SOL":
        return "solana"
    return "polygon"


def _discord_recipient(recipient: str) -> tuple:
    r = (recipient or "").strip()
    if r.startswith("0x") and len(r) == 42:
        return "address", r
    return "username", r.lstrip("@").lower()


async def nltx_request(method: str, path: str, *, json_body=None, token: str = None) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    m = method.lower()
    async with aiohttp.ClientSession() as session:
        fn = getattr(session, m)
        kw = {"headers": headers}
        if json_body is not None:
            kw["json"] = json_body
        async with fn(f"{API_BASE}{path}", **kw) as resp:
            text = await resp.text()
            try:
                body = json.loads(text) if text else {}
            except json.JSONDecodeError:
                body = {"detail": text}
            if resp.status >= 400:
                err = body.get("detail", body)
                return {"_http_error": True, "status_code": resp.status, "error": err, **body}
            return body

# ===================================================
#  BOT SETUP
# ===================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!nltx ", intents=intents, help_command=None)


# ===================================================
#  EVENTS
# ===================================================
@bot.event
async def on_ready():
    print(f"✅ NLTX Discord Bot connected as {bot.user}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="for NLP commands | !nltx help"
        )
    )


@bot.event
async def on_message(message: discord.Message):
    """Process commands; also run NLP on plain messages mentioning the bot."""
    if message.author.bot:
        return
    await bot.process_commands(message)

    # If bot is @mentioned, treat message as NLP command
    if bot.user in message.mentions:
        text = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        if text.startswith("NLTX-"):
            await verify_code(message, text)
        elif text:
            await process_nlp_message(message, text)
    
    # Detect code even without mention (optional, safer with mention)
    elif message.content.startswith("NLTX-"):
        await verify_code(message, message.content.strip())

async def verify_code(message, code):
    """Call backend to verify linking code."""
    payload = {
        "platform": "discord",
        "code": code,
        "platform_id": str(message.author.id),
        "platform_username": message.author.name,
    }
    data = await nltx_request("POST", "/api/users/platform/link-verify", json_body=payload)
    if not data.get("_http_error"):
        if data.get("access_token"):
            USER_TOKENS[message.author.id] = data["access_token"]
        await message.reply(
            embed=make_embed(
                "✅ Account Linked",
                "Your Discord is paired with NLTX. You can use balance, send, and history.",
                color=0x10b981,
            )
        )
    else:
        await message.reply(
            embed=make_embed(
                "❌ Error",
                f"Linking failed: {data.get('error', 'Invalid code')}",
                color=0xef4444,
            )
        )


# ===================================================
#  HELPER EMBED BUILDER
# ===================================================
def make_embed(title: str, description: str, color: int = 0x7c3aed, fields: list = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="NLTX · Natural Language Transaction Exchange")
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    return embed


# ===================================================
#  !nltx help
# ===================================================
@bot.command(name="help")
async def help_cmd(ctx):
    embed = make_embed(
        "🤖 NLTX Bot Help",
        "Send crypto using natural language right from Discord!",
        fields=[
            ("💬 Natural Language", 
             "Just @mention me:\n`@NLTX Send 50 USDT to @alice`\n`@NLTX What's my ETH balance?`\n`@NLTX Price of Bitcoin`",
             False),
            ("📌 Commands",
             "`!nltx send <amt> <token> to <user>` — Send crypto\n"
             "`!nltx balance` — View portfolio\n"
             "`!nltx price <token>` — Live price\n"
             "`!nltx history` — Recent transactions\n"
             "`!nltx limits` — Spending limits\n"
             "`!nltx undo` — Undo last send (within window)",
             False),
            ("🔒 Security",
             "✅ MPC Wallet Protection\n✅ 30s Undo Window\n✅ Fraud Detection\n✅ Spending Limits",
             False),
        ]
    )
    await ctx.send(embed=embed)


# ===================================================
#  !nltx balance
# ===================================================
@bot.command(name="balance")
async def balance_cmd(ctx):
    token = USER_TOKENS.get(ctx.author.id)
    if token:
        data = await nltx_request("GET", "/api/wallet/balances", token=token)
        if not data.get("_http_error") and data.get("balances"):
            fields = []
            for b in data["balances"][:10]:
                ch = b.get("change_24h", 0)
                emoji = "🟢" if ch >= 0 else "🔴"
                fields.append(
                    (
                        f"{b['token']} ({b['network']})",
                        f"{b['balance']:.4f} ≈ ${b['usd_value']:,.2f} {emoji}",
                        False,
                    )
                )
            fields.append(("Total", f"${data.get('total_usd', 0):,.2f}", False))
            embed = make_embed("💎 Your Portfolio", "Live balances from NLTX:", color=0x10b981, fields=fields)
            await ctx.send(embed=embed)
            return

    embed = make_embed(
        "💎 Portfolio (Demo)",
        "Use `NLTX-…` link code from the web app to see your real balances.",
        color=0x10b981,
    )
    await ctx.send(embed=embed)


# ===================================================
#  !nltx price <token>
# ===================================================
@bot.command(name="price")
async def price_cmd(ctx, token: str = "ETH"):
    token = token.upper()
    data = await nltx_request("GET", f"/api/wallet/price/{token}")
    if not data.get("_http_error") and data.get("price_usd"):
        change = data.get("change_24h", 0) or 0
        emoji = "📈" if change >= 0 else "📉"
        color = 0x10b981 if change >= 0 else 0xef4444
        embed = make_embed(
            f"{emoji} {token} Price",
            f"**${data['price_usd']:,.2f} USD**",
            color=color,
            fields=[
                ("24h Change", f"{change:+.2f}%", True),
                ("Source", str(data.get("source", "api")), True),
            ],
        )
        await ctx.send(embed=embed)
        return

    prices = {
        "ETH": (2489.0, 2.4), "BTC": (65430.0, 1.8), "SOL": (101.0, -0.8),
        "MATIC": (0.24, 1.1), "USDT": (1.0, 0.0), "USDC": (1.0, 0.0), "BNB": (380.0, 0.5),
    }
    if token not in prices:
        await ctx.send(f"❓ Unknown token `{token}`. Try: ETH, BTC, SOL, MATIC, USDT, BNB")
        return
    price, change = prices[token]
    emoji = "📈" if change >= 0 else "📉"
    color = 0x10b981 if change >= 0 else 0xef4444
    embed = make_embed(
        f"{emoji} {token} Price",
        f"**${price:,.2f} USD**",
        color=color,
        fields=[("24h Change", f"{change:+.2f}%", True), ("Source", "Fallback", True)],
    )
    await ctx.send(embed=embed)


# ===================================================
#  !nltx history
# ===================================================
@bot.command(name="history")
async def history_cmd(ctx):
    token = USER_TOKENS.get(ctx.author.id)
    if token:
        data = await nltx_request("GET", "/api/transactions/?limit=5", token=token)
        if not data.get("_http_error") and data.get("transactions"):
            fields = []
            for tx in data["transactions"][:5]:
                to = tx.get("to_username") or str(tx.get("to_address", ""))[:16]
                fields.append(
                    (f"{tx.get('amount')} {tx.get('token')} → {to}", f"{tx.get('status')}", False)
                )
            embed = make_embed("📜 Recent Transactions", "From your NLTX account:", fields=fields)
            await ctx.send(embed=embed)
            return
    await ctx.send(embed=make_embed("📜 History", "Link your account to load transactions.", color=0x7c3aed))


# ===================================================
#  !nltx limits
# ===================================================
@bot.command(name="limits")
async def limits_cmd(ctx):
    token = USER_TOKENS.get(ctx.author.id)
    if token:
        data = await nltx_request("GET", "/api/wallet/spending-limits", token=token)
        if not data.get("_http_error") and "daily_limit" in data:
            embed = make_embed(
                "🔒 Spending Limits",
                "Your NLTX limits:",
                color=0x2563eb,
                fields=[
                    ("Daily", f"${data.get('daily_limit', 0):,.0f} used ${data.get('daily_used', 0):,.0f}", True),
                    ("Monthly", f"${data.get('monthly_limit', 0):,.0f}", True),
                    ("Single TX Max", f"${data.get('single_tx_max', 0):,.0f}", True),
                    ("2FA above", f"${data.get('require_2fa_above', 0):,.0f}", True),
                ],
            )
            await ctx.send(embed=embed)
            return
    await ctx.send(embed=make_embed("🔒 Limits", "Link account to view limits.", color=0x2563eb))


# ===================================================
#  !nltx send <amount> <token> to <recipient>
# ===================================================
@bot.command(name="send")
async def send_cmd(ctx, amount: str = None, token: str = None, to_word: str = None, recipient: str = None):
    if not amount or not token or not recipient:
        await ctx.send("❌ Usage: `!nltx send 50 USDT to alice`")
        return

    author_id = ctx.author.id
    net = _network_for_token(token)

    class ConfirmView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)

        @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != author_id:
                await interaction.response.send_message("Not your transaction.", ephemeral=True)
                return
            jwt = USER_TOKENS.get(author_id)
            if not jwt:
                await interaction.response.send_message(
                    "Link first: mention me with your `NLTX-…` code from the web app.",
                    ephemeral=True,
                )
                return
            try:
                amt_f = float(amount)
            except ValueError:
                await interaction.response.send_message("Invalid amount.", ephemeral=True)
                return
            kind, dest = _discord_recipient(recipient)
            body = {
                "amount": amt_f,
                "token": token.upper(),
                "network": net,
                "confirmed": True,
            }
            if kind == "username":
                body["to_username"] = dest
            else:
                body["to_address"] = dest
            res = await nltx_request("POST", "/api/transactions/send", json_body=body, token=jwt)
            if res.get("transaction_id"):
                LAST_TX[author_id] = res["transaction_id"]
                await interaction.response.edit_message(
                    embed=make_embed(
                        "✅ Sent",
                        f"**{amount} {token.upper()}** → **{recipient}**\n"
                        f"Network: {net}\n"
                        f"Tx: `{res.get('tx_hash', '')}`\n\n"
                        f"Undo: `!nltx undo` within {settings.UNDO_WINDOW_SECONDS}s",
                        color=0x10b981,
                    ),
                    view=None,
                )
            else:
                err = res.get("error", res.get("detail", str(res)))
                await interaction.response.edit_message(
                    embed=make_embed("❌ Send failed", str(err)[:500], color=0xef4444),
                    view=None,
                )
            self.stop()

        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.edit_message(
                embed=make_embed("❌ Cancelled", "Transaction was cancelled.", color=0xef4444),
                view=None,
            )
            self.stop()

    view = ConfirmView()
    embed = make_embed(
        "💸 Transaction Preview",
        "Please review and confirm:",
        color=0xf59e0b,
        fields=[
            ("Amount", f"{amount} {token.upper()}", True),
            ("To", recipient, True),
            ("Network", net, True),
            ("⚠️ Undo", f"{settings.UNDO_WINDOW_SECONDS}s after confirm (`!nltx undo`)", False),
        ],
    )
    await ctx.send(embed=embed, view=view)


@bot.command(name="undo")
async def undo_cmd(ctx):
    jwt = USER_TOKENS.get(ctx.author.id)
    if not jwt:
        await ctx.send("Link your account first.")
        return
    tid = LAST_TX.get(ctx.author.id)
    if not tid:
        await ctx.send("No recent transaction. Usage: `!nltx undo` right after a send.")
        return
    res = await nltx_request("POST", f"/api/transactions/undo/{tid}", token=jwt)
    if res.get("_http_error"):
        await ctx.send(f"Undo failed: {res.get('error')}")
    else:
        await ctx.send(res.get("message", "Undone."))


# ===================================================
#  NLP MESSAGE HANDLER (via @mention)
# ===================================================
async def process_nlp_message(message: discord.Message, text: str):
    nlp = get_nlp_service()
    result = await nlp.parse_command(text)
    intent = result.get("intent", "UNKNOWN")
    entities = result.get("entities", {})

    async with message.channel.typing():
        await asyncio.sleep(0.5)

    if intent == "BALANCE":
        ctx = await bot.get_context(message)
        await balance_cmd(ctx)
    elif intent == "PRICE":
        ctx = await bot.get_context(message)
        await price_cmd(ctx, entities.get("query_token", "ETH"))
    elif intent == "HISTORY":
        ctx = await bot.get_context(message)
        await history_cmd(ctx)
    elif intent == "LIMITS":
        ctx = await bot.get_context(message)
        await limits_cmd(ctx)
    elif intent == "HELP":
        ctx = await bot.get_context(message)
        await help_cmd(ctx)
    elif intent == "SEND":
        amt = entities.get("amount", "?")
        tok = entities.get("token", "USDT")
        to = entities.get("to_username", "?")
        ctx = await bot.get_context(message)
        await send_cmd(ctx, str(amt), tok, "to", to)
    else:
        await message.reply(
            embed=make_embed(
                "🤖 NLTX",
                f"{result.get('response_text', 'Not sure what you meant.')}\n\n"
                f"Confidence: {int(result.get('confidence', 0)*100)}%\n"
                f"Try: @{bot.user.name} Send 50 USDT to @alice",
                color=0x7c3aed
            )
        )


# ===================================================
#  BOT RUNNER
# ===================================================
def run_discord_bot():
    if not settings.DISCORD_BOT_TOKEN or "your-discord" in settings.DISCORD_BOT_TOKEN:
        logger.warning("⚠️  Discord bot token not configured. Add DISCORD_BOT_TOKEN to .env")
        print("⚠️  Discord bot skipped — no token in .env")
        return

    print("🎮 NLTX Discord Bot starting...")
    bot.run(settings.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_discord_bot()
