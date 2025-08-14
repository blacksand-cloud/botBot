from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


@dataclass
class FilterSettings:
    min_liquidity_usd: Optional[float] = None
    max_buy_tax_bps: Optional[int] = None
    max_sell_tax_bps: Optional[int] = None
    min_token_age_days: Optional[int] = None
    allow_verified_only: bool = False
    allowed_chains: Set[str] = field(default_factory=set)
    allowed_base_tokens: Set[str] = field(default_factory=set)
    excluded_dexes: Set[str] = field(default_factory=set)
    name_must_not_match_regex: List[str] = field(default_factory=list)


@dataclass
class BlacklistSettings:
    addresses: Set[str] = field(default_factory=set)
    symbols: Set[str] = field(default_factory=set)
    regexes: List[str] = field(default_factory=list)
    labels: Set[str] = field(default_factory=set)


@dataclass
class AppConfig:
    filters: FilterSettings
    coin_blacklist: BlacklistSettings
    developer_blacklist: BlacklistSettings


class RegexMatcher:
    def __init__(self, patterns: Optional[Iterable[str]] = None) -> None:
        self._compiled: List[re.Pattern[str]] = []
        if patterns:
            for pattern in patterns:
                if not pattern:
                    continue
                self._compiled.append(re.compile(pattern))

    def matches_any(self, text: Optional[str]) -> bool:
        if not text:
            return False
        for pattern in self._compiled:
            if pattern.search(text):
                return True
        return False


def _normalize_address(address: Optional[str]) -> Optional[str]:
    if address is None:
        return None
    return address.lower()


def _normalize_symbol(symbol: Optional[str]) -> Optional[str]:
    if symbol is None:
        return None
    return symbol.upper()


def _to_set_lower(values: Optional[Iterable[str]]) -> Set[str]:
    if not values:
        return set()
    return {v.lower() for v in values if isinstance(v, str) and v}


def _to_set_upper(values: Optional[Iterable[str]]) -> Set[str]:
    if not values:
        return set()
    return {v.upper() for v in values if isinstance(v, str) and v}


def _to_set_identity(values: Optional[Iterable[str]]) -> Set[str]:
    if not values:
        return set()
    return {v for v in values if isinstance(v, str) and v}


def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw: Dict[str, Any] = json.load(f)

    raw_filters: Dict[str, Any] = raw.get("filters", {})
    filters = FilterSettings(
        min_liquidity_usd=raw_filters.get("min_liquidity_usd"),
        max_buy_tax_bps=raw_filters.get("max_buy_tax_bps"),
        max_sell_tax_bps=raw_filters.get("max_sell_tax_bps"),
        min_token_age_days=raw_filters.get("min_token_age_days"),
        allow_verified_only=bool(raw_filters.get("allow_verified_only", False)),
        allowed_chains=_to_set_lower(raw_filters.get("allowed_chains")),
        allowed_base_tokens=_to_set_upper(raw_filters.get("allowed_base_tokens")),
        excluded_dexes=_to_set_lower(raw_filters.get("excluded_dexes")),
        name_must_not_match_regex=list(raw_filters.get("name_must_not_match_regex", [])),
    )

    raw_coin_bl = raw.get("coin_blacklist", {})
    coin_bl = BlacklistSettings(
        addresses=_to_set_lower(raw_coin_bl.get("addresses")),
        symbols=_to_set_upper(raw_coin_bl.get("symbols")),
        regexes=list(raw_coin_bl.get("regexes", [])),
        labels=set(),
    )

    raw_dev_bl = raw.get("developer_blacklist", {})
    dev_bl = BlacklistSettings(
        addresses=_to_set_lower(raw_dev_bl.get("addresses")),
        symbols=set(),
        regexes=list(raw_dev_bl.get("regexes", [])),
        labels=_to_set_upper(raw_dev_bl.get("labels")),
    )

    return AppConfig(filters=filters, coin_blacklist=coin_bl, developer_blacklist=dev_bl)


