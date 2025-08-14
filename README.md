# BloomBot Telegram Bridge (Solana)

Trade selected Solana tokens via Telegram and receive real-time buy/sell notifications. This project provides:

- A Telegram bot for commands like `/buy`, `/sell`, `/balance`.
- A BloomBot HTTP client abstraction for executing trades via `https://solana.bloombot.app`.
- A FastAPI server to receive real-time trade webhooks and forward them to Telegram.
- Single entrypoint to run both the bot and the webhook server.

> Note: BloomBot public API endpoints and webhook formats may vary. This project exposes a configurable client and webhook handler. Start in dry-run mode and adapt the endpoint paths and payloads in `app/bloombot_client.py` and `app/webhook_server.py` to match your account or provider docs.

## 1) Prerequisites

- Python 3.10+
- A Telegram bot token from `@BotFather`
- (Optional) A public HTTPS URL to receive webhooks (use Cloudflare Tunnel, Nginx, Caddy, or a VPS)

## 2) Installation

```bash
cd /workspace
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3) Configure environment

Copy `.env.example` to `.env` and fill in values:

```bash
cp .env.example .env
```

Edit `.env`:

- `TELEGRAM_BOT_TOKEN`: Bot token from BotFather
- `TELEGRAM_ALLOWED_CHAT_IDS`: Optional comma-separated chat IDs allowed to use the bot
- `BLOOMBOT_API_BASE`: Defaults to `https://solana.bloombot.app`
- `BLOOMBOT_API_KEY`: Your API key or bearer token (if required)
- `BLOOMBOT_DRY_RUN`: `true` to simulate trades while wiring things up
- `PUBLIC_BASE_URL`: Your public base URL for webhooks (e.g., `https://example.com`)
- `WEB_SERVER_PORT`: Port to run FastAPI (default `8080`)
- `ALLOWED_TOKENS`: Comma-separated symbols or mints to restrict trading (e.g., `BONK,WIF`). If unset, all tokens allowed.
- `TELEGRAM_WEBHOOK_SECRET`: Optional secret used by Telegram when you enable webhook mode. The server validates `X-Telegram-Bot-Api-Secret-Token`.

## 4) Running

- Polling mode (no public URL needed):

```bash
python main.py
```

- Webhook mode (requires `PUBLIC_BASE_URL`): set `TELEGRAM_MODE=webhook` in `.env` then:

```bash
python main.py
```

The process starts:
- Telegram bot (polling or webhook)
- FastAPI server at `http://0.0.0.0:8080`

## 5) Telegram commands

- `/start` – show help and status
- `/tokens` – show allowed tokens
- `/buy <mint_or_symbol> <amount_sol> [slippage_bps]` – buy token using amount of SOL
- `/sell <mint_or_symbol> <amount_percent>` – sell percent of token position
- `/balance [mint_or_symbol]` – show SOL or specific token balance

Examples:

```text
/buy BONK 0.1 300
/sell BONK 50
/balance
```

## 6) Real-time notifications

BloomBot -> webhook -> FastAPI -> Telegram

- Configure BloomBot to POST trade events to: `${PUBLIC_BASE_URL}${BLOOMBOT_WEBHOOK_PATH}` (default `/bloombot/webhook`).
- If your provider signs webhooks, set `BLOOMBOT_WEBHOOK_SECRET` and ensure it matches their configuration.
- In webhook mode for Telegram updates, set `TELEGRAM_WEBHOOK_SECRET` and ensure your reverse proxy preserves the `X-Telegram-Bot-Api-Secret-Token` header.

## 7) Adapting to provider endpoints

Update `app/bloombot_client.py` endpoints and request bodies to match your account. The client is centralized, making future changes minimal. If BloomBot exposes a different payload for webhooks, adjust `app/webhook_server.py` in one place.

## 8) Systemd (optional)

Create `/etc/systemd/system/bloombot-bridge.service`:

```ini
[Unit]
Description=BloomBot Telegram Bridge
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/workspace
EnvironmentFile=/workspace/.env
ExecStart=/workspace/.venv/bin/python /workspace/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bloombot-bridge
```

## 9) Troubleshooting

- Start in `BLOOMBOT_DRY_RUN=true` to validate commands and notifications.
- Enable logs and inspect output. Adjust endpoint paths in the client to match your provider.
- For webhook mode, confirm your URL is reachable and TLS is valid. Use `curl` to test.

## 10) Security

- Restrict access via `TELEGRAM_ALLOWED_CHAT_IDS` and `ALLOWED_TOKENS`.
- Never commit `.env`.
- Treat `BLOOMBOT_API_KEY` and webhook secrets as highly sensitive.
