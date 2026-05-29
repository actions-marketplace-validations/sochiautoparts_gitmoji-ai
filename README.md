<div align="center">

# 🤖 GitMoji AI

### AI-powered commit messages & changelog generator

**Never write a bad commit message again.**

[![PyPI](https://img.shields.io/pypi/v/gitmoji-ai?color=green&label=PyPI)](https://pypi.org/project/gitmoji-ai/)
[![Python](https://img.shields.io/pypi/pyversions/gitmoji-ai?label=Python)](https://pypi.org/project/gitmoji-ai/)
[![Tests](https://img.shields.io/github/actions/workflow/status/sochiautoparts/gitmoji-ai/ci.yml?label=Tests)](https://github.com/sochiautoparts/gitmoji-ai/actions)
[![License](https://img.shields.io/github/license/sochiautoparts/gitmoji-ai?label=License)](LICENSE)
[![Stars](https://img.shields.io/github/stars/sochiautoparts/gitmoji-ai?style=social)](https://github.com/sochiautoparts/gitmoji-ai)

[Installation](#-installation) • [Quick Start](#-quick-start) • [Features](#-features) • [GitHub Action](#-github-action) • [Pro](#-pro-version--starspay) • [Contributing](#-contributing)

</div>

---

## 🎬 Demo

```bash
$ gmai commit

📊 Diff Analysis

  Files changed: 3
  Lines added: +47
  Lines removed: -12
  Summary: Changed 3 file(s): new feature, bug fix

🤖 Generating AI commit suggestions...

💡 Commit Suggestions
┏━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ # ┃ Message                                 ┃ Confidence ┃
┡───╇──────────────────────────────────────────╇────────────┥
│ 1 │ feat(auth): add JWT token validation     │ 95%        │
│ 2 │ ✨ add JWT token validation to auth      │ 90%        │
│ 3 │ feat(auth): implement JWT validation     │ 85%        │
│   │ with refresh token support and expiry    │            │
│   │ checking for enhanced security           │            │
└───┴──────────────────────────────────────────┴────────────┘

Select commit [1/2/3/e(q)dit/(q)uit]: 1

✅ Committed! feat(auth): add JWT token validation
```

---

## ✨ Features

| Feature | Free | Pro |
|---------|:----:|:---:|
| AI commit messages | 50/month | ∞ |
| AI changelog generation | 3/month | ∞ |
| Conventional Commits | ✅ | ✅ |
| Emoji commits | ✅ | ✅ |
| Multi-language (6+ languages) | ✅ | ✅ |
| Git hook integration | ✅ | ✅ |
| GitHub Action | ✅ | ✅ |
| No watermark | ❌ | ✅ |
| Custom commit styles | ❌ | 🔜 Coming Soon |
| Team features | ❌ | 🔜 Coming Soon |
| Priority support | ❌ | ✅ |

---

## 📦 Installation

```bash
# With pip
pip install gitmoji-ai

# With pipx (recommended for CLI tools)
pipx install gitmoji-ai

# With uv
uv tool install gitmoji-ai
```

---

## 🚀 Quick Start

### 1. Set your OpenAI API key

```bash
export GMAI_OPENAI_API_KEY="sk-your-key-here"
```

Get one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys) — costs ~$0.15 per 1M tokens.

### 2. Initialize in your repo

```bash
cd your-project
gmai init
```

This creates `.env` and installs a git hook that suggests commit messages automatically.

### 3. Make a commit

```bash
# Stage your changes
git add .

# Generate AI commit message and commit
gmai commit

# Or with auto-staging
gmai commit --stage

# Or just use git normally — the hook will suggest!
git commit
```

### 4. Generate changelog

```bash
# Auto-generate from recent commits
gmai changelog --version v1.2.0

# Output to file
gmai changelog --version v1.2.0 --output CHANGELOG.md

# Russian language
gmai changelog --version v1.2.0 --lang ru
```

---

## 🎮 Commands

| Command | Description |
|---------|-------------|
| `gmai commit` | 🤖 Generate AI commit message and commit |
| `gmai changelog` | 📝 Generate AI changelog |
| `gmai init` | 🔧 Initialize GitMoji AI in repo |
| `gmai info` | 📊 Show repo info & usage stats |
| `gmai pro activate KEY` | ⭐ Activate Pro license |
| `gmai pro status` | 🔍 Check Pro license status |
| `gmai pro purchase` | 💳 Get Pro license |

### Commit options

```bash
gmai commit --style emoji       # Emoji-style commits: ✨ add login
gmai commit --style plain       # Plain: add login functionality
gmai commit --style conventional # Conventional: feat(auth): add login (default)
gmai commit --lang ru           # Russian: feat(auth): добавить логин
gmai commit --stage             # Auto-stage all changes
gmai commit --sign              # GPG-sign the commit
gmai commit --yes               # Skip confirmation, use first suggestion
gmai commit --path ./my-repo    # Specify repo path
```

### Changelog options

```bash
gmai changelog --version v2.0.0          # Version tag
gmai changelog --format angular          # Angular format
gmai changelog --lang ru                 # Russian changelog
gmai changelog --since v1.0.0            # Only changes since tag
gmai changelog --no-ai                   # Manual grouping (no AI)
gmai changelog --output CHANGELOG.md     # Write to file
```

---

## 🤖 GitHub Action

Use GitMoji AI in your CI/CD pipeline:

```yaml
name: Auto Changelog

on:
  push:
    branches: [main]

jobs:
  changelog:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: sochiautoparts/gitmoji-ai/action@v1
        with:
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          generate-changelog: true
          version: v1.2.0
          language: en
```

Or use it as a PR checker:

```yaml
name: AI Commit Review

on:
  pull_request:

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: sochiautoparts/gitmoji-ai/action@v1
        with:
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          language: en
```

---

## 🌍 Multi-language Support

| Language | Flag | Example |
|----------|------|---------|
| English | 🇬🇧 | `feat(auth): add login validation` |
| Russian | 🇷🇺 | `feat(auth): добавить валидацию логина` |
| Spanish | 🇪🇸 | `feat(auth): añadir validación de login` |
| German | 🇩🇪 | `feat(auth): login-validierung hinzufügen` |
| French | 🇫🇷 | `feat(auth): ajouter la validation du login` |
| Japanese | 🇯🇵 | `feat(auth): ログイン検証を追加` |
| Chinese | 🇨🇳 | `feat(auth): 添加登录验证` |

---

## ⭐ Pro Version & StarsPay

### Why upgrade?

- **∞ Unlimited** AI commits and changelogs
- **No watermark** — clean commit history
- **Custom styles** — create your own commit format
- **Team features** — shared settings and changelogs
- **Priority support** — faster responses

### 💳 StarsPay — Pay with Telegram Stars

Purchase directly in Telegram — pay with Stars, get your license key in seconds!

- **Bot:** 👉 [@allstarspay_bot](https://t.me/allstarspay_bot)

| Plan | Price | Best for |
|------|-------|----------|
| **Free** | $0 | Personal projects |
| **1 месяц** | ⭐ 149/month | Try Pro features |
| **1 год** | ⭐ 999/year | Best value — save 44% |
| **Навсегда** | ⭐ 2,999 | Pay once, use forever |

**3 steps to Pro:**

```bash
# 1. Open @allstarspay_bot in Telegram and pay with Stars
#    👉 https://t.me/allstarspay_bot

# 2. Copy your license key (format: SP-GMA-xxxxxx)

# 3. Activate:
gmai pro activate SP-GMA-xxxxxxxx
```

**Or activate with an existing key:**

```bash
gmai pro activate YOUR-LICENSE-KEY
gmai pro status    # Check your license
```

### 🔐 License Verification (No API Server Needed!)

GitMoji AI verifies Pro licenses **without requiring an API server**. The verification works in two tiers:

#### 1️⃣ Primary: Public `licenses.json` on GitHub

The tool fetches a public JSON file from GitHub to verify licenses — **no authentication, no rate limits, no API server needed**:

- **URL:** `https://raw.githubusercontent.com/sochiautoparts/stars-pay-bot/main/data/licenses.json`
- The JSON file contains license entries with a `key_hash` field (SHA-256 truncated to 16 hex characters)
- Verification: compute `hashlib.sha256(key.encode()).hexdigest()[:16]` and match against `key_hash`
- Also checks `active` field and `expires_at` (0 = lifetime)

#### 2️⃣ Fallback: REST API (if `STARSPAY_API_URL` is set)

If the JSON method doesn't validate and `STARSPAY_API_URL` is configured, the tool falls back to a REST API call:

- **POST** to `{STARSPAY_API_URL}/api/v1/verify`
- **Header:** `X-API-Key: {STARSPAY_API_KEY}`
- **Body:** `{"key": "<license_key>"}`

The `is_pro()` function caches verification results for 1 hour in memory and also saves to local SQLite for offline use.

### Environment Variables for CI/CD

For automated environments (GitHub Actions, Docker, etc.):

```bash
LICENSE_KEY=SP-GMA-xxxxxxxx                                   # Your license key (required for Pro)
STARSPAY_API_URL=                                              # Optional: StarsPay API URL (empty = JSON-only verification)
STARSPAY_API_KEY=                                              # Optional: StarsPay API key (only if using API fallback)
```

- **LICENSE_KEY** — Your Pro license key. If set, the tool verifies it via the public JSON file (primary) or REST API (fallback).
- **STARSPAY_API_URL** — Optional. If set, the REST API is used as a fallback when JSON verification doesn't find the key.
- **STARSPAY_API_KEY** — Optional. API key for the REST API (only needed if `STARSPAY_API_URL` is set).
- If only `LICENSE_KEY` is set, verification uses the public GitHub JSON — **no API server required!**

---

## 🔧 Configuration

Create `.env` in your project root (or set environment variables):

```bash
# Required
GMAI_OPENAI_API_KEY=sk-your-key-here

# Optional
GMAI_DEFAULT_LANGUAGE=en          # Default commit language
GMAI_COMMIT_STYLE=conventional    # Default commit style
GMAI_OPENAI_MODEL=gpt-4o-mini    # AI model
GMAI_PRO_LICENSE_KEY=             # Pro license key

# StarsPay license verification
LICENSE_KEY=                      # License key for Pro features (primary: verified via public GitHub JSON)
STARSPAY_API_URL=                 # Optional: StarsPay API URL (empty = JSON-only verification)
STARSPAY_API_KEY=                 # Optional: StarsPay API key
```

### Git Hook

After `gmai init`, every `git commit` will show AI suggestions in your editor:

```
# 🤖 GitMoji AI Suggestion:
# feat(auth): add JWT token validation
```

Just uncomment the line you like, save, and close the editor!

---

## 🏗️ Architecture

```
gitmoji-ai/
├── src/gitmoji_ai/
│   ├── cli.py          # Typer CLI interface
│   ├── ai_engine.py    # AI commit generation (OpenAI)
│   ├── git_ops.py      # Git operations (diff, commit)
│   ├── changelog.py    # Changelog generator
│   ├── config.py       # Configuration management
│   ├── usage.py        # Usage tracking & license validation (JSON + API)
│   └── suggest.py      # Quick suggest (for hooks)
├── action/
│   └── action.yml      # GitHub Action
├── .github/workflows/
│   ├── ci.yml          # CI pipeline
│   └── changelog.yml   # Auto changelog
├── tests/
│   └── test_core.py    # Test suite
└── pyproject.toml      # Project config
```

---

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md).

1. Fork the repository
2. Create your feature branch: `git checkout -b feat/amazing-feature`
3. Commit with GitMoji AI: `gmai commit` 😉
4. Push: `git push origin feat/amazing-feature`
5. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Made with 🤖 and ❤️ by [GitMoji AI](https://github.com/sochiautoparts/gitmoji-ai)**

[⭐ Star on GitHub](https://github.com/sochiautoparts/gitmoji-ai) • [🐛 Report Bug](https://github.com/sochiautoparts/gitmoji-ai/issues) • [💡 Request Feature](https://github.com/sochiautoparts/gitmoji-ai/issues) • [💎 Get Pro via StarsPay](https://t.me/allstarspay_bot)

</div>
