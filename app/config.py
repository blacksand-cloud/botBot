from __future__ import annotations

from dataclasses import dataclass
import os
from typing import List, Optional


def _split_csv(value: str | None) -> List[int] | None:
	if not value:
		return None
	items: List[int] = []
	for part in value.split(","):
		part = part.strip()
		if not part:
			continue
		try:
			items.append(int(part))
		except ValueError:
			continue
	return items or None


def _split_csv_str(value: str | None) -> List[str] | None:
	if not value:
		return None
	items: List[str] = []
	for part in value.split(","):
		part = part.strip()
		if part:
			items.append(part)
	return [s for s in items] or None


@dataclass
class AppConfig:
	telegram_bot_token: str
	telegram_allowed_chat_ids: Optional[List[int]]
	telegram_mode: str
	telegram_webhook_path: str
	telegram_webhook_secret: Optional[str]

	bloombot_api_base: str
	bloombot_api_key: Optional[str]
	bloombot_dry_run: bool

	public_base_url: Optional[str]
	web_server_host: str
	web_server_port: int

	bloombot_webhook_path: str
	bloombot_webhook_secret: Optional[str]

	default_slippage_bps: int
	default_priority_fee_lamports: int

	allowed_tokens: Optional[List[str]]

	@staticmethod
	def from_env() -> "AppConfig":
		telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
		if not telegram_bot_token:
			raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

		telegram_allowed_chat_ids = _split_csv(os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS"))
		telegram_mode = os.environ.get("TELEGRAM_MODE", "polling").strip().lower()
		telegram_webhook_path = os.environ.get("TELEGRAM_WEBHOOK_PATH", "/telegram/webhook").strip()
		telegram_webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")

		bloombot_api_base = os.environ.get("BLOOMBOT_API_BASE", "https://solana.bloombot.app").rstrip("/")
		bloombot_api_key = os.environ.get("BLOOMBOT_API_KEY")
		bloombot_dry_run = os.environ.get("BLOOMBOT_DRY_RUN", "true").strip().lower() == "true"

		public_base_url = os.environ.get("PUBLIC_BASE_URL")
		web_server_host = os.environ.get("WEB_SERVER_HOST", "0.0.0.0")
		web_server_port = int(os.environ.get("WEB_SERVER_PORT", "8080"))

		bloombot_webhook_path = os.environ.get("BLOOMBOT_WEBHOOK_PATH", "/bloombot/webhook").strip()
		bloombot_webhook_secret = os.environ.get("BLOOMBOT_WEBHOOK_SECRET")

		default_slippage_bps = int(os.environ.get("DEFAULT_SLIPPAGE_BPS", "300"))
		default_priority_fee_lamports = int(os.environ.get("DEFAULT_PRIORITY_FEE_LAMPORTS", "0"))

		allowed_tokens = _split_csv_str(os.environ.get("ALLOWED_TOKENS"))
		if allowed_tokens:
			allowed_tokens = [t.lower() for t in allowed_tokens]

		return AppConfig(
			telegram_bot_token=telegram_bot_token,
			telegram_allowed_chat_ids=telegram_allowed_chat_ids,
			telegram_mode=telegram_mode,
			telegram_webhook_path=telegram_webhook_path,
			telegram_webhook_secret=telegram_webhook_secret,
			bloombot_api_base=bloombot_api_base,
			bloombot_api_key=bloombot_api_key,
			bloombot_dry_run=bloombot_dry_run,
			public_base_url=public_base_url,
			web_server_host=web_server_host,
			web_server_port=web_server_port,
			bloombot_webhook_path=bloombot_webhook_path,
			bloombot_webhook_secret=bloombot_webhook_secret,
			default_slippage_bps=default_slippage_bps,
			default_priority_fee_lamports=default_priority_fee_lamports,
			allowed_tokens=allowed_tokens,
		)