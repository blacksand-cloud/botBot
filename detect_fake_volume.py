#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from urllib import request, error

DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"


@dataclass
class TxnWindow:
    buys: int = 0
    sells: int = 0

    @property
    def total(self) -> int:
        return int(self.buys) + int(self.sells)


@dataclass
class PairStats:
    chain_id: str
    dex_id: Optional[str]
    pair_address: str
    base_token: Dict[str, Any]
    quote_token: Dict[str, Any]
    price_usd: Optional[float]
    liquidity_usd: Optional[float]
    volume_h24: Optional[float]
    volume_h1: Optional[float]
    volume_m5: Optional[float]
    txns_h24: TxnWindow = field(default_factory=TxnWindow)
    txns_h1: TxnWindow = field(default_factory=TxnWindow)
    txns_m5: TxnWindow = field(default_factory=TxnWindow)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionResult:
    suspicious: bool
    score: float
    reasons: List[str]
    pair: PairStats
    pocket_universe: Optional[Dict[str, Any]] = None


def http_get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> Dict[str, Any]:
    req = request.Request(url, method="GET")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return json.loads(data.decode("utf-8"))
    except error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} for {url}: {e.reason}")
    except error.URLError as e:
        raise RuntimeError(f"Network error for {url}: {e.reason}")


def http_post_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None, timeout: int = 25) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            resp_data = resp.read()
            return json.loads(resp_data.decode("utf-8"))
    except error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = ""
        raise RuntimeError(f"HTTP {e.code} for {url}: {e.reason} {body}")
    except error.URLError as e:
        raise RuntimeError(f"Network error for {url}: {e.reason}")


