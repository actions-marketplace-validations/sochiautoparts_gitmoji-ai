"""
Usage tracking — Free tier limits and Pro license validation

License verification works two ways:
1. Primary: Via public licenses.json on GitHub (no API server needed)
   - URL: https://raw.githubusercontent.com/sochiautoparts/stars-pay-bot/main/data/licenses.json
   - Publicly accessible, no rate limit, no authentication
   - Matches SHA-256 truncated to 16 chars against key_hash
2. Fallback: Via REST API (if STARSPAY_API_URL is set)
   - POST to {STARSPAY_API_URL}/api/v1/verify with X-API-Key header
"""

import hashlib
import os
import sqlite3
import time
import logging
from pathlib import Path
from datetime import datetime

import httpx

from gitmoji_ai.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# License verification cache (in-memory, 1-hour TTL)
# ---------------------------------------------------------------------------
_pro_cache: dict = {"result": None, "timestamp": 0.0}
_PRO_CACHE_TTL = 3600  # 1 hour in seconds

# Public licenses.json URL — no auth, no rate limit
LICENSES_JSON_URL = (
    "https://raw.githubusercontent.com/sochiautoparts/stars-pay-bot/main/data/licenses.json"
)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    settings = get_settings()
    settings.ensure_config_dir()
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            timestamp REAL NOT NULL,
            details TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS license (
            key TEXT PRIMARY KEY,
            activated_at REAL,
            expires_at REAL,
            plan_id TEXT DEFAULT 'pro',
            email TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            last_verified_at REAL
        )
    """)
    # Migration: add last_verified_at column if it doesn't exist
    try:
        conn.execute("ALTER TABLE license ADD COLUMN last_verified_at REAL")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------

def track_usage(action: str, details: str = "") -> None:
    """Record a usage event"""
    conn = _get_db()
    conn.execute(
        "INSERT INTO usage (action, timestamp, details) VALUES (?, ?, ?)",
        (action, time.time(), details),
    )
    conn.commit()
    conn.close()


def get_monthly_usage(action: str) -> int:
    """Get usage count for the current month"""
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0).timestamp()
    conn = _get_db()
    cursor = conn.execute(
        "SELECT COUNT(*) as cnt FROM usage WHERE action = ? AND timestamp >= ?",
        (action, month_start),
    )
    count = cursor.fetchone()["cnt"]
    conn.close()
    return count


def check_limit(action: str) -> tuple[bool, int]:
    """Check if action is within limits. Returns (allowed, remaining)"""
    settings = get_settings()

    # Pro users have no limits
    if settings.is_pro or is_pro():
        return True, 999

    used = get_monthly_usage(action)

    if action == "commit":
        limit = settings.free_commits_per_month
    elif action == "changelog":
        limit = settings.free_changelog_per_month
    else:
        limit = 50  # default

    remaining = max(0, limit - used)
    return used < limit, remaining


# ---------------------------------------------------------------------------
# License verification — Primary: public JSON on GitHub
# ---------------------------------------------------------------------------

def _verify_via_json(key: str) -> dict:
    """Verify via public licenses.json on GitHub.

    The JSON file contains an array of license entries, each with:
      - key_hash: SHA-256 of the license key, truncated to 16 hex chars
      - active:   bool — whether the license is currently active
      - expires_at: Unix timestamp (0 = lifetime)
      - project:  project name
      - plan:     plan identifier

    No authentication is required; the file is served via raw.githubusercontent.com.
    """
    try:
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        resp = httpx.get(LICENSES_JSON_URL, timeout=10)
        if resp.status_code != 200:
            logger.debug("licenses.json fetch returned status %d", resp.status_code)
            return {"valid": False, "reason": "json_fetch_failed"}
        data = resp.json()
        for lic in data.get("licenses", []):
            if lic.get("key_hash") == key_hash and lic.get("active"):
                expires_at = lic.get("expires_at", 0)
                if expires_at > 0 and time.time() > expires_at:
                    return {"valid": False, "reason": "expired"}
                return {
                    "valid": True,
                    "project": lic.get("project"),
                    "plan": lic.get("plan"),
                    "expires_at": expires_at,
                    "source": "licenses_json",
                }
        return {"valid": False, "reason": "key_not_found"}
    except Exception as exc:
        logger.warning("licenses.json verification error: %s", exc)
        return {"valid": False, "reason": "json_error"}


# ---------------------------------------------------------------------------
# License verification — Fallback: REST API
# ---------------------------------------------------------------------------

def _verify_via_api(key: str, api_url: str) -> dict:
    """Verify a license key via the StarsPay REST API.

    POST {api_url}/api/v1/verify
    Header: X-API-Key: {STARSPAY_API_KEY}
    Body: {"key": "<license_key>"}
    """
    api_key = os.getenv("STARSPAY_API_KEY", "")
    try:
        response = httpx.post(
            f"{api_url}/api/v1/verify",
            json={"key": key},
            headers={"X-API-Key": api_key},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("valid"):
                return {
                    "valid": True,
                    "plan": data.get("plan_id", data.get("plan", "pro")),
                    "expires_at": data.get("expires_at"),
                    "email": data.get("email", ""),
                    "source": "starspay_api",
                }
            return {"valid": False, "reason": data.get("reason", "invalid")}
        elif response.status_code == 401:
            logger.warning("StarsPay API key is invalid")
            return {"valid": False, "reason": "api_key_invalid"}
        elif response.status_code == 404:
            logger.warning("License key not found in StarsPay")
            return {"valid": False, "reason": "not_found"}
        else:
            logger.warning("StarsPay API returned status %d", response.status_code)
            return {"valid": False, "reason": f"api_error_{response.status_code}"}
    except httpx.TimeoutException:
        logger.warning("StarsPay API request timed out")
        return {"valid": False, "reason": "timeout"}
    except httpx.ConnectError:
        logger.warning("Cannot connect to StarsPay API")
        return {"valid": False, "reason": "connection_error"}
    except Exception as exc:
        logger.warning("StarsPay API verification failed: %s", exc)
        return {"valid": False, "reason": "unknown_error"}


# ---------------------------------------------------------------------------
# Main license verification entry point
# ---------------------------------------------------------------------------

def verify_license(license_key: str) -> dict:
    """Verify a license key. Returns dict with 'valid' key.

    Strategy:
    1. Try the public licenses.json on GitHub first (always works, no server needed).
    2. If that doesn't validate and STARSPAY_API_URL is set, fall back to the REST API.
    3. If both fail, return the last failure reason.
    """
    if not license_key:
        return {"valid": False, "reason": "no_key"}

    # Try public JSON first (always works, no server needed)
    result = _verify_via_json(license_key)
    if result.get("valid"):
        return result

    # Fallback to API if configured
    api_url = os.getenv("STARSPAY_API_URL", "")
    if api_url:
        api_result = _verify_via_api(license_key, api_url)
        if api_result.get("valid"):
            return api_result
        # Keep API result as the final result (more specific reason)
        result = api_result

    return result


# ---------------------------------------------------------------------------
# is_pro — with 1-hour in-memory cache
# ---------------------------------------------------------------------------

def is_pro() -> bool:
    """Check if the current user has a valid Pro license.

    Reads the LICENSE_KEY env var, calls verify_license(), and caches
    the result for 1 hour to avoid repeated network calls.
    """
    global _pro_cache

    # Return cached result if still fresh
    now = time.time()
    if _pro_cache["result"] is not None and (now - _pro_cache["timestamp"]) < _PRO_CACHE_TTL:
        return _pro_cache["result"]

    # Check env var for license key
    license_key = os.getenv("LICENSE_KEY", "")
    if not license_key:
        _pro_cache = {"result": False, "timestamp": now}
        return False

    # Verify via the two-tier system (JSON first, then API)
    result = verify_license(license_key)
    valid = result.get("valid", False)
    _pro_cache = {"result": valid, "timestamp": now}

    # If valid, also cache locally in SQLite for offline fallback
    if valid:
        _save_license_locally(license_key, result)

    return valid


# ---------------------------------------------------------------------------
# Local SQLite cache for offline use
# ---------------------------------------------------------------------------

def _save_license_locally(key: str, result: dict) -> None:
    """Save a verified license to the local DB for offline fallback."""
    try:
        conn = _get_db()
        now = time.time()
        expires_at = result.get("expires_at", 0) or (now + 30 * 86400)
        plan = result.get("plan", "pro")
        conn.execute(
            "INSERT OR REPLACE INTO license (key, activated_at, expires_at, plan_id, email, active, last_verified_at) "
            "VALUES (?, ?, ?, ?, '', 1, ?)",
            (key, now, expires_at, plan, now),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("Failed to save license locally: %s", exc)


_LOCAL_CACHE_MAX_AGE = 7 * 86400  # 7 days — local cache is only valid this long after last online verification


def _local_check_pro(key: str) -> bool:
    """Check if a license key is valid locally (cached from previous verification).

    The local cache is only valid for 7 days after the last successful
    online verification, to prevent indefinite Pro status via DB editing.
    """
    if not key or len(key) < 10:
        return False

    now = time.time()
    cache_cutoff = now - _LOCAL_CACHE_MAX_AGE
    conn = _get_db()
    cursor = conn.execute(
        "SELECT * FROM license WHERE key = ? AND active = 1 AND expires_at > ? "
        "AND (last_verified_at IS NOT NULL AND last_verified_at > ?)",
        (key, now, cache_cutoff),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


# ---------------------------------------------------------------------------
# Backward-compatible API (used by CLI, Actions, etc.)
# ---------------------------------------------------------------------------

def activate_license(key: str, email: str = "") -> bool:
    """Activate a Pro license key. Validates against the two-tier system, then saves locally."""
    if not key or len(key) < 10:
        return False

    # Validate via the two-tier system
    result = verify_license(key)

    if not result.get("valid"):
        # Also try local validation for offline/cached keys
        if _local_check_pro(key):
            return True
        return False

    # Save locally
    _save_license_locally(key, result)
    return True


def check_license_valid() -> bool:
    """Check if current license is valid (local SQLite check with 7-day cache expiry)"""
    license_key = os.getenv("LICENSE_KEY", "")
    if not license_key:
        settings = get_settings()
        license_key = settings.pro_license_key
    if not license_key:
        return False

    now = time.time()
    cache_cutoff = now - _LOCAL_CACHE_MAX_AGE
    conn = _get_db()
    cursor = conn.execute(
        "SELECT * FROM license WHERE key = ? AND active = 1 AND expires_at > ? "
        "AND (last_verified_at IS NOT NULL AND last_verified_at > ?)",
        (license_key, now, cache_cutoff),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def check_license_with_api() -> dict:
    """Full license check. Returns detailed info about the license status."""
    license_key = os.getenv("LICENSE_KEY", "")
    if not license_key:
        settings = get_settings()
        license_key = settings.pro_license_key
    if not license_key:
        return {"valid": False, "reason": "no_key", "tier": "free"}

    # Try the two-tier verification
    result = verify_license(license_key)
    if result.get("valid"):
        return {
            "valid": True,
            "tier": result.get("plan", "pro"),
            "expires_at": result.get("expires_at"),
            "source": result.get("source", "unknown"),
        }

    # Fallback to local cache
    if check_license_valid():
        return {"valid": True, "tier": "pro", "source": "local_cache"}

    return {"valid": False, "reason": result.get("reason", "expired"), "tier": "free"}


def get_usage_stats() -> dict:
    """Get usage statistics"""
    settings = get_settings()
    return {
        "commits_this_month": get_monthly_usage("commit"),
        "changelogs_this_month": get_monthly_usage("changelog"),
        "commit_limit": settings.free_commits_per_month,
        "changelog_limit": settings.free_changelog_per_month,
        "is_pro": settings.is_pro or is_pro(),
        "license_status": check_license_with_api(),
    }
