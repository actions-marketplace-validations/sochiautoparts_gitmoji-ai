"""
License validation through GitHub Sponsors API

How it works:
1. User sponsors the project on GitHub ($5/month = Pro)
2. gmai pro login — authenticates with GitHub
3. We check if user is an active sponsor via GitHub API
4. If yes → Pro unlocked automatically

No license keys needed — your GitHub sponsorship IS your license!
"""

import os
import time
import logging
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import httpx

from gitmoji_ai.config import get_settings

logger = logging.getLogger(__name__)

# === Configuration ===
SPONSOR_TIER_PRO = 5       # $5/month = Pro
SPONSOR_TIER_TEAM = 20     # $20/month = Team
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")  # Set via env var; empty = PAT-only flow

SPONSOR_TARGET = "sochiautoparts"  # GitHub account to sponsor


class SponsorNetworkError(Exception):
    """GitHub could not be reached (timeout / connection error).

    Raised by the sponsor checks so callers can distinguish a network
    failure (token status UNKNOWN — the token must be kept) from a
    definitively invalid token (safe to delete).
    """

# === Data ===
@dataclass
class SponsorInfo:
    """Information about a sponsor"""
    github_login: str
    github_id: int
    tier_amount: int       # USD cents per month
    tier_name: str         # "Free", "Pro" or "Team"
    is_active: bool
    expires_at: float      # timestamp


# === Local token storage ===
def _get_auth_file() -> Path:
    settings = get_settings()
    settings.ensure_config_dir()
    return settings.config_dir / "auth.json"


def save_github_token(token: str) -> None:
    """Save GitHub OAuth token locally with restricted permissions (600)"""
    import json
    auth_file = _get_auth_file()
    auth_file.write_text(json.dumps({
        "github_token": token,
        "saved_at": time.time(),
    }), encoding="utf-8")
    # Restrict file permissions to owner-only (read/write)
    try:
        os.chmod(auth_file, 0o600)
    except OSError:
        logger.warning("Could not set permissions on auth file")
    logger.info("GitHub token saved with restricted permissions")


def load_github_token() -> Optional[str]:
    """Load saved GitHub token"""
    import json
    auth_file = _get_auth_file()
    if not auth_file.exists():
        return None
    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
        return data.get("github_token")
    except Exception:
        return None


def clear_github_token() -> None:
    """Remove saved GitHub token"""
    auth_file = _get_auth_file()
    if auth_file.exists():
        auth_file.unlink()


# === GitHub Sponsors API ===
def check_sponsor_status(github_token: str) -> Optional[SponsorInfo]:
    """
    Check if the GitHub user is an active sponsor.
    
    Uses GitHub GraphQL API to check sponsorships.
    Returns SponsorInfo if active sponsor, None otherwise.
    Raises SponsorNetworkError when GitHub cannot be reached.
    """
    query = """
    query($login: String!) {
      user(login: $login) {
        sponsorshipsAsSponsor(first: 10, activeOnly: true) {
          nodes {
            sponsorable {
              login
            }
            tier {
              monthlyPriceInCents
              name
            }
            isActive
          }
        }
      }
    }
    """

    # First get the user's login
    user_login = _get_github_login(github_token)
    if not user_login:
        return None

    try:
        response = httpx.post(
            "https://api.github.com/graphql",
            headers={
                "Authorization": f"bearer {github_token}",
                "Content-Type": "application/json",
            },
            json={"query": query, "variables": {"login": user_login}},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        sponsorships = (
            data.get("data", {})
            .get("user", {})
            .get("sponsorshipsAsSponsor", {})
            .get("nodes", [])
        )

        for sponsorship in sponsorships:
            sponsorable = sponsorship.get("sponsorable", {}).get("login", "")
            if sponsorable.lower() == SPONSOR_TARGET.lower():
                tier = sponsorship.get("tier", {})
                amount = tier.get("monthlyPriceInCents", 0) // 100  # cents to dollars
                if amount >= SPONSOR_TIER_TEAM:
                    tier_name = "Team"
                elif amount >= SPONSOR_TIER_PRO:
                    tier_name = "Pro"
                else:
                    tier_name = "Free"  # below the Pro threshold

                return SponsorInfo(
                    github_login=user_login,
                    github_id=0,
                    tier_amount=amount,
                    tier_name=tier_name,
                    is_active=sponsorship.get("isActive", False),
                    expires_at=time.time() + (35 * 86400),  # 35 days (buffer)
                )

        return None  # Not a sponsor

    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        raise SponsorNetworkError(f"cannot reach GitHub API: {exc}") from exc
    except Exception as e:
        logger.error(f"Failed to check sponsor status: {e}")
        return None


def _get_github_login(token: str) -> Optional[str]:
    """Get GitHub username from token.

    Returns None for invalid/rejected tokens (HTTP 401/403 and other HTTP
    errors). Raises SponsorNetworkError when GitHub cannot be reached
    (timeout / connection error).
    """
    try:
        response = httpx.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/json",
            },
            timeout=10,
        )
        if response.status_code in (401, 403):
            return None  # token rejected — definitive answer
        response.raise_for_status()
        return response.json().get("login")
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        raise SponsorNetworkError(f"cannot reach github.com: {exc}") from exc
    except Exception:
        return None