def parse_pair_obj(obj: Dict[str, Any]) -> PairStats:
    def _safe_num(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _window(obj_: Dict[str, Any], key: str) -> TxnWindow:
        win = obj_.get("txns", {}).get(key, {}) if obj_.get("txns") else {}
        return TxnWindow(buys=int(win.get("buys", 0) or 0), sells=int(win.get("sells", 0) or 0))

    liquidity = obj.get("liquidity") or {}
    return PairStats(
        chain_id=str(obj.get("chainId") or ""),
        dex_id=obj.get("dexId"),
        pair_address=str(obj.get("pairAddress") or obj.get("pairAddress")),
        base_token=obj.get("baseToken") or {},
        quote_token=obj.get("quoteToken") or {},
        price_usd=_safe_num(obj.get("priceUsd")),
        liquidity_usd=_safe_num(liquidity.get("usd")),
        volume_h24=_safe_num((obj.get("volume") or {}).get("h24")),
        volume_h1=_safe_num((obj.get("volume") or {}).get("h1")),
        volume_m5=_safe_num((obj.get("volume") or {}).get("m5")),
        txns_h24=_window(obj, "h24"),
        txns_h1=_window(obj, "h1"),
        txns_m5=_window(obj, "m5"),
        raw=obj,
    )


def fetch_pairs_by_token(token_address: str) -> List[PairStats]:
    url = f"{DEXSCREENER_BASE}/tokens/{token_address}"
    data = http_get_json(url)
    pairs = data.get("pairs") or []
    return [parse_pair_obj(p) for p in pairs]


def fetch_pair_by_chain_and_address(chain: str, pair_address: str) -> Optional[PairStats]:
    url = f"{DEXSCREENER_BASE}/pairs/{chain}/{pair_address}"
    data = http_get_json(url)
    pairs = data.get("pairs") or []
    if not pairs:
        return None
    return parse_pair_obj(pairs[0])


DEXSCREENER_URL_RE = re.compile(r"https?://(?:www\.)?dexscreener\.com/([\w-]+)/([0-9a-zA-Zx]{5,})")


def parse_dexscreener_url(url: str) -> Optional[Tuple[str, str]]:
    m = DEXSCREENER_URL_RE.search(url)
    if not m:
        return None
    return m.group(1), m.group(2)


def safe_div(numer: Optional[float], denom: Optional[float]) -> Optional[float]:
    try:
        if numer is None or denom in (None, 0):
            return None
        return float(numer) / float(denom)
    except Exception:
        return None


def apply_heuristics(pair: PairStats) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []

    liquidity = pair.liquidity_usd or 0.0
    vol24 = pair.volume_h24 or 0.0
    vol1h = pair.volume_h1 or 0.0
    vol5m = pair.volume_m5 or 0.0
    tx24 = pair.txns_h24.total
    tx1h = pair.txns_h1.total
    tx5m = pair.txns_m5.total

    # Heuristic 1: High 24h volume with very low tx count
    if vol24 >= 50000 and tx24 <= 10:
        score += 35
        reasons.append(f"High 24h volume (${vol24:,.0f}) with very low tx count in 24h ({tx24})")

    # Heuristic 2: Large avg trade size relative to liquidity
    avg_trade_usd = safe_div(vol24, tx24)
    pct_of_liq = safe_div(avg_trade_usd, liquidity)
    if avg_trade_usd is not None and avg_trade_usd >= 25000 and tx24 <= 20:
        score += 20
        reasons.append(f"Large average trade size (${avg_trade_usd:,.0f}) with low tx count ({tx24})")
    if pct_of_liq is not None and pct_of_liq >= 0.05:  # 5%+ of liquidity per average trade is odd
        score += 10
        reasons.append(f"Average trade size equals {pct_of_liq*100:.1f}% of liquidity")

    # Heuristic 3: Volume to liquidity ratio too high without matching txs
    vol_liq_ratio = safe_div(vol24, liquidity)
    if vol_liq_ratio is not None and vol_liq_ratio >= 10 and tx24 <= 30:
        score += 15
        reasons.append(f"24h volume/liquidity ratio is {vol_liq_ratio:.1f}x with low txs ({tx24})")

    # Heuristic 4: Extreme buy/sell imbalance
    if tx24 > 0:
        buy_ratio = safe_div(pair.txns_h24.buys, tx24)
        if buy_ratio is not None and (buy_ratio >= 0.95 or buy_ratio <= 0.05):
            score += 10
            reasons.append(f"Extreme buy/sell imbalance in 24h (buys={pair.txns_h24.buys}, sells={pair.txns_h24.sells})")

    # Heuristic 5: 5m spike relative to 1h/24h
    rel_5m_1h = safe_div(vol5m, vol1h)
    rel_5m_24h = safe_div(vol5m, vol24)
    if rel_5m_1h is not None and rel_5m_1h >= 0.6 and vol1h > 0:
        score += 10
        reasons.append(f"5m volume spike equals {rel_5m_1h*100:.0f}% of 1h volume")
    if rel_5m_24h is not None and rel_5m_24h >= 0.25 and vol24 > 0:
        score += 5
        reasons.append(f"5m volume spike equals {rel_5m_24h*100:.0f}% of 24h volume")

    # Heuristic 6: Very low liquidity with high volume
    if liquidity > 0 and vol24 >= 200000 and liquidity <= 20000:
        score += 15
        reasons.append(f"Very low liquidity (${liquidity:,.0f}) with very high 24h volume (${vol24:,.0f})")

    # Normalize score to 0-100 cap
    score = min(100.0, score)

    return score, reasons


def query_pocket_universe(pair: PairStats, api_url: Optional[str], api_key: Optional[str]) -> Optional[Dict[str, Any]]:
    if not api_url:
        return None
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "chainId": pair.chain_id,
        "pairAddress": pair.pair_address,
        "baseToken": pair.base_token,
        "quoteToken": pair.quote_token,
        "liquidityUsd": pair.liquidity_usd,
        "volume": {
            "h24": pair.volume_h24,
            "h1": pair.volume_h1,
            "m5": pair.volume_m5,
        },
        "txns": {
            "h24": {"buys": pair.txns_h24.buys, "sells": pair.txns_h24.sells},
            "h1": {"buys": pair.txns_h1.buys, "sells": pair.txns_h1.sells},
            "m5": {"buys": pair.txns_m5.buys, "sells": pair.txns_m5.sells},
        },
    }

    try:
        return http_post_json(api_url, payload, headers=headers)
    except Exception as e:
        return {"error": str(e)}


def evaluate_pair(pair: PairStats, pocket_universe_url: Optional[str], pocket_universe_key: Optional[str]) -> DetectionResult:
    score, reasons = apply_heuristics(pair)
    pu = query_pocket_universe(pair, pocket_universe_url, pocket_universe_key)

    if pu and isinstance(pu, dict):
        # If the API returns a risk score or explicit flag, incorporate lightly
        api_score = None
        api_flag = None
        if "riskScore" in pu and isinstance(pu["riskScore"], (int, float)):
            api_score = float(pu["riskScore"])  # expected 0-100
        if "isFakeVolume" in pu:
            api_flag = bool(pu["isFakeVolume"])  # expected boolean

        if api_score is not None:
            # Blend with 60% heuristic, 40% API weight
            score = min(100.0, 0.6 * score + 0.4 * api_score)
            reasons.append(f"PocketUniverse risk score blended: {api_score:.1f}")
        if api_flag is True:
            score = min(100.0, max(score, 80.0))
            reasons.append("PocketUniverse flagged as fake volume")
        if "error" in pu:
            reasons.append(f"PocketUniverse error: {pu['error']}")

    suspicious = score >= 50.0
    return DetectionResult(suspicious=suspicious, score=score, reasons=reasons, pair=pair, pocket_universe=pu)


