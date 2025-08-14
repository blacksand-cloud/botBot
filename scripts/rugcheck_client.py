import os
import time
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_TIMEOUT_SECONDS = 15

class RugcheckClient:
    def __init__(self) -> None:
        self.api_base = os.environ.get("RUGCHECK_API_BASE", "https://api.rugcheck.xyz").rstrip("/")
        self.api_key = os.environ.get("RUGCHECK_API_KEY", "").strip()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        if self.api_key:
            self.session.headers.update({"X-API-KEY": self.api_key})

    def _get(self, path: str) -> Optional[Dict[str, Any]]:
        url = f"{self.api_base}{path}"
        try:
            response = self.session.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return response.json()
            # In case JSON not declared but response is JSON
            try:
                return response.json()
            except Exception:
                return None
        except requests.RequestException:
            return None

    def fetch_token_report(self, chain: str, contract: str) -> Optional[Dict[str, Any]]:
        # Try a series of likely endpoints used by Rugcheck; return first JSON dict we get
        candidate_paths = [
            f"/v1/tokens/{chain}/{contract}",
            f"/v1/tokens/{contract}",
            f"/tokens/scan/{chain}/{contract}",
            f"/tokens/{chain}/{contract}",
            f"/search?id={contract}",
        ]
        for path in candidate_paths:
            data = self._get(path)
            if isinstance(data, dict):
                return data
            # Be kind; avoid hitting rate limits
            time.sleep(0.2)
        return None

    @staticmethod
    def is_good(report: Dict[str, Any]) -> bool:
        # Consider multiple possible fields for verdict/label
        verdict_candidates = [
            report.get("verdict"),
            report.get("status"),
            report.get("label"),
            report.get("score_label"),
            (report.get("score") or {}).get("label") if isinstance(report.get("score"), dict) else None,
        ]
        for verdict in verdict_candidates:
            if isinstance(verdict, str) and verdict.strip().lower() == "good":
                return True
        # Some APIs may provide a numeric score; treat explicitly marked bad as not good
        risk = report.get("risk")
        if isinstance(risk, str) and risk.lower() in {"high", "bad", "danger"}:
            return False
        return False

    @staticmethod
    def is_bundled_supply(report: Dict[str, Any]) -> bool:
        # Check explicit flags
        bundled_flags = [
            report.get("bundled"),
            report.get("isBundled"),
            report.get("supply_bundled"),
            report.get("is_supply_bundled"),
        ]
        for flag in bundled_flags:
            if isinstance(flag, bool) and flag:
                return True
            if isinstance(flag, str) and flag.strip().lower() in {"true", "yes", "bundled"}:
                return True
        # Check labels/tags arrays
        for key in ("labels", "tags", "flags"):
            val = report.get(key)
            if isinstance(val, list):
                joined = ",".join(str(x).lower() for x in val)
                if any(tok in joined for tok in ["bundle", "bundled", "supply_bundled"]):
                    return True
        # Env-configurable extra label names
        extra_labels = os.environ.get("BUNDLED_LABELS", "").split(",")
        extra_labels = [x.strip().lower() for x in extra_labels if x.strip()]
        if extra_labels:
            full_text = str(report).lower()
            if any(label in full_text for label in extra_labels):
                return True
        return False

    @staticmethod
    def extract_developer_address(report: Dict[str, Any]) -> Optional[str]:
        # Try the common keys for deployer/creator/owner
        for key in (
            "developer",
            "developer_address",
            "deployer",
            "deployer_address",
            "creator",
            "creator_address",
            "owner",
            "owner_address",
            "authority",
            "mint_authority",
        ):
            val = report.get(key)
            if isinstance(val, str) and len(val) > 0:
                return val
            if isinstance(val, dict):
                for subkey in ("address", "pubkey", "wallet"):
                    sval = val.get(subkey)
                    if isinstance(sval, str) and len(sval) > 0:
                        return sval
        return None