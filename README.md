# Coin Pattern Bot

A minimal async Python bot that fetches token data from Dexscreener and optionally Pump.fun, stores snapshots in SQLite, detects events (pump, rug, tier-1, CEX listing placeholder), and logs findings for pattern analysis.

## Features
- Async data fetchers (Dexscreener; Pump.fun optional/stub)
- SQLite storage via aiosqlite
- Detection rules for pump/rug/tier-1
- Simple config via `config.yaml`
- CLI runner for one-off or looped execution

## Quickstart

1. Install dependencies:

```bash
pip install -r /workspace/requirements.txt
```

2. Adjust configuration in `/workspace/config.yaml` as needed.

3. Run database init and a single analysis pass:

```bash
python /workspace/main.py init-db
python /workspace/main.py run-once --config /workspace/config.yaml
```

4. Run in a loop:

```bash
python /workspace/main.py run-loop --config /workspace/config.yaml
```

## Notes on APIs
- Dexscreener provides public endpoints for token and pair data. We query by token address when available or perform fuzzy search by query as a fallback.
- Pump.fun endpoints are not stable. The fetcher is disabled by default. Set `sources.pumpfun.enabled: true` and provide `sources.pumpfun.base_url` when you have a working endpoint, or extend `coinbot/fetchers/pumpfun.py` to integrate on-chain or community feeds.

## Detection Heuristics
- Pump: price up >= `thresholds.pump_percent_increase` within `pump_window_minutes`.
- Rug: price down >= `thresholds.rug_percent_drop` AND liquidity down >= `thresholds.rug_liquidity_drop_percent` within `rug_window_minutes`.
- Tier-1: liquidity and 24h volume exceed configured thresholds.
- CEX Listing: placeholder hook for integrating with external listing feeds (e.g., exchange announcements, CoinGecko/CMC APIs).

## Data
Data stored under `/workspace/data/coinbot.sqlite3` by default. Tables include `tokens`, `pairs`, `snapshots`, and `events`.

## Extensibility
- Add new sources under `coinbot/fetchers/` and register them in `analyzer.py`.
- Modify thresholds in `config.yaml` to tune detections.