import asyncio
import logging
from dotenv import load_dotenv

from app.config import AppConfig
from app.telegram_bot import build_application
from app.webhook_server import create_app, setup_telegram_webhook
import uvicorn


logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("main")


async def start_uvicorn(fastapi_app, app_config: AppConfig):
	config = uvicorn.Config(app=fastapi_app, host=app_config.web_server_host, port=app_config.web_server_port, log_level="info")
	server = uvicorn.Server(config)
	logger.info("Starting FastAPI server on %s:%s", app_config.web_server_host, app_config.web_server_port)
	await server.serve()


async def start_telegram(application, app_config: AppConfig):
	if app_config.telegram_mode == "webhook":
		assert app_config.public_base_url, "PUBLIC_BASE_URL must be set for webhook mode"
		await application.initialize()
		await application.start()
		await setup_telegram_webhook(application, app_config)
		logger.info("Telegram webhook configured: %s%s", app_config.public_base_url, app_config.telegram_webhook_path)
		while True:
			await asyncio.sleep(3600)
	else:
		logger.info("Starting Telegram polling mode")
		await application.run_polling(close_loop=False, drop_pending_updates=True)


async def main_async():
	load_dotenv(override=True)
	app_config = AppConfig.from_env()

	# Build Telegram app first
	telegram_application = await build_application(app_config)

	# Create FastAPI and inject Telegram application
	fastapi_app = create_app(app_config, telegram_application)

	await asyncio.gather(
		start_uvicorn(fastapi_app, app_config),
		start_telegram(telegram_application, app_config),
	)


if __name__ == "__main__":
	try:
		asyncio.run(main_async())
	except (KeyboardInterrupt, SystemExit):
		logger.info("Shutdown requested. Bye!")