# === Alternative: Device Flow Auth (no OAuth app needed) ===
def device_flow_login() -> Optional[str]:
    """
    GitHub Device Flow authentication.
    
    If GITHUB_CLIENT_ID is set, uses the real OAuth device flow:
    1. POST to GitHub to get device + user codes
    2. Show user the code and URL
    3. Poll for access token
    4. Validate sponsor status
    
    If GITHUB_CLIENT_ID is NOT set, falls back to PAT-based approach.
    """
    client_id = GITHUB_CLIENT_ID
    
    if not client_id:
        # No OAuth app configured — fall back to PAT approach
        print("\n🔗 To link your GitHub sponsorship as your Pro license:")
        print("")
        print("  1. Go to: https://github.com/sponsors/sochiautoparts")
        print("  2. Choose a tier ($5/month = Pro, $20/month = Team)")
        print("  3. Complete sponsorship")
        print("  4. Create a PAT with 'read:user' scope:")
        print("     https://github.com/settings/tokens/new?scopes=read:user")
        print("  5. Run: gmai pro login <your-pat>")
        print("")
        print("  Your sponsorship = your Pro license! 🎉")
        print("  Cancel sponsorship = Pro expires at end of billing period.")
        print("")
        print("  [dim]To enable interactive device flow, set GITHUB_CLIENT_ID env var.[/dim]")
        return None
    
    # --- Real Device Flow ---
    try:
        # Step 1: Request device and user codes
        resp = httpx.post(
            "https://github.com/login/device/code",
            data={"client_id": client_id, "scope": "read:user"},
            headers={"Accept": "application/json"},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"❌ Failed to start device flow: {resp.status_code}")
            print("  Falling back to PAT approach. Run: gmai pro login <your-pat>")
            return None
        
        data = resp.json()
        device_code = data.get("device_code", "")
        user_code = data.get("user_code", "")
        verification_uri = data.get("verification_uri", "https://github.com/login/device")
        interval = data.get("interval", 5)
        expires_in = data.get("expires_in", 900)
        
        # Step 2: Show user the code
        print("\n🔗 GitHub Device Flow Authentication")
        print("=" * 40)
        print(f"")
        print(f"  1. Open this URL in your browser:")
        print(f"     [bold cyan]{verification_uri}[/bold cyan]")
        print(f"")
        print(f"  2. Enter this code:")
        print(f"     [bold yellow]{user_code}[/bold yellow]")
        print(f"")
        print(f"  Waiting for authorization... (expires in {expires_in // 60} minutes)")
        
        # Step 3: Poll for access token
        import time as _time
        start = _time.time()
        while (_time.time() - start) < expires_in:
            _time.sleep(interval)
            
            poll_resp = httpx.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
                timeout=15,
            )
            
            poll_data = poll_resp.json()
            
            if "access_token" in poll_data:
                token = poll_data["access_token"]
                print("\n✅ Authorization successful!")
                
                # Step 4: Validate sponsor status
                print("🔍 Checking sponsor status...")
                is_pro, info, network_error = validate_sponsor_token(token)
                if is_pro and info:
                    print(f"\n⭐ Pro activated via GitHub Sponsors!")
                    print(f"  Account: @{info.github_login}")
                    print(f"  Tier: {info.tier_name} (${info.tier_amount}/month)")
                    return token
                elif network_error:
                    print("\n⚠️ Network error — could not verify sponsor status.")
                    print("  Check your connection and run again later: gmai pro login <your-pat>")
                    return None
                else:
                    print("\n⚠️ Authorization successful, but you're not a sponsor yet.")
                    print("  Sponsor the project at: https://github.com/sponsors/sochiautoparts")
                    print("  Then run: gmai pro login <your-pat>")
                    return None
            
            error = poll_data.get("error", "")
            if error == "authorization_pending":
                # User hasn't entered the code yet — keep waiting
                continue
            elif error == "slow_down":
                interval += 5
                continue
            elif error == "expired_token":
                print("\n❌ Device code expired. Please try again.")
                return None
            elif error == "access_denied":
                print("\n❌ Authorization denied by user.")
                return None
            else:
                print(f"\n❌ Unexpected error: {error}")
                return None
        
        print("\n❌ Device flow timed out. Please try again.")
        return None
        
    except httpx.TimeoutException:
        print("\n❌ Network timeout during device flow. Check your internet connection.")
        return None
    except Exception as exc:
        print(f"\n❌ Device flow error: {exc}")
        print("  Falling back to PAT approach. Run: gmai pro login <your-pat>")
        return None


def validate_sponsor_token(token: str) -> tuple[bool, Optional[SponsorInfo], bool]:
    """
    Validate a GitHub token and check sponsor status.
    Returns (is_pro, sponsor_info, network_error).

    network_error=True means GitHub was unreachable — the token status is
    UNKNOWN and a saved token must NOT be deleted.
    Only Pro/Team tier sponsors get is_pro=True.
    """
    # Check if token is valid
    try:
        login = _get_github_login(token)
    except SponsorNetworkError:
        return False, None, True
    if not login:
        return False, None, False

    # Check sponsor status
    try:
        info = check_sponsor_status(token)
    except SponsorNetworkError:
        return False, None, True

    if info and info.is_active and info.tier_name in ("Pro", "Team"):
        # Save token for future checks
        save_github_token(token)
        return True, info, False

    return False, None, False


def is_pro_via_sponsor() -> tuple[bool, Optional[str]]:
    """
    Check if current user has Pro via GitHub Sponsors.
    Returns (is_pro, tier_name)
    """
    # Check license key first (via is_pro)
    from gitmoji_ai.usage import is_pro as check_is_pro
    if check_is_pro():
        return True, "Pro (License Key)"

    # Check saved GitHub token
    github_token = load_github_token()
    if not github_token:
        return False, None

    # Validate
    is_pro, info, network_error = validate_sponsor_token(github_token)
    if is_pro and info:
        return True, f"{info.tier_name} (GitHub Sponsor)"

    if network_error:
        # GitHub unreachable — token status unknown: keep the token and retry later
        logger.warning("GitHub unreachable while verifying sponsor token — keeping saved token")
        return False, None

    # Token invalid or not a (Pro/Team) sponsor anymore
    clear_github_token()
    return False, None