def result_to_dict(res: DetectionResult) -> Dict[str, Any]:
    return {
        "suspicious": res.suspicious,
        "score": round(res.score, 1),
        "reasons": res.reasons,
        "pair": {
            "chainId": res.pair.chain_id,
            "pairAddress": res.pair.pair_address,
            "dexId": res.pair.dex_id,
            "baseToken": res.pair.base_token,
            "quoteToken": res.pair.quote_token,
            "liquidityUsd": res.pair.liquidity_usd,
            "volume": {"h24": res.pair.volume_h24, "h1": res.pair.volume_h1, "m5": res.pair.volume_m5},
            "txns": {
                "h24": {"buys": res.pair.txns_h24.buys, "sells": res.pair.txns_h24.sells},
                "h1": {"buys": res.pair.txns_h1.buys, "sells": res.pair.txns_h1.sells},
                "m5": {"buys": res.pair.txns_m5.buys, "sells": res.pair.txns_m5.sells},
            },
        },
        "pocketUniverse": res.pocket_universe,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Detect fake volume on Dex pairs using heuristics and optional Pocket Universe API.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--token", help="Token address to fetch all Dexscreener pairs")
    src.add_argument("--pair", help="Pair address with --chain to fetch a specific pair")
    src.add_argument("--dexscreener-url", help="Direct Dexscreener pair URL, e.g. https://dexscreener.com/ethereum/0x...")

    parser.add_argument("--chain", help="Chain id or name for --pair (e.g., ethereum, bsc, polygon)")

    parser.add_argument("--pocket-universe-url", default=os.environ.get("POCKET_UNIVERSE_URL"), help="Optional Pocket Universe API endpoint for fake volume checks")
    parser.add_argument("--pocket-universe-key", default=os.environ.get("POCKET_UNIVERSE_API_KEY"), help="Optional Pocket Universe API key")

    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")
    parser.add_argument("--threshold", type=float, default=50.0, help="Suspicion threshold (0-100), default 50")
    parser.add_argument("--top", type=int, default=3, help="When using --token, evaluate up to N top-liquidity pairs")

    args = parser.parse_args(argv)

    pairs: List[PairStats] = []
    if args.dexscreener_url:
        parsed = parse_dexscreener_url(args.dexscreener_url)
        if not parsed:
            print("Could not parse dexscreener URL. Expected format: https://dexscreener.com/<chain>/<pair>", file=sys.stderr)
            return 2
        chain, pair_addr = parsed
        pair = fetch_pair_by_chain_and_address(chain, pair_addr)
        if not pair:
            print("Pair not found on Dexscreener", file=sys.stderr)
            return 3
        pairs = [pair]
    elif args.pair:
        if not args.chain:
            print("--chain is required when using --pair", file=sys.stderr)
            return 2
        pair = fetch_pair_by_chain_and_address(args.chain, args.pair)
        if not pair:
            print("Pair not found on Dexscreener", file=sys.stderr)
            return 3
        pairs = [pair]
    elif args.token:
        pairs = fetch_pairs_by_token(args.token)
        if not pairs:
            print("No pairs found for token", file=sys.stderr)
            return 3
        # sort by liquidity desc and keep top N
        pairs.sort(key=lambda p: (p.liquidity_usd or 0.0), reverse=True)
        pairs = pairs[: max(1, int(args.top))]

    results = [evaluate_pair(p, args.pocket_universe_url, args.pocket_universe_key) for p in pairs]

    if args.json:
        print(json.dumps([result_to_dict(r) for r in results], indent=2))
    else:
        for r in results:
            base = r.pair.base_token.get("symbol") or r.pair.base_token.get("name") or "?"
            quote = r.pair.quote_token.get("symbol") or r.pair.quote_token.get("name") or "?"
            print(f"Pair {base}/{quote} on {r.pair.chain_id} ({r.pair.pair_address})")
            print(f"  Liquidity: ${r.pair.liquidity_usd:,.0f} | Volume(24h): ${r.pair.volume_h24:,.0f} | Tx(24h): {r.pair.txns_h24.total}")
            print(f"  Suspicious score: {r.score:.1f} -> {'SUSPICIOUS' if r.suspicious else 'OK'}")
            if r.reasons:
                print("  Reasons:")
                for reason in r.reasons:
                    print(f"   - {reason}")
            print()

    # Exit non-zero if any pair is at or above threshold
    exit_suspicious = any(r.score >= float(args.threshold) for r in results)
    return 1 if exit_suspicious else 0


if __name__ == "__main__":
    sys.exit(main())