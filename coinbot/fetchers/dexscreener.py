from __future__ import annotations

import aiohttp
import asyncio
import logging
from typing import Any, Dict, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


DEX_BASE = "https://api.dexscreener.com/latest/dex"


class DexscreenerFetcher:
	def __init__(self, timeout_seconds: int, max_retries: int) -> None:
		self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
		self._session: Optional[aiohttp.ClientSession] = None
		self._max_retries = max_retries

	async def __aenter__(self) -> "DexscreenerFetcher":
		self._session = aiohttp.ClientSession(timeout=self._timeout)
		return self

	async def __aexit__(self, exc_type, exc, tb) -> None:
		if self._session:
			await self._session.close()
			self._session = None

	def _get_session(self) -> aiohttp.ClientSession:
		assert self._session is not None, "Fetcher session not started"
		return self._session

	@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=5), retry=retry_if_exception_type(aiohttp.ClientError))
	async def _get_json(self, url: str) -> Dict[str, Any]:
		session = self._get_session()
		async with session.get(url) as resp:
			resp.raise_for_status()
			return await resp.json()

	async def search(self, query: str) -> List[Dict[str, Any]]:
		# Dexscreener has a search endpoint under /search?q=
		url = f"https://api.dexscreener.com/latest/dex/search?q={query}"
		try:
			data = await self._get_json(url)
			return data.get("pairs", [])
		except Exception as e:
			logging.warning(f"Dexscreener search failed for {query}: {e}")
			return []

	async def pairs_by_token(self, chain: str, token_address: str) -> List[Dict[str, Any]]:
		# /tokens/{chain}/{tokenAddress}
		url = f"{DEX_BASE}/tokens/{chain}/{token_address}"
		try:
			data = await self._get_json(url)
			return data.get("pairs", [])
		except Exception as e:
			logging.debug(f"Dexscreener pairs_by_token failed for {chain}:{token_address}: {e}")
			return []