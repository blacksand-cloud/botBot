import argparse
import json
import os
from pathlib import Path
from typing import List, Set

from dotenv import load_dotenv
from rich import print
from rich.table import Table

from scripts.rugcheck_client import RugcheckClient

load_dotenv()

DATA_DIR = Path("/workspace/data")
TOKENS_BLACKLIST_PATH = DATA_DIR / "blacklist_tokens.json"
DEVS_BLACKLIST_PATH = DATA_DIR / "blacklist_devs.json"


def load_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    with path.open("r") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]


def load_blacklist(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    try:
        with path.open("r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {str(x) for x in data}
    except Exception:
        pass
    return set()


def save_blacklist(path: Path, items: Set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(sorted(items), f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check tokens with Rugcheck and manage blacklists")
    parser.add_argument("--token", help="Single token mint/contract to check", default=None)
    parser.add_argument("--tokens", help="Path to file with token mints/contracts (one per line)", default=str(DATA_DIR / "tokens.txt"))
    parser.add_argument("--chain", help="Chain name (default from env or 'solana')", default=os.environ.get("RUGCHECK_CHAIN", "solana"))
    parser.add_argument("--dry", help="Dry run (do not modify blacklists)", action="store_true")
    args = parser.parse_args()

    tokens: List[str] = []
    if args.token:
        tokens = [args.token.strip()]
    else:
        tokens = load_lines(Path(args.tokens))

    if not tokens:
        print("[yellow]No tokens provided. Add to /workspace/data/tokens.txt or use --token[/yellow]")
        return

    tokens_blacklist = load_blacklist(TOKENS_BLACKLIST_PATH)
    devs_blacklist = load_blacklist(DEVS_BLACKLIST_PATH)

    client = RugcheckClient()

    table = Table(title="Rugcheck Results")
    table.add_column("Token")
    table.add_column("Verdict")
    table.add_column("Bundled?")
    table.add_column("Developer")
    table.add_column("Action")

    for token in tokens:
        report = client.fetch_token_report(args.chain, token)
        if report is None:
            table.add_row(token, "[red]Unknown[/red]", "?", "?", "Skip")
            continue

        good = client.is_good(report)
        bundled = client.is_bundled_supply(report)
        developer = client.extract_developer_address(report) or "?"

        action = "Allow"
        if not good:
            action = "Skip"
        if bundled:
            action = "Blacklist"

        table.add_row(
            token,
            "[green]Good[/green]" if good else "[red]Not Good[/red]",
            "[red]Yes[/red]" if bundled else "No",
            developer,
            action,
        )

        if action == "Blacklist" and not args.dry:
            tokens_blacklist.add(token)
            if developer and developer != "?":
                devs_blacklist.add(developer)

    print(table)

    if not args.dry:
        save_blacklist(TOKENS_BLACKLIST_PATH, tokens_blacklist)
        save_blacklist(DEVS_BLACKLIST_PATH, devs_blacklist)
        print(f"Saved token blacklist to {TOKENS_BLACKLIST_PATH}")
        print(f"Saved developer blacklist to {DEVS_BLACKLIST_PATH}")
    else:
        print("[yellow]Dry run: no blacklists were modified[/yellow]")


if __name__ == "__main__":
    main()