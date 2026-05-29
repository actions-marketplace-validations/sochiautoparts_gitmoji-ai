"""
Usage tracking — Free tier limits and Pro license validation
Supports StarsPay API for real license validation
"""

import os
import sqlite3
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta

import httpx

from gitmoji_ai.config import get_settings

logger = logging.getLogger(__name__)

# StarsPay API configuration — read from environment with defaults
STARSPAY_API_URL = os.environ.get("STARSPAY_API_URL", "")
STARSPAY_API_KEY = os.environ.get("STARSPAY_API_KEY", "")
LICENSE_KEY = os.environ.get("LICENSE_KEY", "")
PRODUCT_ID = "gitmoji-ai"


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
            active INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    return conn


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
    if settings.is_pro or is_pro_via_starspay():
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


def verify_license_via_starspay(key: str) -> dict:
    """
    Verify a license key via the StarsPay REST API.
    POST {STARSPAY_API_URL}/api/v1/verify
    Header: X-API-Key: {STARSPAY_API_KEY}
    Body: {"key": "{LICENSE_KEY}"}
    Returns: {"valid": bool, "plan_id": str, "expires_at": float, ...}
    """
    api_url = os.environ.get("STARSPAY_API_URL", STARSPAY_API_URL)
    api_key = os.environ.get("STARSPAY_API_KEY", STARSPAY_API_KEY)

    if not api_url:
        logger.debug("STARSPAY_API_URL not configured, skipping API verification")
        return {"valid": False, "reason": "not_configured"}

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
                    "plan_id": data.get("plan_id", "pro"),
                    "expires_at": data.get("expires_at"),
                    "email": data.get("email", ""),
                    "source": "starspay_api",
                }
            return {
                "valid": False,
                "reason": data.get("reason", "invalid"),
            }
        elif response.status_code == 401:
            logger.warning("StarsPay API key is invalid")
            return {"valid": False, "reason": "api_key_invalid"}
        elif response.status_code == 404:
            logger.warning("License key not found in StarsPay")
            return {"valid": False, "reason": "not_found"}
        else:
            logger.warning(f"StarsPay API returned status {response.status_code}")
            return {"valid": False, "reason": f"api_error_{response.status_code}"}
    except httpx.TimeoutException:
        logger.warning("StarsPay API request timed out")
        return {"valid": False, "reason": "timeout"}
    except httpx.ConnectError:
        logger.warning("Cannot connect to StarsPay API")
        return {"valid": False, "reason": "connection_error"}
    except Exception as e:
        logger.warning(f"StarsPay API verification failed: {e}")
        return {"valid": False, "reason": "unknown_error"}


def is_pro_via_starspay() -> bool:
    """
    Check if the current user has a valid Pro license via StarsPay.
    Reads STARSPAY_API_URL, STARSPAY_API_KEY, and LICENSE_KEY from env.
    - If STARSPAY_API_URL is not set, returns False (no check, basic usage).
    - If configured, verifies the license key via API.
    - Falls back to local cache if API is unreachable.
    """
    api_url = os.environ.get("STARSPAY_API_URL", STARSPAY_API_URL)
    license_key = os.environ.get("LICENSE_KEY", LICENSE_KEY)

    # Not configured — allow basic usage
    if not api_url:
        return False

    if not license_key:
        return False

    # Try StarsPay API verification
    result = verify_license_via_starspay(license_key)
    if result.get("valid"):
        return True

    # Fallback: check local cache
    return _local_check_pro(license_key)


