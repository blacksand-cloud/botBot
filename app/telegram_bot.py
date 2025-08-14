from __future__ import annotations

import logging
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from .config import AppConfig
from .bloombot_client import BloomBotClient


logger = logging.getLogger("telegram")


def _is_allowed(app_config: AppConfig, chat_id: int) -> bool:
	if not app_config.telegram_allowed_chat_ids:
		return True
	return chat_id in app_config.telegram_allowed_chat_ids


def _is_token_allowed(app_config: AppConfig, token: str) -> bool:
	if not app_config.allowed_tokens:
		return True
	return token.lower() in app_config.allowed_tokens


async def _reply(update: Update, text: str):
	if update.effective_chat:
		await update.effective_chat.send_message(text=text, parse_mode=ParseMode.MARKDOWN)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	app_config: AppConfig = context.application.bot_data["app_config"]
	if not _is_allowed(app_config, update.effective_chat.id if update.effective_chat else 0):
		return
	await _reply(update, "BloomBot bridge is online. Use /buy, /sell, /balance. Use /tokens to list allowed tokens.")


async def tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	app_config: AppConfig = context.application.bot_data["app_config"]
	if not _is_allowed(app_config, update.effective_chat.id if update.effective_chat else 0):
		return
	if not app_config.allowed_tokens:
		await _reply(update, "No token allowlist is configured. All tokens are allowed.")
		return
	await _reply(update, "Allowed tokens:\n- " + "\n- ".join(sorted({t.upper() for t in app_config.allowed_tokens})))


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	app_config: AppConfig = context.application.bot_data["app_config"]
	if not _is_allowed(app_config, update.effective_chat.id if update.effective_chat else 0):
		return
	if len(context.args) < 2:
		await _reply(update, "Usage: /buy <mint_or_symbol> <amount_sol> [slippage_bps]")
		return
	symbol_or_mint = context.args[0]
	if not _is_token_allowed(app_config, symbol_or_mint):
		await _reply(update, "This token is not in the allowed list. Use /tokens to see allowed tokens.")
		return
	try:
		amount_sol = float(context.args[1])
	except ValueError:
		await _reply(update, "amount_sol must be a number")
		return
	slippage_bps: Optional[int] = None
	if len(context.args) >= 3:
		try:
			slippage_bps = int(context.args[2])
		except ValueError:
			await _reply(update, "slippage_bps must be an integer")
			return

	client = context.application.bot_data["bloombot_client"]
	await _reply(update, f"Placing BUY for `{symbol_or_mint}`: `{amount_sol}` SOL...")
	result = await client.buy_token(symbol_or_mint, amount_sol, slippage_bps)
	if result.ok:
		await _reply(update, f"✅ BUY OK: {result.message}\nTx: `{result.tx_signature or 'n/a'}`")
	else:
		await _reply(update, f"❌ BUY FAILED: {result.message}")


async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	app_config: AppConfig = context.application.bot_data["app_config"]
	if not _is_allowed(app_config, update.effective_chat.id if update.effective_chat else 0):
		return
	if len(context.args) < 2:
		await _reply(update, "Usage: /sell <mint_or_symbol> <amount_percent>")
		return
	symbol_or_mint = context.args[0]
	if not _is_token_allowed(app_config, symbol_or_mint):
		await _reply(update, "This token is not in the allowed list. Use /tokens to see allowed tokens.")
		return
	try:
		amount_percent = float(context.args[1])
	except ValueError:
		await _reply(update, "amount_percent must be a number")
		return

	client = context.application.bot_data["bloombot_client"]
	await _reply(update, f"Placing SELL for `{symbol_or_mint}`: `{amount_percent}%`...")
	result = await client.sell_token(symbol_or_mint, amount_percent)
	if result.ok:
		await _reply(update, f"✅ SELL OK: {result.message}\nTx: `{result.tx_signature or 'n/a'}`")
	else:
		await _reply(update, f"❌ SELL FAILED: {result.message}")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	app_config: AppConfig = context.application.bot_data["app_config"]
	if not _is_allowed(app_config, update.effective_chat.id if update.effective_chat else 0):
		return
	symbol_or_mint = context.args[0] if len(context.args) >= 1 else None
	client = context.application.bot_data["bloombot_client"]
	data = await client.get_balance(symbol_or_mint)
	if "error" in data:
		await _reply(update, f"❌ BALANCE FAILED: {data['error']}")
		return
	lines = ["Balance:"]
	for k, v in data.items():
		lines.append(f"- {k}: {v}")
	await _reply(update, "\n".join(lines))


async def build_application(app_config: AppConfig) -> Application:
	application = (
		ApplicationBuilder()
		.token(app_config.telegram_bot_token)
		.rate_limiter(None)
		.build()
	)

	application.bot_data["app_config"] = app_config
	application.bot_data["bloombot_client"] = BloomBotClient(app_config)

	application.add_handler(CommandHandler("start", start_command))
	application.add_handler(CommandHandler("tokens", tokens_command))
	application.add_handler(CommandHandler("buy", buy_command))
	application.add_handler(CommandHandler("sell", sell_command))
	application.add_handler(CommandHandler("balance", balance_command))

	return application