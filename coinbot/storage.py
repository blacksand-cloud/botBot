from __future__ import annotations

import aiosqlite
from typing import Any, Dict, List, Optional, Tuple
import json
import os

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS tokens (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	chain TEXT NOT NULL,
	token_address TEXT NOT NULL,
	symbol TEXT,
	name TEXT,
	first_seen_ts INTEGER,
	UNIQUE(chain, token_address)
);

CREATE TABLE IF NOT EXISTS pairs (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	token_id INTEGER NOT NULL,
	dex_id TEXT,
	pair_address TEXT,
	base_symbol TEXT,
	quote_symbol TEXT,
	UNIQUE(token_id, pair_address),
	FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS snapshots (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	token_id INTEGER NOT NULL,
	pair_id INTEGER,
	ts INTEGER NOT NULL,
	price_usd REAL,
	liquidity_usd REAL,
	volume_24h_usd REAL,
	holders INTEGER,
	source TEXT,
	payload_json TEXT,
	FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE,
	FOREIGN KEY (pair_id) REFERENCES pairs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_token_ts ON snapshots(token_id, ts);

CREATE TABLE IF NOT EXISTS events (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	token_id INTEGER NOT NULL,
	ts INTEGER NOT NULL,
	event_type TEXT NOT NULL,
	details_json TEXT,
	FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_token_ts ON events(token_id, ts);
"""


class Database:
	def __init__(self, sqlite_path: str) -> None:
		self.sqlite_path = sqlite_path
		self._conn: Optional[aiosqlite.Connection] = None

	async def initialize(self) -> None:
		os.makedirs(os.path.dirname(self.sqlite_path), exist_ok=True)
		self._conn = await aiosqlite.connect(self.sqlite_path)
		await self._conn.executescript(SCHEMA_SQL)
		await self._conn.commit()

	@property
	def conn(self) -> aiosqlite.Connection:
		assert self._conn is not None, "Database not initialized"
		return self._conn

	async def close(self) -> None:
		if self._conn is not None:
			await self._conn.close()
			self._conn = None

	async def upsert_token(self, chain: str, token_address: str, symbol: Optional[str], name: Optional[str], first_seen_ts: int) -> int:
		await self.conn.execute(
			"""
			INSERT INTO tokens(chain, token_address, symbol, name, first_seen_ts)
			VALUES (?, ?, ?, ?, ?)
			ON CONFLICT(chain, token_address) DO UPDATE SET
				symbol=COALESCE(excluded.symbol, tokens.symbol),
				name=COALESCE(excluded.name, tokens.name)
			""",
			(chain, token_address, symbol, name, first_seen_ts),
		)
		await self.conn.commit()
		cur = await self.conn.execute("SELECT id FROM tokens WHERE chain=? AND token_address=?", (chain, token_address))
		row = await cur.fetchone()
		assert row is not None
		return int(row[0])

	async def upsert_pair(self, token_id: int, dex_id: Optional[str], pair_address: Optional[str], base_symbol: Optional[str], quote_symbol: Optional[str]) -> int:
		await self.conn.execute(
			"""
			INSERT INTO pairs(token_id, dex_id, pair_address, base_symbol, quote_symbol)
			VALUES (?, ?, ?, ?, ?)
			ON CONFLICT(token_id, pair_address) DO UPDATE SET
				dex_id=COALESCE(excluded.dex_id, pairs.dex_id),
				base_symbol=COALESCE(excluded.base_symbol, pairs.base_symbol),
				quote_symbol=COALESCE(excluded.quote_symbol, pairs.quote_symbol)
			""",
			(token_id, dex_id, pair_address, base_symbol, quote_symbol),
		)
		await self.conn.commit()
		cur = await self.conn.execute("SELECT id FROM pairs WHERE token_id=? AND pair_address IS ?", (token_id, pair_address))
		row = await cur.fetchone()
		assert row is not None
		return int(row[0])

	async def insert_snapshot(self, token_id: int, pair_id: Optional[int], ts: int, price_usd: Optional[float], liquidity_usd: Optional[float], volume_24h_usd: Optional[float], holders: Optional[int], source: str, payload: Dict[str, Any]) -> int:
		payload_json = json.dumps(payload, separators=(",", ":"))
		cur = await self.conn.execute(
			"""
			INSERT INTO snapshots(token_id, pair_id, ts, price_usd, liquidity_usd, volume_24h_usd, holders, source, payload_json)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
			""",
			(token_id, pair_id, ts, price_usd, liquidity_usd, volume_24h_usd, holders, source, payload_json),
		)
		await self.conn.commit()
		return int(cur.lastrowid)

	async def insert_event(self, token_id: int, ts: int, event_type: str, details: Dict[str, Any]) -> int:
		details_json = json.dumps(details, separators=(",", ":"))
		cur = await self.conn.execute(
			"INSERT INTO events(token_id, ts, event_type, details_json) VALUES (?, ?, ?, ?)",
			(token_id, ts, event_type, details_json),
		)
		await self.conn.commit()
		return int(cur.lastrowid)

	async def recent_snapshots(self, token_id: int, since_ts: int) -> List[Dict[str, Any]]:
		cur = await self.conn.execute(
			"SELECT ts, price_usd, liquidity_usd, volume_24h_usd, holders FROM snapshots WHERE token_id=? AND ts>=? ORDER BY ts ASC",
			(token_id, since_ts),
		)
		rows = await cur.fetchall()
		return [
			{"ts": r[0], "price_usd": r[1], "liquidity_usd": r[2], "volume_24h_usd": r[3], "holders": r[4]}
			for r in rows
		]