def _local_check_pro(key: str) -> bool:
    """Check if a license key is valid locally (cached from previous API check)"""
    if not key or len(key) < 10:
        return False

    conn = _get_db()
    cursor = conn.execute(
        "SELECT * FROM license WHERE key = ? AND active = 1 AND expires_at > ?",
        (key, time.time()),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def _local_validate(key: str) -> dict:
    """Local fallback validation"""
    if not key or len(key) < 10:
        return {"valid": False, "reason": "invalid_format"}

    if not key.startswith("SP-"):
        return {"valid": False, "reason": "invalid_prefix"}

    conn = _get_db()
    cursor = conn.execute(
        "SELECT * FROM license WHERE key = ? AND active = 1 AND expires_at > ?",
        (key, time.time()),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "valid": True,
            "plan_id": row["plan_id"] if "plan_id" in row.keys() else "pro",
            "expires_at": row["expires_at"],
        }
    return {"valid": False, "reason": "not_found"}


def validate_license_via_api(key: str, product_id: str = PRODUCT_ID) -> dict:
    """
    Validate a license key via StarsPay API.
    Uses POST /api/v1/verify endpoint.
    Returns: {"valid": bool, "plan_id": str, "expires_at": float, ...}
    """
    api_url = os.environ.get("STARSPAY_API_URL", STARSPAY_API_URL)
    api_key = os.environ.get("STARSPAY_API_KEY", STARSPAY_API_KEY)

    if not api_url:
        logger.debug("STARSPAY_API_URL not configured, using local validation")
        return _local_validate(key)

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
                    "plan_id": data.get("plan_id", "pro"),
                    "expires_at": data.get("expires_at"),
                    "source": "starspay_api",
                }
            return {
                "valid": False,
                "reason": data.get("reason", "invalid"),
            }
    except Exception as e:
        logger.warning(f"StarsPay API validation failed, falling back to local: {e}")

    # Fallback: local validation
    return _local_validate(key)


def activate_license(key: str, email: str = "") -> bool:
    """
    Activate a Pro license key.
    Validates against StarsPay API first, then saves locally.
    """
    if not key or len(key) < 10:
        return False

    # Validate via StarsPay API
    result = validate_license_via_api(key)

    if not result.get("valid"):
        # Also try local validation for offline/cached keys
        local = _local_validate(key)
        if not local.get("valid"):
            return False
        result = local

    # Save locally
    conn = _get_db()
    now = time.time()
    expires_at = result.get("expires_at", now + (30 * 86400))
    plan_id = result.get("plan_id", "pro")

    conn.execute(
        "INSERT OR REPLACE INTO license (key, activated_at, expires_at, plan_id, email, active) VALUES (?, ?, ?, ?, ?, 1)",
        (key, now, expires_at, plan_id, email),
    )
    conn.commit()
    conn.close()
    return True


def check_license_valid() -> bool:
    """Check if current license is valid (local check)"""
    settings = get_settings()
    if not settings.pro_license_key:
        # Also check LICENSE_KEY env var
        env_key = os.environ.get("LICENSE_KEY", LICENSE_KEY)
        if env_key:
            conn = _get_db()
            cursor = conn.execute(
                "SELECT * FROM license WHERE key = ? AND active = 1 AND expires_at > ?",
                (env_key, time.time()),
            )
            row = cursor.fetchone()
            conn.close()
            return row is not None
        return False

    conn = _get_db()
    cursor = conn.execute(
        "SELECT * FROM license WHERE key = ? AND active = 1 AND expires_at > ?",
        (settings.pro_license_key, time.time()),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def check_license_with_api() -> dict:
    """
    Full license check via StarsPay API + local.
    Returns detailed info about the license status.
    """
    settings = get_settings()
    key = settings.pro_license_key or os.environ.get("LICENSE_KEY", LICENSE_KEY)

    if not key:
        return {"valid": False, "reason": "no_key", "tier": "free"}

    # Try StarsPay API first
    result = validate_license_via_api(key)

    if result.get("valid"):
        return {
            "valid": True,
            "tier": result.get("plan_id", "pro"),
            "expires_at": result.get("expires_at"),
            "source": "starspay_api",
        }

    # Fallback to local
    if check_license_valid():
        return {
            "valid": True,
            "tier": "pro",
            "source": "local_cache",
        }

    return {"valid": False, "reason": result.get("reason", "expired"), "tier": "free"}


def get_usage_stats() -> dict:
    """Get usage statistics"""
    return {
        "commits_this_month": get_monthly_usage("commit"),
        "changelogs_this_month": get_monthly_usage("changelog"),
        "commit_limit": get_settings().free_commits_per_month,
        "changelog_limit": get_settings().free_changelog_per_month,
        "is_pro": get_settings().is_pro or is_pro_via_starspay(),
        "license_status": check_license_with_api(),
    }
