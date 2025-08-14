from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from filters import FilterEngine, load_config


def load_tokens() -> List[Dict[str, Any]]:
    return [
        {
            "address": "0x1111111111111111111111111111111111111111",
            "symbol": "GOOD",
            "name": "GoodToken",
            "developer_address": "0xdeedbeefdeedbeefdeedbeefdeedbeefdeedbeef",
            "developer_labels": ["CLEAN_TEAM"],
            "chain": "ethereum",
            "base_token_symbol": "WETH",
            "dex": "uniswapv2",
            "liquidity_usd": 25000,
            "buy_tax_bps": 100,
            "sell_tax_bps": 100,
            "age_days": 45,
            "verified": True,
        },
        {
            "address": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "symbol": "SAFE?",
            "name": "Looks Safe But Blacklisted",
            "developer_address": "0xdeedbeefdeedbeefdeedbeefdeedbeefdeedbeef",
            "developer_labels": ["CLEAN_TEAM"],
            "chain": "ethereum",
            "base_token_symbol": "WETH",
            "dex": "uniswapv2",
            "liquidity_usd": 500000,
            "buy_tax_bps": 50,
            "sell_tax_bps": 50,
            "age_days": 365,
            "verified": True,
        },
        {
            "address": "0x3333333333333333333333333333333333333333",
            "symbol": "RUG",
            "name": "Definitely Rug",
            "developer_address": "0xabcabcabcabcabcabcabcabcabcabcabcabcab",
            "developer_labels": ["KNOWN_RUGGER_GROUP_X"],
            "chain": "bsc",
            "base_token_symbol": "WBNB",
            "dex": "unknowndex",
            "liquidity_usd": 8000,
            "buy_tax_bps": 1500,
            "sell_tax_bps": 2000,
            "age_days": 1,
            "verified": False,
        },
    ]


def main() -> None:
    config_path = os.environ.get("CONFIG_PATH", os.path.join(os.path.dirname(__file__), "config.json"))
    config = load_config(config_path)
    engine = FilterEngine(config)

    tokens = load_tokens()
    results: List[Dict[str, Any]] = []
    for token in tokens:
        allowed, reasons = engine.evaluate(token)
        results.append({
            "address": token.get("address"),
            "symbol": token.get("symbol"),
            "allowed": allowed,
            "reasons": reasons,
        })

    print(json.dumps({"results": results}, indent=2))


if __name__ == "__main__":
    main()