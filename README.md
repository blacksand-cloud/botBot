# Fake Volume Detector (Dexscreener + optional Pocket Universe)

A small Python CLI to flag coins/pairs with potentially fake trading volume using heuristics on Dexscreener data, with optional Pocket Universe API blending.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

- Detect by Dexscreener URL:

```bash
python detect_fake_volume.py --dexscreener-url https://dexscreener.com/ethereum/0xPAIR --json
```

- Detect by chain + pair:

```bash
python detect_fake_volume.py --pair 0xPAIR --chain ethereum
```

- Detect top-liquidity pairs for a token:

```bash
python detect_fake_volume.py --token 0xTOKEN --top 5 --json
```

Exit code is 1 if any evaluated pair meets or exceeds the threshold (default 50), else 0.

## Optional: Pocket Universe

Set endpoint and key via flags or env vars `POCKET_UNIVERSE_URL` and `POCKET_UNIVERSE_API_KEY`.
The CLI posts pair context and blends a returned `riskScore` (0-100) or respects `isFakeVolume=true` if provided.

```bash
POCKET_UNIVERSE_URL=https://your-pocket-universe-endpoint \
POCKET_UNIVERSE_API_KEY=xxxx \
python detect_fake_volume.py --dexscreener-url https://dexscreener.com/ethereum/0xPAIR --json
```

## Heuristics (summary)

- High 24h volume with very low tx count
- Large average trade size, esp. vs. liquidity
- High 24h volume/liquidity ratio with few txs
- Extreme buy/sell imbalance
- 5m volume spikes disproportionate to 1h/24h
- Very low liquidity with very high 24h volume

Thresholds are conservative defaults and may be tuned in code.