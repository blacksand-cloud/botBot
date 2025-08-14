from __future__ import annotations

from dataclasses import dataclass
from typing import List

import yaml


@dataclass
class AppConfig:
	loop_interval_seconds: int
	log_level: str
	chains: List[str]


@dataclass
class DexscreenerConfig:
	max_retries: int
	timeout_seconds: int
	use_token_lookup: bool


@dataclass
class PumpFunConfig:
	base_url: str
	timeout_seconds: int
	enabled: bool


@dataclass
class ThresholdsConfig:
	pump_percent_increase: float
	pump_window_minutes: int
	rug_percent_drop: float
	rug_liquidity_drop_percent: float
	rug_window_minutes: int
	tier1_min_liquidity_usd: float
	tier1_min_volume_24h_usd: float


@dataclass
class StorageConfig:
	sqlite_path: str


@dataclass
class RootConfig:
	app: AppConfig
	sources_dexscreener: DexscreenerConfig
	sources_pumpfun: PumpFunConfig
	thresholds: ThresholdsConfig
	storage: StorageConfig
	watchlist_queries: List[str]


def load_config(path: str) -> RootConfig:
	with open(path, "r") as f:
		cfg = yaml.safe_load(f)
	app = AppConfig(**cfg["app"]) 
	dex = DexscreenerConfig(**cfg["sources"]["dexscreener"]) 
	pump = PumpFunConfig(**cfg["sources"]["pumpfun"]) 
	thr = ThresholdsConfig(**cfg["thresholds"]) 
	storage = StorageConfig(**cfg["storage"]) 
	queries = cfg.get("watchlist", {}).get("queries", [])
	return RootConfig(
		app=app,
		sources_dexscreener=dex,
		sources_pumpfun=pump,
		thresholds=thr,
		storage=storage,
		watchlist_queries=queries,
	)