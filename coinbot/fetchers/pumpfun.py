from __future__ import annotations

import aiohttp
import logging
from typing import Any, Dict, List, Optional


class PumpFunFetcher:
	def __init__(self, base_url: str, timeout_seconds: int) -> None:
		self._base_url = base_url.rstrip("/")
		self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
		self._session: Optional[aiohttp.ClientSession] = None

	async def __aenter__(self) -> "PumpFunFetcher":
		self._session = aiohttp.ClientSession(timeout=self._timeout)
		return self

	async def __aexit__(self, exc_type, exc, tb) -> None:
		if self._session:
			await self._session.close()
			self._session = None

	def _get_session(self) -> aiohttp.ClientSession:
		assert self._session is not None, "Fetcher session not started"
		return self._session

	async def recent_tokens(self, limit: int = 50) -> List[Dict[str, Any]]:
		if not self._base_url:
			logging.info("Pump.fun fetcher disabled (no base_url)")
			return []
		url = f"{self._base_url}/recent?limit={limit}"
		try:
			async with self._get_session().get(url) as resp:
				resp.raise_for_status()
				return await resp.json()
		except Exception as e:
			logging.warning(f"Pump.fun recent tokens failed: {e}")
			return []