from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application

from .config import AppConfig


logger = logging.getLogger("webhook")


def _validate_signature(secret: Optional[str], payload: bytes, signature: Optional[str]) -> bool:
	if not secret:
		return True
	if not signature:
		return False
	mac = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
	return hmac.compare_digest(mac, signature)


def create_app(app_config: AppConfig, application: Optional[Application] = None) -> FastAPI:
	app = FastAPI()
	# Attach application for outbound notifications and Telegram update processing
	app.state.telegram_application = application

	@app.get("/healthz")
	async def health() -> Dict[str, str]:
		return {"status": "ok"}

	@app.post(app_config.bloombot_webhook_path)
	async def bloombot_webhook(request: Request, x_signature: Optional[str] = Header(default=None)) -> JSONResponse:
		raw = await request.body()
		if not _validate_signature(app_config.bloombot_webhook_secret, raw, x_signature):
			raise HTTPException(status_code=401, detail="invalid signature")
		try:
			event = json.loads(raw.decode("utf-8"))
		except Exception:
			raise HTTPException(status_code=400, detail="invalid json")

		# Forward to Telegram if bot application is present
		if app.state.telegram_application:
			try:
				chat_ids = app_config.telegram_allowed_chat_ids
				message = _format_trade_event(event)
				if not chat_ids:
					logger.warning("No TELEGRAM_ALLOWED_CHAT_IDS set; skipping outbound notifications.")
				else:
					for chat_id in chat_ids:
						await app.state.telegram_application.bot.send_message(chat_id=chat_id, text=message)
			except Exception as e:
				logger.exception("Failed to forward webhook to Telegram: %s", e)
		return JSONResponse({"ok": True})

	# Telegram webhook endpoint (optional if using polling)
	@app.post(app_config.telegram_webhook_path)
	async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: Optional[str] = Header(default=None)) -> JSONResponse:
		if not app.state.telegram_application:
			raise HTTPException(status_code=503, detail="telegram application not ready")
		if app_config.telegram_webhook_secret:
			if x_telegram_bot_api_secret_token != app_config.telegram_webhook_secret:
				raise HTTPException(status_code=401, detail="invalid telegram secret token")
		try:
			payload = await request.json()
		except Exception:
			raise HTTPException(status_code=400, detail="invalid json")
		try:
			update = Update.de_json(payload, app.state.telegram_application.bot)
			await app.state.telegram_application.process_update(update)
		except Exception as e:
			logger.exception("Failed to process Telegram update: %s", e)
			raise HTTPException(status_code=500, detail="processing error")
		return JSONResponse({"ok": True})

	return app


def _format_trade_event(event: Dict[str, Any]) -> str:
	side = event.get("side", "?").upper()
	token = event.get("token") or event.get("mint") or "?"
	amount = event.get("amount")
	unit = event.get("amount_unit", "")
	signature = event.get("signature") or event.get("tx") or "n/a"
	price = event.get("price")

	parts = [f"{side} {token}"]
	if amount is not None:
		parts.append(f"amount: {amount}{(' ' + unit) if unit else ''}")
	if price is not None:
		parts.append(f"price: {price}")
	parts.append(f"tx: {signature}")
	return " | ".join(parts)


async def setup_telegram_webhook(application: Application, app_config: AppConfig) -> None:
	assert app_config.public_base_url
	url = f"{app_config.public_base_url}{app_config.telegram_webhook_path}"
	await application.bot.set_webhook(url=url, allowed_updates=["message", "callback_query"], secret_token=app_config.telegram_webhook_secret or None)