import argparse
import asyncio
import logging
import os

from coinbot.config import load_config
from coinbot.storage import Database
from coinbot.analyzer import Analyzer


async def cmd_init_db(config_path: str) -> None:
	config = load_config(config_path)
	db = Database(config.storage.sqlite_path)
	await db.initialize()
	await db.close()
	print(f"Initialized DB at {config.storage.sqlite_path}")


async def cmd_run_once(config_path: str) -> None:
	config = load_config(config_path)
	logging.basicConfig(level=getattr(logging, config.app.log_level.upper(), logging.INFO))
	db = Database(config.storage.sqlite_path)
	await db.initialize()
	analyzer = Analyzer(config=config, db=db)
	await analyzer.run_once()
	await db.close()


async def cmd_run_loop(config_path: str) -> None:
	config = load_config(config_path)
	logging.basicConfig(level=getattr(logging, config.app.log_level.upper(), logging.INFO))
	db = Database(config.storage.sqlite_path)
	await db.initialize()
	analyzer = Analyzer(config=config, db=db)
	try:
		while True:
			await analyzer.run_once()
			await asyncio.sleep(config.app.loop_interval_seconds)
	finally:
		await db.close()


def main() -> None:
	parser = argparse.ArgumentParser(description="Coin Pattern Bot")
	parser.add_argument("command", choices=["init-db", "run-once", "run-loop"]) 
	parser.add_argument("--config", default="/workspace/config.yaml")
	args = parser.parse_args()

	if args.command == "init-db":
		asyncio.run(cmd_init_db(args.config))
	elif args.command == "run-once":
		asyncio.run(cmd_run_once(args.config))
	elif args.command == "run-loop":
		asyncio.run(cmd_run_loop(args.config))


if __name__ == "__main__":
	main()