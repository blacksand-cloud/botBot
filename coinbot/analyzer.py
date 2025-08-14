from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .config import RootConfig
from .storage import Database
from .fetchers.dexscreener import DexscreenerFetcher
from .fetchers.pumpfun import PumpFunFetcher


class Analyzer:
	def __init__(self, config: RootConfig, db: Database) -> None:
		self.config = config
		self.db = db

	async def run_once(self) -> None:
		# Fetch from sources (Dexscreener search based on watchlist)
		logging.info("Starting analysis pass")
		now_ts = int(time.time())
		await self._fetch_from_dexscreener(now_ts)
		if self.config.sources_pumpfun.enabled:
			await self._fetch_from_pumpfun(now_ts)
		logging.info("Analysis pass complete")

	async def _fetch_from_dexscreener(self, now_ts: int) -> None:
		async with DexscreenerFetcher(
			timeout_seconds=self.config.sources_dexscreener.timeout_seconds,
			max_retries=self.config.sources_dexscreener.max_retries,
		) as dex:
			for query in self.config.watchlist_queries:
				pairs = await dex.search(query)
				for pair in pairs:
					try:
						await self._ingest_dex_pair(pair, now_ts)
					except Exception as e:
						logging.debug(f"Failed to ingest pair: {e}")

	async def _ingest_dex_pair(self, pair: Dict[str, Any], now_ts: int) -> None:
		# Example pair keys per Dexscreener: chainId, pairAddress, baseToken { address, symbol, name }, quoteToken, priceUsd, liquidity { usd }, volume { h24 }, dexId
		chain = str(pair.get("chainId") or "")
		base = pair.get("baseToken") or {}
		token_address = base.get("address") or ""
		if not chain or not token_address:
			return
		token_symbol = base.get("symbol")
		token_name = base.get("name")
		token_id = await self.db.upsert_token(chain=chain, token_address=token_address, symbol=token_symbol, name=token_name, first_seen_ts=now_ts)

		pair_address = pair.get("pairAddress")
		dex_id = pair.get("dexId")
		quote = pair.get("quoteToken") or {}
		pair_id = await self.db.upsert_pair(
			token_id=token_id,
			dex_id=dex_id,
			pair_address=pair_address,
			base_symbol=token_symbol,
			quote_symbol=quote.get("symbol"),
		)

		price_usd = _safe_float(pair.get("priceUsd"))
		liquidity_usd = _safe_float(((pair.get("liquidity") or {}).get("usd")))
		volume_24h_usd = _safe_float(((pair.get("volume") or {}).get("h24")))
		holders = None  # Dexscreener does not provide holders
		source = "dexscreener"
		await self.db.insert_snapshot(
			token_id=token_id,
			pair_id=pair_id,
			ts=now_ts,
			price_usd=price_usd,
			liquidity_usd=liquidity_usd,
			volume_24h_usd=volume_24h_usd,
			holders=holders,
			source=source,
			payload=pair,
		)

		await self._detect_events(token_id, now_ts)

	async def _fetch_from_pumpfun(self, now_ts: int) -> None:
		async with PumpFunFetcher(
			base_url=self.config.sources_pumpfun.base_url,
			timeout_seconds=self.config.sources_pumpfun.timeout_seconds,
		) as pf:
			tokens = await pf.recent_tokens(limit=50)
			for t in tokens:
				try:
					await self._ingest_pump_token(t, now_ts)
				except Exception as e:
					logging.debug(f"Failed to ingest pump token: {e}")

	async def _ingest_pump_token(self, token: Dict[str, Any], now_ts: int) -> None:
		# This depends on the actual Pump.fun API response shape. Using common Solana fields as placeholders.
		chain = "solana"
		token_address = token.get("mint") or token.get("address") or ""
		if not token_address:
			return
		symbol = token.get("symbol") or token.get("ticker")
		name = token.get("name")
		token_id = await self.db.upsert_token(chain=chain, token_address=token_address, symbol=symbol, name=name, first_seen_ts=now_ts)
		price_usd = _safe_float(token.get("priceUsd") or token.get("price_usd"))
		liquidity_usd = _safe_float(token.get("liquidityUsd") or token.get("liquidity_usd"))
		volume_24h_usd = _safe_float(token.get("volume24hUsd") or token.get("volume_24h_usd"))
		holders = token.get("holders")
		await self.db.insert_snapshot(
			token_id=token_id,
			pair_id=None,
			ts=now_ts,
			price_usd=price_usd,
			liquidity_usd=liquidity_usd,
			volume_24h_usd=volume_24h_usd,
			holders=holders,
			source="pumpfun",
			payload=token,
		)
		await self._detect_events(token_id, now_ts)

	async def _detect_events(self, token_id: int, now_ts: int) -> None:
		thr = self.config.thresholds
		# Look back over windows
		pump_since = now_ts - thr.pump_window_minutes * 60
		rug_since = now_ts - thr.rug_window_minutes * 60
		recent = await self.db.recent_snapshots(token_id=token_id, since_ts=min(pump_since, rug_since))
		if len(recent) < 2:
			return
		prices = [r["price_usd"] for r in recent if r["price_usd"] is not None]
		lq = [r["liquidity_usd"] for r in recent if r["liquidity_usd"] is not None]
		vols = [r["volume_24h_usd"] for r in recent if r["volume_24h_usd"] is not None]

		# Pump detection: compare last to first in window
		pump_recent = [r for r in recent if r["ts"] >= pump_since]
		if len(pump_recent) >= 2:
			first = next((r for r in pump_recent if r["price_usd"] is not None), None)
			last = next((r for r in reversed(pump_recent) if r["price_usd"] is not None), None)
			if first and last and first["price_usd"] and last["price_usd"] and first["price_usd"] > 0:
				pct = (last["price_usd"] - first["price_usd"]) / first["price_usd"] * 100
				if pct >= thr.pump_percent_increase:
					await self.db.insert_event(token_id, now_ts, "pump", {"percent_increase": pct})
					logging.info(f"Pump detected token={token_id} +{pct:.1f}%")

		# Rug detection: large price and liquidity drop
		rug_recent = [r for r in recent if r["ts"] >= rug_since]
		if len(rug_recent) >= 2:
			max_price = max((r["price_usd"] or 0) for r in rug_recent)
			last_price = next((r["price_usd"] for r in reversed(rug_recent) if r["price_usd"] is not None), None)
			max_lq = max((r["liquidity_usd"] or 0) for r in rug_recent)
			last_lq = next((r["liquidity_usd"] for r in reversed(rug_recent) if r["liquidity_usd"] is not None), None)
			price_drop = None
			lq_drop = None
			if max_price and last_price is not None and max_price > 0:
				price_drop = (max_price - last_price) / max_price * 100
			if max_lq and last_lq is not None and max_lq > 0:
				lq_drop = (max_lq - last_lq) / max_lq * 100
			if (price_drop or 0) >= thr.rug_percent_drop and (lq_drop or 0) >= thr.rug_liquidity_drop_percent:
				await self.db.insert_event(token_id, now_ts, "rug", {"price_drop": price_drop, "liquidity_drop": lq_drop})
				logging.info(f"Rug detected token={token_id} price_drop={price_drop:.1f}% lq_drop={lq_drop:.1f}%")

		# Tier-1 heuristic: using last snapshot values
		last = recent[-1]
		if (last.get("liquidity_usd") or 0) >= thr.tier1_min_liquidity_usd and (last.get("volume_24h_usd") or 0) >= thr.tier1_min_volume_24h_usd:
			await self.db.insert_event(token_id, now_ts, "tier1", {"liquidity_usd": last.get("liquidity_usd"), "volume_24h_usd": last.get("volume_24h_usd")})
			logging.info(f"Tier-1 candidate token={token_id}")

		# CEX listing: placeholder, requires external signals
		# Hook here to integrate with external APIs or announcement feeds


def _safe_float(val: Any) -> Optional[float]:
	try:
		if val is None:
			return None
		return float(val)
	except Exception:
		return None