from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from .config import AppConfig


@dataclass
class TradeResult:
    ok: bool
    message: str
    tx_signature: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class BloomBotClient:
    def __init__(self, config: AppConfig):
        self._config = config
        self._client = httpx.AsyncClient(base_url=config.bloombot_api_base, timeout=20.0)

    async def close(self):
        await self._client.aclose()

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._config.bloombot_api_key:
            headers["Authorization"] = f"Bearer {self._config.bloombot_api_key}"
        return headers

    async def buy_token(self, symbol_or_mint: str, amount_sol: float, slippage_bps: int | None = None) -> TradeResult:
        if self._config.bloombot_dry_run:
            return TradeResult(ok=True, message=f"Simulated BUY {symbol_or_mint} for {amount_sol} SOL @ slippage {slippage_bps or self._config.default_slippage_bps}bps (dry-run)")

        payload = {
            "token": symbol_or_mint,
            "amount_sol": amount_sol,
            "slippage_bps": slippage_bps or self._config.default_slippage_bps,
        }
        # TODO: Replace with actual BloomBot endpoint path and schema
        resp = await self._client.post("/api/trade/buy", json=payload, headers=self._headers())
        if resp.status_code // 100 == 2:
            data = resp.json()
            return TradeResult(ok=True, message="BUY placed", tx_signature=data.get("signature"), data=data)
        return TradeResult(ok=False, message=f"BUY failed: {resp.status_code} {resp.text}")

    async def sell_token(self, symbol_or_mint: str, amount_percent: float) -> TradeResult:
        if self._config.bloombot_dry_run:
            return TradeResult(ok=True, message=f"Simulated SELL {symbol_or_mint} {amount_percent}% (dry-run)")

        payload = {
            "token": symbol_or_mint,
            "percent": amount_percent,
        }
        # TODO: Replace with actual BloomBot endpoint path and schema
        resp = await self._client.post("/api/trade/sell", json=payload, headers=self._headers())
        if resp.status_code // 100 == 2:
            data = resp.json()
            return TradeResult(ok=True, message="SELL placed", tx_signature=data.get("signature"), data=data)
        return TradeResult(ok=False, message=f"SELL failed: {resp.status_code} {resp.text}")

    async def get_balance(self, symbol_or_mint: Optional[str] = None) -> Dict[str, Any]:
        if self._config.bloombot_dry_run:
            if not symbol_or_mint:
                return {"SOL": 1.2345}
            return {symbol_or_mint: 123456.0}

        params = {"token": symbol_or_mint} if symbol_or_mint else None
        # TODO: Replace with actual BloomBot endpoint path and schema
        resp = await self._client.get("/api/wallet/balance", params=params, headers=self._headers())
        if resp.status_code // 100 == 2:
            return resp.json()
        return {"error": f"BALANCE failed: {resp.status_code}", "details": resp.text}