class CoinBlacklist:
    def __init__(self, settings: BlacklistSettings):
        self.addresses_lower = set(settings.addresses)
        self.symbols_upper = set(settings.symbols)
        self.regex_matcher = RegexMatcher(settings.regexes)

    def is_blacklisted(self, token: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        address = _normalize_address(token.get("address"))
        symbol = _normalize_symbol(token.get("symbol"))
        name = token.get("name")

        if address and address in self.addresses_lower:
            return True, f"coin address blacklisted: {address}"
        if symbol and symbol in self.symbols_upper:
            return True, f"coin symbol blacklisted: {symbol}"
        if (symbol and self.regex_matcher.matches_any(symbol)) or (name and self.regex_matcher.matches_any(name)):
            return True, "coin name/symbol matches blacklist regex"
        return False, None


class DeveloperBlacklist:
    def __init__(self, settings: BlacklistSettings):
        self.addresses_lower = set(settings.addresses)
        self.labels_upper = set(settings.labels)
        self.regex_matcher = RegexMatcher(settings.regexes)

    def is_blacklisted(self, token: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        dev_address = _normalize_address(
            token.get("developer_address") or token.get("deployer") or token.get("creator")
        )
        dev_labels = token.get("developer_labels") or []
        dev_labels_upper = {str(lbl).upper() for lbl in dev_labels}

        if dev_address and dev_address in self.addresses_lower:
            return True, f"developer address blacklisted: {dev_address}"
        if self.labels_upper and (self.labels_upper & dev_labels_upper):
            return True, f"developer label blacklisted: {(self.labels_upper & dev_labels_upper).pop()}"
        # Allow regex matching against any stringy metadata we might have
        possible_texts = [
            token.get("developer_name"),
            token.get("deployer_note"),
            token.get("audit_label"),
        ]
        for text in possible_texts:
            if isinstance(text, str) and self.regex_matcher.matches_any(text):
                return True, "developer metadata matches blacklist regex"
        return False, None


class FilterEngine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.coin_blacklist = CoinBlacklist(config.coin_blacklist)
        self.developer_blacklist = DeveloperBlacklist(config.developer_blacklist)
        self.name_block_matcher = RegexMatcher(config.filters.name_must_not_match_regex)

    def evaluate(self, token: Dict[str, Any]) -> Tuple[bool, List[str]]:
        reasons: List[str] = []

        # Hard blocks: coin blacklist and developer blacklist
        coin_bl, coin_reason = self.coin_blacklist.is_blacklisted(token)
        if coin_bl:
            reasons.append(coin_reason or "coin blacklisted")
            return False, reasons

        dev_bl, dev_reason = self.developer_blacklist.is_blacklisted(token)
        if dev_bl:
            reasons.append(dev_reason or "developer blacklisted")
            return False, reasons

        f = self.config.filters

        # Dex exclusion
        dex = token.get("dex")
        if isinstance(dex, str) and f.excluded_dexes and dex.lower() in f.excluded_dexes:
            reasons.append(f"excluded dex: {dex}")

        # Allowed chains constraint
        chain = token.get("chain")
        if isinstance(chain, str) and f.allowed_chains and chain.lower() not in f.allowed_chains:
            reasons.append(f"chain not allowed: {chain}")

        # Allowed base tokens constraint
        base = token.get("base_token_symbol")
        if isinstance(base, str) and f.allowed_base_tokens and _normalize_symbol(base) not in f.allowed_base_tokens:
            reasons.append(f"base token not allowed: {base}")

        # Name regex blocklist
        name = token.get("name") or token.get("symbol")
        if isinstance(name, str) and self.name_block_matcher.matches_any(name):
            reasons.append("name matches blocked pattern")

        # Quantitative thresholds
        liq = token.get("liquidity_usd")
        if isinstance(liq, (int, float)) and isinstance(f.min_liquidity_usd, (int, float)):
            if liq < float(f.min_liquidity_usd):
                reasons.append(f"liquidity below minimum: {liq} < {f.min_liquidity_usd}")

        buy_tax = token.get("buy_tax_bps")
        if isinstance(buy_tax, (int, float)) and isinstance(f.max_buy_tax_bps, (int, float)):
            if float(buy_tax) > float(f.max_buy_tax_bps):
                reasons.append(f"buy tax too high: {buy_tax}bps > {f.max_buy_tax_bps}bps")

        sell_tax = token.get("sell_tax_bps")
        if isinstance(sell_tax, (int, float)) and isinstance(f.max_sell_tax_bps, (int, float)):
            if float(sell_tax) > float(f.max_sell_tax_bps):
                reasons.append(f"sell tax too high: {sell_tax}bps > {f.max_sell_tax_bps}bps")

        age = token.get("age_days")
        if isinstance(age, (int, float)) and isinstance(f.min_token_age_days, (int, float)):
            if float(age) < float(f.min_token_age_days):
                reasons.append(f"token too new: {age}d < {f.min_token_age_days}d")

        verified = token.get("verified")
        if f.allow_verified_only and not bool(verified):
            reasons.append("token not verified")

        allowed = len(reasons) == 0
        return allowed, reasons


__all__ = [
    "FilterSettings",
    "BlacklistSettings",
    "AppConfig",
    "load_config",
    "FilterEngine",
]