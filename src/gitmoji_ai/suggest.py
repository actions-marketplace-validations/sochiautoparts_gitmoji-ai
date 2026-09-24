"""
Quick suggest command — for git hooks integration
Outputs a single commit message without interactive prompts
"""

import asyncio
import os
import sys
from gitmoji_ai.git_ops import get_staged_diff, get_unstaged_diff, get_diff_against_branch
from gitmoji_ai.ai_engine import generate_commit_messages
from gitmoji_ai.config import get_settings
from gitmoji_ai.usage import check_limit, is_pro, track_usage


def suggest_commit(path: str = ".", language: str = "en", style: str = "conventional") -> str:
    """Generate a single commit suggestion (non-interactive, for hooks)"""
    
    # Check rate limits — free users have limited commits per month
    allowed, remaining = check_limit("commit")
    if not allowed:
        print("⚠️ Monthly commit limit reached. Upgrade to Pro for unlimited.", file=sys.stderr)
        return ""

    diff = get_staged_diff(path)
    if not diff:
        diff = get_unstaged_diff(path)
    if not diff:
        # CI (GitHub Actions): there are no staged/unstaged changes — analyze
        # the diff against the base branch of the pull request instead.
        base_branch = (os.environ.get("GMAI_BASE_BRANCH") or "").strip()
        if base_branch:
            diff = get_diff_against_branch(base_branch, path)
    if not diff:
        return ""

    suggestions = asyncio.run(generate_commit_messages(diff, language, style))
    if suggestions:
        message = suggestions[0].message
        # Add watermark for free tier
        if not is_pro():
            message += " (gitmoji-ai free)"
        # Count the suggestion towards the free-tier monthly limit
        track_usage("commit")
        return message
    return ""
